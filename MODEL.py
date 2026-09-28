import os
import re
import json
from typing import List, Dict, Optional, Tuple, Any
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


class SyllabusModel:
    """
    Two-Pass Curriculum-Anchored Course Discovery & Syllabus Locator Model:
    
    1. Pass 1 (Master Curriculum Discovery):
       Extracts all official course codes & titles from the Curriculum / Scheme of Instruction
       tables in the front matter of the document.
       
    2. Pass 2 (Detailed Syllabus Body Search):
       Scans through body pages to locate the exact page where each course's detailed
       syllabus starts (identifying Units, Modules, Course Outcomes, and Textbooks).
       
    3. Pass 3 (Standalone Fallback):
       Detects courses that appear in the body even if omitted from the front curriculum table.
    """

    COURSE_CODE_REGEX = re.compile(
        r"\b([0-9]{2}[A-Z]{2,5}\d{2,7}[A-Z]?|[A-Z]{2,5}\s*[-–—]?\s*\d{2,7}[A-Z]?|[A-Z]{2,4}-[A-Z]{2,4}-\d{2,6}|[A-Z]\d{2}[A-Z]{2,4}\d{2,6}|[A-Z]{2,4}\d{2}[A-Z]\d{2,4})\b"
    )

    EXCLUDED_PREFIXES = (
        "ISO", "QS", "PHI", "INTEL", "INDIA", "IEEE", "ISBN", "ISSN", "ANSI",
        "ASTM", "ASME", "DIN", "VOL", "REF", "FIG", "TAB", "PAGE", "HTTP", "WWW",
        "TIMER", "IC", "CONTROLLER", "REG", "ROM", "RAM", "PORT", "PIN",
        "CO", "PO", "PSO", "PEO", "SL", "SNO",
        "HILL", "WILEY", "HALL", "PRESS", "SONS", "MCGRAW", "PEARSON", "OXFORD",
        "CAMBRIDGE", "SPRINGER", "ELSEVIER", "TATA", "PRENTICE", "REPRINT", "EDITION"
    )

    SYLLABUS_MARKERS = [
        r"\bunit\s*[-–—\s:.]*(?:[ivx\d]+|one|two|three)\b",
        r"\bmodule\s*[-–—\s:.]*(?:[ivx\d]+|one|two|three)\b",
        r"\bcourse\s*objectives?\b",
        r"\bcourse\s*outcomes?\b",
        r"\blearning\s*outcomes?\b",
        r"\btext\s*books?\b",
        r"\breference\s*books?\b",
        r"\bl\s*[:\-–—]?\s*\d+\s*t\s*[:\-–—]?\s*\d+\s*p\s*[:\-–—]?\s*\d+",
        r"\blecture\s*hours\b",
        r"\bcredits\b",
        r"\bpre[-–—\s]?requisite\b"
    ]

    TOC_MARKERS = [
        r"scheme\s+of\s+instruction",
        r"curriculum\s+&\s+scheme",
        r"curriculum\s+and\s+scheme",
        r"course\s+structure",
        r"table\s+of\s+contents",
        r"list\s+of\s+subjects",
        r"list\s+of\s+courses",
        r"semester\s+curriculum"
    ]

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.file_type = os.path.splitext(file_path)[1].lower()
        self.pages: List[Dict[str, Any]] = []
        self.courses_catalog: List[Dict[str, Any]] = []
        self._load_document()
        self._run_two_pass_indexing()

    def _load_document(self):
        """Loads and extracts text per page."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: '{self.file_path}'")

        if self.file_type == ".pdf":
            self._load_pdf()
        elif self.file_type in [".pptx", ".ppt"]:
            self._load_pptx()
        else:
            raise ValueError(f"Unsupported format: {self.file_type}")

    def _load_pdf(self):
        doc = pymupdf.open(self.file_path)
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            raw_text = page.get_text()

            if len(raw_text.strip()) < 40 and OCR_AVAILABLE:
                try:
                    pix = page.get_pixmap(dpi=150)
                    img = Image.open(io.BytesIO(pix.tobytes()))
                    ocr_text = pytesseract.image_to_string(img)
                    if len(ocr_text.strip()) > len(raw_text.strip()):
                        raw_text = ocr_text
                except Exception:
                    pass

            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            self.pages.append({
                "number": page_num,
                "text": raw_text,
                "lines": lines
            })
        doc.close()

    def _load_pptx(self):
        from pptx import Presentation
        prs = Presentation(self.file_path)
        for slide_idx, slide in enumerate(prs.slides):
            slide_num = slide_idx + 1
            slide_text_blocks = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        if paragraph.text.strip():
                            slide_text_blocks.append(paragraph.text.strip())

            full_text = "\n".join(slide_text_blocks)
            self.pages.append({
                "number": slide_num,
                "text": full_text,
                "lines": slide_text_blocks
            })

    def _run_two_pass_indexing(self):
        """
        Builds the course index:
        Pass 1: Discover all official course codes & titles from Curriculum tables.
        Pass 2: Locate each course's detailed syllabus page in the body.
        Pass 3: Add any standalone body courses.
        """
        master_courses: Dict[str, Dict[str, Any]] = {}

        # -------------------------------------------------------------
        # PASS 1: Scan Front Matter Curriculum / Scheme Tables (Pages 1-25)
        # -------------------------------------------------------------
        for p in self.pages[:25]:
            p_text = p["text"].lower()
            is_toc = any(re.search(tm, p_text) for tm in self.TOC_MARKERS)
            has_units = any(re.search(u, p_text) for u in self.SYLLABUS_MARKERS[:2])

            if is_toc and not has_units:
                for line in p["lines"]:
                    m_code = self.COURSE_CODE_REGEX.search(line)
                    if m_code:
                        code = m_code.group(1).upper()
                        if code.startswith(self.EXCLUDED_PREFIXES):
                            continue
                        
                        # Extract title after code
                        parts = re.split(rf"\b{re.escape(code)}\b", line, flags=re.IGNORECASE)
                        title = ""
                        if len(parts) > 1:
                            rem = parts[1].strip()
                            # Strip trailing L T P C numbers
                            rem = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", rem).strip()
                            rem = re.sub(r"^\d+[\.\)]\s*", "", rem).strip()
                            rem = re.sub(r"^[:\-–—\s]+", "", rem).strip()
                            if len(rem) >= 3 and not rem.isdigit():
                                title = rem

                        norm_code = re.sub(r"[^A-Z0-9]", "", code)
                        if norm_code and norm_code not in master_courses:
                            master_courses[norm_code] = {
                                "code": code,
                                "title": title,
                                "curriculum_page": p["number"],
                                "syllabus_page": None,
                                "source": "curriculum_table"
                            }

        # -------------------------------------------------------------
        # PASS 2: Locate Detailed Syllabus Starting Page for each Code
        # -------------------------------------------------------------
        for norm_code, item in master_courses.items():
            code = item["code"]
            for p in self.pages:
                p_text_norm = re.sub(r"[^A-Z0-9]", "", p["text"].upper())
                if norm_code in p_text_norm:
                    p_lower = p["text"].lower()
                    is_syllabus = any(re.search(sm, p_lower) for sm in self.SYLLABUS_MARKERS)
                    is_toc = any(re.search(tm, p_lower) for tm in self.TOC_MARKERS)

                    if is_syllabus and not is_toc:
                        item["syllabus_page"] = p["number"]
                        # Refine title if missing or numeric
                        if not item["title"] or item["title"].isdigit() or len(item["title"]) <= 2:
                            extracted_title = ""
                            for idx, l in enumerate(p["lines"][:10]):
                                if norm_code in re.sub(r"[^A-Z0-9]", "", l.upper()):
                                    parts = re.split(rf"\b{re.escape(code)}\b", l, flags=re.IGNORECASE)
                                    if len(parts) > 1:
                                        cand = parts[1].strip()
                                        cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                                        cand = re.sub(r"^[:\-–—\s]+", "", cand).strip()
                                        if len(cand) >= 3 and not cand.isdigit():
                                            extracted_title = cand
                                            break
                                    if idx + 1 < len(p["lines"]):
                                        cand = p["lines"][idx + 1].strip()
                                        cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                                        if len(cand) >= 3 and not cand.isdigit() and not any(k in cand.upper() for k in ["CATEGORY", "PRE-REQUISITE", "L T P C", "SEMESTER", "SYLLABUS"]):
                                            extracted_title = cand
                                            break
                            if extracted_title:
                                item["title"] = extracted_title
                        break

        # -------------------------------------------------------------
        # PASS 3: Detect Standalone Body Courses
        # -------------------------------------------------------------
        for p in self.pages:
            p_lower = p["text"].lower()
            is_toc = any(re.search(tm, p_lower) for tm in self.TOC_MARKERS)
            if is_toc:
                continue

            has_markers = any(re.search(sm, p_lower) for sm in self.SYLLABUS_MARKERS)
            if has_markers:
                for idx, l in enumerate(p["lines"][:8]):
                    m_code = self.COURSE_CODE_REGEX.search(l)
                    if m_code:
                        code = m_code.group(1).upper()
                        if code.startswith(self.EXCLUDED_PREFIXES):
                            continue
                        norm_code = re.sub(r"[^A-Z0-9]", "", code)
                        if norm_code not in master_courses:
                            title = ""
                            parts = re.split(rf"\b{re.escape(code)}\b", l, flags=re.IGNORECASE)
                            if len(parts) > 1:
                                cand = parts[1].strip()
                                cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                                cand = re.sub(r"^[:\-–—\s]+", "", cand).strip()
                                if len(cand) >= 3 and not cand.isdigit():
                                    title = cand

                            if not title and idx + 1 < len(p["lines"]):
                                cand = p["lines"][idx + 1].strip()
                                cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                                if len(cand) >= 3 and not cand.isdigit() and not any(k in cand.upper() for k in ["CATEGORY", "PRE-REQUISITE", "L T P C", "SEMESTER", "SYLLABUS"]):
                                    title = cand

                            master_courses[norm_code] = {
                                "code": code,
                                "title": title,
                                "curriculum_page": None,
                                "syllabus_page": p["number"],
                                "source": "body_syllabus"
                            }

        # Build final catalog list sorted by syllabus page
        catalog = []
        for norm_code, item in master_courses.items():
            page_num = item["syllabus_page"] or item["curriculum_page"] or 1
            catalog.append({
                "code": item["code"],
                "title": item["title"] or item["code"],
                "page": page_num,
                "is_detailed_syllabus": item["syllabus_page"] is not None
            })

        catalog.sort(key=lambda x: (x["page"], x["code"]))
        self.courses_catalog = catalog

    def list_all_courses(self) -> List[Dict[str, Any]]:
        """Returns all verified courses in the document."""
        return self.courses_catalog

    def find_subject_page(self, subject_name: str, subject_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fast direct course locator utilizing the two-pass indexed catalog.
        """
        norm_code = re.sub(r"[^A-Z0-9]", "", subject_code.upper()) if subject_code else ""
        clean_name = subject_name.strip().upper() if subject_name else ""

        # 1. Exact Course Code Match
        if norm_code:
            for c in self.courses_catalog:
                if re.sub(r"[^A-Z0-9]", "", c["code"].upper()) == norm_code:
                    return {
                        "course_code": c["code"],
                        "course_title": c["title"],
                        "page_number": c["page"],
                        "unit_type": "Page",
                        "status": "Found in Master Index"
                    }

        # 2. Exact Title Match
        if clean_name:
            for c in self.courses_catalog:
                if clean_name in c["title"].upper() or c["title"].upper() in clean_name:
                    return {
                        "course_code": c["code"],
                        "course_title": c["title"],
                        "page_number": c["page"],
                        "unit_type": "Page",
                        "status": "Found by Title Match"
                    }

        return None


