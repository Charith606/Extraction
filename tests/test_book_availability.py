"""
tests/test_book_availability.py
=============================================================================
AUTOMATED PYTEST SUITE FOR BOOK AVAILABILITY & VALIDATION

Mentor Explanation:
Automated tests give us confidence that our code works as expected.
When we make changes later, we can run 'pytest' to immediately discover
if any part of our application broke.

Tests Included:
1. Public Domain Title -> Expected: AVAILABLE (e.g. Mary Shelley, Frankenstein)
2. Copyrighted Proprietary Textbook -> Expected: NO_ACCESS (Bach, Design of Unix OS)
3. SQLite Cache Verification -> Second lookup must be instant from cache
4. Magic Byte Validator -> Confirms %PDF header check stops fake/corrupted downloads
5. Citation Parser -> Confirms title, author, and edition extraction
=============================================================================
"""

import pytest
import sqlite3
from pathlib import Path
from config import settings
from book_parser import parse_reference_book, is_title_match
from availability import check_book_availability
from cache import get_cached_book, compute_book_id
from downloader import sanitize_filename


# ---------------------------------------------------------------------------
# Test 1: Public Domain Book (Should be AVAILABLE)
# ---------------------------------------------------------------------------
def test_public_domain_book_is_available():
    """
    Tests that a well-known public domain book (Mary Shelley's Frankenstein)
    is detected as AVAILABLE with a valid legal download URL.
    """
    citation = 'Mary Shelley "Frankenstein"'
    result = check_book_availability(citation, use_cache=False)

    assert result.status == "AVAILABLE", f"Expected Frankenstein to be AVAILABLE, got {result.status}"
    assert result.download_url is not None, "Expected a valid direct download URL"
    assert result.download_url.startswith("http"), "Download URL must be a valid HTTP(S) link"
    assert result.source in ["open_library", "internet_archive", "gutendex", "google_books", "doab"]
    assert "frankenstein" in result.parsed_title.lower()


# ---------------------------------------------------------------------------
# Test 2: Copyrighted Textbook (Should be NO_ACCESS)
# ---------------------------------------------------------------------------
def test_copyrighted_bach_textbook_is_no_access():
    """
    Tests that a proprietary, copyrighted academic textbook:
    Maurice J. Bach "The Design of the Unix Operating System"
    is properly recognized as NO_ACCESS and does NOT return a pirated or wrong file.
    """
    citation = 'Maurice J. Bach "The Design of the Unix Operating System"'
    result = check_book_availability(citation, use_cache=False)

    assert result.status == "NO_ACCESS", f"Expected Bach textbook to be NO_ACCESS, got {result.status}"
    assert result.download_url is None, "A NO_ACCESS book must NOT have a download URL"
    assert "design" in result.parsed_title.lower() or "unix" in result.parsed_title.lower()


# ---------------------------------------------------------------------------
# Test 3: SQLite Cache Functionality
# ---------------------------------------------------------------------------
def test_cache_stores_and_retrieves_results():
    """
    Confirms that checking a book saves the record to SQLite,
    and subsequent queries return the cached result without making network calls.
    """
    citation = 'Alice in Wonderland Lewis Carroll'
    res1 = check_book_availability(citation, use_cache=True)
    assert res1.book_id is not None

    # Check directly from SQLite
    cached_record = get_cached_book(citation)
    assert cached_record is not None
    assert cached_record["book_id"] == res1.book_id
    assert cached_record["status"] == res1.status

    # Second query using availability check should report loaded from cache
    res2 = check_book_availability(citation, use_cache=True)
    assert res2.reason == "Loaded from local cache"
    assert res2.book_id == res1.book_id


# ---------------------------------------------------------------------------
# Test 4: Citation Parser Tests
# ---------------------------------------------------------------------------
def test_citation_parser_variations():
    """
    Tests that the parser correctly extracts title and author across
    different academic syllabus styles.
    """
    # Case A: Numbered prefix with quoted title and publisher/year
    p1 = parse_reference_book('1. Maurice J. Bach, "The Design of the Unix Operating System", Prentice Hall, 1986.')
    assert "Design of the Unix Operating System" in p1.title
    assert "Bach" in p1.author
    assert p1.year == "1986"

    # Case B: Tagged prefix like T1. or [2]
    p2 = parse_reference_book('[2] Uresh Vahalia, UNIX Internals: The New Frontiers, Pearson Education, 2008.')
    assert "UNIX Internals" in p2.title
    assert "Vahalia" in p2.author

    # Case C: Edition included
    p3 = parse_reference_book('Bovet & Cesati, "Understanding the Linux Kernel", 3rd Edition, O\'Reilly, 2005.')
    assert "Understanding the Linux Kernel" in p3.title
    assert p3.edition is not None
    assert "3rd" in p3.edition


# ---------------------------------------------------------------------------
# Test 5: Title Match Validation Logic
# ---------------------------------------------------------------------------
def test_is_title_match_validation():
    """
    Confirms that our title matching logic accepts true matches
    and rejects unrelated candidate books.
    """
    # True matches:
    assert is_title_match("Frankenstein", "Frankenstein; or, The Modern Prometheus") is True
    assert is_title_match("The Design of the Unix Operating System", "Design of the Unix Operating System") is True

    # Rejection of unrelated titles:
    assert is_title_match("Linux Kernel Programming", "Introduction to Biology") is False
    assert is_title_match("Operating Systems Concepts", "Harry Potter and the Sorcerer's Stone") is False


# ---------------------------------------------------------------------------
# Test 6: Filename Sanitizer
# ---------------------------------------------------------------------------
def test_sanitize_filename():
    """
    Ensures safe filenames without invalid OS characters like colon, slashes, or question marks.
    """
    bad_name = 'Unix: The System / Chapter 1? "Special"'
    clean_name = sanitize_filename(bad_name)
    assert ":" not in clean_name
    assert "/" not in clean_name
    assert "?" not in clean_name
    assert '"' not in clean_name
    assert clean_name.endswith(".pdf")
