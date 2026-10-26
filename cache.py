"""
cache.py
=============================================================================
SQLITE PERSISTENT CACHE FOR BOOK AVAILABILITY

Mentor Explanation:
Why do we need a cache?
When a student opens a syllabus, there might be 5 to 10 textbooks listed.
Without a cache, every page refresh or click would make multiple HTTP network
calls to Open Library, Internet Archive, Google Books, etc.
That wastes bandwidth, slows down the user interface, and can trigger HTTP 429
(Rate Limit / Too Many Requests) errors from free public APIs.

Why SQLite instead of Redis or PostgreSQL?
1. Built into Python: Python includes the 'sqlite3' module in its standard
   library. No 'pip install' or background daemon (like redis-server) required!
2. Single-file storage: The whole database is just one file on disk
   ('book_availability_cache.db'). You can easily back it up or delete it.
3. Fast & ACID compliant: SQLite handles thousands of reads per second,
   which is more than enough for our syllabus project.
=============================================================================
"""

import sqlite3
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from config import settings


def compute_book_id(raw_citation: str) -> str:
    """
    Computes a deterministic, unique 16-character hexadecimal ID for any book citation.

    Syntax explanation:
    - .strip().lower(): Normalizes whitespace and capitalization so that
      'Bach Unix' and '  bach unix  ' produce the exact same ID.
    - hashlib.sha256(...): Cryptographic hash function. It turns any input string
      into a fixed 64-character hash.
    - [:16]: We slice the first 16 characters to give us a short, clean, URL-safe ID.
    """
    normalized = " ".join(raw_citation.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def get_db_connection() -> sqlite3.Connection:
    """
    Creates and returns a connection to the SQLite database.

    Syntax explanation:
    - settings.DATABASE_PATH: Path object from config.py.
    - check_same_thread=False: SQLite by default restricts connections to the
      thread that created them. In web servers like FastAPI, different threads
      might handle requests, so we set check_same_thread=False to avoid crashes.
    - conn.row_factory = sqlite3.Row: By default, sqlite3 returns tuples: (val1, val2).
      Setting row_factory to sqlite3.Row allows accessing columns by name: row['status']!
    """
    conn = sqlite3.connect(str(settings.DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Initializes the database schema if it does not already exist.
    Called once when the application starts up.
    """
    # The 'with' statement guarantees the connection will commit and close cleanly
    # even if an unexpected error occurs during table creation.
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # CREATE TABLE IF NOT EXISTS:
        # Idempotent command; running this multiple times will never overwrite
        # or delete existing cached records.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS book_availability (
                book_id TEXT PRIMARY KEY,
                raw_citation TEXT NOT NULL,
                parsed_title TEXT NOT NULL,
                parsed_author TEXT NOT NULL,
                status TEXT NOT NULL,         -- 'AVAILABLE' or 'NO_ACCESS'
                source TEXT,                  -- 'open_library', 'internet_archive', etc.
                download_url TEXT,            -- Direct legal PDF URL (if AVAILABLE)
                preview_url TEXT,             -- Secondary preview/borrow link
                file_size_bytes INTEGER,      -- Known or probed byte size
                checked_at TEXT NOT NULL      -- ISO 8601 formatted timestamp
            );
            """
        )

        # Indexing book_id ensures lookups take less than 1 millisecond
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_book_id ON book_availability (book_id);
            """
        )
        conn.commit()


def get_cached_book(raw_citation: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a cached check result using the raw citation string.
    Returns a dictionary of column names and values, or None if not cached yet.
    """
    book_id = compute_book_id(raw_citation)
    return get_cached_book_by_id(book_id)


def get_cached_book_by_id(book_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a cached check result by its 16-character book ID.
    Used by the download route: GET /api/download/{id}.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT book_id, raw_citation, parsed_title, parsed_author,
                   status, source, download_url, preview_url,
                   file_size_bytes, checked_at
            FROM book_availability
            WHERE book_id = ?
            LIMIT 1;
            """,
            (book_id,),  # Parameterized query with '?' protects against SQL injection attacks!
        )
        row = cursor.fetchone()

        if row is None:
            return None

        # Convert the sqlite3.Row object to a standard Python dictionary
        return dict(row)


def save_book_cache(
    raw_citation: str,
    parsed_title: str,
    parsed_author: str,
    status: str,
    source: Optional[str] = None,
    download_url: Optional[str] = None,
    preview_url: Optional[str] = None,
    file_size_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Saves or updates the availability check for a book in the SQLite database.

    Syntax explanation:
    - INSERT OR REPLACE INTO: If a record with the same book_id already exists,
      SQLite will replace it with the refreshed data.
    - datetime.utcnow().isoformat(): Generates standard ISO timestamp (e.g. '2026-10-24T05:30:00').
    """
    book_id = compute_book_id(raw_citation)
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO book_availability (
                book_id, raw_citation, parsed_title, parsed_author,
                status, source, download_url, preview_url,
                file_size_bytes, checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                book_id,
                raw_citation,
                parsed_title,
                parsed_author,
                status,
                source,
                download_url,
                preview_url,
                file_size_bytes,
                now_iso,
            ),
        )
        conn.commit()

    return {
        "book_id": book_id,
        "raw_citation": raw_citation,
        "parsed_title": parsed_title,
        "parsed_author": parsed_author,
        "status": status,
        "source": source,
        "download_url": download_url,
        "preview_url": preview_url,
        "file_size_bytes": file_size_bytes,
        "checked_at": now_iso,
    }


# Automatically ensure table exists when this module is imported
init_db()
