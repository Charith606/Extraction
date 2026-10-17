"""
Reference-Book Topic & Page Extractor.

Supports 3 legitimate ways to extract topic pages without needing to download pirated textbooks:
  1. Open Library API (Look up by ISBN or Book Title - Free, official, no download required)
  2. Paste-In Mode (Paste Table of Contents copied from Google Books Preview, Amazon "Look Inside", or Publisher website)
  3. Local PDF Mode (If a user uploads their own digital PDF textbook - reads Bookmarks or scanned Contents)

Usage:
  python extract_topic_pages.py --isbn 9780131103627
  python extract_topic_pages.py --title "Computer Networks"
  python extract_topic_pages.py --paste
  python extract_topic_pages.py --pdf mybook.pdf
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

# PyMuPDF is optional so the script can still run in API/Paste mode even if fitz isn't installed
try:
    import pymupdf as fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    try:
        import fitz
        PYMUPDF_AVAILABLE = True
    except ImportError:
        PYMUPDF_AVAILABLE = False


# ==============================================================================
# COMMON UTILITY: Add End Pages
# ==============================================================================
def add_end_pages(entries: List[Dict[str, Any]], total_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Computes the ending page for every topic based on when the next topic 
    of the same or higher level starts.
    """
    if not entries:
        return []

    # If total_pages isn't known, default to the highest start page + 30
    max_start = max(e["start"] for e in entries)
    fallback_total = total_pages if total_pages and total_pages >= max_start else max_start + 30

    for i, e in enumerate(entries):
        end = fallback_total
        for nxt in entries[i + 1:]:
            if nxt["level"] <= e["level"]:
                if nxt["start"] > e["start"]:
                    end = nxt["start"] - 1
                else:
                    end = e["start"]
                break
        e["end"] = max(end, e["start"])
    return entries


# ==============================================================================
# METHOD 1: Open Library API (Zero Downloads)
# ==============================================================================
OPEN_LIBRARY_USER_AGENT = "SyllabusReferenceExtractor/1.0 (academic; open-source)"


