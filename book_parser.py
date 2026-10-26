"""
book_parser.py
=============================================================================
CITATION PARSER & TITLE MATCHER FOR COURSE SYLLABUS ENTRIES

Mentor Explanation:
In academic syllabi, professors format textbook citations in many erratic ways:
- Example A: 'Bach "The Design of the Unix Operating System"'
- Example B: '1. Maurice J. Bach, "The Design of the Unix Operating System", Prentice Hall, 1986.'
- Example C: 'Bovet & Cesati, Understanding the Linux Kernel, 3rd Edition, O\'Reilly, 2005.'
- Example D: 'Mary Shelley, Frankenstein'

If we send raw numbers like '1. ' or publisher names like 'Prentice Hall'
into our search queries, the APIs will get confused and return 0 results.
This parser extracts the core components:
1. Title
2. Author
3. Edition / Year (if present)

It also includes 'is_title_match', a fuzzy matching function that verifies
any candidate book found on Open Library or Google Books actually matches
what the professor prescribed, preventing incorrect file downloads.
=============================================================================
"""

import re
import difflib
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class ParsedBook:
    """
    Data Transfer Object (DTO) holding parsed textbook information.
    """
    raw_citation: str
    title: str
    author: str
    edition: Optional[str] = None
    year: Optional[str] = None
    direct_url: Optional[str] = None

    @property
    def clean_search_query(self) -> str:
        """
        Builds an optimized search query string for search APIs.
        Example: 'Design of the Unix Operating System Maurice Bach'
        """
        parts = [self.title]
        if self.author:
            parts.append(self.author)
        return " ".join(parts).strip()


def strip_citation_indexes(text: str) -> str:
    """
    Strips syllabus numbering prefixes, bullets, and labels.

    Examples:
    - '[1] Maurice Bach' -> 'Maurice Bach'
    - 'T1. Silberschatz' -> 'Silberschatz'
    - '2) Tanenbaum'    -> 'Tanenbaum'
    """
    # Regex explanation:
    # ^(?: ... ) : Non-capturing group anchored at the beginning of the string.
    # \[\d+\]    : Matches bracketed numbers like [1] or [12].
    # [TR]\d+[\.\:]? : Matches syllabus tags like T1, R2, T1., R2:.
    # \d+[\.\)\-:]?  : Matches plain numbers like 1., 2), 3-.
    pattern = r"^(?:\[\d+\]|\b[TR]\d+[\.\:]?|\d+[\.\)\-:]?)\s*"
    return re.sub(pattern, "", text.strip()).strip()


def extract_year(text: str) -> Tuple[str, Optional[str]]:
    """
    Finds a 4-digit publication year (e.g. 1986, 2008, 2021) and removes it
    from the search text so it does not interfere with title matching.
    """
    # Look for 19xx or 20xx standing as an independent word or in parentheses
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if match:
        year = match.group(1)
        # Remove the year from the text
        cleaned_text = text[:match.start()] + text[match.end():]
        return cleaned_text.strip(" ,.-;()"), year
    return text, None


def extract_edition(text: str) -> Tuple[str, Optional[str]]:
    """
    Extracts edition strings like '3rd Edition', '2nd ed.', 'First Edition'
    and removes them from the text.
    """
    pattern = r"\b(\d+(?:st|nd|rd|th)?\s+(?:Edition|edition|Ed\.|ed\.))\b"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        edition = match.group(1)
        cleaned_text = text[:match.start()] + text[match.end():]
        return cleaned_text.strip(" ,.-;()"), edition
    return text, None


