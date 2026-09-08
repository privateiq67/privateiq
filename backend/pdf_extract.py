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
PROBE_STRIDE = 2  # default stride for short docs; adaptive for long
MAX_PROBE_PAGES = 80  # max pages to *probe* (not a front-only page cutoff)
MAX_FULL_OCR_PAGES = 28  # budget for expensive full-DPI OCR
OCR_NEIGHBOUR = 2  # expand hits by ±2 pages

SECTION_PATTERNS = {
    "income_statement": [
        r"statement of comprehensive income",
        r"consolidated (?:statement of )?comprehensive income",
        r"group (?:statement of )?comprehensive income",
        r"profit and loss account",
        r"profit\s*(?:&|and)\s*loss\s+account",
        r"consolidated profit\s*(?:&|and)\s*loss",
        r"group profit\s*(?:&|and)\s*loss",
        r"income statement",
        r"consolidated income statement",
        r"group income statement",
        r"consolidated statement of (?:profit|comprehensive income)",
        # Intentionally NOT bare "profit and loss" — matches "profit and loss reserves"
    ],
    "balance_sheet": [
        r"statement of financial position",
        r"balance sheet",
        r"group balance sheet",
        r"consolidated balance sheet",
        r"consolidated (?:statement of )?financial position",
        r"group (?:statement of )?financial position",
    ],
    "cash_flow": [
        r"statement of cash flows?",
        r"cash flow statement",
        r"group (?:statement of )?cash flows?",
        r"consolidated (?:statement of )?cash flows?",
    ],
}

# Keywords used during low-res probe (broader than section headers)
PROBE_KEYWORDS = re.compile(
    r"(?i)\b("
    r"balance\s*sheet|"
    r"group\s+balance\s*sheet|"
    r"statement\s+of\s+financial\s+position|"
    r"profit\s*(?:and|&)\s*loss|"
    r"income\s+statement|"
    r"comprehensive\s+income|"
    r"consolidated\s+(?:income|statement)|"
    r"cash\s*flows?|"
    r"turnover|"
    r"revenue|"
    r"fixed\s+assets|"
    r"current\s+assets|"
    r"net\s+assets|"
    r"operating\s+profit|"
    r"profit\s+before\s+tax"
    r")\b"
)

YEAR_RE = re.compile(r"\b(20[1-3]\d)\b")
YEAR_ENDED_RE = re.compile(
    r"(?i)(?:year|period)\s+ended\s+"
    r"(?:\d{1,2}\s+)?"
    r"(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+"
    r"(20[1-3]\d)"
)


_AT_DATE_RE = re.compile(
    r"(?i)\b(?:as\s+at|at)\s+\d{1,2}\s+"
    r"(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+(20[1-3]\d)"
)


def year_ended_from_text(text: str) -> Optional[str]:
    """Best-effort current period year from statement title lines."""
    blob = text or ""
    m = YEAR_ENDED_RE.search(blob)
    if m:
        return m.group(1)
    m = _AT_DATE_RE.search(blob)
    if m:
        return m.group(1)
    return None

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


