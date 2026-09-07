"""Careful PDF financial-statement extraction (fallback when iXBRL unavailable).

Pipeline:
1. Digital text with positions via pdfplumber (preferred) or PyMuPDF.
2. Detect image-only / scanned PDFs (no digital text).
3. Smart OCR when needed:
   a) Low-res or every-Nth-page probe for Balance Sheet / P&L / Cash Flow keywords
   b) Full OCR only on candidate pages (±1 neighbour)
   c) Run section/year-column/row clustering on OCR words
4. Detect unit scale (£ / £000 / £m) per section.
5. Detect year column headers; associate numbers with current vs prior year.
6. Never invent numbers; every value carries provenance.
7. Never silently succeed with 0 rows on scanned PDFs — surface OCR requirement.

Limitations (honest):
- Scanned image-only PDFs depend on OCR quality and tesseract being installed.
- Multi-column layouts with notes columns can still confuse year assignment.
- Not all UK filings use standard labels; synonym map covers common variants.
- Many recent Companies House full accounts are scanned image PDFs.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

MIN_DIGITAL_CHARS = 80
PROBE_DPI_SCALE = 1.0  # low-res probe (~72 dpi * 1)
FULL_OCR_DPI_SCALE = 2.0  # ~144 dpi equivalent via fitz Matrix
PROBE_STRIDE = 2  # every Nth page during probe
MAX_PROBE_PAGES = 50
OCR_NEIGHBOUR = 1

SECTION_PATTERNS = {
    "income_statement": [
        r"statement of comprehensive income",
        r"profit and loss account",
        r"profit\s*(?:&|and)\s*loss\s+account",
        r"income statement",
        r"consolidated statement of (?:profit|comprehensive income)",
        # Intentionally NOT bare "profit and loss" — matches "profit and loss reserves"
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

# Keywords used during low-res probe (broader than section headers)
PROBE_KEYWORDS = re.compile(
    r"(?i)\b("
    r"balance\s*sheet|"
    r"statement\s+of\s+financial\s+position|"
    r"profit\s*(?:and|&)\s*loss|"
    r"income\s+statement|"
    r"comprehensive\s+income|"
    r"cash\s*flows?|"
    r"turnover|"
    r"revenue|"
    r"fixed\s+assets|"
    r"current\s+assets|"
    r"net\s+assets"
    r")\b"
)

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
    method: str = "pdf"  # pdf | pdf_ocr


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("–", "-").replace("—", "-").split())


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def detect_scale(text: str) -> int:
    t = text.lower()
    if re.search(r"£\s*m\b|£m\b|in millions|£'?m\b", t):
        return 1_000_000
    # OCR often mangles £'000 as E'000 / £000 / £'000
    if re.search(r"£'?0{3}\b|£000\b|£'000\b|e'?000\b|in thousands|£\s*000", t):
        return 1_000
    return 1


def detect_section(text: str) -> Optional[str]:
    t = _norm(text)
    for section, patterns in SECTION_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, t):
                return section
    return None


def page_mentions_financials(text: str) -> bool:
    """True if probe/OCR text looks like a financial statement page."""
    if not text or not text.strip():
        return False
    if detect_section(text):
        return True
    return bool(PROBE_KEYWORDS.search(text))


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


def _pdf_page_count(content: bytes) -> int:
    try:
        import fitz

        with fitz.open(stream=content, filetype="pdf") as doc:
            return len(doc)
    except Exception:
        return 0


def is_image_only_pdf(page_texts: list[str], *, min_chars: int = MIN_DIGITAL_CHARS) -> bool:
    """True when essentially no digital text exists across the document."""
    if not page_texts:
        return True
    rich = sum(1 for t in page_texts if len((t or "").strip()) >= min_chars)
    total_chars = sum(len((t or "").strip()) for t in page_texts)
    # Image-only: zero rich pages and virtually no text overall
    return rich == 0 and total_chars < min_chars


def _ocr_page_words(
    content: bytes,
    page_index: int,
    *,
    dpi_scale: float = FULL_OCR_DPI_SCALE,
) -> tuple[list[Word], str]:
    """OCR a single page. Returns (words, plain_text). Empty on failure / missing deps."""
    try:
        import fitz
        import pytesseract
        from pytesseract import Output
        from PIL import Image
    except ImportError as e:
        logger.warning("OCR dependencies missing: %s", e)
        return [], ""

    if not tesseract_available():
        logger.warning("tesseract binary not found on PATH")
        return [], ""

    words: list[Word] = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        if page_index >= len(doc):
            return [], ""
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            data = pytesseract.image_to_data(img, output_type=Output.DICT)
            plain = pytesseract.image_to_string(img) or ""
        except Exception as e:
            logger.warning("tesseract failed on page %s: %s", page_index, e)
            return [], ""
        n = len(data["text"])
        scale_x = page.rect.width / img.size[0] if img.size[0] else 1.0
        scale_y = page.rect.height / img.size[1] if img.size[1] else 1.0
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            x0 = data["left"][i] * scale_x
            y0 = data["top"][i] * scale_y
            x1 = x0 + data["width"][i] * scale_x
            y1 = y0 + data["height"][i] * scale_y
            words.append(Word(text=txt, x0=x0, x1=x1, top=y0, bottom=y1, page=page_index))
    return words, plain


def _ocr_page_text_only(
    content: bytes,
    page_index: int,
    *,
    dpi_scale: float = PROBE_DPI_SCALE,
) -> str:
    """Cheap text-only OCR for probing (no word boxes)."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    if not tesseract_available():
        return ""
    with fitz.open(stream=content, filetype="pdf") as doc:
        if page_index >= len(doc):
            return ""
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            return pytesseract.image_to_string(img) or ""
        except Exception:
            return ""