if __name__ == "__main__":
    import sys
    print("=" * 65)
    print("      TWO-PASS CURRICULUM-ANCHORED COURSE DISCOVERY MODEL      ")
    print("=" * 65)

    file_path = input("Enter path to Syllabus PDF (e.g. VIT_SYLLABUS.pdf): ").strip().strip('"').strip("'")
    if not file_path or not os.path.exists(file_path):
        print("Error: File not found.")
        sys.exit(1)

    print(f"\n[+] Indexing document via Two-Pass Curriculum Engine: {file_path} ...")
    model = SyllabusModel(file_path)
    all_courses = model.list_all_courses()

    print(f"[✓] Discovered {len(all_courses)} Total Courses!")
    print("\n--- Discovered Courses Summary ---")
    for idx, c in enumerate(all_courses[:15], 1):
        print(f"  {idx:2d}. [{c['code']}] {c['title']} -> Page {c['page']}")
    if len(all_courses) > 15:
        print(f"  ... and {len(all_courses) - 15} more courses.")

    while True:
        print("\n" + "-" * 65)
        query = input("Search by Course Code or Subject Name (or 'q' to quit): ").strip()
        if query.lower() == 'q':
            break
        if not query:
            continue

        res = model.find_subject_page(subject_name=query, subject_code=query)
        if res:
            print("\n🎯 Exact Subject Syllabus Found!")
            print(f"  • Course Code  : {res['course_code']}")
            print(f"  • Course Title : {res['course_title']}")
            print(f"  • Syllabus Page: Page {res['page_number']}")
            print(f"  • Status       : {res['status']}")
        else:
            print(f"❌ Could not find course '{query}'.")
