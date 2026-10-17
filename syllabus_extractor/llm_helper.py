import os
import re
import json
import hashlib
from typing import List, Dict, Tuple, Optional, Any
from pydantic import BaseModel, model_validator
from .llm_engine import LLMEngine
from .config import config


class SectionRange(BaseModel):
    start: int
    end: int

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.start < 0 or self.end < 0:
            raise ValueError("Line numbers cannot be negative")
        if self.start > self.end:
            raise ValueError(f"start ({self.start}) must be <= end ({self.end})")
        return self


class SyllabusBoundaryOutput(BaseModel):
    units: Optional[SectionRange] = None
    course_outcomes: Optional[SectionRange] = None
    co_po_matrix: Optional[SectionRange] = None
    books: Optional[SectionRange] = None


class LLMLineRangeBoundaryHelper:
    """
    Identifies variable section boundaries (Course Outcomes, CO-PO Matrix, Books, Units)
    by returning line ranges rather than generated text, guaranteeing strict grounding.
    
    Uses LLMEngine with strict Pydantic schema validation and Primary -> Backup escalation,
    falling back to rule-based heuristics if no LLM credentials or valid outputs exist.
    """

    def __init__(self, llm_engine: Optional[LLMEngine] = None):
        self.llm = llm_engine or LLMEngine()
        # Initialize backup engine if escalation is enabled
        self.backup_llm = None
        if config.enable_escalation and config.backup_provider not in ["heuristic", self.llm.provider]:
            try:
                self.backup_llm = LLMEngine(provider=config.backup_provider)
            except Exception:
                self.backup_llm = None

    def identify_section_ranges(self, lines: List[str]) -> Dict[str, Optional[Tuple[int, int]]]:
        """
        Determines line index ranges [start_idx, end_idx] (0-indexed, end inclusive)
        for variable college syllabus sections.
        """
        if not lines:
            return {"metadata": None, "units": None, "course_outcomes": None, "co_po_matrix": None, "books": None}

        # 1. Try Primary LLM if active
        if self.llm.provider != "heuristic":
            llm_ranges = self._query_llm_for_ranges(self.llm, lines)
            if llm_ranges:
                return llm_ranges

            # 2. Escalation Ladder: If primary fails, try backup model before heuristic
            if self.backup_llm and self.backup_llm.provider != "heuristic":
                backup_ranges = self._query_llm_for_ranges(self.backup_llm, lines)
                if backup_ranges:
                    return backup_ranges

        # 3. Deterministic rule-based boundary fallback
        return self._compute_section_ranges_heuristic(lines)

    def _query_llm_for_ranges(self, engine: LLMEngine, lines: List[str]) -> Optional[Dict[str, Optional[Tuple[int, int]]]]:
        system_prompt = (
            "You are an expert document layout parser for university syllabus documents. "
            "Given numbered lines of a course syllabus, identify the 0-indexed line ranges [start_line, end_line] (inclusive) "
            "for these sections: 'units', 'course_outcomes', 'co_po_matrix', 'books'. "
            "Return a strictly valid JSON object with format:\n"
            '{"units": {"start": 0, "end": 40}, "course_outcomes": {"start": 41, "end": 50}, "co_po_matrix": null, "books": {"start": 51, "end": 60}}\n'
            "Or null for any section that is absent. Do not invent or overlap invalid lines."
        )

        n = len(lines)
        numbered_lines = "\n".join(f"{i}: {line}" for i, line in enumerate(lines[:120]))
        user_prompt = f"Identify the line index ranges for each section in this syllabus snippet (0 to {n-1}):\n\n{numbered_lines}"

        try:
            raw_json_str = engine.generate(system_prompt, user_prompt, temperature=0.0)
            if not raw_json_str:
                return None

            # Clean JSON formatting wrappers
            clean_str = re.sub(r"^```(?:json)?\s*", "", raw_json_str.strip())
            clean_str = re.sub(r"\s*```$", "", clean_str).strip()
            data = json.loads(clean_str)

            # Adapt both array format [start, end] and object format {"start": s, "end": e}
            normalized_data = {}
            for k in ["units", "course_outcomes", "co_po_matrix", "books"]:
                val = data.get(k)
                if isinstance(val, list) and len(val) == 2:
                    normalized_data[k] = {"start": val[0], "end": val[1]}
                elif isinstance(val, dict) and "start" in val and "end" in val:
                    normalized_data[k] = val
                else:
                    normalized_data[k] = None

            # Strict Pydantic validation
            parsed_output = SyllabusBoundaryOutput.model_validate(normalized_data)
            ranges: Dict[str, Optional[Tuple[int, int]]] = {}

            for key in ["units", "course_outcomes", "co_po_matrix", "books"]:
                range_obj = getattr(parsed_output, key)
                if range_obj and 0 <= range_obj.start <= range_obj.end < n:
                    ranges[key] = (range_obj.start, range_obj.end)
                else:
                    ranges[key] = None

            if any(ranges.values()):
                return ranges
        except Exception:
            pass

        return None

    def _compute_section_ranges_heuristic(self, lines: List[str]) -> Dict[str, Optional[Tuple[int, int]]]:
        n = len(lines)
        ranges: Dict[str, Optional[Tuple[int, int]]] = {
            "metadata": None,
            "units": None,
            "course_outcomes": None,
            "co_po_matrix": None,
            "books": None,
            "textbooks": None,
            "references": None
        }

        units_start = None
        co_start = None
        matrix_start = None
        books_start = None
        textbooks_start = None
        references_start = None

        co_regex = re.compile(r"\b(?:COURSE\s*OUTCOMES?|COGNITIVE\s*LEVEL\s*MAPPING|OUTCOMES\s*\(COS\))\b", re.IGNORECASE)
        matrix_regex = re.compile(r"\b(?:MAPPING\s*WITH\s*PROGRAMME\s*OUTCOMES|CO\s*[-–—]?\s*PO\s*MAPPING|CO-PO\s*MATRIX|CO\s*PO\s*PSO\s*MAPPING)\b", re.IGNORECASE)
        textbooks_regex = re.compile(r"\b(?:TEXT\s*BOOKS?|TEXTBOOK|PRESCRIBED\s*BOOKS?)\b", re.IGNORECASE)
        references_regex = re.compile(r"\b(?:REFERENCES?|REFERENCE\s*BOOKS?|OTHER\s*REFERENCES?|SUGGESTED\s*READINGS?)\b", re.IGNORECASE)
        units_regex = re.compile(r"\b(?:UNIT|MODULE|CHAPTER|PART)\s*[-–—:\s]*([IVX\d]+|ONE|TWO|THREE)\b", re.IGNORECASE)
        syllabus_kw_regex = re.compile(r"^(?:SYLLABUS|COURSE CONTENT|UNITS)\s*[:\-–—]?\s*$", re.IGNORECASE)

        for i, line in enumerate(lines):
            l = line.strip()
            if syllabus_kw_regex.search(l) or (units_regex.search(l) and units_start is None):
                if units_start is None:
                    units_start = i
            elif co_regex.search(l):
                if co_start is None:
                    co_start = i
            elif matrix_regex.search(l):
                if matrix_start is None:
                    matrix_start = i
            elif textbooks_regex.search(l):
                if textbooks_start is None:
                    textbooks_start = i
                if books_start is None:
                    books_start = i
            elif references_regex.search(l):
                if references_start is None:
                    references_start = i
                if books_start is None:
                    books_start = i

        first_section_start = min([pos for pos in [units_start, co_start, matrix_start, books_start] if pos is not None] or [n])
        if first_section_start > 0:
            ranges["metadata"] = (0, first_section_start - 1)

        section_starts = []
        if units_start is not None:
            section_starts.append(("units", units_start))
        if co_start is not None:
            section_starts.append(("course_outcomes", co_start))
        if matrix_start is not None:
            section_starts.append(("co_po_matrix", matrix_start))
        if textbooks_start is not None:
            section_starts.append(("textbooks", textbooks_start))
        if references_start is not None:
            section_starts.append(("references", references_start))
        elif books_start is not None and textbooks_start is None and references_start is None:
            section_starts.append(("books", books_start))

        section_starts.sort(key=lambda x: x[1])

        for idx, (sec_name, start_i) in enumerate(section_starts):
            if idx + 1 < len(section_starts):
                end_i = section_starts[idx + 1][1] - 1
            else:
                end_i = n - 1
            if end_i >= start_i:
                ranges[sec_name] = (start_i, end_i)

        if ranges["textbooks"] or ranges["references"]:
            b_start = min([r[0] for r in [ranges["textbooks"], ranges["references"]] if r is not None])
            b_end = max([r[1] for r in [ranges["textbooks"], ranges["references"]] if r is not None])
            ranges["books"] = (b_start, b_end)

        return ranges