CONTENTS_PAGE_RE = re.compile(
    r"(?i)(profit\s*(?:and|&)\s*loss\s*account|balance\s*sheet|"
    r"statement\s+of\s+financial\s+position|cash\s*flows?|"
    r"statement\s+of\s+changes\s+in\s+equity)"
    r"[^\d]{0,40}?(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?"
)


def contents_page_hints(text: str) -> list[int]:
    """Parse contents-page OCR for printed statement page numbers (1-based)."""
    pages: list[int] = []
    for m in CONTENTS_PAGE_RE.finditer(text or ""):
        for g in m.groups()[1:]:
            if not g:
                continue
            try:
                pages.append(int(g))
            except ValueError:
                pass
    return pages


def probe_financial_pages(
    content: bytes,
    n_pages: int,
    *,
    stride: int = PROBE_STRIDE,
    max_probe: int = MAX_PROBE_PAGES,
) -> tuple[list[int], dict[str, Any]]:
    """
    Low-res / every-Nth-page probe to find pages mentioning financial statements.
    Returns candidate page indices (0-based) and probe stats.
    """
    hits: list[int] = []
    probe_stats: dict[str, Any] = {
        "probed_pages": [],
        "hit_pages": [],
        "stride": stride,
    }
    limit = min(n_pages, max_probe)
    # Always include early pages (cover/contents often list statement page nos)
    indices = sorted(set(list(range(0, min(5, limit))) + list(range(0, limit, max(1, stride)))))
    for i in indices:
        text = _ocr_page_text_only(content, i, dpi_scale=PROBE_DPI_SCALE)
        probe_stats["probed_pages"].append(i)
        if page_mentions_financials(text):
            hits.append(i)
            probe_stats["hit_pages"].append(i)
            # Contents pages often only *mention* statements — keep probing
            # If this page looks like an actual statement header, still record it
    return hits, probe_stats


def expand_candidate_pages(
    hits: list[int],
    n_pages: int,
    *,
    neighbour: int = OCR_NEIGHBOUR,
) -> list[int]:
    """Expand probe hits by ±neighbour and clamp to document."""
    selected: set[int] = set()
    for h in hits:
        for d in range(-neighbour, neighbour + 1):
            p = h + d
            if 0 <= p < n_pages:
                selected.add(p)
    return sorted(selected)


def cluster_rows(page_words: list[Word], y_tol: float = 4.0) -> list[list[Word]]:
    if not page_words:
        return []
    ordered = sorted(page_words, key=lambda w: (w.top, w.x0))
    rows: list[list[Word]] = []
    current = [ordered[0]]
    for w in ordered[1:]:
        # OCR Y jitter is larger — slightly looser tolerance when words are sparse
        tol = y_tol
        if abs(w.top - current[-1].top) <= tol:
            current.append(w)
        else:
            rows.append(sorted(current, key=lambda x: x.x0))
            current = [w]
    rows.append(sorted(current, key=lambda x: x.x0))
    return rows