def _normalize_scale_text(text: str) -> str:
    """OCR-tolerant normalisation before unit/scale regexes.

    Handles curly/smart quotes, common £→E/L misreads next to 000, and O↔0
    inside thousand markers. Does not invent units from body narrative alone.
    """
    t = (text or "").lower()
    for a, b in (
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201a", "'"),
        ("\u2032", "'"),  # prime
        ("\u00b4", "'"),
        ("`", "'"),
        ("´", "'"),
        ("′", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
    ):
        t = t.replace(a, b)
    t = re.sub(r"[\s\u00a0]+", " ", t)
    return t


# Prefer millions before thousands. Patterns are OCR-tolerant (O↔0, £↔e/l/€).
# Currency glyph OCR often maps £ → $ / E / e. Do NOT use bare "l" before "m"
# (false-positive on "...al misstatements"). Prefer explicit £/$/€ or standalone Em/£m.
_SCALE_MILLIONS_RE = re.compile(
    r"(?:"
    r"[£€$]\s*'?\s*m\b|"
    r"[£€$]m\b|"
    r"(?<![a-z])e\s*'?\s*m\b|"  # Em / E m as unit token, not "...e m..."
    r"\bin\s+millions?\b|"
    r"\ball\s+figures\s+in\s+[£€$e]?\s*'?\s*m\b|"
    r"[£€$]\s*millions?\b"
    r")",
    re.I,
)

# Thousands: £'000, £000, $000 (OCR of £000), '000, 000s, in thousands, E'OOO, etc.
_SCALE_THOUSANDS_RE = re.compile(
    r"(?:"
    r"[£€$]\s*'\s*[0o]{3}\s*s?\b|"  # £'000 / $'000 / £'000s
    r"[£€$]\s*[0o]{3}\s*s?\b|"  # £000 / $000 / £OOO (common OCR £→$)
    r"(?<![a-z])[el]\s*'\s*[0o]{3}\s*s?\b|"  # E'000 / L'000
    r"(?<![a-z])[el]\s*[0o]{3}\s*s?\b|"  # E000 / L000
    r"(?<![\w.])'\s*[0o]{3}\s*s?\b|"  # '000 / '000s column headers
    r"(?<![\w.])[0o]{3}\s*s\b|"  # 000s
    r"\bin\s+thousands?\b|"
    r"\ball\s+figures\s+in\s+[£€$el]?\s*'?[0o]{3}\s*s?\b|"
    r"figures?\s+(?:are\s+)?in\s+[£€$el]?\s*'?[0o]{3}\s*s?\b|"
    r"[£€$]\s*thousands?\b|"
    r"(?<![a-z])[el]\s*thousands?\b|"
    r"\([£€$el]?\s*'?[0o]{3}\s*s?\)|"  # (£'000) / ($000)
    r"\[[£€$el]?\s*'?[0o]{3}\s*s?\]"
    r")",
    re.I,
)

# Phrases that look like unit declarations (header/table context), not random body.
_SCALE_HEADERISH_RE = re.compile(
    r"(?i)("
    r"notes?|all\s+figures|amounts?\s+(?:are\s+)?in|expressed\s+in|"
    r"profit\s*(?:and|&)\s*loss|income\s+statement|balance\s+sheet|"
    r"financial\s+position|statement\s+of|consolidated|"
    r"\b20[1-3]\d\b|"  # year headers near unit columns
    r"[£€$el]\s*'?[0o]{3}|[£€$]\s*'?m\b|'\s*[0o]{3}|\$\s*[0o]{3}"
    r")"
)


def detect_scale(text: str) -> int:
    """Return 1 / 1_000 / 1_000_000 from unit markers in *text*.

    OCR-tolerant. Prefer calling detect_scale_prefer_header for page text so
    body mentions of "thousands of customers" do not flip statement units.
    """
    t = _normalize_scale_text(text)
    if not t.strip():
        return 1
    if _SCALE_MILLIONS_RE.search(t):
        return 1_000_000
    if _SCALE_THOUSANDS_RE.search(t):
        return 1_000
    return 1


def detect_scale_prefer_header(text: str, *, header_extra: str = "") -> int:
    """Detect scale preferring section/table-header context over body narrative.

    Order: explicit header_extra (e.g. top table rows) → first ~1.2k chars /
    early lines → full page only if a unit token sits near a headerish phrase.
    """
    chunks: list[str] = []
    if header_extra and header_extra.strip():
        chunks.append(header_extra)
    raw = text or ""
    lines = raw.splitlines()
    early = "\n".join(lines[:18])
    chunks.append(early)
    chunks.append(raw[:1200])

    for chunk in chunks:
        scale = detect_scale(chunk)
        if scale != 1:
            return scale

    # Full-page fallback: only accept if unit token is near headerish context
    t = _normalize_scale_text(raw)
    for cre, scale in ((_SCALE_MILLIONS_RE, 1_000_000), (_SCALE_THOUSANDS_RE, 1_000)):
        for m in cre.finditer(t):
            window = t[max(0, m.start() - 80) : m.end() + 80]
            if _SCALE_HEADERISH_RE.search(window):
                return scale
    return 1



def detect_section(text: str) -> Optional[str]:
    """Return statement type for a page.

    When multiple patterns match (common on OCR pages that mention both the
    balance sheet header and a later P&L cross-reference), prefer the match
    that appears earliest in the page text so the header wins.
    """
    t = _norm(text)
    best_section = None
    best_pos = 10**9
    for section, patterns in SECTION_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, t)
            if m and m.start() < best_pos:
                best_pos = m.start()
                best_section = section
    return best_section