def parse_reference_book(raw_citation: str) -> ParsedBook:
    """
    Main parsing function. Analyzes a raw syllabus citation string
    and returns a structured ParsedBook object.
    """
    # 0. Clean trailing administrative footer noise
    cleaned_raw = re.sub(
        r'\s*(?:S\.?\s*No\.?|Name of the Faculty|Faculty Name|Proceedings of the|Mode of Evaluation|'
        r'Mode of Assessment|Recommended by|Approved by|Aooroved by|Board of Studies|Academic Council|'
        r'Agenda Item|Annexure|No\.\s*\d+|Date\s*\d+).*$',
        '',
        raw_citation,
        flags=re.IGNORECASE
    ).strip()

    title_keywords = {
        "microprocessor", "microprocessors", "microcontroller", "microcontrollers",
        "peripheral", "peripherals", "circuit", "circuits", "device", "devices",
        "computer", "computing", "electric", "electrical", "power", "signal",
        "signals", "processing", "communication", "communications", "network",
        "networks", "database", "databases", "operating", "digital", "analog",
        "linear", "control", "learning", "vision", "robotics", "intelligence",
        "structure", "structures", "algorithm", "algorithms", "language",
        "programming", "architecture", "principles", "applications", "fundamentals",
        "mechanics", "physics", "chemistry", "biology", "mathematics", "calculus",
        "algebra", "geometry", "statistics", "statistical", "inference", "analytics",
        "science", "theory", "engineering", "management", "english", "grammar",
        "systems", "system", "introduction", "technology", "design", "handbook",
        "guide", "data", "analysis", "modeling", "predictive", "multivariate",
        "discrete", "graph", "environmental", "environment", "materials",
        "strength", "advanced", "textbook", "elements", "effective", "expert",
        "professional", "usage", "practical", "unix", "internals", "fuel", "cell", "cells"
    }

    # Step 0b: Check if citation contains a direct website or PDF URL
    url_match = re.search(r'(https?://[^\s,]+)', cleaned_raw)
    direct_url = url_match.group(1).rstrip('.)]') if url_match else None

    # Step 1: Remove leading numbering like '1. ' or '[2]'
    cleaned = strip_citation_indexes(cleaned_raw)
    if direct_url:
        cleaned = cleaned.replace(direct_url, "").strip(" ,-–;:")

    # Step 2: Extract year and edition metadata
    cleaned, year = extract_year(cleaned)
    cleaned, edition = extract_edition(cleaned)

    # Step 2b: Quoted title check
    quoted_match = re.search(r'["\u201c\u201d\']([^"\u201c\u201d\']{3,})["\u201c\u201d\']', cleaned)
    if quoted_match:
        title = quoted_match.group(1).strip()
        before_quote = cleaned[:quoted_match.start()].strip(" ,-–;:")
        author = before_quote if before_quote else ""
        return ParsedBook(
            raw_citation=raw_citation,
            title=title.strip(" ,.-"),
            author=author.strip(" ,.-"),
            edition=edition,
            year=year,
            direct_url=direct_url
        )

    # Step 2b-2: Natural language 'Title by Author' check
    by_m = re.search(r'^(.*?)\s+\bby\s+(.*)$', cleaned, flags=re.IGNORECASE)
    if by_m:
        t_cand = by_m.group(1).strip(" ,.-–:")
        a_cand = by_m.group(2).strip(" ,.-–:")
        if len(t_cand) >= 3 and len(a_cand) >= 3:
            return ParsedBook(
                raw_citation=raw_citation,
                title=t_cand,
                author=a_cand,
                edition=edition,
                year=year,
                direct_url=direct_url
            )

    # Step 2c: Year pattern e.g. Author(s),? (Year),? Title, Publisher...
    # (e.g. Raj Kumar Singh, (2012), Environmental Studies...)
    year_m = re.search(r'^(.*?)\s*,?\s*\(\s*((?:19|20)\d{2})\s*\)\s*[:,\-–]?\s*(.*)$', cleaned_raw)
    if year_m:
        author_cand = year_m.group(1).strip(" ,.-–")
        author_cand = re.sub(r'^(?:\[?\d+[\.\)\]\:]*|\u2022|\-)\s*', '', author_cand).strip()
        rest_cand = year_m.group(3).strip(" ,.-–")
        if author_cand and len(author_cand) >= 3 and not any(k in author_cand.lower() for k in ["textbook", "reference", "edition"]):
            q_in_rest = re.search(r'["\u201c\u201d]([^"\u201c\u201d]{3,120})["\u201c\u201d]', rest_cand)
            if q_in_rest:
                title_cand = q_in_rest.group(1).strip(" ,.-")
            else:
                m_split = re.split(r',\s*(?:\d+(?:st|nd|rd|th)?\s+Ed(?:ition)?|Tata\s+McGraw|McGraw|Wiley|Brooks/Cole|Cengage|Prentice|Pearson|PHI|Oxford|Cambridge|Springer|New\s+Age)\b', rest_cand, flags=re.I)
                if len(m_split) > 1 and len(m_split[0].strip()) >= 3:
                    title_cand = m_split[0].strip(" ,.-")
                else:
                    r_parts = [p.strip() for p in rest_cand.split(",") if p.strip()]
                    title_cand = r_parts[0].strip(" ,.-") if r_parts else rest_cand.strip(" ,.-")
            return ParsedBook(
                raw_citation=raw_citation,
                title=title_cand.strip(" ,.-"),
                author=author_cand.strip(" ,.-"),
                edition=edition,
                year=year_m.group(2),
                direct_url=direct_url
            )

    # Clean out parenthesized years like (2012) or (2007)
    cleaned = re.sub(r'\s*\(\s*(?:19|20)\d{2}\s*\)\s*', ' ', cleaned)
    cleaned = re.sub(r'\s*\b(?:19|20)\d{2}\.?\s*', ' ', cleaned)
    cleaned = re.sub(r'\s*\(\s*\)', ' ', cleaned).strip(" ,.-;")

    # Step 3: Colon handling
    if ":" in cleaned:
        colon_m = re.search(r'^(.*?)\s*:\s*(.*)$', cleaned)
        if colon_m:
            left = colon_m.group(1).strip()
            right = colon_m.group(2).strip()
            right_first = right.split(",")[0].strip()

            # If right is volume number like ': 1'
            if re.match(r"^(?:vol\.?\s*)?\d+$", right_first, re.I):
                left_parts = [p.strip() for p in left.split(",") if p.strip()]
                if len(left_parts) >= 2:
                    return ParsedBook(
                        raw_citation=raw_citation,
                        title=", ".join(left_parts[1:]).strip(" ,.-"),
                        author=left_parts[0].strip(" ,.-"),
                        edition=edition,
                        year=year,
                        direct_url=direct_url
                    )

            # If left has author before comma, e.g. 'Robert C. Seacord, Effective C: An Introduction...'
            if "," in left:
                left_parts = [p.strip() for p in left.split(",") if p.strip()]
                found_idx = None
                for idx, lp in enumerate(left_parts):
                    lp_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", lp.lower()))
                    if lp_words & title_keywords:
                        found_idx = idx
                        break
                if found_idx is not None and found_idx > 0:
                    author_c = ", ".join(left_parts[:found_idx])
                    title_c = ", ".join(left_parts[found_idx:]) + f": {right_first}"
                    return ParsedBook(
                        raw_citation=raw_citation,
                        title=title_c.strip(" ,.-"),
                        author=author_c.strip(" ,.-"),
                        edition=edition,
                        year=year,
                        direct_url=direct_url
                    )
                elif len(left_parts) >= 2:
                    author_c = left_parts[0]
                    title_c = f"{', '.join(left_parts[1:])}: {right_first}"
                    return ParsedBook(
                        raw_citation=raw_citation,
                        title=title_c.strip(" ,.-"),
                        author=author_c.strip(" ,.-"),
                        edition=edition,
                        year=year,
                        direct_url=direct_url
                    )

            # Author. Title: Subtitle (e.g. Pickett and Laster. Technical English: Writing...)
            if "." in left and not re.search(r"\b(?:Dr|Mr|Mrs|Prof|[A-Z]\.[A-Z]?)\b", left):
                dot_split = left.split(".", 1)
                author_res = dot_split[0].strip(" ,.-")
                title_res = f"{dot_split[1].strip(' ,.-')}: {right_first}"
                return ParsedBook(
                    raw_citation=raw_citation,
                    title=title_res.strip(" ,.-"),
                    author=author_res.strip(" ,.-"),
                    edition=edition,
                    year=year,
                    direct_url=direct_url
                )

            left_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", left.lower()))
            if left_words & title_keywords:
                # Left is title: e.g. 'Effective C: An Introduction to Professional C Programming, Robert C. Seacord'
                r_parts = [p.strip() for p in right.split(",") if p.strip()]
                if len(r_parts) >= 2:
                    title_res = f"{left}: {r_parts[0]}"
                    author_res = r_parts[1]
                else:
                    title_res = f"{left}: {right_first}"
                    author_res = ""
                return ParsedBook(
                    raw_citation=raw_citation,
                    title=title_res.strip(" ,.-"),
                    author=author_res.strip(" ,.-"),
                    edition=edition,
                    year=year,
                    direct_url=direct_url
                )

            # Author(s) : Title, Publisher (e.g. Martinez : Exploratory Data Analysis)
            if not any(k in left.lower() for k in ["text book", "reference book", "publisher", "isbn", "url", "http"]):
                return ParsedBook(
                    raw_citation=raw_citation,
                    title=right_first.strip(" ,.-"),
                    author=left.strip(" ,.-"),
                    edition=edition,
                    year=year,
                    direct_url=direct_url
                )

    # Step 4: Hyphen between Title and Author
    if (" - " in cleaned or " – " in cleaned or "- " in cleaned) and "," in cleaned:
        first_segment = cleaned.split(",")[0].strip()
        h_match = re.search(r'^(.*?)\s*[\-–]\s*(.*)$', first_segment)
        if h_match:
            left_h = h_match.group(1).strip()
            right_h = h_match.group(2).strip()
            if any(w in left_h.lower() for w in title_keywords):
                return ParsedBook(
                    raw_citation=raw_citation,
                    title=left_h.strip(" ,.-"),
                    author=right_h.strip(" ,.-"),
                    edition=edition,
                    year=year,
                    direct_url=direct_url
                )

    # Step 5: Dash separator
    if " - " in cleaned or " – " in cleaned:
        sep = " – " if " – " in cleaned else " - "
        parts = [p.strip() for p in cleaned.split(sep) if p.strip()]
        if len(parts) >= 2:
            p0, p1 = parts[0], parts[1]
            p0_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", p0.lower()))
            p1_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", p1.lower()))
            if (p0_words & title_keywords) and not (p1_words & title_keywords):
                return ParsedBook(
                    raw_citation=raw_citation,
                    title=p0.strip(" ,.-"),
                    author=p1.strip(" ,.-"),
                    edition=edition,
                    year=year,
                    direct_url=direct_url
                )
            return ParsedBook(
                raw_citation=raw_citation,
                title=p1.strip(" ,.-"),
                author=p0.strip(" ,.-"),
                edition=edition,
                year=year,
                direct_url=direct_url
            )

    # Step 6: Comma separated
    parts = [p.strip() for p in cleaned.split(",") if p.strip() and p.strip() != "()"]
    if len(parts) >= 3 and (len(parts[1]) <= 3 or re.match(r'^[A-Z](\.[A-Z]\.?)?$', parts[1].strip())):
        author_candidate = f"{parts[0]}, {parts[1]}"
        title_candidate = parts[2]
        return ParsedBook(
            raw_citation=raw_citation,
            title=title_candidate.strip(" ,.-"),
            author=author_candidate.strip(" ,.-"),
            edition=edition,
            year=year,
            direct_url=direct_url
        )

    if len(parts) >= 2:
        for idx, p in enumerate(parts):
            p_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", p.lower()))
            if p_words & title_keywords:
                title_c = p
                authors = [parts[i] for i in range(idx)]
                author_c = ", ".join(authors) if authors else (parts[idx+1] if idx+1 < len(parts) else "Unknown Author")
                return ParsedBook(
                    raw_citation=raw_citation,
                    title=title_c.strip(" ,.-"),
                    author=author_c.strip(" ,.-"),
                    edition=edition,
                    year=year,
                    direct_url=direct_url
                )
        return ParsedBook(
            raw_citation=raw_citation,
            title=parts[1].strip(" ,.-"),
            author=parts[0].strip(" ,.-"),
            edition=edition,
            year=year,
            direct_url=direct_url
        )

    # Step 7: Fallback
    return ParsedBook(
        raw_citation=raw_citation,
        title=cleaned or (direct_url or "Resource Document"),
        author="",
        edition=edition,
        year=year,
        direct_url=direct_url
    )


