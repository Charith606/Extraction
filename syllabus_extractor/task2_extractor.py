import re
from typing import List, Dict, Optional, Tuple, Any, Union
from .reader import PDFDocumentReader, PDFPage
from .models import (
    CourseMeta, TopicEntry, UnitEntry, CourseOutcome,
    ProgrammeOutcome, COPOMappingEntry, BookEntry, Task1Response, Task2Response
)
from .task2_bloom import normalize_printed_bloom, infer_bloom_from_text
from .task1_discovery import CourseDiscoveryEngine
from .llm_engine import LLMEngine
from .llm_helper import LLMLineRangeBoundaryHelper
from .verification import VerificationLayer


class CourseDetailExtractor:
    """
    Deterministic syllabus extractor for Task 2 with verification and LLM boundary assistance.
    
    1. Locates candidate course block across pages with sub-millisecond index lookup.
    2. Resolves section line ranges via cached LLM boundary helper or robust deterministic segmenter.
    3. Parses units, hours, topics, COs, POs, CO-PO matrix, and books with university-agnostic rules.
    4. Passes results through VerificationLayer (grounding checks, matrix consistency, 'nothing lost' accounting).
    5. Guarantees deterministic, stably sorted output matching exact Task 2 specification.
    """

    UNIT_HEADER_REGEX = re.compile(
        r"^(?:UNIT|MODULE|CHAPTER|PART)\s*[-–—:\s]*([IVX\d]+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\b\s*[-–—:.]*\s*(.*)$",
        re.IGNORECASE
    )

    STANDALONE_ROMAN_REGEX = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*$", re.IGNORECASE)

    ROMAN_MAP = {
        "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
        "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10
    }

    CO_REGEX = re.compile(r"^(CO\s*[-–—:\._]?\s*0*(\d+))\s*[-–—:\._]*\s*(.*)$", re.IGNORECASE)
    PO_REGEX = re.compile(r"^(PO\s*[-–—:\._]?\s*0*(\d+))\s*[-–—:\._]*\s*(.*)$", re.IGNORECASE)
    PSO_REGEX = re.compile(r"^(PSO\s*[-–—:\._]?\s*0*(\d+))\s*[-–—:\._]*\s*(.*)$", re.IGNORECASE)

    def __init__(self, reader: PDFDocumentReader, llm_engine: Optional[LLMEngine] = None, discovery_resp: Optional[Task1Response] = None):
        self.reader = reader
        self.pages = reader.pages
        self.filename = reader.filename
        self.cached_pos: Optional[List[ProgrammeOutcome]] = None
        self._cached_discovery: Optional[Task1Response] = discovery_resp
        self.llm_engine = llm_engine or LLMEngine()
        self.boundary_helper = LLMLineRangeBoundaryHelper(llm_engine=self.llm_engine)

    def run(self, target_course_code: str) -> Task2Response:
        code_clean = target_course_code.strip().upper()
        norm_target_code = re.sub(r"[^A-Z0-9]", "", code_clean)
        
        # 1. Authoritative discovery to resolve exact body syllabus start page
        if self._cached_discovery is None:
            discovery = CourseDiscoveryEngine(self.reader)
            self._cached_discovery = discovery.run()
        t1_resp = self._cached_discovery
        
        target_entry = None
        target_idx = None

        for idx, c in enumerate(t1_resp.courses):
            norm_c_code = re.sub(r"[^A-Z0-9]", "", c.code.upper())
            if norm_c_code and norm_target_code and (norm_c_code == norm_target_code or norm_target_code in norm_c_code):
                target_entry = c
                target_idx = idx
                break

        if not target_entry:
            for idx, c in enumerate(t1_resp.courses):
                norm_c_title = re.sub(r"[^A-Z0-9]", "", c.title.upper())
                if (code_clean and code_clean in c.title.upper()) or (norm_target_code and norm_target_code in norm_c_title):
                    target_entry = c
                    target_idx = idx
                    break

        if not target_entry and t1_resp.courses:
            # Fallback to first discovered course if target was empty or generic
            if not target_course_code or target_course_code.upper() in ["N/A", "NONE", "ALL", "DEFAULT"]:
                target_entry = t1_resp.courses[0]
                target_idx = 0

        if not target_entry:
            return Task2Response(
                course=CourseMeta(code=target_course_code, title="", pages=[]),
                not_extracted=["course", "units", "course_outcomes", "programme_outcomes", "co_po_matrix", "books"]
            )

        start_page = target_entry.page
        next_course_page = None
        if target_idx is not None and target_idx + 1 < len(t1_resp.courses):
            next_course_page = t1_resp.courses[target_idx + 1].page

        # Determine course pages starting from the true syllabus start page
        course_pages_nums = self._determine_course_pages(start_page, next_course_page, target_entry.code)
        course_pages = [p for p in self.pages if p.page_num in course_pages_nums]
        block_source_text = "\n".join(p.raw_text for p in course_pages)
        document_source_text = self.reader.get_raw_text()

        # Combine block lines with start and end boundaries
        next_code = t1_resp.courses[target_idx + 1].code if (target_idx is not None and target_idx + 1 < len(t1_resp.courses)) else ""
        block_lines = []
        for p in course_pages:
            p_lines = [l.strip() for l in p.lines if l.strip()]
            if p.page_num == start_page and target_entry.code:
                for idx, l in enumerate(p_lines):
                    if target_entry.code.upper() in l.upper():
                        p_lines = p_lines[idx:]
                        break
            if next_course_page and p.page_num == next_course_page and next_code:
                for idx, l in enumerate(p_lines):
                    if next_code.upper() in l.upper():
                        p_lines = p_lines[:idx]
                        break
            block_lines.extend(p_lines)

        # 2. Extract section line ranges with boundary helper
        section_ranges = self.boundary_helper.identify_section_ranges(block_lines)

        # 3. Extract Course Metadata
        meta = self._extract_course_metadata(target_entry.code, target_entry.title, course_pages_nums, course_pages)

        # 4. Extract Units & Topics
        units = self._extract_units_and_topics(course_pages, block_lines, section_ranges.get("units"))

        # 5. Extract Course Outcomes
        course_outcomes = self._extract_course_outcomes(course_pages, block_lines, section_ranges.get("course_outcomes"))

        # 6. Extract Programme Outcomes from prelude
        programme_outcomes = self._extract_programme_outcomes(course_pages)

        # 7. Extract CO-PO Matrix
        co_po_matrix = self._extract_co_po_matrix(course_pages, block_lines, section_ranges.get("co_po_matrix"))

        # 8. Extract Books
        books = self._extract_books(course_pages, block_lines, section_ranges.get("books"), section_ranges.get("textbooks"), section_ranges.get("references"))

        # 9. Audit missing sections
        not_extracted = []
        if not units:
            not_extracted.append("units")
        if not course_outcomes:
            not_extracted.append("course_outcomes")
        if not programme_outcomes:
            not_extracted.append("programme_outcomes")
        if not co_po_matrix:
            not_extracted.append("co_po_matrix")
        if not books:
            not_extracted.append("books")

        raw_response = Task2Response(
            course=meta,
            units=units,
            course_outcomes=course_outcomes,
            programme_outcomes=programme_outcomes,
            co_po_matrix=co_po_matrix,
            books=books,
            not_extracted=not_extracted
        )

        # 10. Pass through Verification Layer
        verified_response = VerificationLayer.verify(
            response=raw_response,
            block_source_text=block_source_text,
            document_source_text=document_source_text
        )

        return verified_response

    def _find_course_fast(self, code_clean: str, norm_target_code: str) -> Optional[Tuple[str, str, int, Optional[int]]]:
        """Fast O(N_pages) scanner to locate course header page, prioritizing true detailed syllabus pages over curriculum tables."""
        if not norm_target_code or len(norm_target_code) < 3:
            return None

        candidates = []

        for p in self.pages:
            p_text = p.raw_text
            p_text_norm = re.sub(r"[^A-Z0-9]", "", p_text.upper())
            if norm_target_code not in p_text_norm:
                continue

            lines = [l.strip() for l in p.lines if l.strip()]
            top_lines = lines[:15]
            top_text = " ".join(top_lines).lower()
            norm_top = re.sub(r"[^A-Z0-9]", "", top_text.upper())

            # Check if code appears in top header
            code_in_top = norm_target_code in norm_top
            if not code_in_top:
                for hl in p.horizontal_lines[:10]:
                    if norm_target_code in re.sub(r"[^A-Z0-9]", "", hl.upper()):
                        code_in_top = True
                        break

            # Count distinct course codes on page to identify multi-course curriculum tables
            distinct_codes = set()
            for l in lines:
                for m in CourseDiscoveryEngine.COURSE_CODE_REGEX.finditer(l):
                    c = re.sub(r"[^A-Z0-9]", "", m.group(1).upper())
                    if len(c) >= 4 and c not in CourseDiscoveryEngine.EXCLUDED_CODE_PREFIXES:
                        distinct_codes.add(c)

            is_multi_course_table = len(distinct_codes) >= 3

            p_lower = p_text.lower()
            has_units = any(re.search(u, p_lower) for u in [
                r"\bunit\s*[-–—:\s]*(?:i|1|one|[ivx\d]+)\b",
                r"\bmodule\s*[-–—:\s]*(?:i|1|one|[ivx\d]+)\b",
                r"\bchapter\s*[-–—:\s]*(?:i|1|one|[ivx\d]+)\b"
            ])
            has_outcomes = any(re.search(o, p_lower) for o in [
                r"\bcourse\s*objectives?\b",
                r"\bcourse\s*outcomes?\b",
                r"\blearning\s*outcomes?\b",
                r"\bco\d+\b",
                r"\bexpected\s*course\s*outcomes?\b"
            ])
            has_books = any(re.search(b, p_lower) for b in [
                r"\btext\s*books?\b",
                r"\breference\s*books?\b",
                r"\btext\s*book\(s\)"
            ])
            has_ltpc = any(re.search(m, p_lower) for m in [
                r"\bl\s*[:\-–—]?\s*\d+\s*t\s*[:\-–—]?\s*\d+\s*p\s*[:\-–—]?\s*\d+",
                r"\blecture\s*hours\b",
                r"\bcredits\b",
                r"\bpre[-–—\s]?requisite\b"
            ])

            score = 0
            if code_in_top:
                score += 50
            if has_units:
                score += 70
            if has_outcomes:
                score += 70
            if has_books:
                score += 30
            if has_ltpc:
                score += 20

            # Heavily penalize curriculum tables / index lists
            if is_multi_course_table and not (has_units or has_outcomes):
                score -= 250
            elif is_multi_course_table:
                score -= 100

            if any(k in p_lower for k in ["scheme of instruction", "curriculum & scheme", "course structure", "table of contents", "list of courses", "list of subjects"]):
                if not (has_units or has_outcomes):
                    score -= 250

            # Title extraction
            found_title = ""
            for idx, l in enumerate(lines[:15]):
                if norm_target_code in re.sub(r"[^A-Z0-9]", "", l.upper()):
                    parts = re.split(rf"\b{re.escape(code_clean)}\b", l, flags=re.IGNORECASE)
                    if len(parts) > 1:
                        cand = parts[1].strip()
                        cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                        cand = re.sub(r"^[:\-–—\s]+", "", cand).strip()
                        if len(cand) >= 3 and not cand.isdigit():
                            found_title = cand
                            break
                    if idx + 1 < len(lines):
                        cand = lines[idx + 1].strip()
                        cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                        if len(cand) >= 3 and not cand.isdigit() and not any(k in cand.upper() for k in ["CATEGORY", "PRE-REQUISITE", "L T P C", "SEMESTER", "SYLLABUS"]):
                            found_title = cand
                            break

            if not found_title:
                for hl in p.horizontal_lines[:10]:
                    if norm_target_code in re.sub(r"[^A-Z0-9]", "", hl.upper()):
                        parts = re.split(rf"\b{re.escape(code_clean)}\b", hl, flags=re.IGNORECASE)
                        if len(parts) > 1:
                            cand = parts[1].strip()
                            cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                            cand = re.sub(r"^[:\-–—\s]+", "", cand).strip()
                            if len(cand) >= 3 and not cand.isdigit():
                                found_title = cand
                                break

            candidates.append({
                "page_num": p.page_num,
                "score": score,
                "title": found_title
            })

        if not candidates:
            return None

        # Sort candidate pages by score descending
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]

        # Prioritize positive score candidates
        pos_candidates = [c for c in candidates if c["score"] > 0]
        if pos_candidates:
            best = pos_candidates[0]

        found_page_num = best["page_num"]
        found_title = re.sub(r"\s+\d+\s+\d+\s+\d+(\s+\d+)?\s*$", "", best["title"]).strip()

        # Find next course start page
        next_course_page = None
        for p in self.pages[found_page_num:]:
            top_lines = p.lines[:6]
            found_diff = False
            for l in top_lines:
                m = CourseDiscoveryEngine.COURSE_CODE_REGEX.search(l)
                if m:
                    cand_code = re.sub(r"[^A-Z0-9]", "", m.group(1).upper())
                    if cand_code != norm_target_code and len(cand_code) >= 4 and cand_code not in CourseDiscoveryEngine.EXCLUDED_CODE_PREFIXES:
                        found_diff = True
                        break
            if found_diff:
                next_course_page = p.page_num
                break

        return (code_clean, found_title, found_page_num, next_course_page)

    def _determine_course_pages(self, start_page: int, next_start_page: Optional[int], code: str) -> List[int]:
        if next_start_page and next_start_page >= start_page:
            if next_start_page > start_page:
                p_next = self.reader.get_page(next_start_page)
                is_at_top = False
                if p_next:
                    for l in p_next.lines[:3]:
                        if CourseDiscoveryEngine.COURSE_CODE_REGEX.search(l) or CourseDiscoveryEngine.SEMESTER_HEADER_REGEX.match(l):
                            is_at_top = True
                            break
                max_p = next_start_page if not is_at_top else next_start_page - 1
            else:
                max_p = start_page
        else:
            max_p = min(len(self.pages), start_page + 6)

        max_p = max(start_page, min(max_p, start_page + 6, len(self.pages)))
        pages = list(range(start_page, max_p + 1))
        return pages

    def _extract_course_metadata(self, code: str, title: str, page_nums: List[int], pages: List[PDFPage]) -> CourseMeta:
        clean_title = re.sub(r"\s+\d+\s+\d+\s+\d+(\s+\d+)?\s*$", "", title).strip()
        meta = CourseMeta(code=code, title=clean_title, pages=page_nums)
        if not pages:
            return meta

        full_text = "\n".join(p.raw_text for p in pages[:2])

        # Locate the course starting offset in pages[0]
        start_line_idx = 0
        if code:
            for idx, l in enumerate(pages[0].lines):
                if code.upper() in l.upper():
                    start_line_idx = idx
                    break
        
        start_hl_idx = 0
        if code:
            for idx, hl in enumerate(pages[0].horizontal_lines):
                if code.upper() in hl.upper():
                    start_hl_idx = idx
                    break

        scan_lines = pages[0].lines[start_line_idx : start_line_idx + 35]
        if len(pages) > 1 and start_line_idx + 20 >= len(pages[0].lines):
            scan_lines += pages[1].lines[:25]

        scan_hl = pages[0].horizontal_lines[start_hl_idx : start_hl_idx + 20]
        if len(pages) > 1 and start_hl_idx + 10 >= len(pages[0].horizontal_lines):
            scan_hl += pages[1].horizontal_lines[:15]

        # Title refinement if empty or needs cleaning
        if not meta.title or meta.title == code:
            for hl in scan_hl[:10]:
                if code in hl.upper():
                    parts = re.split(rf"\b{re.escape(code)}\b", hl, flags=re.IGNORECASE)
                    if len(parts) > 1:
                        cand = parts[1].strip()
                        cand = re.sub(r"\b\d+\s+\d+\s+\d+(\s+\d+)?\b.*", "", cand).strip()
                        cand = re.sub(r"^[:\-–—\s]+", "", cand).strip()
                        if cand and len(cand) >= 3:
                            meta.title = cand
                            break

        VALID_CATEGORY_CODES = {
            "BS", "BSC", "PC", "PCC", "CS", "HS", "HSMC", "HSS", "ES", "ESC", "PE", "PEC",
            "OE", "OEC", "MC", "EEC", "CC", "EC", "FC", "SC", "VAC", "AEC", "SEC", "AC", "PROJ", "INT"
        }
        INVALID_CATEGORIES = {
            "PERIODS", "PERIOD", "HOURS", "HOUR", "CONTACT HOURS", "CREDITS", "CREDIT",
            "L", "T", "P", "C", "CIE", "SEE", "TOTAL", "SEMESTER", "SEM", "SL.NO", "S.NO",
            "COURSE CODE", "COURSE TITLE", "PREAMBLE", "PREREQUISITE", "PRE-REQUISITE",
            "THEORY", "PRACTICALS", "PRACTICAL", "LAB", "LABORATORY", "PROGRAMME", "BRANCH",
            "COURSE", "TITLE", "CODE", "CONTINUOUS", "ASSESSMENT", "EXAMINATIONS"
        }

        # 1. Look for tabular Category + L-T-P-C in horizontal lines (e.g., "2 PC 3 0 0 3" or "PC 3 0 0 3")
        for hl in scan_hl:
            m_cat_ltpc = re.search(r"\b([A-Z]{2,4})\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\b", hl)
            if m_cat_ltpc:
                cand_cat = m_cat_ltpc.group(1).upper()
                if cand_cat in VALID_CATEGORY_CODES and cand_cat not in INVALID_CATEGORIES:
                    if not meta.category:
                        meta.category = cand_cat
                    if meta.credits is None:
                        meta.lecture = int(m_cat_ltpc.group(2))
                        meta.tutorial = int(m_cat_ltpc.group(3))
                        meta.practical = int(m_cat_ltpc.group(4))
                        meta.credits = int(m_cat_ltpc.group(5))
                    break

        # 2. Category extraction from explicit label or text
        if not meta.category:
            m_cat = re.search(r"\bCategory\s*[:\-–—]?\s*([A-Za-z0-9\(\)\s–-]+)", "\n".join(scan_lines), re.IGNORECASE)
            if not m_cat:
                m_cat = re.search(r"\bCategory\s*[:\-–—]?\s*([A-Za-z0-9\(\)\s–-]+)", full_text, re.IGNORECASE)
            if m_cat:
                cat_val = m_cat.group(1).split("\n")[0].strip()
                cat_val = re.sub(r"\b(L|T|P|Credit|Credits|Periods|Hours|Contact\s*Hours|PREAMBLE|Semester|Sem)\b.*", "", cat_val, flags=re.IGNORECASE).strip()
                cat_val = re.sub(r"[:\-–—\s]+$", "", cat_val).strip()
                if cat_val and cat_val.upper() not in INVALID_CATEGORIES and len(cat_val) <= 25:
                    meta.category = cat_val

        if not meta.category:
            for idx, l in enumerate(scan_lines):
                if l.upper() == "CATEGORY" and idx + 1 < len(scan_lines):
                    for forward in range(idx + 1, min(idx + 12, len(scan_lines))):
                        cand = scan_lines[forward].strip()
                        if cand.upper() in VALID_CATEGORY_CODES or any(k in cand.lower() for k in ["core", "basic science", "engineering science", "humanities", "elective", "mandatory"]):
                            meta.category = cand
                            break

        # 3. L-T-P-C extraction
        if meta.credits is None:
            m_ltpc = re.search(r"L\s*[:\-–—]?\s*(\d+(?:\.\d+)?)\s*T\s*[:\-–—]?\s*(\d+(?:\.\d+)?)\s*P\s*[:\-–—]?\s*(\d+(?:\.\d+)?)\s*(?:Credit|Credits|C)\s*[:\-–—]?\s*(\d+(?:\.\d+)?)", full_text, re.IGNORECASE)
            if m_ltpc:
                meta.lecture = self._parse_num(m_ltpc.group(1))
                meta.tutorial = self._parse_num(m_ltpc.group(2))
                meta.practical = self._parse_num(m_ltpc.group(3))
                meta.credits = self._parse_num(m_ltpc.group(4))

        if meta.credits is None:
            # Check scan_hl for tabular "L T P C \n 3 0 0 3"
            for hl in scan_hl:
                m_row = re.search(r"\b(\d)\s+(\d)\s+(\d)\s+(\d)\b", hl)
                if m_row and not any(k in hl.upper() for k in ["DATE", "TIME", "202", "199", "REGULATIONS", "TOTAL"]):
                    meta.lecture = int(m_row.group(1))
                    meta.tutorial = int(m_row.group(2))
                    meta.practical = int(m_row.group(3))
                    meta.credits = int(m_row.group(4))
                    break

        if meta.credits is None:
            # Check for T P C format (e.g. JNTU format: T P C / 3+1 0 3)
            m_tpc_inline = re.search(r"\bT\s*[:\-–—]?\s*(\d+)(?:\+(\d+))?\s+P\s*[:\-–—]?\s*(\d+)\s+C\s*[:\-–—]?\s*(\d+)", full_text, re.IGNORECASE)
            if m_tpc_inline:
                meta.lecture = self._parse_num(m_tpc_inline.group(1))
                meta.tutorial = self._parse_num(m_tpc_inline.group(2)) if m_tpc_inline.group(2) else 0
                meta.practical = self._parse_num(m_tpc_inline.group(3))
                meta.credits = self._parse_num(m_tpc_inline.group(4))
            else:
                for idx, hl in enumerate(scan_hl[:10]):
                    if re.search(r"\bT\s+P\s+C\b", hl, re.IGNORECASE) and idx + 1 < len(scan_hl):
                        next_hl = scan_hl[idx + 1].strip()
                        m_tpc_vals = re.search(r"\b(\d+)(?:\+(\d+))?\s+(\d+)\s+(\d+)\b", next_hl)
                        if m_tpc_vals:
                            meta.lecture = self._parse_num(m_tpc_vals.group(1))
                            meta.tutorial = self._parse_num(m_tpc_vals.group(2)) if m_tpc_vals.group(2) else 0
                            meta.practical = self._parse_num(m_tpc_vals.group(3))
                            meta.credits = self._parse_num(m_tpc_vals.group(4))
                            break
                if meta.credits is None:
                    for idx, l in enumerate(scan_lines[:15]):
                        if re.match(r"^T\s+P\s+C\s*$", l.strip(), re.IGNORECASE) and idx + 1 < len(scan_lines):
                            next_line = scan_lines[idx + 1].strip()
                            m_tpc_vals = re.match(r"^(\d+)(?:\+(\d+))?\s+(\d+)\s+(\d+)\s*$", next_line)
                            if m_tpc_vals:
                                meta.lecture = self._parse_num(m_tpc_vals.group(1))
                                meta.tutorial = self._parse_num(m_tpc_vals.group(2)) if m_tpc_vals.group(2) else 0
                                meta.practical = self._parse_num(m_tpc_vals.group(3))
                                meta.credits = self._parse_num(m_tpc_vals.group(4))
                                break

        if meta.credits is None:
            m_cred_single = re.search(r"\bCredits\s*[:\-–—]?\s*(\d+)\b", "\n".join(scan_lines), re.IGNORECASE)
            if not m_cred_single:
                m_cred_single = re.search(r"\bCredits\s*[:\-–—]?\s*(\d+)\b", full_text, re.IGNORECASE)
            if m_cred_single:
                meta.credits = int(m_cred_single.group(1))

            for idx, l in enumerate(scan_lines[:15]):
                if l.upper() == "L" and idx + 7 < len(scan_lines):
                    tokens = [scan_lines[idx + o].upper() for o in range(4)]
                    if "T" in tokens and "P" in tokens:
                        num_tokens = []
                        for forward in range(idx + 4, min(idx + 12, len(scan_lines))):
                            val = scan_lines[forward].strip()
                            if re.match(r"^\d+(?:\.\d+)?$", val):
                                num_tokens.append(self._parse_num(val))
                                if len(num_tokens) == 4:
                                    break
                        if len(num_tokens) >= 4:
                            meta.lecture, meta.tutorial, meta.practical, meta.credits = num_tokens[:4]
                            break

        return meta

    def _parse_num(self, val_str: str) -> Union[int, float]:
        val = float(val_str)
        return int(val) if val.is_integer() else val

    def _extract_units_and_topics(
        self,
        pages: List[PDFPage],
        block_lines: List[str],
        unit_range: Optional[Tuple[int, int]]
    ) -> List[UnitEntry]:
        units: List[UnitEntry] = []
        if not pages:
            return units

        if unit_range:
            scan_lines = block_lines[unit_range[0]:unit_range[1] + 1]
        else:
            scan_lines = block_lines

        stop_markers = [
            r"^(?:TEXT\s*BOOKS?|TEXT\s*BOOK\(S\)|REFERENCES?|REFERENCE\s*BOOKS?|COURSE\s*DESIGNERS?|MODE\s*OF\s*EVALUATION|RECOMMENDED\s*BY|APPROVED\s*BY|PROCEEDINGS\s*OF|TOTAL\s*LECTURE\s*HOURS)\b"
        ]

        current_unit: Optional[Dict[str, Any]] = None
        unit_blocks: List[Dict[str, Any]] = []

        for l in scan_lines:
            if not unit_range and any(re.search(sm, l, re.IGNORECASE) for sm in stop_markers):
                break

            m_u = self.UNIT_HEADER_REGEX.match(l)
            m_roman = self.STANDALONE_ROMAN_REGEX.match(l)

            if m_u:
                if current_unit:
                    unit_blocks.append(current_unit)
                u_raw_num = m_u.group(1).upper()
                u_num = int(u_raw_num) if u_raw_num.isdigit() else self.ROMAN_MAP.get(u_raw_num, len(unit_blocks) + 1)
                u_title = m_u.group(2).strip()
                
                # Extract trailing hours from header title if present (e.g. "Supervised Learning - I 7 hours")
                hours = None
                m_title_hr = re.search(r"\b(\d+)\s*(?:hours?|hrs?|periods?)\s*$", u_title, re.IGNORECASE)
                if m_title_hr:
                    hours = int(m_title_hr.group(1))
                    u_title = u_title[:m_title_hr.start()].strip()

                current_unit = {
                    "number": u_num,
                    "title": u_title,
                    "hours": hours,
                    "lines": []
                }
            elif m_roman and len(l) <= 4:
                if current_unit:
                    unit_blocks.append(current_unit)
                u_num = self.ROMAN_MAP.get(l.upper(), len(unit_blocks) + 1)
                current_unit = {
                    "number": u_num,
                    "title": "",
                    "hours": None,
                    "lines": []
                }
            elif current_unit:
                # Check if this line is standalone hours indicator (e.g. "4 hours" or "7 hrs")
                m_standalone_hr = re.match(r"^\s*(\d+)\s*(?:hours?|hrs?|periods?)\s*$", l, re.IGNORECASE)
                if m_standalone_hr and current_unit["hours"] is None:
                    current_unit["hours"] = int(m_standalone_hr.group(1))
                    continue

                # Check if title continuation (e.g. "Introduction to Machine Learning and Pre-" followed by "requisites")
                if current_unit["title"].endswith("-") or current_unit["title"].endswith("and") or (len(current_unit["lines"]) == 0 and len(l.split()) <= 3 and not current_unit["title"]):
                    if current_unit["title"].endswith("-"):
                        current_unit["title"] = current_unit["title"] + l
                    elif not current_unit["title"]:
                        current_unit["title"] = l
                    else:
                        current_unit["title"] += " " + l
                    continue

                # Ignore table column headers inside unit content
                if l.upper() not in ["CONTENT", "HOURS", "COS", "COGNITIVE", "LEVEL", "COGNITIVE LEVEL"]:
                    current_unit["lines"].append(l)

        if current_unit:
            unit_blocks.append(current_unit)

        # Process extracted unit blocks into UnitEntry objects
        global_topic_id = 1
        for ub in unit_blocks:
            raw_text = " ".join(ub["lines"]).strip()
            # Trim trailing experiential learning, resources, total hours
            raw_text = re.sub(r"\b(?:EXPERIENTIAL\s*LEARNING|RESOURCES|TOTAL\s*LECTURE\s*HOURS)\b.*$", "", raw_text, flags=re.IGNORECASE).strip()
            
            hours = ub.get("hours")
            if hours is None:
                m_hr = re.search(r"(\d+)\s*(?:Hours?|Hrs?|Periods?|Lecture\s*Hours?)\b", raw_text, re.IGNORECASE)
                if m_hr:
                    hours = int(m_hr.group(1))

            topic_strings = self._split_topics(raw_text)
            topics = []
            for ts in topic_strings:
                if not ts or len(ts) < 2:
                    continue
                bloom_lvl, src = infer_bloom_from_text(ts)
                topics.append(TopicEntry(
                    id=f"T{global_topic_id}",
                    text=ts,
                    bloom=bloom_lvl,
                    bloom_source=src
                ))
                global_topic_id += 1

            clean_u_title = re.sub(r"[\ufffd\s]+", " ", ub["title"]).strip()
            clean_u_title = re.sub(r"\s+\d+\s*(?:hours?|hrs?|periods?)\s*$", "", clean_u_title, flags=re.IGNORECASE).strip()

            units.append(UnitEntry(
                number=ub["number"],
                title=clean_u_title,
                hours=hours,
                text=raw_text,
                topics=topics
            ))

        return units

    def _split_topics(self, text: str) -> List[str]:
        raw_parts = re.split(r"\s*[-–—;•\ufffd]\s*", text)
        topics = []
        for p in raw_parts:
            cleaned = p.strip()
            cleaned = re.sub(r"^[\d\.\)\s]+", "", cleaned)
            cleaned = re.sub(r"[:\-–—\s\ufffd]+$", "", cleaned).strip()
            cleaned = re.sub(r"^\b\d+\s*hours?\b", "", cleaned, flags=re.IGNORECASE).strip()
            if cleaned and len(cleaned) >= 2 and not cleaned.isdigit():
                topics.append(cleaned)
        return topics

    def _extract_course_outcomes(
        self,
        pages: List[PDFPage],
        block_lines: List[str],
        co_range: Optional[Tuple[int, int]]
    ) -> List[CourseOutcome]:
        if not pages:
            return []

        if co_range:
            scan_lines = block_lines[co_range[0]:co_range[1] + 1]
        else:
            co_start_idx = -1
            for idx, l in enumerate(block_lines):
                if re.search(r"\bCOURSE\s*OUTCOMES?\b", l, re.IGNORECASE) or re.search(r"\bEXPECTED\s*COURSE\s*OUTCOMES?\b", l, re.IGNORECASE):
                    co_start_idx = idx + 1
                    break
            if co_start_idx == -1:
                return []
            scan_lines = block_lines[co_start_idx:]

        stop_markers = [
            r"\b(?:MAPPING\s*WITH|CO-PO|CO\s*-\s*PO|CO\s*-\s*PO\s*-\s*PSO|MAPPING\s*TABLE|SYLLABUS|TEXT\s*BOOKS?|TEXT\s*BOOK\(S\)|REFERENCES?|COURSE\s*DESIGNERS?|MODULE\s*[:\d]|UNIT\s*[:\d]|CHAPTER\s*[:\d])\b",
            r"\bPO1\s+PO2\s+PO3\b"
        ]

        current_co_id = None
        current_co_text_parts = []
        current_co_printed_bloom = None
        seen_cos_dict: Dict[str, CourseOutcome] = {}

        def flush_current():
            nonlocal current_co_id, current_co_text_parts, current_co_printed_bloom
            if current_co_id:
                full_stmt = " ".join(current_co_text_parts).strip()
                # Clean any leaked table headers or mapping text from statement
                full_stmt = re.sub(r"\b(?:CO\s*[-–—]?\s*PO(?:\s*[-–—]?\s*PSO)?\s*(?:Mapping\s*Table|Mapping)?|MAPPING\s*WITH\s*PROGRAMME\s*OUTCOMES|Course\s*Outcomes\s*Program\s*Outcomes).*$", "", full_stmt, flags=re.IGNORECASE).strip()
                if full_stmt and len(full_stmt) >= 3:
                    bloom_lvl, src = self._resolve_bloom(full_stmt, current_co_printed_bloom)
                    # Deduplicate: only store non-empty statement, keep longer/better statement if exists
                    if current_co_id not in seen_cos_dict or len(full_stmt) > len(seen_cos_dict[current_co_id].statement):
                        seen_cos_dict[current_co_id] = CourseOutcome(co=current_co_id, statement=full_stmt, bloom=bloom_lvl, bloom_source=src)

        for l in scan_lines:
            if not co_range and any(re.search(sm, l, re.IGNORECASE) for sm in stop_markers):
                break

            m_co = self.CO_REGEX.match(l)
            m_numbered = re.match(r"^(\d+)[\.\)]\s*(.*)$", l)

            if m_co:
                matched_id = f"CO{m_co.group(2)}"
                matched_text = m_co.group(3).strip() if m_co.group(3) else ""

                # If this line is just a standalone duplicate CO ID from table columns, don't wipe existing statement
                if matched_id == current_co_id and not matched_text:
                    continue

                flush_current()
                current_co_id = matched_id
                current_co_text_parts = [matched_text] if matched_text else []
                current_co_printed_bloom = None

            elif m_numbered and len(m_numbered.group(1)) <= 2:
                num_val = int(m_numbered.group(1))
                matched_id = f"CO{num_val}"
                rem_text = m_numbered.group(2).strip()

                if matched_id == current_co_id and not rem_text:
                    continue

                flush_current()
                current_co_id = matched_id
                current_co_text_parts = [rem_text] if rem_text else []
                current_co_printed_bloom = None

            elif current_co_id:
                printed_bloom = normalize_printed_bloom(l)
                if printed_bloom and len(l.split()) <= 3:
                    current_co_printed_bloom = printed_bloom
                elif not l.lower().startswith("after successful completion") and not l.lower().startswith("at the end of this course") and l.upper() not in ["COGNITIVE", "LEVEL", "COGNITIVE LEVEL"]:
                    if re.search(r"\b(?:PO\d|PSO\d|Mapping\s*Table|Program\s*Outcomes)\b", l, re.IGNORECASE):
                        break
                    current_co_text_parts.append(l)

        flush_current()
        return list(seen_cos_dict.values())

    def _resolve_bloom(self, statement: str, printed_bloom: Optional[str]) -> Tuple[str, str]:
        if printed_bloom:
            return printed_bloom, "printed"
        m_paren = re.search(r"\((Remember|Understand|Apply|Analyze|Analyse|Evaluate|Create|K\d|L\d)\)\s*$", statement, re.IGNORECASE)
        if m_paren:
            norm = normalize_printed_bloom(m_paren.group(1))
            if norm:
                return norm, "printed"
        return infer_bloom_from_text(statement)

    def _extract_programme_outcomes(self, pages: List[PDFPage]) -> List[ProgrammeOutcome]:
        if self.cached_pos is not None:
            return self.cached_pos

        pos: List[ProgrammeOutcome] = []
        seen_po_ids = set()
        current_po_id = None
        current_po_parts = []
        in_po_section = False

        def flush_po():
            nonlocal current_po_id, current_po_parts
            if current_po_id and current_po_id not in seen_po_ids:
                stmt = " ".join(current_po_parts).strip()
                stmt = re.sub(r"\b(?:PROGRAM\s*SPECIFIC\s*OUTCOMES|PROGRAMME\s*SPECIFIC\s*OUTCOMES|On\s*successful\s*completion\s*of\s*the\s*Program).*$", "", stmt, flags=re.IGNORECASE).strip()
                if stmt:
                    pos.append(ProgrammeOutcome(po=current_po_id, statement=stmt))
                    seen_po_ids.add(current_po_id)
            current_po_id = None
            current_po_parts = []

        for p in self.pages[:25]:
            p_text = p.raw_text.lower()
            has_po_kw = any(k in p_text for k in ["programme outcomes", "program outcomes", "program specific outcomes", "programme specific outcomes"])
            if has_po_kw:
                in_po_section = True
            elif in_po_section and pos:
                flush_po()
                self.cached_pos = pos
                return pos

            if not in_po_section:
                continue

            for line in p.lines:
                line_clean = line.strip()
                if not line_clean:
                    continue

                if any(term in line_clean.upper() for term in ["PROGRAM EDUCATIONAL OBJECTIVES", "COURSE STRUCTURE", "SEMESTER I", "SEMESTER - I", "SCHEME OF INSTRUCTION", "I-SEMESTER", "CURRICULUM", "CATEGORY CREDIT DETAIL", "SPECIALIZATION ELECTIVE"]):
                    if in_po_section and pos:
                        flush_po()
                        self.cached_pos = pos
                        return pos

                if re.search(r"^(?:PROGRAM\s*SPECIFIC\s*OUTCOMES|PROGRAMME\s*SPECIFIC\s*OUTCOMES|PROGRAM\s*OUTCOMES|PROGRAMME\s*OUTCOMES)\b", line_clean, re.IGNORECASE):
                    flush_po()
                    continue

                if re.search(r"^on\s*successful\s*completion\s*of\s*the\s*program", line_clean, re.IGNORECASE) or re.search(r"^will\s*be\s*able\s*to", line_clean, re.IGNORECASE):
                    continue

                if re.match(r"^(?:B\.C\.A|BCA|B\.TECH|B\.E\.|BACHELOR\s*OF|MASTER\s*OF|DEPARTMENT\s*OF|Page\s*\d+|Report\s*On|Proceedings)\b", line_clean, re.IGNORECASE):
                    continue

                m_po = self.PO_REGEX.match(line_clean)
                m_pso = self.PSO_REGEX.match(line_clean)
                match = m_po or m_pso

                if match:
                    flush_po()
                    prefix = "PSO" if m_pso else "PO"
                    num_val = int(match.group(2)) if match.group(2).isdigit() else match.group(2)
                    current_po_id = f"{prefix}{num_val}"
                    stmt_initial = match.group(3).strip() if match.group(3) else ""
                    current_po_parts = [stmt_initial] if stmt_initial else []
                elif current_po_id:
                    if not line_clean.isdigit():
                        current_po_parts.append(line_clean)

        flush_po()
        self.cached_pos = pos
        return pos

    def _extract_co_po_matrix(
        self,
        pages: List[PDFPage],
        block_lines: List[str],
        matrix_range: Optional[Tuple[int, int]]
    ) -> List[COPOMappingEntry]:
        matrix: List[COPOMappingEntry] = []
        if not pages:
            return matrix

        scan_lines = [l for p in pages for l in p.horizontal_lines] or block_lines

        matrix_start_idx = 0
        found_start = False
        for idx, l in enumerate(scan_lines):
            if re.search(r"\b(?:CO\s*[-–—]?\s*PO(?:\s*[-–—]?\s*PSO)?\s*(?:Mapping\s*Table|Mapping)?|MAPPING\s*WITH\s*PROGRAMME\s*OUTCOMES|COURSE\s*ARTICULATION\s*MATRIX|PO1\s*PO2\s*PO3)\b", l, re.IGNORECASE):
                matrix_start_idx = idx + 1
                found_start = True
                break
        
        if found_start:
            scan_lines = scan_lines[matrix_start_idx:]

        stop_markers = [
            r"^(?:SYLLABUS|TEXT\s*BOOKS?|REFERENCES?|COURSE\s*DESIGNERS?|COURSE\s*CONTENT)\b"
        ]

        mapping_rows_raw: Dict[str, List[str]] = {}
        current_row_co = None

        for l in scan_lines:
            if any(re.search(sm, l, re.IGNORECASE) for sm in stop_markers):
                break
            if "S- Strong" in l or "S-" in l or "Correlation Levels:" in l:
                break

            m_co = re.match(r"^(CO\s*\d+)\b", l, re.IGNORECASE)
            if m_co:
                current_row_co = re.sub(r"\s+", "", m_co.group(1)).upper()
                rem = l[m_co.end():].strip()
                mapping_rows_raw[current_row_co] = [rem] if rem else []
            elif current_row_co:
                if re.match(r"^(?:Course\s*Correlation|Correlation|Level)\b", l, re.IGNORECASE):
                    break
                mapping_rows_raw[current_row_co].append(l)

        col_keys = [f"PO{i}" for i in range(1, 13)] + [f"PSO{i}" for i in range(1, 4)]

        for co_id, tokens in mapping_rows_raw.items():
            flat_tokens = []
            for t in tokens:
                for sub in re.split(r"\s+", t):
                    if sub in ["S", "M", "L", "H", "3", "2", "1", "-"]:
                        flat_tokens.append(sub)

            for col_idx, col_name in enumerate(col_keys):
                if col_idx < len(flat_tokens):
                    val = flat_tokens[col_idx]
                    if val and val != "-":
                        strength_val = int(val) if val.isdigit() else val
                        matrix.append(COPOMappingEntry(co=co_id, po=col_name, strength=strength_val))

        return matrix

    def _extract_books(
        self,
        pages: List[PDFPage],
        block_lines: List[str],
        books_range: Optional[Tuple[int, int]],
        tb_range: Optional[Tuple[int, int]],
        ref_range: Optional[Tuple[int, int]]
    ) -> List[BookEntry]:
        textbooks = []
        references = []
        if not pages:
            return []

        current_section = None
        stop_markers = [
            r"^(?:MODE\s*OF\s*EVALUATION|RECOMMENDED\s*BY|APPROVED\s*BY|PROCEEDINGS\s*OF|COURSE\s*DESIGNERS?|SYLLABUS|MAPPING\s*WITH|SOFTWARE/TOOLS)\b",
            r"^(?:Course\s*Code|Course\s*Title|Pre-Requisite|Anti-Requisite|Co-Requisite)\b"
        ]

        scan_lines = block_lines[books_range[0]:books_range[1] + 1] if books_range else block_lines

        for l in scan_lines:
            if not books_range and any(re.search(sm, l, re.IGNORECASE) for sm in stop_markers):
                current_section = None
                continue
            if re.search(r"^(?:TEXT\s*BOOKS?|TEXT\s*BOOK\(S\)|TEXTBOOK\(S\)?|PRESCRIBED\s*BOOKS?)\s*[:\-–—]?\s*$", l, re.IGNORECASE):
                current_section = "textbooks"
                continue
            elif re.search(r"^(?:REFERENCES?|REFERENCE\s*BOOKS?|OTHER\s*REFERENCES?|VIDEO\s*LECTURES?|WEB\s*RESOURCES?|ONLINE\s*RESOURCES?)\s*[:\-–—]?\s*$", l, re.IGNORECASE):
                current_section = "references"
                continue

            if current_section == "textbooks":
                textbooks.append(l)
            elif current_section == "references":
                references.append(l)

        clean_tb = self._join_book_entries(textbooks)
        clean_ref = self._join_book_entries(references)

        books_list: List[BookEntry] = []
        for tb in clean_tb:
            books_list.append(BookEntry(kind="text", text=tb))
        for ref in clean_ref:
            books_list.append(BookEntry(kind="reference", text=ref))

        return books_list

    def _join_book_entries(self, lines: List[str]) -> List[str]:
        entries = []
        current_entry = []
        for l in lines:
            s = l.strip()
            if not s:
                continue
            if re.match(r"^(B\.C\.A|BCA|B\.TECH|B\.E\.)\s*[-–—]\s*", s, re.IGNORECASE):
                continue
            if any(re.match(sm, s, re.IGNORECASE) for sm in [
                r"^(?:MODE\s*OF\s*EVALUATION|RECOMMENDED\s*BY|APPROVED\s*BY|PROCEEDINGS\s*OF|ITEM\s*\d+|Course\s*Code|Course\s*Title|Pre-Requisite|Anti-Requisite|Co-Requisite)"
            ]):
                break

            # Handle standalone list numbers (e.g. '1', '2', '3')
            if re.match(r"^\d+[\.\)]?$", s) and len(s) <= 3:
                if current_entry:
                    entries.append(" ".join(current_entry).strip())
                current_entry = []
                continue

            # Check if current_entry ends with publication year/edition/publisher and next line starts a new book citation
            if current_entry:
                last_line = current_entry[-1].strip()
                ends_with_citation_term = bool(
                    re.search(r"(?:19\d\d|20\d\d|Edition|Ed\.)[\.]\s*$", last_line, re.IGNORECASE) and not last_line.endswith(",")
                ) or bool(
                    re.search(r"\b(?:Pearson(?:\s+Education)?|PHI|TMH|McGraw[\s\-]?Hill|Wiley|Springer|Press|Publishers?|Media|Publications?|Hall|Sons|Oxford|Cambridge|GitBook|Apress|Packt|CRC(?:\s+Press)?)\b[\.,]?\s*$", last_line, re.IGNORECASE)
                )
                is_continuation = bool(re.match(r"^(?:Edition|Ed\.|Press|Publisher|Publishing|Vol|Volume|pp|Pages|ISBN|ISSN|and|&|,|-|\d+th|\d+st|\d+nd|\d+rd)\b", s, re.IGNORECASE))
                if ends_with_citation_term and not is_continuation:
                    entries.append(" ".join(current_entry).strip())
                    current_entry = [s]
                    continue

            if re.match(r"^\d+[\.\)]\s*", s):
                if current_entry:
                    entries.append(" ".join(current_entry).strip())
                current_entry = [re.sub(r"^\d+[\.\)]\s*", "", s)]
            elif re.match(r"^https?://", s, re.IGNORECASE):
                if current_entry and not (len(current_entry) == 1 and re.match(r"^\d+[\.\)]?$", current_entry[0].strip())):
                    entries.append(" ".join(current_entry).strip())
                    current_entry = [s]
                else:
                    current_entry.append(s)
            elif current_entry:
                # If current entry already has a URL, separate standalone subsequent lines
                if any("http://" in part or "https://" in part for part in current_entry):
                    entries.append(" ".join(current_entry).strip())
                    current_entry = [s]
                else:
                    current_entry.append(s)
            else:
                current_entry = [s]

        if current_entry:
            joined = " ".join(current_entry).strip()
            if joined:
                entries.append(joined)

        return entries