def page_mentions_financials(text: str) -> bool:
    """True if probe/OCR text looks like a financial statement page."""
    if not text or not text.strip():
        return False
    if detect_section(text):
        return True
    return bool(PROBE_KEYWORDS.search(text))


def parse_number_token(token: str, *, scale_hint: int = 1) -> Optional[float]:
    raw = token.strip().replace("\xa0", "").replace("£", "").replace("$", "")
    if not raw or raw in ("—", "–", "-", "−", "n/a", "na"):
        return None
    # Skip pure years used as headers
    if re.fullmatch(r"20[1-3]\d", raw):
        return None
    neg = False
    t = raw
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1]
    t = t.replace("%", "").replace("−", "-").strip()
    # Normal UK thousands: strip commas 2,488.6 → 2488.6
    if "," in t and re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", t):
        t = t.replace(",", "")
    elif "," in t:
        # OCR mixed junk — drop commas
        t = t.replace(",", "")
    # £m OCR often turns 2,296.3 into 2.2963 (comma→dot collapsed)
    if scale_hint >= 1_000_000 and re.fullmatch(r"-?\d{1,3}\.\d{4}", t):
        sign = "-" if t.startswith("-") else ""
        body = t.lstrip("-")
        a, b = body.split(".", 1)
        t = f"{sign}{a}{b[:3]}.{b[3:]}"  # 2.2963 → 2296.3
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
    r"(?i)("
    r"(?:consolidated\s+|group\s+)?"
    r"(?:statement\s+of\s+)?"
    r"(?:comprehensive\s+)?income|"
    r"(?:consolidated\s+|group\s+)?(?:profit\s*(?:and|&)\s*loss(?:\s+account)?|"
    r"income\s+statement)|"
    r"(?:consolidated\s+|group\s+)?balance\s*sheet|"
    r"(?:consolidated\s+|group\s+)?statement\s+of\s+financial\s+position|"
    r"(?:consolidated\s+|group\s+)?(?:statement\s+of\s+)?cash\s*flows?|"
    r"statement\s+of\s+changes\s+in\s+equity"
    r")"
    r"[^\d]{0,60}?(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?"
)

# Stronger contents lines: "Consolidated income statement ..... 86"
CONTENTS_LINE_RE = re.compile(
    r"(?i)^\s*("
    r"(?:consolidated|group)\s+(?:statement\s+of\s+)?(?:comprehensive\s+)?income|"
    r"(?:consolidated|group)\s+profit\s*(?:and|&)\s*loss|"
    r"(?:consolidated|group)\s+income\s+statement|"
    r"(?:consolidated|group)\s+balance\s*sheet|"
    r"(?:consolidated|group)\s+statement\s+of\s+financial\s+position|"
    r"(?:consolidated|group)\s+(?:statement\s+of\s+)?cash\s*flows?|"
    r"profit\s*(?:and|&)\s*loss\s+account|"
    r"balance\s*sheet|"
    r"statement\s+of\s+financial\s+position|"
    r"statement\s+of\s+cash\s*flows?"
    r").{0,80}?(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?\s*$",
    re.M,
)


def contents_page_hints(text: str) -> list[int]:
    """Parse contents-page OCR for printed statement page numbers (1-based)."""
    pages: list[int] = []
    blob = text or ""
    for cre in (CONTENTS_LINE_RE, CONTENTS_PAGE_RE):
        for m in cre.finditer(blob):
            for g in m.groups()[1:]:
                if not g:
                    continue
                try:
                    pages.append(int(g))
                except ValueError:
                    pass
    # Dedupe preserve order
    seen: set[int] = set()
    out: list[int] = []
    for p in pages:
        if p not in seen and 1 <= p <= 400:
            seen.add(p)
            out.append(p)
    return out


def adaptive_probe_stride(n_pages: int) -> int:
    """Stride grows with document length so long reports still get whole-doc coverage."""
    if n_pages <= 40:
        return 1
    if n_pages <= 80:
        return 2
    if n_pages <= 120:
        return 3
    if n_pages <= 200:
        return 4
    return 5


