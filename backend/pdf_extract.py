"""Careful PDF financial-statement extraction (fallback when iXBRL unavailable).

Pipeline:
1. Digital text with positions via pdfplumber (preferred) or PyMuPDF.
2. Detect statement sections (P&L / SOCI, SOFP / Balance Sheet, Cash Flow).
3. Detect unit scale (£ / £000 / £m) per section.
4. Detect year column headers; associate numbers with current vs prior year.
5. Row clustering by Y with label on the left, numeric columns on the right.
6. OCR only if digital text is insufficient (< MIN_DIGITAL_CHARS on a target page).
7. Never invent numbers; every value carries provenance.

Limitations (honest):
- Scanned image-only PDFs depend on OCR quality.
- Multi-column layouts with notes columns can still confuse year assignment.
- Not all UK filings use standard labels; synonym map covers common variants.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

MIN_DIGITAL_CHARS = 80

SECTION_PATTERNS = {
    "income_statement": [
        r"statement of comprehensive income",
        r"profit and loss account",
        r"profit\s*(?:&|and)\s*loss",
        r"income statement",
        r"consolidated statement of (?:profit|comprehensive income)",
    ],
    "balance_sheet": [
        r"statement of financial position",
        r"balance sheet",
        r"consolidated (?:statement of )?financial position",
    ],
    "cash_flow": [
        r"statement of cash flows?",
        r"cash flow statement",
        r"consolidated (?:statement of )?cash flows?",
    ],
}

YEAR_RE = re.compile(r"\b(20[1-3]\d)\b")
NUMBER_TOKEN_RE = re.compile(
    r"^\(?-?£?-?[\d,]+(?:\.\d+)?\)?%?$|^[\d,]+(?:\.\d+)?$"
)


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    page: int


@dataclass
class ExtractedRow:
    label: str
    values_by_year: dict[str, float]  # year -> value (scale applied)
    page: int
    raw_numbers: list[str] = field(default_factory=list)
    scale: int = 1
    section: str = ""


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("–", "-").replace("—", "-").split())


def detect_scale(text: str) -> int:
    t = text.lower()
    if re.search(r"£\s*m\b|£m\b|in millions|£'?m\b", t):
        return 1_000_000
    if re.search(r"£'?0{3}\b|£000\b|£'000\b|in thousands|£\s*000", t):
        return 1_000
    return 1


def detect_section(text: str) -> Optional[str]:
    t = _norm(text)
    for section, patterns in SECTION_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, t):
                return section
    return None


def parse_number_token(token: str) -> Optional[float]:
    t = token.strip().replace("\xa0", "").replace(",", "").replace("£", "")
    if not t or t in ("—", "–", "-", "−", "n/a", "na"):
        return None
    # Skip pure years used as headers
    if re.fullmatch(r"20[1-3]\d", t):
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1]
    t = t.replace("%", "").replace("−", "-")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", t):
        return None
    try:
        val = float(t)
    except ValueError:
        return None
    # Filter note references / tiny integers that are almost certainly note numbers
    # (caller may still accept after scale)
    return -abs(val) if neg else val


def _words_from_pdfplumber(content: bytes) -> tuple[list[Word], list[str]]:
    import io

    import pdfplumber

    words: list[Word] = []
    page_texts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_texts.append(page.extract_text() or "")
            for w in page.extract_words(use_text_flow=True, keep_blank_chars=False) or []:
                words.append(
                    Word(
                        text=w["text"],
                        x0=float(w["x0"]),
                        x1=float(w["x1"]),
                        top=float(w["top"]),
                        bottom=float(w["bottom"]),
                        page=i,
                    )
                )
    return words, page_texts


def _words_from_pymupdf(content: bytes) -> tuple[list[Word], list[str]]:
    import fitz

    words: list[Word] = []
    page_texts: list[str] = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            page_texts.append(page.get_text("text") or "")
            for w in page.get_text("words"):
                # w: x0, y0, x1, y1, word, block, line, word_no
                words.append(
                    Word(
                        text=w[4],
                        x0=float(w[0]),
                        x1=float(w[2]),
                        top=float(w[1]),
                        bottom=float(w[3]),
                        page=i,
                    )
                )
    return words, page_texts


def _ocr_page_words(content: bytes, page_index: int) -> list[Word]:
    """OCR a single page when digital text is insufficient. Optional dependency path."""
    try:
        import fitz
        import pytesseract
        from pytesseract import Output
        from PIL import Image
    except ImportError:
        return []

    words: list[Word] = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        if page_index >= len(doc):
            return []
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            data = pytesseract.image_to_data(img, output_type=Output.DICT)
        except Exception:
            return []
        n = len(data["text"])
        # Map image coords back roughly to page coords
        scale_x = page.rect.width / img.size[0]
        scale_y = page.rect.height / img.size[1]
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            x0 = data["left"][i] * scale_x
            y0 = data["top"][i] * scale_y
            x1 = x0 + data["width"][i] * scale_x
            y1 = y0 + data["height"][i] * scale_y
            words.append(Word(text=txt, x0=x0, x1=x1, top=y0, bottom=y1, page=page_index))
    return words


def cluster_rows(page_words: list[Word], y_tol: float = 4.0) -> list[list[Word]]:
    if not page_words:
        return []
    ordered = sorted(page_words, key=lambda w: (w.top, w.x0))
    rows: list[list[Word]] = []
    current = [ordered[0]]
    for w in ordered[1:]:
        if abs(w.top - current[-1].top) <= y_tol:
            current.append(w)
        else:
            rows.append(sorted(current, key=lambda x: x.x0))
            current = [w]
    rows.append(sorted(current, key=lambda x: x.x0))
    return rows


def detect_year_columns(rows: list[list[Word]], page_width: float) -> list[tuple[str, float]]:
    """
    Return list of (year, center_x) for numeric year headers found on the right half.
    Order is left-to-right (often prior year left, current right — or reverse).
    UK accounts often show current year on the left of the number columns.
    We return columns in left-to-right order; caller maps by year string.
    """
    year_cols: list[tuple[str, float]] = []
    seen = set()
    for row in rows[:25]:  # headers near top of section
        row_text = " ".join(w.text for w in row)
        years = YEAR_RE.findall(row_text)
        if not years:
            continue
        for w in row:
            m = YEAR_RE.fullmatch(w.text.strip())
            if not m:
                continue
            # Prefer year tokens in the right 55% of the page (number columns)
            mid = (w.x0 + w.x1) / 2
            if page_width and mid < page_width * 0.40:
                continue
            y = m.group(1)
            if y in seen:
                continue
            seen.add(y)
            year_cols.append((y, mid))
    year_cols.sort(key=lambda t: t[1])
    return year_cols


def _label_and_numbers(
    row: list[Word],
    year_cols: list[tuple[str, float]],
    page_width: float,
) -> tuple[str, dict[str, float], list[str]]:
    """Split a row into left-side label and year-aligned numbers."""
    if not row:
        return "", {}, []

    # Numbers are typically in the right portion
    split_x = page_width * 0.45 if page_width else (year_cols[0][1] - 20 if year_cols else 9999)

    label_parts: list[str] = []
    number_words: list[Word] = []
    for w in row:
        mid = (w.x0 + w.x1) / 2
        tok = w.text.strip()
        is_num = bool(NUMBER_TOKEN_RE.match(tok.replace(" ", ""))) and parse_number_token(tok) is not None
        # Year headers themselves are not values
        if YEAR_RE.fullmatch(tok):
            continue
        if is_num and mid >= split_x:
            number_words.append(w)
        elif mid < split_x:
            label_parts.append(tok)
        elif not is_num:
            label_parts.append(tok)

    label = " ".join(label_parts).strip(" :.-")
    raw_nums = [w.text for w in number_words]
    values: dict[str, float] = {}

    if year_cols and number_words:
        # Assign each number to nearest year column by x-center
        for w in number_words:
            val = parse_number_token(w.text)
            if val is None:
                continue
            # Skip note-like tiny ints when scale is 1? Keep; filter later by label match.
            mid = (w.x0 + w.x1) / 2
            nearest = min(year_cols, key=lambda yc: abs(yc[1] - mid))
            # Only bind if reasonably close (within ~15% page width)
            if page_width and abs(nearest[1] - mid) > page_width * 0.15:
                continue
            year = nearest[0]
            if year not in values:
                values[year] = val
    elif number_words:
        # No year headers: take leftmost number as "current" placeholder year ""
        val = parse_number_token(number_words[0].text)
        if val is not None:
            values[""] = val

    return label, values, raw_nums


def extract_rows_from_words(
    words: list[Word],
    page_texts: list[str],
    *,
    max_pages: int = 80,
) -> tuple[list[ExtractedRow], dict[str, Any]]:
    stats: dict[str, Any] = {"pages_scanned": 0, "sections": [], "ocr_pages": []}
    # Group words by page
    by_page: dict[int, list[Word]] = {}
    for w in words:
        by_page.setdefault(w.page, []).append(w)

    results: list[ExtractedRow] = []
    active_section: Optional[str] = None
    active_scale = 1
    active_years: list[tuple[str, float]] = []

    for page_idx in sorted(by_page.keys()):
        if page_idx >= max_pages:
            break
        stats["pages_scanned"] += 1
        page_words = by_page[page_idx]
        text = page_texts[page_idx] if page_idx < len(page_texts) else " ".join(w.text for w in page_words)
        page_width = max((w.x1 for w in page_words), default=600.0)

        section_hit = detect_section(text)
        if section_hit:
            active_section = section_hit
            active_scale = detect_scale(text)
            if active_section not in stats["sections"]:
                stats["sections"].append(active_section)

        if not active_section:
            continue

        # Re-detect scale if page mentions units
        page_scale = detect_scale(text)
        if page_scale != 1:
            active_scale = page_scale

        rows = cluster_rows(page_words)
        year_cols = detect_year_columns(rows, page_width)
        if year_cols:
            active_years = year_cols

        for row in rows:
            label, values, raw_nums = _label_and_numbers(row, active_years or year_cols, page_width)
            if not label or not values:
                continue
            # Skip header-ish labels
            if _norm(label) in ("note", "notes", "£", "£000", "£'000", "£m"):
                continue
            if YEAR_RE.fullmatch(label.strip()):
                continue

            scaled = {y: v * active_scale for y, v in values.items()}
            results.append(
                ExtractedRow(
                    label=label,
                    values_by_year=scaled,
                    page=page_idx + 1,
                    raw_numbers=raw_nums,
                    scale=active_scale,
                    section=active_section,
                )
            )

    return results, stats


def extract_from_pdf_bytes(content: bytes, *, allow_ocr: bool = True) -> tuple[list[ExtractedRow], dict[str, Any]]:
    stats: dict[str, Any] = {"engine": None, "ocr_used": False}
    words: list[Word] = []
    page_texts: list[str] = []

    try:
        words, page_texts = _words_from_pdfplumber(content)
        stats["engine"] = "pdfplumber"
    except Exception as e:
        logger.warning("pdfplumber failed: %s; trying pymupdf", e)
        try:
            words, page_texts = _words_from_pymupdf(content)
            stats["engine"] = "pymupdf"
        except Exception as e2:
            stats["error"] = f"digital_extract_failed: {e2}"
            return [], stats

    # OCR sparse pages that look like financial sections by title but lack text
    if allow_ocr:
        try:
            import fitz

            with fitz.open(stream=content, filetype="pdf") as doc:
                n_pages = len(doc)
        except Exception:
            n_pages = len(page_texts)

        for i, text in enumerate(page_texts):
            if len(text.strip()) >= MIN_DIGITAL_CHARS:
                continue
            # Only OCR if neighbouring pages suggest accounts, or always try first 40
            if i > 40:
                continue
            ocr_words = _ocr_page_words(content, i)
            if ocr_words:
                words = [w for w in words if w.page != i] + ocr_words
                page_texts[i] = " ".join(w.text for w in ocr_words)
                stats["ocr_used"] = True

    rows, row_stats = extract_rows_from_words(words, page_texts)
    stats.update(row_stats)
    stats["rows"] = len(rows)
    return rows, stats


def rows_to_year_dicts(
    rows: list[ExtractedRow],
    *,
    filing_date: str = "",
    source_url: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Convert extracted rows into year-keyed labelled dicts for the normaliser.

    Returns list of intermediate structures:
      {period, filing_date, parsing_status, labelled: [{label, value, section, provenance}]}
    """
    years: dict[str, list[dict]] = {}
    unknown_bucket: list[dict] = []

    for row in rows:
        for year, value in row.values_by_year.items():
            item = {
                "label": row.label,
                "value": value,
                "section": row.section,
                "provenance": {
                    "method": "pdf",
                    "raw_label": row.label,
                    "raw_value": ",".join(row.raw_numbers),
                    "scale_applied": row.scale,
                    "page": row.page,
                    "confidence": 70,
                },
            }
            if source_url:
                item["source"] = source_url
            if year:
                years.setdefault(year, []).append(item)
            else:
                unknown_bucket.append(item)

    # If only unknown year, assign filing year if parseable
    out: list[dict] = []
    for year in sorted(years.keys(), reverse=True):
        out.append(
            {
                "period": year,
                "filing_date": filing_date,
                "parsing_status": "pdf",
                "labelled": years[year],
            }
        )

    if unknown_bucket and not out:
        period = ""
        m = YEAR_RE.search(filing_date or "")
        if m:
            period = m.group(1)
        out.append(
            {
                "period": period or "unknown",
                "filing_date": filing_date,
                "parsing_status": "pdf",
                "labelled": unknown_bucket,
            }
        )

    return out
