import os
import json
import hashlib
import re
from typing import List, Dict, Optional, Tuple, Set, Any
from .reader import PDFDocumentReader, PDFPage
from .models import CourseEntry, Task1Response

_GLOBAL_TASK1_CACHE: Dict[str, Task1Response] = {}


class CourseDiscoveryEngine:
    """
    Deterministic structural course discovery & segmentation engine for Task 1.
    Splits the document into candidate course blocks by looking for the structural signature of a course page:
    - Header row with hours, credits, category or L-T-P-C
    - Units / modules section with detailed topic content
    - Outcomes section (Course Objectives, Course Outcomes, COs)
    - Books section (Textbooks, Reference Books)

    Filters out curriculum scheme tables, table of contents, and indexes by requiring a minimum
    structural signature. Detects course codes by pattern, but treats 'no code' as a valid result.
    """

    # Academic course code pattern (strictly uppercase to avoid false positives on words like 'is35', 'to100')
    COURSE_CODE_REGEX = re.compile(
        r"\b([0-9]{2}[A-Z]{2,5}\d{2,7}[A-Z]?|[A-Z]{2,5}\s*[-–—]?\s*\d{2,7}[A-Z]?|[A-Z]{2,4}-[A-Z]{2,4}-\d{2,6}|[A-Z]\d{2}[A-Z]{2,4}\d{2,6}|[A-Z]{2,4}\d{2}[A-Z]\d{2,4})\b"
    )

    # Exclude standard prefixes that are NOT course codes
    EXCLUDED_CODE_PREFIXES = (
        "ISO", "QS", "PHI", "INTEL", "INDIA", "IEEE", "ISBN", "ISSN", "ANSI",
        "ASTM", "ASME", "DIN", "VOL", "REF", "FIG", "TAB", "PAGE", "HTTP", "WWW",
        "TIMER", "IC", "CONTROLLER", "REG", "ROM", "RAM", "PORT", "PIN",
        "CO", "PO", "PSO", "PEO", "SL", "SNO",
        "HILL", "WILEY", "HALL", "PRESS", "SONS", "MCGRAW", "PEARSON", "OXFORD",
        "CAMBRIDGE", "SPRINGER", "ELSEVIER", "TATA", "PRENTICE", "REPRINT", "EDITION"
    )

    # Unit 1 markers indicating the start of a detailed course syllabus
    FIRST_UNIT_MARKERS = [
        r"\bunit\s*[-–—\s:.]*(?:i|1|one)\b",
        r"\bmodule\s*[-–—\s:.]*(?:i|1|one)\b",
        r"\bchapter\s*[-–—\s:.]*(?:i|1|one)\b"
    ]

    # All unit markers
    ALL_UNIT_MARKERS = [
        r"\bunit\s*[-–—\s:.]*(?:[ivx\d]+|one|two|three|four|five)\b",
        r"\bmodule\s*[-–—\s:.]*(?:[ivx\d]+|one|two|three|four|five)\b",
        r"\bchapter\s*[-–—\s:.]*(?:[ivx\d]+|one|two|three|four|five)\b"
    ]

    # Structural signature markers for course syllabus
    CREDITS_HOURS_MARKERS = [
        r"\bl\s*[:\-–—]?\s*\d+\s*t\s*[:\-–—]?\s*\d+\s*p\s*[:\-–—]?\s*\d+\s*(?:c|credit|credits)\s*[:\-–—]?\s*\d+",
        r"\bl\s*[-–—\s:]+\s*t\s*[-–—\s:]+\s*p\s*[-–—\s:]+\s*c",
        r"\bt\s*[-–—\s:]+\s*p\s*[-–—\s:]+\s*c",
        r"\b(?:lecture\s*hours|periods?|credits?)\s*[:\-–—]?\s*\d+",
        r"\bcategory\s*[:\-–—]?\s*[a-z0-9\(\)]+",
        r"\b\d\s+\d\s+\d\s+\d\b",
        r"\b\d+\+\d+\s+\d+\s+\d+\b",
        r"\b\d+\+\d+\b"
    ]

    OUTCOMES_MARKERS = [
        r"\bcourse\s*objectives?\b",
        r"\bcourse\s*outcomes?\b",
        r"\blearning\s*outcomes?\b",
        r"\bco\s*[-–—]?\s*po\b",
        r"\bmapping\s*with\s*programme\s*outcomes\b",
        r"\bco\d+\s*[:\-–—.]"
    ]

    BOOKS_MARKERS = [
        r"\btext\s*books?\b",
        r"\breference\s*books?\b",
        r"\bprescribed\s*books?\b"
    ]

    NON_COURSE_TERMS = {
        "TABLE OF CONTENTS", "CONTENTS", "SYLLABUS", "INDEX", "CURRICULUM",
        "SCHEME OF INSTRUCTION", "SCHEME OF EXAMINATION", "PROGRAMME OUTCOMES",
        "PROGRAM EDUCATIONAL OBJECTIVES", "PROGRAM SPECIFIC OBJECTIVES",
        "PROGRAM SPECIFIC OUTCOMES", "PROGRAMME SPECIFIC OUTCOMES",
        "MAPPING WITH PROGRAMME OUTCOMES", "MAPPING WITH PROGRAMME OUTCOMES AND PROGRAMME SPECIFIC OUTCOMES",
        "VISION AND MISSION", "VISION", "MISSION", "SEMESTER", "SEMESTERS",
        "CREDITS", "COURSE OBJECTIVES", "COURSE OUTCOMES", "EVALUATION SCHEME",
        "ACADEMIC REGULATIONS", "LIST OF ELECTIVES", "OPEN ELECTIVES",
        "PROFESSIONAL ELECTIVES", "HONOURS DEGREE", "MINORS DEGREE",
        "DEPARTMENT OF COMPUTER SCIENCE", "ANNA UNIVERSITY", "VTU", "JNTU",
        "AICTE", "CHOICE BASED CREDIT SYSTEM", "CBCS", "AUTONOMOUS",
        "REGULATIONS", "CURRICULUM AND SYLLABI", "RULES AND REGULATIONS",
        "DEGREE OF BACHELOR", "MASTER OF ENGINEERING", "BACHELOR OF TECHNOLOGY",
        "TOTAL CREDITS", "CONTINUOUS ASSESSMENT", "END SEMESTER EXAMINATIONS",
        "INSTITUTE OF TECHNOLOGY", "COLLEGE OF ENGINEERING", "DEEMED UNIVERSITY",
        "LIST OF EXPERIMENTS", "SUBJECT TITLE", "COURSE CODE", "COURSE TITLE",
        "EXPERIENTIAL LEARNING", "RESOURCES", "COURSE CONTENT", "COURSE CONTENTS",
        "FOREIGN LANGUAGE", "FOREIGN LANGUAGE^", "AUDIT COURSE",
        "SUGGESTED LAB MANUALS", "SUGGESTED BOOKS", "LAB MANUALS", "TEXT BOOKSS"
    }

    def __init__(self, reader: PDFDocumentReader):
        self.reader = reader
        self.filename = reader.filename
        self.pages = reader.pages

    def run(self, use_cache: bool = True) -> Task1Response:
        """
        Executes structural course discovery and segmentation with persistent caching.
        """
        cache_key = None
        pdf_path = getattr(self.reader, "pdf_path", None)
        if use_cache and pdf_path and os.path.isfile(pdf_path):
            try:
                mtime = os.path.getmtime(pdf_path)
                fsize = os.path.getsize(pdf_path)
                cache_key = f"{os.path.abspath(pdf_path)}_{fsize}_{mtime}"
                if cache_key in _GLOBAL_TASK1_CACHE:
                    return _GLOBAL_TASK1_CACHE[cache_key]

                cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")
                os.makedirs(cache_dir, exist_ok=True)
                hash_id = hashlib.md5(f"{pdf_path}_{fsize}_{mtime}".encode("utf-8")).hexdigest()
                disk_file = os.path.join(cache_dir, f"task1_{hash_id}.json")
                if os.path.exists(disk_file):
                    with open(disk_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    resp = Task1Response(**data)
                    _GLOBAL_TASK1_CACHE[cache_key] = resp
                    return resp
            except Exception:
                pass

        # Step 1: Discover all candidate course blocks
        raw_candidates = self._discover_all_candidate_courses()

        # Step 2: Locate the true detailed syllabus starting page for each candidate
        final_candidates: List[Dict[str, Any]] = []
        candidates_by_code: Dict[str, int] = {}
        candidates_by_title: Dict[str, int] = {}

        for cand in raw_candidates:
            code = cand.get("code", "").strip()
            title = cand.get("title", "").strip()
            source = cand.get("source", "body")
            if not self._is_valid_course_title(title):
                continue
            if code and not self._is_valid_course_code(code):
                continue

            norm_title = re.sub(r"[^A-Z0-9]", "", title.upper())
            norm_code = re.sub(r"[^A-Z0-9]", "", code.upper())
            norm_code_base = norm_code.rstrip("L")

            found_idx = None
            if norm_code and norm_code in candidates_by_code:
                found_idx = candidates_by_code[norm_code]
            elif norm_code_base and norm_code_base in candidates_by_code:
                found_idx = candidates_by_code[norm_code_base]
            elif norm_title in candidates_by_title:
                found_idx = candidates_by_title[norm_title]

            if found_idx is not None:
                existing = final_candidates[found_idx]
                if existing.get("source") != "body" and source == "body":
                    existing["title"] = title
                    existing["source"] = "body"
                    existing["fallback_page"] = cand.get("fallback_page", existing["fallback_page"])
                    if code:
                        existing["code"] = code
                elif not existing.get("code") and code:
                    existing["code"] = code
                if norm_code:
                    candidates_by_code[norm_code] = found_idx
                if norm_code_base:
                    candidates_by_code[norm_code_base] = found_idx
            else:
                new_idx = len(final_candidates)
                final_candidates.append({
                    "code": code,
                    "title": title,
                    "fallback_page": cand.get("fallback_page", 1),
                    "source": source
                })
                if norm_code:
                    candidates_by_code[norm_code] = new_idx
                if norm_code_base:
                    candidates_by_code[norm_code_base] = new_idx
                candidates_by_title[norm_title] = new_idx

        # Pre-evaluate candidates to determine whether this document contains actual detailed course syllabi
        evaluated_candidates = []
        has_body_syllabi = False

        for cand in final_candidates:
            code = cand.get("code", "").strip()
            title = cand.get("title", "").strip()
            fallback = cand.get("fallback_page", 1)
            start_page, score = self._find_detailed_syllabus_page_with_score(code, title, fallback_page=fallback)
            
            target_p = self.reader.get_page(start_page)
            is_toc = target_p and (self._is_toc_or_scheme_page(target_p.raw_text) or self._is_cover_or_prelude_page(start_page, target_p.raw_text))
            
            if score > 0 and not is_toc:
                has_body_syllabi = True

            evaluated_candidates.append({
                "code": code,
                "title": title,
                "fallback": fallback,
                "start_page": start_page,
                "score": score,
                "is_toc": is_toc,
                "source": cand.get("source", "body")
            })

        final_courses: List[CourseEntry] = []
        for item in evaluated_candidates:
            code = item["code"]
            title = item["title"]
            start_page = item["start_page"]
            score = item["score"]
            is_toc = item["is_toc"]

            if has_body_syllabi:
                # If document contains actual syllabi, exclude candidates that failed to match
                # a detailed syllabus page or that point to TOC/curriculum table pages
                if score <= 0 or is_toc:
                    continue
            else:
                if score <= 0:
                    start_page = item["fallback"]

            final_courses.append(CourseEntry(code=code, title=title, page=start_page))

        # Stably sort courses by page, then code, then title
        final_courses.sort(key=lambda x: (x.page, x.code, x.title))

        resp = Task1Response(
            document=self.filename,
            course_count=len(final_courses),
            courses=final_courses
        )
        if cache_key:
            try:
                _GLOBAL_TASK1_CACHE[cache_key] = resp
                cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")
                os.makedirs(cache_dir, exist_ok=True)
                hash_id = hashlib.md5(f"{pdf_path}_{fsize}_{mtime}".encode("utf-8")).hexdigest()
                disk_file = os.path.join(cache_dir, f"task1_{hash_id}.json")
                with open(disk_file, "w", encoding="utf-8") as f:
                    json.dump(resp.model_dump(), f)
            except Exception:
                pass
        return resp

    def _filter_running_headers(self, lines: List[str]) -> List[str]:
        """
        Removes running headers, footers, standalone page numbers, and university titles.
        """
        filtered = []
        for l in lines:
            s = l.strip()
            if not s:
                continue
            if s.isdigit() and len(s) <= 3:
                continue
            if re.match(r"^(B\.C\.A|BCA|B\.TECH|B\.E\.|M\.E\.|M\.TECH)\s*[-–—]\s*", s, re.IGNORECASE):
                continue
            if re.match(r"^Page\s+\d+\s+of\s+\d+", s, re.IGNORECASE):
                continue
            if re.match(r"^Foreign\s*Language\^?$", s, re.IGNORECASE):
                continue
            if any(s.upper().startswith(k) for k in ["MOHAN BABU UNIVERSITY", "LOYOLA COLLEGE", "ANNA UNIVERSITY", "AARUPADAI VEEDU", "PAGE "]):
                continue
            filtered.append(s)
        return filtered

    def _has_course_structural_signature(self, page_text: str) -> bool:
        """
        Evaluates whether a page has the structural signature of a course syllabus block.
        Supports single-page and multi-page syllabus layouts.
        """
        text_lower = page_text.lower()
        has_credits_hours = any(re.search(m, text_lower) for m in self.CREDITS_HOURS_MARKERS)
        has_units = any(re.search(u, text_lower) for u in self.ALL_UNIT_MARKERS)
        has_first_unit = any(re.search(u, text_lower) for u in self.FIRST_UNIT_MARKERS)
        has_outcomes = any(re.search(o, text_lower) for o in self.OUTCOMES_MARKERS)
        has_books = any(re.search(b, text_lower) for b in self.BOOKS_MARKERS)
        has_prereq = bool(re.search(r"\b(?:pre[-–—\s]?requisite|course\s*description)\b", text_lower))
        has_copo_table = bool(re.search(r"\bco[-–—\s]?po(?:\s*[-–—]?\s*pso)?\s*mapping\b", text_lower))
        has_header_label = bool(re.search(r"\bcourse\s*code\b", text_lower) and re.search(r"\bcourse\s*title\b", text_lower))
        has_semester_header = bool(self.SEMESTER_HEADER_REGEX.search(page_text))

        # Multi-page or single-page course start indicators:
        if has_semester_header and (has_units or has_outcomes or has_credits_hours or has_books):
            return True
        if has_header_label and (has_outcomes or has_units or has_prereq or has_credits_hours or has_copo_table):
            return True
        if has_units and (has_credits_hours or has_outcomes or has_books or has_copo_table or has_first_unit):
            return True
        if has_outcomes and (has_credits_hours or has_units or has_copo_table or has_prereq):
            return True
        return False

    def _is_valid_course_code(self, code: str) -> bool:
        c = code.upper().strip()
        if c.startswith(self.EXCLUDED_CODE_PREFIXES):
            return False
        if "@" in code or ".com" in code.lower() or "/" in code or ".pdf" in code.lower():
            return False
        if re.match(r"^[A-Z]+[-–—]?(19\d{2}|20\d{2})$", c):
            return False
        if re.match(r"^(?:CO|PO|PSO)\d*$", c):
            return False
        if re.match(r"^GS\d+$", c):
            return False
        has_digit = any(char.isdigit() for char in c)
        has_alpha = any(char.isalpha() for char in c)
        return has_digit and has_alpha and 4 <= len(c) <= 15

    def _is_toc_or_scheme_page(self, page_text: str) -> bool:
        text_lower = page_text.lower()
        has_toc_kw = any(k in text_lower for k in [
            "scheme of instruction", "curriculum & scheme", "curriculum and scheme",
            "course structure", "table of contents", "list of courses", "list of subjects",
            "category credit detail", "credit requirement for course categories",
            "details of elective courses", "foundation courses (fc)",
            "foundation courses - hss, bs and es courses", "core courses relevant to the programme",
            "details of open elective courses", "curriculum and scheme of instruction",
            "category a", "category b", "category c", "category d",
            "scheduling of courses", "schedulingofcourses"
        ])
        distinct_codes = set()
        for m in self.COURSE_CODE_REGEX.finditer(page_text):
            c = re.sub(r"[^A-Z0-9]", "", m.group(1).upper())
            if len(c) >= 4 and not c.startswith(self.EXCLUDED_CODE_PREFIXES):
                distinct_codes.add(c)
        has_many_codes = len(distinct_codes) >= 6

        has_units = any(re.search(u, text_lower) for u in self.ALL_UNIT_MARKERS)
        has_outcomes = any(re.search(o, text_lower) for o in self.OUTCOMES_MARKERS)
        return (has_toc_kw or has_many_codes) and not has_units and not has_outcomes

    def _is_cover_or_prelude_page(self, page_num: int, page_text: str) -> bool:
        if page_num > 15:
            return False
        text_lower = page_text.lower()
        if any(re.search(u, text_lower) for u in self.ALL_UNIT_MARKERS):
            return False

        cover_keywords = [
            "regulations 20", "rules and regulations", "vision and mission",
            "program educational objectives", "choice based credit system",
            "curriculum and syllabi for", "degrees offered", "academic regulations",
            "institute of technology", "college of engineering"
        ]
        return any(kw in text_lower for kw in cover_keywords)

    # Reference & Book author / publisher / edition patterns to reject
    BOOK_TERMS_REGEX = re.compile(
        r"\b(?:edition|ed\.|pearson|phi|tmh|mcgraw[\s\-]?hill|springer|elsevier|wiley|cengage|oxford|cambridge|press|publishers?|publications?|author|vol\.|volume|reprint|isbn|issn|bhavsar|balagurusamy|tanenbaum|forouzan|silberschatz|sommerville|stallings|korth|navathe|galvin|gagne|muneeswaran|chand|s\.\s*chand|dandamudi|palanisamy|scientech|bansal|laxmi|bhat|charotar|prasanna|deepthi|chandrasekhariah|prism|samantha|horowitz|sahni|anderson|freed|kavi|mahesh|kulkarni)\b",
        re.IGNORECASE
    )

    SEMESTER_HEADER_REGEX = re.compile(
        r"^(?:I|II|III|IV|V|VI|VII|VIII|\d+)\s*(?:YEAR|YR|B\.?TECH|B\.?E\.?)\s*[-–—]?\s*(?:I|II|III|IV|V|VI|VII|VIII|\d+)?\s*(?:SEM|SEMESTER)?\b",
        re.IGNORECASE
    )

    def _is_valid_course_title(self, title: str) -> bool:
        cleaned = title.strip().upper()
        cleaned = cleaned.replace("\ufffd", " - ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned.endswith(".") or cleaned.endswith(",") or cleaned.endswith(";") or cleaned.endswith("&") or cleaned.endswith("+") or cleaned.endswith("-") or cleaned.startswith("&"):
            return False
        if any(cleaned == t or cleaned.startswith(t + " ") or cleaned.endswith(" " + t) for t in ["PROGRAMME", "BRANCH", "PROGRAMME & BRANCH", "PROGRAM & BRANCH", "PROGRAMME &", "PROGRAM &"]):
            return False
        if any(ext in title.lower() for ext in [".pdf", ".docx", ".doc", ".html", "http://", "https://"]):
            return False
        if re.match(r"^(?:ITEM\s*\d+|ANNEXURE|PROCEEDINGS|REPORT\s*ON\b)", cleaned):
            return False
        if re.search(r"\b(?:PSO\d|CO\d|PO\d)\b", cleaned) and not re.search(r"\b(?:ENGINEERING|SCIENCE|MATHEMATICS|PHYSICS|CHEMISTRY|SYSTEM|CIRCUIT|PROGRAMMING|STUDIES|MANAGEMENT|DESIGN|COMMUNICATION)\b", cleaned):
            return False
        if re.match(r"^(?:AND|OR)\s+", cleaned):
            return False
        if re.match(r"^[•\*\-–—:➢▶►✓\s]*(THIS COURSE|THE COURSE|STUDENTS WILL|AT THE END|AFTER COMPLETING|TO PROVIDE|TO INTRODUCE|TO ENABLE|TO DEVELOP|TO EQUIP|IN THIS|LEADING COMPANIES|THIS SUBJECT|THE OBJECTIVE|THE MAIN OBJECTIVE|THE AIM|AIM OF THE COURSE|COURSE DESCRIPTION|PREAMBLE|PREREQUISITES?|COURSE OBJECTIVES?|TO\s+[A-Z]+)\b", cleaned):
            return False
        if len(cleaned.split()) > 10:
            return False
        if not re.search(r"[A-Za-z]{3,}", cleaned) and not re.search(r"[\u0B80-\u0BFF]{3,}", cleaned):
            return False
        if any(k in cleaned for k in ["INSTITUTE OF", "COLLEGE OF", "UNIVERSITY", "DEPARTMENT OF", "FACULTY OF", "AFFILIATED TO"]):
            return False
        if self.BOOK_TERMS_REGEX.search(cleaned):
            return False
        if re.match(r"^\d+[\.\)]\s+", title.strip()) and ("," in title or "-" in title or "–" in title or "—" in title):
            return False
        if re.match(r"^[•\*\.\d\s:\-–—]*(UNIT|MODULE|CHAPTER|PART|SECTION)\s*[-–—:\s]*([IVX\d]+|ONE|TWO|THREE|FOUR|FIVE)\b", cleaned, re.IGNORECASE):
            return False
        if re.match(r"^[•\*\.\d\s:\-–—]*(COURSE OBJECTIVES?|COURSE OUTCOMES?|TEXT\s*BOOKS?|TEXT\s*BOOKSS|REFERENCES?|REFERENCE\s*BOOKS?|PREREQUISITES?|PRE-REQUISITE|SYLLABUS|CO\d+|PO\d+|MAPPING WITH|LIST OF EXPERIMENTS|EXERCISE|SUGGESTED LAB MANUALS|LAB MANUALS|MANUALS)\b", cleaned, re.IGNORECASE):
            return False
        for term in self.NON_COURSE_TERMS:
            if term == cleaned or cleaned.startswith(term + " ") or cleaned.endswith(" " + term):
                return False
        if re.match(r"^(B\.E\.|B\.TECH|M\.E\.|M\.TECH|B\.SC|M\.SC|DIPLOMA|B\.C\.A|BCA)\b", cleaned):
            return False
        if self.SEMESTER_HEADER_REGEX.match(cleaned):
            return False
        if re.match(r"^(?:SEMESTER|YEAR|PART|TERM)\s+([IVX\d]+|ONE|TWO|THREE)$", cleaned):
            return False
        if re.match(r"^(?:T\s*P\s*C|L\s*T\s*P\s*C|\d+\+\d+\s+\d+\s+\d+|\d+\s+\d+\s+\d+)\s*$", cleaned, re.IGNORECASE):
            return False
        return True

    def _clean_title(self, raw_title: str) -> str:
        t = raw_title.strip()
        t = t.replace("\ufffd", " - ")
        t = re.sub(r"\(Common\s+to\s+[^)]+\)", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^[\d]+[\.\)\-–—\s]+", "", t)
        t = re.sub(r"^[•\*\-–—:]+\s*", "", t)
        t = re.sub(r"\s+(?:LIT|T\+P\+PBL|T\+PBL|T\+P|P|T|L|CDP|PW|IPW|---)\s+[\d\-]+(?:\s+[\d\-]+)*(?:\s+(?:HUM|BS|ES(?:\s*\([A-Z\s\-]+\))?|SD|OE|PC|PE|ET|DIC|TCP))*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+(?:HUM|BS|ES(?:\s*\([A-Z\s\-]+\))?|SD|OE|PC|PE|ET|DIC|TCP)\s*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+T\s+[\d\-]+.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+LIT\s+[\d\-]+.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+L\s+[\d\-]+.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+---.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+\d(?:\s+\d){3,4}(?:\s+(?:NIL|[A-Z\s]+))?$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+\d\s+\d\s+\d\s+\d\s*$", "", t)
        t = re.sub(r"\s+\d\s*Credits?$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+L\s*[:\s-]\s*T.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+NIL\s*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+Pre-Requisite.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+Anti-Requisite.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+Co-Requisite.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+(?:Theory\s*Only|Lab\s*Only|Embedded\s*Theory\s*(?:and|&)\s*Lab|Project\s*Only|Online\s*Course)(?:\s+\d+(?:\.\d+)?)*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+\d+\.\d+\s+\d+\.\d+\s*$", "", t)
        t = re.sub(r"\s+(?:T\+P\+PBL|T\+PBL|T\+P|P|T)\s+\d+(?:\.\d+)?\.?$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+\d+\.\s*$", "", t)
        
        t = re.sub(r"\s+(?:BS|BSC|PC|PCC|CS|HS|HSMC|HSS|ES|ESC|PE|PEC|OE|OEC|MC|EEC|CC|EC|FC|SC|VAC|AEC|SEC)\s+\d+(?:\s+\d+)*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+\d+\s+\d+\s+\d+(?:\s+\d+)*\s*$", "", t)
        t = re.sub(r"\s+(?:BS|BSC|PC|PCC|CS|HS|HSMC|HSS|ES|ESC|PE|PEC|OE|OEC|MC|EEC|CC|EC|FC|SC|VAC|AEC|SEC)\s*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+PHYSICS/CHEMISTRY\s*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=\bSCIENCE AND ENGINEERING)\s+CHEMISTRY\b", "", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=\bSMART MATERIALS)\s+PHYSICS\b", "", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=\bPROBABILITY AND STATISTICS)\s+MATHEMATICS\b", "", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=\bRESOURCE MANAGEMENT TECHNIQUE)\s+MATHEMATICS\b", "", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=\bENERGY PHYSICS)\s+PHYSICS\b", "", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=\bSPACE SCIENCE)\s+PHYSICS\b", "", t, flags=re.IGNORECASE)
        t = re.sub(r"(?<=\bFUNDAMENTALS OF NANO SCIENCE)\s+PHYSICS\b", "", t, flags=re.IGNORECASE)

        t = re.sub(r"[:\-–—\s]+$", "", t)
        t = re.sub(r"\s+", " ", t)
        return t.strip()

    def _stitch_multiline_title(self, lines: List[str], start_idx: int, initial_title: str) -> str:
        current_title = initial_title.strip()
        idx = start_idx + 1

        while idx < len(lines) and idx < start_idx + 4:
            next_line = lines[idx].strip()
            if not next_line:
                idx += 1
                continue

            if re.search(r"\b(Programme|Branch|Preamble|Prerequisite|Pre-Requisite|Category|Credits?|UNIT|MODULE|COURSE OBJECTIVES?|COURSE OUTCOMES?|COURSE DESCRIPTION|SYLLABUS|L\s*[:\s-]\s*T)\b", next_line, re.IGNORECASE):
                break
            if self.COURSE_CODE_REGEX.search(next_line):
                break
            if next_line.upper() in self.NON_COURSE_TERMS or any(next_line.upper().startswith(t) for t in ["PROGRAMME", "BRANCH", "SEMESTER", "CATEGORY", "L T P C"]):
                break
            if next_line.startswith("(") and "common" in next_line.lower():
                idx += 1
                continue

            ends_with_connector = bool(re.search(r"\b(AND|OF|FOR|IN|TO|&|WITH|ON|THE|COST|TOTAL|HUMAN|ETHICSAND|SCIENCE)\b", current_title, re.IGNORECASE))
            is_valid_continuation = bool(re.match(r"^[A-Za-z0-9\s&/\-]+$", next_line)) and len(next_line.split()) <= 5

            if ends_with_connector or is_valid_continuation:
                current_title = f"{current_title} {next_line}".strip()
                idx += 1
            else:
                break

        return self._clean_title(current_title)

    def _discover_all_candidate_courses(self) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        # Pass 1: Scan Detailed Syllabus Pages using Structural Signatures & Explicit Headers
        for page in self.pages:
            if self._is_cover_or_prelude_page(page.page_num, page.raw_text):
                continue
            if self._is_toc_or_scheme_page(page.raw_text):
                continue
            if not self._has_course_structural_signature(page.raw_text):
                continue

            cleaned_lines = self._filter_running_headers(page.lines)

            # Check for explicit Course Code / Course Title label layout
            found_header_course = False
            for idx, line in enumerate(cleaned_lines):
                if re.search(r"Course\s*Code", line, re.IGNORECASE):
                    # Check the next lines for course code and title
                    for nxt_idx in range(idx + 1, min(idx + 5, len(cleaned_lines))):
                        nxt_line = cleaned_lines[nxt_idx]
                        m_code = self.COURSE_CODE_REGEX.search(nxt_line)
                        if m_code:
                            code = m_code.group(1).replace(" ", "")
                            if not self._is_valid_course_code(code):
                                continue
                            rem = nxt_line[m_code.end():].strip()
                            title_idx = nxt_idx
                            initial_title = rem
                            if not rem and nxt_idx + 1 < len(cleaned_lines):
                                title_idx = nxt_idx + 1
                                initial_title = cleaned_lines[nxt_idx + 1]
                            
                            full_title = self._stitch_multiline_title(cleaned_lines, title_idx, initial_title)
                            if self._is_valid_course_title(full_title):
                                candidates.append({"code": code, "title": full_title, "fallback_page": page.page_num, "source": "body"})
                                found_header_course = True
                                break
                    if found_header_course:
                        break

            if found_header_course:
                continue

            page_lower = page.raw_text.lower()
            has_first_unit = any(re.search(u, page_lower) for u in self.FIRST_UNIT_MARKERS)
            has_objectives = bool(re.search(r"\bcourse\s*objectives?\b", page_lower))
            has_units = any(re.search(u, page_lower) for u in self.ALL_UNIT_MARKERS)

            # Look for lines starting with / containing a valid course code across the page
            found_code_in_page = False
            for idx, line in enumerate(cleaned_lines):
                if "@" in line or line.startswith("http") or self.BOOK_TERMS_REGEX.search(line):
                    continue
                m_code = self.COURSE_CODE_REGEX.search(line)
                if m_code:
                    code = m_code.group(1).replace(" ", "")
                    if not self._is_valid_course_code(code):
                        continue

                    rem = line[m_code.end():].strip()
                    if rem:
                        title_start_idx = idx
                        initial_title = rem
                    elif idx + 1 < len(cleaned_lines):
                        next_l = cleaned_lines[idx + 1].strip()
                        if re.match(r"^(Subject|Course)\s*(Title|Name|Code\s*&\s*Title)?$", next_l, re.IGNORECASE) and idx + 2 < len(cleaned_lines):
                            title_start_idx = idx + 2
                            initial_title = cleaned_lines[idx + 2]
                        else:
                            title_start_idx = idx + 1
                            initial_title = cleaned_lines[idx + 1]
                    else:
                        continue

                    full_title = self._stitch_multiline_title(cleaned_lines, title_start_idx, initial_title)
                    if self._is_valid_course_title(full_title):
                        candidates.append({"code": code, "title": full_title, "fallback_page": page.page_num, "source": "body"})
                        found_code_in_page = True
            
            # Second priority: Check for Semester header followed by Course Title (e.g., JNTU / R13 / Autonomous pattern)
            found_semester_course = False
            if not found_code_in_page:
                for idx, line in enumerate(cleaned_lines[:15]):
                    if self.SEMESTER_HEADER_REGEX.match(line) or re.match(r"^(?:T\s*P\s*C|L\s*T\s*P\s*C)\s*$", line, re.IGNORECASE):
                        for j in range(idx + 1, min(idx + 6, len(cleaned_lines))):
                            cand_line = cleaned_lines[j].strip()
                            if not cand_line:
                                continue
                            if re.match(r"^(?:T|P|C|L|Credits?|\d+\+\d+|\d+|\d+\s+\d+\s+\d+|--)\s*$", cand_line, re.IGNORECASE):
                                continue
                            if re.match(r"^(?:T\s*P\s*C|L\s*T\s*P\s*C)\s*$", cand_line, re.IGNORECASE):
                                continue
                            if self.BOOK_TERMS_REGEX.search(cand_line) or (re.match(r"^\d+[\.\)]\s+", cand_line) and ("," in cand_line or "-" in cand_line)):
                                continue
                            if re.match(r"^(?:OBJECTIVES?|UNIT|MODULE|CHAPTER|COURSE\s*OBJECTIVES?|COURSE\s*OUTCOMES?|LAB\s*EXPERIMENTS?|EXERCISE)\b", cand_line, re.IGNORECASE):
                                break
                            
                            full_title = self._stitch_multiline_title(cleaned_lines, j, cand_line)
                            if self._is_valid_course_title(full_title):
                                candidates.append({"code": "", "title": full_title, "fallback_page": page.page_num, "source": "body"})
                                found_semester_course = True
                                break
                        if found_semester_course:
                            break

            # Third priority: Only if NO course code or semester course found, scan candidate lines for a valid course title
            if not found_code_in_page and not found_semester_course and (has_first_unit or has_objectives):
                for idx, line in enumerate(cleaned_lines[:5]):
                    if any(re.search(u, line, re.IGNORECASE) for u in self.ALL_UNIT_MARKERS):
                        break
                    if self.BOOK_TERMS_REGEX.search(line) or (re.match(r"^\d+[\.\)]\s+", line) and ("," in line or "-" in line)):
                        continue
                    if len(line.split()) >= 2 and self._is_valid_course_title(line):
                        full_title = self._stitch_multiline_title(cleaned_lines, idx, line)
                        if len(full_title.split()) >= 2 and self._is_valid_course_title(full_title):
                            candidates.append({"code": "", "title": full_title, "fallback_page": page.page_num, "source": "body"})
                            break

        # Pass 2: Scan Curriculum Scheme pages for additional course list discovery
        for page in self.pages:
            page_lower = page.raw_text.lower()
            if any(re.search(u, page_lower) for u in self.ALL_UNIT_MARKERS):
                continue

            has_codes = bool(self.COURSE_CODE_REGEX.search(page.raw_text))
            is_curriculum_page = has_codes or any(k in page_lower for k in [
                "curriculum", "scheme of instruction", "course structure", "semester",
                "elective", "category a", "category b", "category c", "category d",
                "foundation courses", "core courses", "offering dept", "prerequisite",
                "s.no", "subject code", "course code", "fc (bs)", "fc (hss)", " credits"
            ])
            if not is_curriculum_page:
                continue

            lines = page.lines
            i = 0
            while i < len(lines):
                line = lines[i]
                m_code = self.COURSE_CODE_REGEX.search(line)
                if m_code:
                    code = m_code.group(1).replace(" ", "")
                    if not self._is_valid_course_code(code):
                        i += 1
                        continue
                    
                    rem = line[m_code.end():].strip()
                    title_parts = [rem] if rem else []
                    j = i + 1
                    
                    while j < len(lines):
                        l_next = lines[j].strip()
                        if not l_next:
                            j += 1
                            continue
                        if self.COURSE_CODE_REGEX.search(l_next):
                            break
                        if any(l_next.upper().startswith(k) for k in [
                            "FC", "CC", "EC", "PI", "BS", "BSC", "PC", "PCC", "PE", "OE",
                            "MC", "CS", "ES", "ESC", "HS", "HSMC", "HSS", "EEC", "NIL",
                            "3 0", "2 2", "0 0", "1 0", "2 0", "3 1", "0 2", "1 "
                        ]):
                            break
                        if l_next.upper() in ["MECH", "CIVIL", "AUTO", "BIOTECH", "EEE", "ECE", "CSE", "IT", "CHEMISTRY", "PHYSICS", "MATHEMATICS", "MANAGEMENT", "ENGLISH", "MECHANICAL"]:
                            if j + 1 < len(lines) and any(lines[j+1].strip().upper().startswith(k) for k in ["FC", "CC", "EC", "PI", "BS", "PC", "PE", "OE", "NIL", "3 0", "2 2", "0 0"]):
                                break
                        title_parts.append(l_next)
                        j += 1

                    raw_table_title = " ".join(title_parts)
                    full_title = self._clean_title(raw_table_title)
                    if self._is_valid_course_title(full_title):
                        candidates.append({"code": code, "title": full_title, "fallback_page": page.page_num, "source": "table"})
                    i = max(i + 1, j)
                else:
                    i += 1

        return candidates

    def _find_detailed_syllabus_page(self, code: str, title: str, fallback_page: int) -> int:
        page, _ = self._find_detailed_syllabus_page_with_score(code, title, fallback_page)
        return page

    def _find_detailed_syllabus_page_with_score(self, code: str, title: str, fallback_page: int) -> Tuple[int, int]:
        code_base = code.rstrip("L").strip() if code else ""
        code_pattern = re.compile(rf"\b{re.escape(code)}\b", re.IGNORECASE) if code else None
        code_base_pattern = re.compile(rf"\b{re.escape(code_base)}\b", re.IGNORECASE) if (code_base and len(code_base) >= 4) else None
        
        clean_title = title.strip().lower()
        norm_title = re.sub(r"[^a-z0-9]", "", clean_title)
        norm_base = re.sub(r"lab|laboratory|practicals?", "", norm_title)
        is_target_lab = "lab" in norm_title or "laboratory" in clean_title

        # Construct OCR-tolerant pattern (e.g. BCHY101L -> BCHY[1Il|][0Oo][1Il|]L)
        ocr_code_pattern = None
        if code and len(code) >= 4:
            pattern_parts = []
            for char in code:
                if char in "0Oo":
                    pattern_parts.append(r"[0Oo]")
                elif char in "1Il|":
                    pattern_parts.append(r"[1Il|]")
                elif char in "5Ss":
                    pattern_parts.append(r"[5Ss]")
                elif char in "8Bb":
                    pattern_parts.append(r"[8Bb]")
                else:
                    pattern_parts.append(re.escape(char))
            ocr_code_pattern = re.compile(rf"\b{''.join(pattern_parts)}\b", re.IGNORECASE)

        best_page = fallback_page
        best_score = -100

        for page in self.pages:
            if self._is_cover_or_prelude_page(page.page_num, page.raw_text):
                continue
            if self._is_toc_or_scheme_page(page.raw_text):
                continue

            text_lower = page.raw_text.lower()
            norm_page_text = re.sub(r"[^a-z0-9]", "", text_lower)

            top_lines = self._filter_running_headers(page.lines)[:15]
            top_text = " ".join(top_lines).lower()
            norm_top = re.sub(r"[^a-z0-9]", "", top_text)

            if top_lines and top_lines[0].strip().upper() in ["SYLLABUS", "INDEX"]:
                continue

            code_in_page = bool((code_pattern and code_pattern.search(text_lower)) or (code_base_pattern and code_base_pattern.search(text_lower)) or (ocr_code_pattern and ocr_code_pattern.search(text_lower)))
            title_in_page = bool(clean_title and (clean_title in text_lower or (len(norm_title) >= 4 and norm_title in norm_page_text)))
            base_in_page = bool(norm_base and len(norm_base) >= 5 and norm_base in norm_page_text and (is_target_lab == ("lab" in norm_page_text)))

            if not (code_in_page or title_in_page or base_in_page):
                continue

            score = 0

            if code:
                if code_in_page:
                    score += 300
                if (code_pattern and code_pattern.search(top_text)) or (code_base_pattern and code_base_pattern.search(top_text)) or (ocr_code_pattern and ocr_code_pattern.search(top_text)):
                    score += 50
            else:
                if code_in_page:
                    score += 80

            if title_in_page:
                score += 70
            elif base_in_page:
                score += 50
            if clean_title and (clean_title in top_text or (len(norm_title) >= 4 and norm_title in norm_top)):
                score += 30

            has_unit_1_this = any(re.search(u, text_lower) for u in self.FIRST_UNIT_MARKERS)
            next_page = self.reader.get_page(page.page_num + 1)
            has_unit_1_next = False
            if next_page:
                has_unit_1_next = any(re.search(u, next_page.raw_text.lower()) for u in self.FIRST_UNIT_MARKERS)

            if has_unit_1_this:
                score += 80
            elif has_unit_1_next:
                score += 50

            unit_count = sum(1 for u in self.ALL_UNIT_MARKERS if re.search(u, text_lower))
            if unit_count > 0:
                score += 20 + (unit_count * 5)

            detail_count = sum(1 for d in self.CREDITS_HOURS_MARKERS + self.OUTCOMES_MARKERS if re.search(d, text_lower))
            if detail_count > 0:
                score += 40 + (detail_count * 10)

            # Count distinct course codes on page
            distinct_codes = set()
            for l in page.lines:
                for m in self.COURSE_CODE_REGEX.finditer(l):
                    c = re.sub(r"[^A-Z0-9]", "", m.group(1).upper())
                    if len(c) >= 4 and c not in self.EXCLUDED_CODE_PREFIXES:
                        distinct_codes.add(c)

            is_multi_course = len(distinct_codes) >= 3

            # Heavily penalize summary / curriculum table pages
            if is_multi_course and unit_count == 0 and not any(re.search(o, text_lower) for o in self.OUTCOMES_MARKERS):
                score -= 500
            elif is_multi_course:
                score -= 150

            if any(k in text_lower for k in ["scheme of instruction", "curriculum & scheme", "curriculum and scheme", "course structure", "table of contents", "list of courses", "list of subjects", "foundation courses", "category a", "category b"]):
                if unit_count == 0 and not any(re.search(o, text_lower) for o in self.OUTCOMES_MARKERS):
                    score -= 500

            if score > best_score:
                best_score = score
                best_page = page.page_num

        return best_page, best_score