def detect_year_columns(rows: list[list[Word]], page_width: float) -> list[tuple[str, float]]:
    """
    Return list of (year, center_x) for comparative year headers.

    Prefers a header row that contains TWO year tokens (current + prior).
    Ignores title-line dates like "31 July 2025" / "year ended 2025".
    """
    dateish = re.compile(
        r"(?i)\b(january|february|march|april|may|june|july|august|september|"
        r"october|november|december|ended|as\s+at|year\s+ended|period\s+ended)\b"
    )

    def row_year_words(row: list[Word]) -> list[tuple[str, float, Word]]:
        out = []
        for w in row:
            m = YEAR_RE.fullmatch(w.text.strip())
            if not m:
                continue
            mid = (w.x0 + w.x1) / 2
            out.append((m.group(1), mid, w))
        return out

    # Pass 1: rows with >=2 distinct years, not date-phrase rows
    for row in rows[:30]:
        row_text = " ".join(w.text for w in row)
        if dateish.search(row_text) and len(YEAR_RE.findall(row_text)) < 2:
            continue
        # Skip pure title lines that also contain a month + single year
        yw = row_year_words(row)
        years = []
        seen_y = set()
        for y, mid, _w in yw:
            if page_width and mid < page_width * 0.30:
                continue
            if y in seen_y:
                continue
            seen_y.add(y)
            years.append((y, mid))
        if len(years) >= 2:
            # If row looks like "31 July 2025" alone, reject; dual years OK even with month
            if dateish.search(row_text) and len(years) < 2:
                continue
            years.sort(key=lambda t: t[1])
            return years

    # Pass 2: single-year headers only in the right 55%, not on dateish rows
    year_cols: list[tuple[str, float]] = []
    seen: set[str] = set()
    for row in rows[:25]:
        row_text = " ".join(w.text for w in row)
        if dateish.search(row_text):
            continue
        for y, mid, _w in row_year_words(row):
            if page_width and mid < page_width * 0.45:
                continue
            if y in seen:
                continue
            seen.add(y)
            year_cols.append((y, mid))
    year_cols.sort(key=lambda t: t[1])
    return year_cols