def _fetch_json(url: str, timeout: int = 8) -> Optional[Dict[str, Any]]:
    """Helper to fetch JSON safely from public APIs."""
    req = urllib.request.Request(url, headers={"User-Agent": OPEN_LIBRARY_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def extract_from_open_library(query: str, is_isbn: bool = False, author: str = "") -> Optional[Dict[str, Any]]:
    """
    Queries Open Library API for the book record and table of contents.
    Works with ISBN (e.g., '9780131103627') or Book Title (e.g., 'Artificial Intelligence').
    """
    clean_query = query.strip()
    edition_data = None
    book_title = clean_query
    total_pages = None
    ol_key = None
    author_name = author

    # Step 1: Query by ISBN or Search by Title
    if is_isbn or re.match(r"^(97(8|9))?\d{9}[\dX]$", clean_query.replace("-", "")):
        isbn_clean = clean_query.replace("-", "")
        url = f"https://openlibrary.org/isbn/{isbn_clean}.json"
        edition_data = _fetch_json(url)
        if edition_data:
            book_title = edition_data.get("title", clean_query)
            total_pages = edition_data.get("number_of_pages")
            ol_key = edition_data.get("key")
    else:
        # Clean title by removing parenthetical publisher info and separating author if formatted "Title by Author"
        clean_title = re.sub(r"\(.*?\)", "", clean_query).strip()
        if " by " in clean_title:
            parts = clean_title.split(" by ", 1)
            clean_title = parts[0].strip()
            if not author:
                author = parts[1].strip()

        clean_author = re.sub(r"\(.*?\)", "", author).replace("Dr.", "").strip()

        # Search Open Library by title and author
        params = {"title": clean_title, "limit": 3}
        if clean_author:
            params["author"] = clean_author
        search_url = f"https://openlibrary.org/search.json?{urllib.parse.urlencode(params)}"
        search_res = _fetch_json(search_url)

        if (not search_res or not search_res.get("docs")) and clean_author:
            # Fallback search by title only
            search_url = f"https://openlibrary.org/search.json?title={urllib.parse.quote(clean_title)}&limit=3"
            search_res = _fetch_json(search_url)

        if search_res and search_res.get("docs"):
            doc = search_res["docs"][0]
            book_title = doc.get("title", clean_title)
            if doc.get("author_name"):
                author_name = doc["author_name"][0]
            total_pages = doc.get("number_of_pages_median") or doc.get("number_of_pages")
            ol_key = doc.get("key")

            # Check up to 3 editions for registered TOC
            editions = doc.get("edition_key", [])
            for ed_key in editions[:3]:
                edition_url = f"https://openlibrary.org/books/{ed_key}.json"
                ed_json = _fetch_json(edition_url)
                if ed_json:
                    if not edition_data:
                        edition_data = ed_json
                    if ed_json.get("table_of_contents"):
                        edition_data = ed_json
                        break

    if not edition_data and not ol_key:
        return None

    if edition_data:
        book_title = edition_data.get("title", book_title)
        total_pages = edition_data.get("number_of_pages", total_pages)
        raw_toc = edition_data.get("table_of_contents", [])
    else:
        raw_toc = []

    # Step 2: Parse Open Library TOC into structured entries if present
    entries = []
    current_page = 1

    for item in raw_toc:
        # Open Library TOC items can be dicts or strings
        if isinstance(item, dict):
            title = item.get("title", "").strip()
            level = item.get("level", 1)
            raw_page = item.get("pagenum", "")

            # Extract page number digits if present
            page_match = re.search(r"\d+", str(raw_page))
            if page_match:
                start_page = int(page_match.group(0))
                current_page = start_page
            else:
                start_page = current_page

            if title:
                entries.append({"level": int(level), "title": title, "start": start_page})

        elif isinstance(item, str):
            clean_str = item.strip()
            # Match formats like: "1. Introduction -- 1" or "Chapter 1: Basics ... 15"
            m = re.match(r"^(?P<title>.+?)[\s\.\u00b7\u2026_-]{2,}(?P<page>\d+)\s*$", clean_str)
            if m:
                entries.append({
                    "level": 1,
                    "title": m.group("title").strip(),
                    "start": int(m.group("page"))
                })
            else:
                entries.append({
                    "level": 1,
                    "title": clean_str,
                    "start": current_page
                })
                current_page += 10

    if entries:
        entries = add_end_pages(entries, total_pages)

    return {
        "source": "Open Library API",
        "book_title": book_title,
        "author": author_name,
        "total_pages": total_pages or (entries[-1]["end"] if entries else None),
        "openlibrary_key": ol_key,
        "openlibrary_url": f"https://openlibrary.org{ol_key}" if ol_key else f"https://openlibrary.org/search?q={urllib.parse.quote(clean_query)}",
        "topics": entries
    }


# ==============================================================================
# METHOD 2: Paste-In Mode (Paste TOC from Google Books / Amazon / Publisher)
# ==============================================================================
LINE_WITH_PAGE = re.compile(
    r"^(?P<title>.+?)[\s\.\u00b7\u2026_-]{2,}(?P<page>\d{1,4})\s*$"
)

def extract_from_contents_text(raw_text: str, total_pages: Optional[int] = None) -> Dict[str, Any]:
    """
    Parses a pasted Table of Contents text snippet.
    Handles wrapped/multiline titles, dot-leaders, and chapter numbering.
    """
    entries = []
    pending_title_prefix = ""

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = LINE_WITH_PAGE.match(line)
        if m:
            full_title = f"{pending_title_prefix} {m.group('title')}".strip(" .")
            pending_title_prefix = ""

            # Guess hierarchy level from numbering (e.g. 1.2.3 -> 3, 1.2 -> 2, others -> 1)
            num = re.match(r"^(\d+(?:\.\d+)*)\s", full_title)
            level = num.group(1).count(".") + 1 if num else 1

            entries.append({
                "level": level,
                "title": full_title,
                "start": int(m.group("page"))
            })
        else:
            # Possible wrapped line of title
            if len(line) > 3 and not re.match(r"^\d+$", line):
                pending_title_prefix = line
            else:
                pending_title_prefix = ""

    entries = add_end_pages(entries, total_pages)
    return {
        "source": "Pasted Table of Contents",
        "total_pages": total_pages or (entries[-1]["end"] if entries else 0),
        "topics": entries
    }


# ==============================================================================
# METHOD 3: Local PDF File Mode (Bookmarks + Scan Fallback)
# ==============================================================================
def entries_from_pdf_bookmarks(doc: Any) -> List[Dict[str, Any]]:
    """Extracts topics from PDF's built-in outline."""
    toc = doc.get_toc()
    if not toc:
        return []

    entries = []
    for level, title, page in toc:
        if page > 0:
            clean_title = re.sub(r"\s+", " ", title).strip()
            entries.append({
                "level": level,
                "title": clean_title,
                "start": page
            })
    return entries


def fix_pdf_page_offset(doc: Any, entries: List[Dict[str, Any]], last_contents_page: int) -> int:
    """
    Finds difference between printed page number and physical PDF page.
    Searches only in a tight window [start_page, start_page + 45] to avoid false matches.
    """
    if not entries:
        return 0

    offsets = []
    total_pages = len(doc)

    for e in entries[:15]:
        short_title = re.sub(r"^\d+(?:\.\d+)*\s*", "", e["title"]).strip()
        short_title = re.sub(r"[^\w\s]", "", short_title)[:35].strip()
        if len(short_title) < 5:
            continue

        printed_page = e["start"]
        search_start = max(last_contents_page + 1, printed_page)
        search_end = min(total_pages, printed_page + 45)

        for p in range(search_start, search_end):
            if doc[p].search_for(short_title):
                offsets.append((p + 1) - printed_page)
                break

    if not offsets:
        return 0
    return Counter(offsets).most_common(1)[0][0]


def extract_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extracts topics and pages from a local PDF textbook."""
    if not PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) is required for PDF processing. Run: pip install pymupdf")

    doc = fitz.open(pdf_path)
    total = len(doc)

    entries = entries_from_pdf_bookmarks(doc)
    source = "PDF Bookmarks"

    if not entries:
        # Fallback: scan contents pages
        contents_text = ""
        last_page = 0
        for i in range(min(35, total)):
            text = doc[i].get_text()
            if len(LINE_WITH_PAGE.findall(text)) >= 3:
                contents_text += "\n" + text
                last_page = i

        parsed = extract_from_contents_text(contents_text, total_pages=total)
        entries = parsed["topics"]
        if entries:
            offset = fix_pdf_page_offset(doc, entries, last_page)
            for e in entries:
                e["start"] += offset
            entries = [e for e in entries if 1 <= e["start"] <= total]
            source = "PDF Contents Page (Scanned)"

    entries = add_end_pages(entries, total)
    doc.close()

    return {
        "source": source,
        "total_pages": total,
        "topics": entries
    }


# ==============================================================================
# UNIFIED INTERFACE
# ==============================================================================
def extract_topic_pages(
    pdf_path: Optional[str] = None,
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    toc_text: Optional[str] = None,
    total_pages: Optional[int] = None
) -> Dict[str, Any]:
    """
    Single master function for your project. Tries methods in priority order:
    1. If `toc_text` is provided -> parses pasted contents text.
    2. If `isbn` or `title` is provided -> queries Open Library API.
    3. If `pdf_path` is provided -> extracts from local PDF file.
    """
    # 1. Text Paste
    if toc_text and toc_text.strip():
        return extract_from_contents_text(toc_text, total_pages=total_pages)

    # 2. Open Library Online API (ISBN or Title)
    if isbn:
        res = extract_from_open_library(isbn, is_isbn=True)
        if res:
            return res

    if title:
        res = extract_from_open_library(title, is_isbn=False)
        if res:
            return res

    # 3. Local PDF
    if pdf_path:
        return extract_from_pdf(pdf_path)

    return {
        "source": "None",
        "total_pages": 0,
        "topics": [],
        "message": "No valid source found. Please supply a PDF, valid ISBN/Title, or paste the Table of Contents."
    }


# ==============================================================================
# CLI EXECUTION
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract reference-book topic page ranges without full downloads.")
    parser.add_argument("--pdf", help="Path to local PDF book file")
    parser.add_argument("--isbn", help="ISBN of the reference book (e.g. 9780131103627)")
    parser.add_argument("--title", help="Title of the reference book (e.g. 'Computer Networks')")
    parser.add_argument("--paste", action="store_true", help="Interactive paste mode for Table of Contents")

    args = parser.parse_args()

    result = None

    if args.paste:
        print("\n--- Paste Table of Contents below. Press Enter twice or Ctrl+D / Ctrl+Z when done ---")
        lines = []
        try:
            while True:
                line = input()
                if not line and lines and not lines[-1]:
                    break
                lines.append(line)
        except EOFError:
            pass
        pasted_text = "\n".join(lines)
        result = extract_from_contents_text(pasted_text)

    elif args.isbn:
        print(f"Searching Open Library for ISBN: {args.isbn}...")
        result = extract_from_open_library(args.isbn, is_isbn=True)
        if not result:
            print("No Table of Contents record found on Open Library for this ISBN.")
            print("Tip: Use Google Books preview / Amazon and try '--paste' mode!")

    elif args.title:
        print(f"Searching Open Library for Title: '{args.title}'...")
        result = extract_from_open_library(args.title, is_isbn=False)
        if not result:
            print("No Table of Contents record found on Open Library for this title.")
            print("Tip: Use Google Books preview / Amazon and try '--paste' mode!")

    elif args.pdf:
        print(f"Processing PDF: {args.pdf}...")
        result = extract_from_pdf(args.pdf)

    else:
        parser.print_help()
        sys.exit(0)

    if result and result.get("topics"):
        print(f"\nSource: {result['source']} | Total Pages: {result.get('total_pages', 'N/A')}\n")
        for t in result["topics"]:
            indent = "  " * (t["level"] - 1)
            print(f"{indent}• {t['title']}  ->  pages {t['start']} to {t['end']}")

        with open("topic_pages.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print("\nSaved output to topic_pages.json")
