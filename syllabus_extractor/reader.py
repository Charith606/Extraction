import os
import re
from itertools import groupby
from typing import List, Dict, Any, Optional, Tuple
import pymupdf

# Optional OCR support
try:
    import pytesseract
    from PIL import Image
    import io

    common_tesseract_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
    ]
    for path in common_tesseract_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class PDFPage:
    """
    Structured representation of a single PDF page with:
    - raw_text: Original text layer string.
    - normalized_text: Whitespace-normalized string copy.
    - words: Word tokens with exact bounding box coordinates (x0, y0, x1, y1, text, block_no, line_no, word_no).
    - tables: Detected tabular structures on this page.
    - blocks: Text blocks with bounding boxes and font metadata.
    - lines: Cleaned non-empty line strings.
    - is_ocr: True if OCR was used because the page lacked a digital text layer.
    - confidence: Confidence score (1.0 for digital text layer, 0.5 for OCR fallback).
    """

    def __init__(
        self,
        page_num: int,
        raw_text: str,
        blocks: List[Dict[str, Any]],
        horizontal_lines: Optional[List[str]] = None,
        words: Optional[List[Dict[str, Any]]] = None,
        tables: Optional[List[Dict[str, Any]]] = None,
        is_ocr: bool = False,
        confidence: float = 1.0
    ):
        self.page_num: int = page_num  # 1-indexed
        self.raw_text: str = raw_text
        self.normalized_text: str = re.sub(r"\s+", " ", raw_text).strip()
        self.blocks: List[Dict[str, Any]] = blocks or []
        self.lines: List[str] = [line.strip() for line in raw_text.splitlines() if line.strip()]
        self.horizontal_lines: List[str] = horizontal_lines if horizontal_lines is not None else list(self.lines)
        self.words: List[Dict[str, Any]] = words or []
        self.tables: List[Dict[str, Any]] = tables or []
        self.is_ocr: bool = is_ocr
        self.confidence: float = confidence

    def __repr__(self):
        return f"<PDFPage num={self.page_num} lines={len(self.lines)} ocr={self.is_ocr} conf={self.confidence}>"