def refine_year_columns(
    rows: list[list[Word]],
    year_cols: list[tuple[str, float]],
    page_width: float,
) -> list[tuple[str, float]]:
    """Snap year header X positions to clusters of significant numeric values.

    OCR often places year headers slightly to the right of the actual number
    columns (common on scanned UK accounts), which pushes current-year amounts
    into the label/notes zone.
    """
    if len(year_cols) < 2:
        return year_cols
    xs: list[float] = []
    for row in rows:
        for w in row:
            val = parse_number_token(w.text)
            if val is None or abs(val) < 100:
                continue
            if _is_note_ref(val):
                continue
            xs.append((w.x0 + w.x1) / 2)
    if len(xs) < 4:
        return year_cols
    xs.sort()
    n = len(year_cols)
    # Split sorted X into n contiguous groups of roughly equal size
    refined: list[tuple[str, float]] = []
    for i, (year, _old_x) in enumerate(year_cols):
        start = int(round(i * len(xs) / n))
        end = int(round((i + 1) * len(xs) / n))
        group = xs[start:end] or xs
        mid = group[len(group) // 2]
        refined.append((year, mid))
    return refined


def _is_note_ref(val: float) -> bool:

    """UK accounts notes column is typically a small positive integer (1–99)."""
    return val == int(val) and 1 <= abs(val) <= 99


def _label_and_numbers(
    row: list[Word],
    year_cols: list[tuple[str, float]],
    page_width: float,
) -> tuple[str, dict[str, float], list[str]]:
    """Split a row into left-side label and year-aligned numbers.

    Skips the Notes column (small ints left of the year columns). When multiple
    numbers map to the same year, prefer the one closest to the column center,
    breaking ties toward non-note magnitudes.
    """
    if not row:
        return "", {}, []

    leftmost_year_x = min((yc[1] for yc in year_cols), default=None)
    # Label/notes vs values split: left of first year column (with slack for notes)
    if leftmost_year_x is not None:
        # Leave room for number columns that sit slightly left of year headers
        split_x = leftmost_year_x - (page_width * 0.12 if page_width else 40)
        notes_max_x = leftmost_year_x - (page_width * 0.14 if page_width else 50)
    else:
        split_x = page_width * 0.42 if page_width else 9999
        notes_max_x = split_x

    label_parts: list[str] = []
    number_words: list[Word] = []
    for w in row:
        mid = (w.x0 + w.x1) / 2
        tok = w.text.strip()
        is_num = bool(NUMBER_TOKEN_RE.match(tok.replace(" ", ""))) and parse_number_token(tok) is not None
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
        # year -> list of (distance, is_note, abs_val, val)
        candidates: dict[str, list[tuple[float, bool, float, float]]] = {}
        for w in number_words:
            val = parse_number_token(w.text)
            if val is None:
                continue
            mid = (w.x0 + w.x1) / 2
            # Drop note-column tokens sitting left of the year headers
            if mid < notes_max_x and _is_note_ref(val):
                continue
            nearest = min(year_cols, key=lambda yc: abs(yc[1] - mid))
            dist = abs(nearest[1] - mid)
            if page_width and dist > page_width * 0.22:
                continue
            year = nearest[0]
            candidates.setdefault(year, []).append((dist, _is_note_ref(val), abs(val), val))

        for year, opts in candidates.items():
            # Prefer non-note, then closer to column, then larger magnitude
            opts.sort(key=lambda t: (t[1], t[0], -t[2]))
            values[year] = opts[0][3]
    elif number_words:
        # No year headers: skip leading note refs; take first real amount
        for w in number_words:
            val = parse_number_token(w.text)
            if val is None or _is_note_ref(val):
                continue
            values[""] = val
            break

    return label, values, raw_nums


def extract_rows_from_words(
    words: list[Word],
    page_texts: list[str],
    *,
    max_pages: int = 80,
    default_method: str = "pdf",
    ocr_page_set: Optional[set[int]] = None,
    y_tol: float = 4.0,
) -> tuple[list[ExtractedRow], dict[str, Any]]:
    stats: dict[str, Any] = {"pages_scanned": 0, "sections": [], "ocr_pages": []}
    by_page: dict[int, list[Word]] = {}
    for w in words:
        by_page.setdefault(w.page, []).append(w)

    results: list[ExtractedRow] = []
    active_section: Optional[str] = None
    active_scale = 1
    active_years: list[tuple[str, float]] = []
    ocr_pages = ocr_page_set or set()

    # Prefer slightly looser Y clustering for OCR pages
    ocr_y_tol = max(y_tol, 8.0)

    for page_idx in sorted(by_page.keys()):
        if page_idx >= max_pages:
            break
        stats["pages_scanned"] += 1
        page_words = by_page[page_idx]
        text = page_texts[page_idx] if page_idx < len(page_texts) else " ".join(w.text for w in page_words)
        page_width = max((w.x1 for w in page_words), default=600.0)
        page_method = "pdf_ocr" if page_idx in ocr_pages else default_method
        page_y_tol = ocr_y_tol if page_idx in ocr_pages else y_tol

        section_hit = detect_section(text)
        if section_hit:
            active_section = section_hit
            active_scale = detect_scale(text)
            if active_section not in stats["sections"]:
                stats["sections"].append(active_section)

        page_scale = detect_scale(text)
        if page_scale != 1 and active_section:
            active_scale = page_scale

        rows = cluster_rows(page_words, y_tol=page_y_tol)
        year_cols = detect_year_columns(rows, page_width)
        if year_cols:
            year_cols = refine_year_columns(rows, year_cols, page_width)
            active_years = year_cols

        # Drop sticky section on narrative / notes pages so note tables do not
        # inherit Balance Sheet / P&L and pollute primary statements.
        low_text = _norm(text)
        if re.search(
            r"strategic report|directors. report|independent auditor|"
            r"notes to the financial statements",
            low_text,
        ) and not section_hit:
            active_section = None
            active_years = []
            continue

        # Only extract from pages that have comparative year headers on-page.
        # Contents / strategic report / notes mention statement names but must not
        # contribute figures (they poison year buckets via first-wins merge).
        if not active_section:
            continue
        if not year_cols:
            continue

        pending_header: Optional[str] = None
        for row in rows:
            label, values, raw_nums = _label_and_numbers(row, year_cols, page_width)
            norm_label = _norm(label) if label else ""
            if label and not values:
                if norm_label in (
                    "fixed assets",
                    "current assets",
                    "total fixed assets",
                    "total current assets",
                ):
                    pending_header = label
                continue
            if not label and values and pending_header:
                label = pending_header
                pending_header = None
            if not label or not values:
                continue
            if _norm(label) in ("note", "notes", "£", "£000", "£'000", "£m", "e'000"):
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
                    method=page_method,
                )
            )

    return results, stats