def select_probe_indices(
    n_pages: int,
    *,
    max_probe: int = MAX_PROBE_PAGES,
    stride: int | None = None,
    hit_indices: list[int] | None = None,
) -> tuple[list[int], int]:
    """
    Choose 0-based page indices to probe across the *whole* document.

    Long UK group reports (150–200+ pages) put financial statements in the
    middle/back — never only the first ~40–50 pages. Dense front for contents,
    adaptive stride overall, denser mid/back band. Cap total probes at max_probe.

    ``hit_indices`` is unused for selection (kept for API symmetry / tests that
    pass known hits when composing candidate windows separately).
    """
    del hit_indices  # selection does not depend on prior hits
    if n_pages <= 0:
        return [], 1
    stride = adaptive_probe_stride(n_pages) if stride is None else max(1, int(stride))
    indices: set[int] = set()

    # Dense front matter / contents / directors pages
    for i in range(0, min(12, n_pages)):
        indices.add(i)

    # Whole-document stride (covers back half of long reports)
    for i in range(0, n_pages, stride):
        indices.add(i)
    # Always include last page
    indices.add(n_pages - 1)

    # Denser mid/back where consolidated statements usually sit
    mid_start = int(n_pages * 0.35)
    mid_end = min(n_pages, int(n_pages * 0.95) + 1)
    dense = max(2, stride - 1)
    for i in range(mid_start, mid_end, dense):
        indices.add(i)

    # Extra density in the classic "accounts block" for mid-size docs
    if 40 < n_pages <= 120:
        for i in range(min(15, n_pages), min(n_pages, 55), 2):
            indices.add(i)

    sorted_idx = sorted(indices)
    if len(sorted_idx) <= max_probe:
        return sorted_idx, stride

    # Cap: keep all front pages, then prefer mid/back over early narrative
    front = [i for i in sorted_idx if i < 12]
    mid_back = [i for i in sorted_idx if mid_start <= i < mid_end]
    other = [i for i in sorted_idx if i not in set(front) and i not in set(mid_back)]
    kept: list[int] = list(front)
    budget = max_probe - len(kept)
    # Take mid_back first (evenly subsampled if needed), then other
    if len(mid_back) <= budget:
        kept.extend(mid_back)
        budget = max_probe - len(kept)
        if budget > 0 and other:
            step = max(1, len(other) // budget)
            kept.extend(other[::step][:budget])
    else:
        step = max(1, len(mid_back) // budget)
        kept.extend(mid_back[::step][:budget])
    return sorted(set(kept))[:max_probe], stride


def probe_hit_priority(page_index: int, n_pages: int, *, from_contents: bool = False) -> int:
    """Higher = more likely a real statement page (vs front-matter keyword noise)."""
    if from_contents:
        return 100
    # Prefer middle/back of long docs over cover / strategic report chatter
    if n_pages >= 80:
        if page_index >= int(n_pages * 0.35):
            return 50
        if page_index >= 12:
            return 20
        return 5
    if page_index >= 8:
        return 40
    return 10


def prioritize_ocr_candidates(
    hits: list[int],
    n_pages: int,
    *,
    contents_hits: list[int] | None = None,
    neighbour: int = OCR_NEIGHBOUR,
    max_pages: int = MAX_FULL_OCR_PAGES,
) -> list[int]:
    """
    Expand hits by ±neighbour, score, and cap to ``max_pages``.

    Contents-hint and mid/back statement hits win over front-matter.
    """
    contents_set = set(contents_hits or [])
    scored: dict[int, int] = {}

    def bump(p: int, base: int, dist: int) -> None:
        if not (0 <= p < n_pages):
            return
        # Neighbours slightly below the seed page
        score = base - abs(dist)
        scored[p] = max(scored.get(p, 0), score)

    seeds = sorted(set(hits) | contents_set)
    for h in seeds:
        base = probe_hit_priority(h, n_pages, from_contents=h in contents_set)
        for d in range(-neighbour, neighbour + 1):
            bump(h + d, base, d)

    # Sort by score desc, then page asc for stability
    ordered = sorted(scored.keys(), key=lambda p: (-scored[p], p))
    return ordered[: max(1, max_pages)] if ordered else []


def probe_financial_pages(
    content: bytes,
    n_pages: int,
    *,
    stride: int | None = None,
    max_probe: int = MAX_PROBE_PAGES,
    ocr_text_fn=None,
) -> tuple[list[int], dict[str, Any]]:
    """
    Low-res / strided probe across the whole document for financial keywords.

    Returns candidate hit page indices (0-based) and probe stats.
    ``ocr_text_fn(content, page_index) -> str`` injectable for unit tests.
    """
    ocr_fn = ocr_text_fn or (
        lambda c, i: _ocr_page_text_only(c, i, dpi_scale=PROBE_DPI_SCALE)
    )
    indices, used_stride = select_probe_indices(
        n_pages, max_probe=max_probe, stride=stride
    )
    hits: list[int] = []
    contents_printed: list[int] = []
    probe_stats: dict[str, Any] = {
        "probed_pages": [],
        "hit_pages": [],
        "stride": used_stride,
        "n_pages": n_pages,
        "max_probe": max_probe,
        "contents_printed_pages": [],
    }
    for i in indices:
        text = ocr_fn(content, i)
        probe_stats["probed_pages"].append(i)
        if page_mentions_financials(text):
            hits.append(i)
            probe_stats["hit_pages"].append(i)
        # Contents / index pages: early or pages that look like a TOC
        low = (text or "").lower()
        if i < 15 or "contents" in low or "page" in low[:200]:
            printed = contents_page_hints(text)
            if printed:
                contents_printed.extend(printed)
    if contents_printed:
        probe_stats["contents_printed_pages"] = sorted(set(contents_printed))
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


def printed_pages_to_indices(printed_pages: list[int], n_pages: int) -> list[int]:
    """Map 1-based printed page numbers to likely 0-based PDF indices."""
    out: list[int] = []
    for printed in printed_pages:
        # Cover/front matter offset: printed N often near index N-1 .. N+3
        for idx in (printed - 1, printed, printed + 1, printed + 2, printed + 3):
            if 0 <= idx < n_pages:
                out.append(idx)
    return sorted(set(out))



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


def detect_year_columns(rows: list[list[Word]], page_width: float, *, title_year: Optional[str] = None) -> list[tuple[str, float]]:
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
    # If OCR only caught the prior-year header, synthesise current from title
    if title_year and year_cols:
        years_only = {y for y, _ in year_cols}
        if title_year not in years_only and len(year_cols) == 1:
            prior_y, prior_x = year_cols[0]
            # Place current year column to the left of prior (UK comparative layout)
            delta = max(60.0, page_width * 0.12 if page_width else 60.0)
            year_cols = [(title_year, max(prior_x - delta, page_width * 0.35 if page_width else prior_x - delta)), (prior_y, prior_x)]
            year_cols.sort(key=lambda t: t[1])
    elif title_year and not year_cols:
        # No year tokens — invent two columns in the right half for comparative OCR
        if page_width:
            year_cols = [
                (title_year, page_width * 0.55),
                (str(int(title_year) - 1), page_width * 0.78),
            ]
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
    *,
    scale: int = 1,
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
        is_num = bool(NUMBER_TOKEN_RE.match(tok.replace(" ", ""))) and parse_number_token(tok, scale_hint=scale) is not None
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
            val = parse_number_token(w.text, scale_hint=scale)
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
            val = parse_number_token(w.text, scale_hint=scale)
            if val is None or _is_note_ref(val):
                continue
            values[""] = val
            break

    return label, values, raw_nums


def extract_rows_from_words(
    words: list[Word],
    page_texts: list[str],
    *,
    max_pages: int = 250,
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

        rows = cluster_rows(page_words, y_tol=page_y_tol)
        # Unit markers often live only in the first few table-header rows
        # (OCR may mangle them in plain text). Prefer that context.
        header_extra = " ".join(
            w.text for row in rows[:12] for w in row
        )
        page_scale = detect_scale_prefer_header(text, header_extra=header_extra)

        section_hit = detect_section(text)
        if section_hit:
            active_section = section_hit
            # Sticky: only overwrite scale when a unit is actually declared.
            # Starting a new P&L/BS page must not reset £'000 → 1 just because
            # OCR missed the unit line on that page.
            if page_scale != 1:
                active_scale = page_scale
            if active_section not in stats["sections"]:
                stats["sections"].append(active_section)
        elif page_scale != 1 and active_section:
            active_scale = page_scale

        title_year = year_ended_from_text(text)
        year_cols = detect_year_columns(rows, page_width, title_year=title_year)
        if year_cols:
            year_cols = refine_year_columns(rows, year_cols, page_width)
            active_years = year_cols
        elif active_years and title_year:
            # Keep sticky years but rename left column to title year when obvious
            pass

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

        # Prefer consolidated/group statements; skip company-only BS/P&L pages
        # when the page header clearly says Company (not Group/Consolidated).
        if re.search(r"(?i)\bcompany\s+balance\s+sheet\b", text or "") and not re.search(
            r"(?i)\b(consolidated|group)\s+balance\s+sheet\b", text or ""
        ):
            continue
        if re.search(r"(?i)\bcompany\s+(profit\s*(?:and|&)\s*loss|income\s+statement)\b", text or "") and not re.search(
            r"(?i)\b(consolidated|group)\s+(profit|income)", text or ""
        ):
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
            label, values, raw_nums = _label_and_numbers(row, year_cols, page_width, scale=active_scale)
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
            if _norm(label) in (
                "note",
                "notes",
                "£",
                "£000",
                "£'000",
                "£'000s",
                "£000s",
                "£m",
                "e'000",
                "e000",
                "'000",
                "000s",
            ):
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

    contents_hits: list[int] = printed_pages_to_indices(
        probe_stats.get("contents_printed_pages") or [], n_pages
    )
    # Also scrape contents from the first few probed pages even if keyword-missed
    for early in list(probe_stats.get("probed_pages") or [])[:12]:
        if early >= 15:
            break
        text = _ocr_page_text_only(content, early, dpi_scale=PROBE_DPI_SCALE)
        printed = contents_page_hints(text)
        if printed:
            contents_hits.extend(printed_pages_to_indices(printed, n_pages))
    contents_hits = sorted(set(contents_hits))
    if contents_hits:
        probe_stats["contents_hints"] = contents_hits
        hits = sorted(set(hits + contents_hits))

    candidates = prioritize_ocr_candidates(
        hits,
        n_pages,
        contents_hits=contents_hits,
        neighbour=OCR_NEIGHBOUR,
        max_pages=MAX_FULL_OCR_PAGES,
    )

    # Fallback: denser probe in mid/back if nothing useful found
    if not candidates or (
        n_pages >= 80
        and not contents_hits
        and not any(h >= int(n_pages * 0.3) for h in hits)
    ):
        stats["ocr_probe_fallback"] = True
        mid_start = min(max(12, int(n_pages * 0.35)), n_pages)
        mid_end = min(n_pages, max(mid_start + 1, int(n_pages * 0.85)))
        extra_hits: list[int] = []
        # Stride-2 denser pass in the accounts band
        for i in range(mid_start, mid_end, 2):
            if i in probe_stats.get("probed_pages", []):
                continue
            plain = _ocr_page_text_only(content, i, dpi_scale=PROBE_DPI_SCALE)
            probe_stats.setdefault("probed_pages", []).append(i)
            if page_mentions_financials(plain):
                extra_hits.append(i)
                probe_stats.setdefault("hit_pages", []).append(i)
        hits = sorted(set(hits + extra_hits))
        candidates = prioritize_ocr_candidates(
            hits,
            n_pages,
            contents_hits=contents_hits,
            neighbour=OCR_NEIGHBOUR,
            max_pages=MAX_FULL_OCR_PAGES,
        )
        probe_stats["fallback_hits"] = extra_hits

    if not candidates:
        # Last resort: full-OCR a window in the mid/back accounts zone
        if n_pages >= 80:
            start = int(n_pages * 0.45)
            end = min(n_pages, start + 15)
        else:
            start = min(12, n_pages)
            end = min(n_pages, max(start + 1, 25))
        candidates = list(range(start, end))[:MAX_FULL_OCR_PAGES]
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
    stats["ocr_pages_ocrd"] = len(ocr_pages)
    stats["ocr_hits"] = len(probe_stats.get("hit_pages") or [])
    stats["ocr_probed_count"] = len(probe_stats.get("probed_pages") or [])
    logger.info(
        "OCR probe n_pages=%s probed=%s hits=%s candidates=%s ocrd=%s contents_hints=%s",
        n_pages,
        stats["ocr_probed_count"],
        stats["ocr_hits"],
        len(candidates),
        len(ocr_pages),
        len(contents_hits),
    )
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