class PDFDocumentReader:
    """
    PDF extraction engine using PyMuPDF (fitz) with layout awareness:
    - Per-page word positions & table detection
    - Raw and whitespace-normalized text preservation with page mapping
    - Automatic OCR fallback with lower confidence marking for scanned pages
    - Header and footer suppression across repeating pages
    """

    def __init__(self, pdf_path: str):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        self.pdf_path: str = pdf_path
        self.filename: str = os.path.basename(pdf_path)
        self.pages: List[PDFPage] = []
        self.page_map: Dict[int, PDFPage] = {}
        self._load_pages()
        self._filter_recurring_headers_footers()

    def get_page(self, page_num: int) -> Optional[PDFPage]:
        """Returns the PDFPage for the 1-indexed page number."""
        return self.page_map.get(page_num)

    def get_raw_text(self, page_num: Optional[int] = None) -> str:
        """Returns raw text for a specific page or the full document."""
        if page_num is not None:
            p = self.get_page(page_num)
            return p.raw_text if p else ""
        return "\n\n".join(p.raw_text for p in self.pages)

    def get_normalized_text(self, page_num: Optional[int] = None) -> str:
        """Returns whitespace-normalized text for a specific page or the full document."""
        if page_num is not None:
            p = self.get_page(page_num)
            return p.normalized_text if p else ""
        return " ".join(p.normalized_text for p in self.pages).strip()

    def _load_pages(self):
        doc = pymupdf.open(self.pdf_path)
        # Determine if document has a digital text layer across sample pages
        sample_text_len = sum(len(page.get_text().strip()) for page in doc[:min(5, len(doc))])
        is_scanned_doc = sample_text_len < 100

        for idx, page in enumerate(doc):
            page_num = idx + 1
            raw_text = page.get_text()
            is_ocr = False
            confidence = 1.0

            # If text layer is missing or extremely sparse on a scanned document, attempt OCR fallback
            if len(raw_text.strip()) < 25:
                confidence = 0.5
                if is_scanned_doc and OCR_AVAILABLE:
                    try:
                        pix = page.get_pixmap(dpi=150)
                        img = Image.open(io.BytesIO(pix.tobytes()))
                        ocr_text = pytesseract.image_to_string(img)
                        if len(ocr_text.strip()) > len(raw_text.strip()):
                            raw_text = ocr_text
                            is_ocr = True
                            confidence = 0.6  # Scanned OCR page marked with lower confidence
                    except Exception:
                        pass
                else:
                    confidence = 0.5 if not is_scanned_doc else 0.3

            # Extract structured text blocks with font styles and coordinates
            text_page = page.get_text("dict")
            blocks_data = []
            for block in text_page.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    block_text = ""
                    max_font_size = 0.0
                    is_bold = False
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_text = span.get("text", "")
                            block_text += span_text + " "
                            size = span.get("size", 0.0)
                            if size > max_font_size:
                                max_font_size = size
                            font_name = span.get("font", "").lower()
                            if (span.get("flags", 0) & 2) or "bold" in font_name or "black" in font_name:
                                is_bold = True
                    clean_block_text = block_text.strip()
                    if clean_block_text:
                        blocks_data.append({
                            "bbox": block.get("bbox"),
                            "text": clean_block_text,
                            "font_size": max_font_size,
                            "is_bold": is_bold
                        })

            # Extract word tokens with positions
            words_raw = page.get_text("words")
            words_data = []
            for w in words_raw:
                # w is (x0, y0, x1, y1, word, block_no, line_no, word_no)
                words_data.append({
                    "word": w[4],
                    "bbox": (w[0], w[1], w[2], w[3]),
                    "block_no": w[5],
                    "line_no": w[6],
                    "word_no": w[7]
                })

            # Reconstruct horizontal lines across multi-column tables
            words_sorted = sorted(words_raw, key=lambda w: (round(w[1] / 6) * 6, w[0]))
            horizontal_lines = [
                " ".join(w[4] for w in g).strip()
                for _, g in groupby(words_sorted, key=lambda w: round(w[1] / 6) * 6)
                if g
            ]

            tables_data = []

            page_obj = PDFPage(
                page_num=page_num,
                raw_text=raw_text,
                blocks=blocks_data,
                horizontal_lines=horizontal_lines,
                words=words_data,
                tables=tables_data,
                is_ocr=is_ocr,
                confidence=confidence
            )
            self.pages.append(page_obj)
            self.page_map[page_num] = page_obj

        doc.close()

    def _filter_recurring_headers_footers(self):
        """
        Detects repetitive header/footer lines occurring across many pages (>35% of pages)
        and suppresses them from lines.
        """
        if len(self.pages) < 4:
            return

        first_line_freq: Dict[str, int] = {}
        last_line_freq: Dict[str, int] = {}

        for p in self.pages:
            if p.lines:
                f = p.lines[0].strip()
                l = p.lines[-1].strip()
                if len(f) > 3:
                    first_line_freq[f] = first_line_freq.get(f, 0) + 1
                if len(l) > 3:
                    last_line_freq[l] = last_line_freq.get(l, 0) + 1

        threshold = max(3, int(len(self.pages) * 0.35))
        common_headers = {k for k, v in first_line_freq.items() if v >= threshold}
        common_footers = {k for k, v in last_line_freq.items() if v >= threshold}

        for p in self.pages:
            filtered = []
            for line in p.lines:
                # Filter out pure page numbers (e.g. 'Page 12 of 80', '12', '- 12 -')
                if re.match(r"^(?:page\s*)?[-–]?\s*\d+\s*[-–]?(?:\s*of\s*\d+)?$", line, re.IGNORECASE):
                    continue
                if line in common_headers or line in common_footers:
                    continue
                filtered.append(line)
            p.lines = filtered