def _smart_ocr_words(
    content: bytes,
    n_pages: int,
    stats: dict[str, Any],
) -> tuple[list[Word], list[str], set[int]]:
    """
    Probe then full-OCR candidate pages. Mutates stats with OCR diagnostics.
    """
    if not tesseract_available():
        stats["ocr_required"] = True
        stats["ocr_available"] = False
        stats["ocr_error"] = "tesseract_not_installed"
        stats["parsing_status"] = "ocr_required"
        return [], [""] * n_pages, set()

    stats["ocr_available"] = True
    hits, probe_stats = probe_financial_pages(content, n_pages)
    stats["ocr_probe"] = probe_stats

    # Contents pages (usually 0-4) often list "Profit and loss account 17"
    # Convert printed page numbers → 0-based indices (printed footer ≈ index+offset).
    # Heuristic: printed page N often lands near PDF index N or N+2 for cover/front matter.
    contents_hits: list[int] = []
    for early in list(probe_stats.get("probed_pages") or [])[:5]:
        # Re-use already-probed text via a cheap re-OCR only if we have hits later;
        # instead OCR text_only already ran — call again is OK for early pages (cached by OS).
        text = _ocr_page_text_only(content, early, dpi_scale=PROBE_DPI_SCALE)
        for printed in contents_page_hints(text):
            for idx in (printed - 1, printed, printed + 1, printed + 2):
                if 0 <= idx < n_pages:
                    contents_hits.append(idx)
    if contents_hits:
        probe_stats["contents_hints"] = sorted(set(contents_hits))
        hits = sorted(set(hits + contents_hits))

    candidates = expand_candidate_pages(hits, n_pages)
    # If contents hints exist, prefer a tighter candidate set around them + probe hits
    if contents_hits:
        tight = expand_candidate_pages(sorted(set(contents_hits + hits[:])), n_pages, neighbour=1)
        # Keep early cover/contents pages out unless they were keyword hits
        tight = [p for p in tight if p >= 8 or p in hits]
        if tight:
            candidates = tight
    # Fallback: if probe found nothing, try a broader middle band of the doc
    # (statements usually sit after directors/audit reports ~ pages 10–35)
    if not candidates:
        stats["ocr_probe_fallback"] = True
        mid_start = min(8, n_pages)
        mid_end = min(n_pages, max(mid_start + 1, 35))
        # Probe denser in the middle
        extra_hits: list[int] = []
        for i in range(mid_start, mid_end):
            text = _ocr_page_text_only(content, i, dpi_scale=PROBE_DPI_SCALE)
            if page_mentions_financials(text):
                extra_hits.append(i)
        candidates = expand_candidate_pages(extra_hits, n_pages)
        stats.setdefault("ocr_probe", {})["fallback_hits"] = extra_hits

    if not candidates:
        # Last resort: full-OCR a small fixed window where UK accounts usually live
        candidates = list(range(min(12, n_pages), min(n_pages, 25)))
        stats["ocr_blind_window"] = candidates

    stats["ocr_candidate_pages"] = candidates
    words: list[Word] = []
    page_texts = [""] * n_pages
    ocr_pages: set[int] = set()

    for i in candidates:
        ocr_words, plain = _ocr_page_words(content, i, dpi_scale=FULL_OCR_DPI_SCALE)
        if ocr_words or plain.strip():
            words.extend(ocr_words)
            page_texts[i] = plain if plain.strip() else " ".join(w.text for w in ocr_words)
            ocr_pages.add(i)
            stats.setdefault("ocr_pages", []).append(i)

    stats["ocr_used"] = bool(ocr_pages)
    stats["ocr_required"] = True
    return words, page_texts, ocr_pages


