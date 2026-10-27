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

    # Step 3: High-precision title and author extraction via unified parser
    from reference_book_engine import _parse_book_citation
    author, title = _parse_book_citation(cleaned_raw)

    if not title or title.lower() in {'resource document', 'manual'}:
        title = cleaned or (direct_url or "Resource Document")

    # Filter out placeholder or corrupted authors
    clean_auth = author.strip(" \"'")
    if clean_auth in {"Unknown Author", "I", "II", "III", "IV", "V", "Writing"} or clean_auth.lower() == title.lower():
        clean_auth = ""

    return ParsedBook(
        raw_citation=raw_citation,
        title=title.strip(" \"'"),
        author=clean_auth,
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