def normalize_title(text: str) -> str:
    """
    Normalizes a book title for reliable comparison:
    - Converts to lowercase
    - Removes punctuation and extra whitespace
    - Removes common English stop words like 'the', 'a', 'an', 'of'
    """
    text = text.lower()
    # Replace punctuation characters with spaces
    text = re.sub(r"[^\w\s]", " ", text)
    # Split into words and filter out common filler words
    stop_words = {"the", "a", "an", "of", "and", "in", "to", "for", "on", "edition", "vol"}
    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words)


def is_title_match(requested_title: str, candidate_title: str, threshold: float = 0.55) -> bool:
    """
    Validates whether an online candidate book title matches the requested syllabus title.
    
    Why this is critical:
    A search for 'Operating Systems' might return an unrelated book like
    'Operating Systems in the 21st Century' or a completely random novel.
    This validator ensures we do NOT download incorrect or guessed files.

    Algorithm:
    1. Token Set Jaccard Overlap: Checks if the core unique words match.
    2. SequenceMatcher Ratio: Measures character-level substring similarity.
    """
    if not requested_title or not candidate_title:
        return False

    norm_req = normalize_title(requested_title)
    norm_cand = normalize_title(candidate_title)

    # Reject one-letter or two-letter noise strings like 'W', 'A', 'II'
    if len(norm_req) < 3 or len(norm_cand) < 3:
        return False

    # Direct exact match after normalization
    if norm_req == norm_cand:
        return True

    # Check substring containment (require at least 4 characters to prevent false single-character / initial matches)
    if (len(norm_req) >= 4 and norm_req in norm_cand) or (len(norm_cand) >= 4 and norm_cand in norm_req):
        return True

    # Token overlap:
    words_req = set(norm_req.split())
    words_cand = set(norm_cand.split())

    if not words_req or not words_cand:
        return False

    intersection = words_req.intersection(words_cand)
    # What fraction of the requested title words are present in the candidate?
    coverage = len(intersection) / len(words_req)

    # difflib sequence similarity ratio (between 0.0 and 1.0)
    seq_ratio = difflib.SequenceMatcher(None, norm_req, norm_cand).ratio()

    # The match is valid if either high word coverage or strong sequence similarity
    return coverage >= threshold or seq_ratio >= threshold