def extract_from_pdf_bytes(content: bytes, *, allow_ocr: bool = True) -> tuple[list[ExtractedRow], dict[str, Any]]:
    stats: dict[str, Any] = {
        "engine": None,
        "ocr_used": False,
        "ocr_required": False,
        "ocr_available": tesseract_available(),
        "image_only": False,
        "parsing_status": None,
    }
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
            stats["parsing_status"] = "failed"
            return [], stats

    n_pages = len(page_texts) or _pdf_page_count(content)
    stats["page_count"] = n_pages
    total_digital = sum(len((t or "").strip()) for t in page_texts)
    stats["digital_chars"] = total_digital
    image_only = is_image_only_pdf(page_texts)
    stats["image_only"] = image_only

    ocr_page_set: set[int] = set()

    if image_only:
        stats["ocr_required"] = True
        if not allow_ocr:
            stats["parsing_status"] = "ocr_required"
            stats["note"] = "image_only_pdf_ocr_disabled"
            return [], stats
        if not tesseract_available():
            stats["ocr_available"] = False
            stats["ocr_error"] = "tesseract_not_installed"
            stats["parsing_status"] = "ocr_required"
            stats["note"] = "image_only_pdf_needs_tesseract"
            return [], stats
        words, page_texts, ocr_page_set = _smart_ocr_words(content, n_pages, stats)
    elif allow_ocr:
        # Hybrid: OCR only sparse pages that look like they should have content
        # near financial sections — still avoid blindly OCR-ing entire docs
        sparse_indices = [
            i for i, t in enumerate(page_texts) if len((t or "").strip()) < MIN_DIGITAL_CHARS
        ]
        if sparse_indices and tesseract_available():
            # Only OCR sparse pages adjacent to digitally-detected sections,
            # or sparse pages in the first 40 if a neighbour mentions accounts
            digital_section_pages = {
                i for i, t in enumerate(page_texts) if detect_section(t or "")
            }
            to_ocr: set[int] = set()
            for i in sparse_indices:
                if i > 45:
                    continue
                if any(abs(i - s) <= 2 for s in digital_section_pages):
                    to_ocr.add(i)
            # If almost all pages are sparse but not flagged image_only (edge),
            # fall through to smart OCR
            if len(sparse_indices) >= max(1, int(0.8 * n_pages)):
                stats["ocr_required"] = True
                words, page_texts, ocr_page_set = _smart_ocr_words(content, n_pages, stats)
            else:
                for i in sorted(to_ocr):
                    ocr_words, plain = _ocr_page_words(content, i)
                    if ocr_words:
                        words = [w for w in words if w.page != i] + ocr_words
                        page_texts[i] = plain or " ".join(w.text for w in ocr_words)
                        ocr_page_set.add(i)
                        stats["ocr_used"] = True
                        stats.setdefault("ocr_pages", []).append(i)
        elif sparse_indices and not tesseract_available():
            stats["ocr_required"] = True
            stats["ocr_available"] = False
            stats["note"] = "sparse_pages_need_tesseract"

    default_method = "pdf_ocr" if ocr_page_set and image_only else "pdf"
    rows, row_stats = extract_rows_from_words(
        words,
        page_texts,
        default_method=default_method,
        ocr_page_set=ocr_page_set,
        y_tol=8.0 if ocr_page_set else 4.0,
    )
    stats.update({k: v for k, v in row_stats.items() if k != "ocr_pages" or "ocr_pages" not in stats})
    if "ocr_pages" in row_stats and "ocr_pages" not in stats:
        stats["ocr_pages"] = row_stats["ocr_pages"]
    stats["rows"] = len(rows)

    if image_only and not rows:
        stats["parsing_status"] = "ocr_required" if stats.get("ocr_required") else "failed"
        if stats.get("ocr_used"):
            stats["parsing_status"] = "partial"
            stats["note"] = "ocr_ran_but_no_rows_extracted"
    elif rows and ocr_page_set:
        stats["parsing_status"] = "pdf_ocr"
    elif rows:
        stats["parsing_status"] = "pdf"
    elif image_only:
        stats["parsing_status"] = "ocr_required"
    else:
        stats["parsing_status"] = "partial"

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
        method = getattr(row, "method", None) or "pdf"
        for year, value in row.values_by_year.items():
            item = {
                "label": row.label,
                "value": value,
                "section": row.section,
                "provenance": {
                    "method": method,
                    "raw_label": row.label,
                    "raw_value": ",".join(row.raw_numbers),
                    "scale_applied": row.scale,
                    "page": row.page,
                    "confidence": 65 if method == "pdf_ocr" else 70,
                },
            }
            if source_url:
                item["source"] = source_url
            if year:
                years.setdefault(year, []).append(item)
            else:
                unknown_bucket.append(item)

    out: list[dict] = []
    status = "pdf_ocr" if any(getattr(r, "method", "") == "pdf_ocr" for r in rows) else "pdf"
    for year in sorted(years.keys(), reverse=True):
        out.append(
            {
                "period": year,
                "filing_date": filing_date,
                "parsing_status": status,
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
                "parsing_status": status,
                "labelled": unknown_bucket,
            }
        )

    return out
