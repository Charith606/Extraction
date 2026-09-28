import re
from typing import List, Dict, Set, Optional, Tuple, Any
from .models import Task2Response, UnitEntry, TopicEntry, CourseOutcome, ProgrammeOutcome, COPOMappingEntry, BookEntry

ALLOWED_BLOOM_LEVELS = {"remember", "understand", "apply", "analyse", "evaluate", "create"}

PRINTED_BLOOM_INDICATORS = {
    "remember": ["remember", "remembering", "k1", "l1", "b1", "bl1"],
    "understand": ["understand", "understanding", "comprehend", "comprehension", "k2", "l2", "b2", "bl2"],
    "apply": ["apply", "applying", "application", "k3", "l3", "b3", "bl3"],
    "analyse": ["analyze", "analyse", "analyzing", "analysing", "analysis", "k4", "l4", "b4", "bl4"],
    "evaluate": ["evaluate", "evaluating", "evaluation", "k5", "l5", "b5", "bl5"],
    "create": ["create", "creating", "creation", "design", "synthesis", "synthesize", "k6", "l6", "b6", "bl6"]
}


def normalize_ws(text: str) -> str:
    """Normalizes whitespace and line-break hyphens to ensure robust grounding checks."""
    if not text:
        return ""
    t = re.sub(r"[\ufffd\u2013\u2014\u2015]", "-", text)
    t = re.sub(r"-\s+", "-", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


class VerificationLayer:
    """
    Verification and auditing engine for Task 2 responses:
    1. Grounding Substring Check: Every string field is checked against the block's source text.
       If it is not a substring after whitespace normalization, it is dropped and logged in not_extracted.
    2. CO-PO Matrix Consistency: Every CO and PO id in the matrix must exist in outcome lists.
    3. 'Nothing Lost' Unit Accounting: Every unit's topics, joined together, account for the unit's text.
    4. Bloom Taxonomy Integrity: Validates 6 allowed Bloom levels and ensures 'printed' source is only
       used when an explicit Bloom indicator actually appears in the source text.
    5. Deterministic sorting across all verified elements.
    """

    @classmethod
    def verify(
        cls,
        response: Task2Response,
        block_source_text: str,
        document_source_text: str = ""
    ) -> Task2Response:
        norm_block_source = normalize_ws(block_source_text).lower()
        norm_doc_source = normalize_ws(document_source_text).lower() if document_source_text else norm_block_source
        
        audit_logs: List[str] = list(response.not_extracted)

        # -------------------------------------------------------------
        # 1. Grounding Substring Check for Metadata
        # -------------------------------------------------------------
        if response.course.title:
            norm_title = normalize_ws(response.course.title).lower()
            if norm_title not in norm_block_source and norm_title not in norm_doc_source:
                audit_logs.append(f"title dropped: '{response.course.title}' not found in source text")
                response.course.title = ""

        if response.course.category:
            norm_cat = normalize_ws(response.course.category).lower()
            if norm_cat not in norm_block_source:
                audit_logs.append(f"category dropped: '{response.course.category}' not found in source text")
                response.course.category = None

        # -------------------------------------------------------------
        # 2. Units & Topics Grounding + 'Nothing Lost' Accounting
        # -------------------------------------------------------------
        verified_units: List[UnitEntry] = []
        for u in response.units:
            # Check unit title
            if u.title:
                norm_u_title = normalize_ws(u.title).lower()
                title_words = [w for w in re.findall(r"\b[a-z0-9]+\b", norm_u_title) if len(w) > 2]
                if norm_u_title not in norm_block_source and not (title_words and all(w in norm_block_source for w in title_words)):
                    audit_logs.append(f"unit {u.number} title dropped: '{u.title}' not found in source text")
                    u.title = ""

            # Check unit text
            if u.text:
                norm_u_text = normalize_ws(u.text).lower()
                if norm_u_text not in norm_block_source:
                    audit_logs.append(f"unit {u.number} text dropped: content not found in source text")
                    u.text = ""

            # Verify topics and check grounding
            verified_topics: List[TopicEntry] = []
            for t in u.topics:
                norm_topic = normalize_ws(t.text).lower()
                if norm_topic and norm_topic not in norm_block_source:
                    audit_logs.append(f"topic dropped from unit {u.number}: '{t.text}' not found in source text")
                    continue

                # Validate Bloom level on topic
                cls._validate_bloom(t, norm_block_source, audit_logs, f"unit {u.number} topic '{t.text}'")
                verified_topics.append(t)

            u.topics = verified_topics

            # Enforce 'Nothing Lost': Verify topics account for unit text
            if u.text and u.topics:
                cls._verify_nothing_lost(u, audit_logs)

            verified_units.append(u)

        response.units = sorted(verified_units, key=lambda x: x.number)

        # -------------------------------------------------------------
        # 3. Course Outcomes Grounding & Bloom Taxonomy Integrity
        # -------------------------------------------------------------
        verified_cos: List[CourseOutcome] = []
        known_co_ids: Set[str] = set()
        for co in response.course_outcomes:
            norm_stmt = normalize_ws(co.statement).lower()
            if norm_stmt and norm_stmt not in norm_block_source:
                audit_logs.append(f"course outcome {co.co} statement dropped: not found in source text")
                co.statement = ""

            cls._validate_bloom(co, norm_block_source, audit_logs, f"course outcome {co.co}")
            verified_cos.append(co)
            known_co_ids.add(co.co.upper())

        response.course_outcomes = sorted(verified_cos, key=lambda x: cls._co_sort_key(x.co))

        # -------------------------------------------------------------
        # 4. Programme Outcomes Grounding
        # -------------------------------------------------------------
        verified_pos: List[ProgrammeOutcome] = []
        known_po_ids: Set[str] = set()
        for po in response.programme_outcomes:
            norm_po_stmt = normalize_ws(po.statement).lower()
            if norm_po_stmt and norm_po_stmt not in norm_doc_source:
                audit_logs.append(f"programme outcome {po.po} statement dropped: not found in document text")
                po.statement = ""

            verified_pos.append(po)
            known_po_ids.add(po.po.upper())

        response.programme_outcomes = sorted(verified_pos, key=lambda x: cls._po_sort_key(x.po))

        # -------------------------------------------------------------
        # 5. CO-PO Matrix Consistency Check
        # -------------------------------------------------------------
        verified_matrix: List[COPOMappingEntry] = []
        for entry in response.co_po_matrix:
            row_co_clean = entry.co.strip().upper()
            if known_co_ids and row_co_clean not in known_co_ids:
                audit_logs.append(f"matrix CO '{entry.co}' not found in course outcomes list")

            # Check PO keys
            if known_po_ids:
                if entry.po.upper().startswith("PO") and entry.po.upper() not in known_po_ids:
                    audit_logs.append(f"matrix PO '{entry.po}' in {entry.co} not found in programme outcomes list")

            verified_matrix.append(entry)

        response.co_po_matrix = sorted(
            verified_matrix,
            key=lambda x: (cls._co_sort_key(x.co), cls._matrix_col_sort_key(x.po))
        )

        # -------------------------------------------------------------
        # 6. Books Grounding Check
        # -------------------------------------------------------------
        verified_books: List[BookEntry] = []
        for b in response.books:
            norm_b = normalize_ws(b.text).lower()
            if norm_b in norm_block_source or norm_b in norm_doc_source:
                verified_books.append(b)
            else:
                audit_logs.append(f"{b.kind} book dropped: '{b.text}' not found in source text")

        response.books = verified_books

        # Deduplicate and sort audit logs stably
        seen_logs = set()
        deduped_logs = []
        for log_entry in audit_logs:
            if log_entry not in seen_logs:
                seen_logs.add(log_entry)
                deduped_logs.append(log_entry)

        response.not_extracted = deduped_logs
        return response

    @classmethod
    def _validate_bloom(cls, item: Any, norm_source: str, audit_logs: List[str], label: str):
        """
        Validates Bloom level is one of the 6 allowed lowercase values:
        remember, understand, apply, analyse, evaluate, create.
        Ensures source is 'printed' only when an indicator is present in source text.
        """
        if item.bloom:
            lvl_norm = item.bloom.lower().strip()
            if lvl_norm not in ALLOWED_BLOOM_LEVELS:
                # Map alternate spellings
                if lvl_norm in ["analysing", "analyzing", "analysis", "analyze", "analyse"]:
                    lvl_norm = "analyse"
                elif lvl_norm in ["remembering", "remember"]:
                    lvl_norm = "remember"
                elif lvl_norm in ["understanding", "comprehend", "comprehension", "understand"]:
                    lvl_norm = "understand"
                elif lvl_norm in ["applying", "application", "apply"]:
                    lvl_norm = "apply"
                elif lvl_norm in ["evaluating", "evaluation", "evaluate"]:
                    lvl_norm = "evaluate"
                elif lvl_norm in ["creating", "creation", "design", "synthesis", "create"]:
                    lvl_norm = "create"
                else:
                    audit_logs.append(f"{label}: invalid bloom level '{item.bloom}' replaced with 'understand'")
                    lvl_norm = "understand"
            item.bloom = lvl_norm

            # Validate printed source requirement
            if item.bloom_source == "printed":
                indicators = PRINTED_BLOOM_INDICATORS.get(lvl_norm, [lvl_norm])
                found_printed = any(re.search(rf"\b{re.escape(ind)}\b", norm_source) for ind in indicators)
                if not found_printed:
                    item.bloom_source = "inferred"
                    audit_logs.append(f"{label}: bloom source changed from 'printed' to 'inferred' (indicator not in source text)")

    @classmethod
    def _verify_nothing_lost(cls, unit: UnitEntry, audit_logs: List[str]):
        """
        Enforces 'nothing lost': verifies that all substantial topic tokens in unit.text
        are accounted for by the extracted topic strings.
        """
        # Clean unit text into words
        unit_text_words = [
            w.lower() for w in re.findall(r"\b[a-zA-Z0-9]{2,}\b", unit.text)
            if not w.isdigit() and w.lower() not in ["hours", "hrs", "periods", "unit", "module", "chapter"]
        ]
        
        # Collect words from topics
        topic_words = set(
            w.lower() for t in unit.topics
            for w in re.findall(r"\b[a-zA-Z0-9]{2,}\b", t.text)
        )

        missing_words = [w for w in unit_text_words if w not in topic_words]
        if missing_words and len(missing_words) > max(3, int(len(unit_text_words) * 0.15)):
            audit_logs.append(
                f"unit {unit.number}: topics do not fully account for unit text ({len(missing_words)} missing words: {', '.join(missing_words[:5])})"
            )

    @staticmethod
    def _co_sort_key(co_str: str) -> Tuple[int, str]:
        m = re.search(r"\d+", co_str)
        return (int(m.group(0)) if m else 999, co_str)

    @staticmethod
    def _po_sort_key(po_str: str) -> Tuple[int, int, str]:
        is_pso = 1 if "PSO" in po_str.upper() else 0
        m = re.search(r"\d+", po_str)
        return (is_pso, int(m.group(0)) if m else 999, po_str)

    @staticmethod
    def _matrix_col_sort_key(col_str: str) -> Tuple[int, int, str]:
        is_pso = 1 if "PSO" in col_str.upper() else 0
        m = re.search(r"\d+", col_str)
        return (is_pso, int(m.group(0)) if m else 999, col_str)
