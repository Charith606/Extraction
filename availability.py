"""
availability.py
=============================================================================
LEGAL BOOK PDF AVAILABILITY ENGINE

Mentor Explanation:
Our objective is to verify whether a genuine, free, legally downloadable PDF
of the prescribed book exists online.
Crucially:
- We do NOT guess or scrape piracy sites.
- We do NOT return syllabi or study-guide pamphlets when the user wants the book.
- Borrow-only or preview-only books must be treated as NO_ACCESS
  (while keeping the preview link handy for students to read online).

Availability Check Order (stops at the first confirmed legal PDF):
a. Open Library search.json (checks ebook_access == 'public' and reads the 'ia' id)
b. Internet Archive Metadata API (verifies a real PDF file exists, builds direct URL)
c. Google Books API (checks accessInfo.pdf.isAvailable and downloadLink)
d. Gutendex (Project Gutenberg public-domain repository)
e. DOAB / OAPEN (Directory of Open Access Books)

Library Choice Explanation:
Why httpx over requests?
- 'requests' is synchronous and blocking. If a request takes 5 seconds, the
  entire Python process halts during that time.
- 'httpx' is a modern HTTP client supporting both synchronous and asynchronous
  calls (async/await), connection pooling, and HTTP/2 support. It integrates
  cleanly with modern async web frameworks like FastAPI.
=============================================================================
"""

import os
import re
import urllib.parse
import httpx
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from config import BASE_DIR, settings
from book_parser import ParsedBook, parse_reference_book, is_title_match
from cache import get_cached_book, save_book_cache

# Set up clean logging for debugging and audit trails
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("availability_engine")


@dataclass
class AvailabilityResult:
    """
    Standardized result structure returned by availability checks.
    """
    status: str                  # 'AVAILABLE' or 'NO_ACCESS'
    source: Optional[str]        # 'open_library', 'internet_archive', 'google_books', etc.
    download_url: Optional[str]  # Direct validated PDF URL
    preview_url: Optional[str]   # Secondary preview or borrow URL
    book_id: str                 # Unique 16-char identifier
    parsed_title: str            # Cleaned title
    parsed_author: str           # Cleaned author
    file_size_bytes: Optional[int] = None
    reason: Optional[str] = None # Explanatory note (e.g. 'Copyright restricted')


# ===========================================================================
# Source A: Open Library Search API
# ===========================================================================
def check_open_library(parsed: ParsedBook) -> Tuple[Optional[AvailabilityResult], Optional[str]]:
    """
    Queries Open Library search API (https://openlibrary.org/search.json).

    Legal check rules:
    - ebook_access == "public": Book is in the public domain or openly licensed.
    - ebook_access == "borrowable": Requires digital lending; NOT a free download.
    - ebook_access == "printdisabled": Restricted access.
    
    Returns:
    (AvailabilityResult if a confirmed public IA id is found, or None,
     candidate_preview_url if available)
    """
    search_url = "https://openlibrary.org/search.json"
    headers = {"User-Agent": settings.USER_AGENT}
    params = {
        "title": parsed.title,
        "limit": 5
    }
    if parsed.author:
        params["author"] = parsed.author

    preview_link: Optional[str] = None

    try:
        # httpx.Client with an explicit timeout prevents our app from hanging
        with httpx.Client(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.get(search_url, params=params, headers=headers)

            # Handle rate limiting or server errors gracefully
            if resp.status_code == 429:
                logger.warning("Open Library rate limit (HTTP 429) encountered.")
                return None, None
            if resp.status_code != 200:
                logger.warning(f"Open Library returned HTTP {resp.status_code}")
                return None, None

            data = resp.json()
            docs: List[Dict[str, Any]] = data.get("docs", [])

            for doc in docs:
                candidate_title = doc.get("title", "")
                if not is_title_match(parsed.title, candidate_title):
                    continue  # Skip unrelated books

                # Check if Open Library has an edition key for preview
                key = doc.get("key")
                if key and not preview_link:
                    preview_link = f"https://openlibrary.org{key}"

                ebook_access = doc.get("ebook_access", "").lower()
                ia_identifiers = doc.get("ia", [])

                # Strict Rule: Only "public" counts as freely downloadable
                if ebook_access == "public" and ia_identifiers:
                    # Found a public domain or open-access book on Internet Archive
                    primary_ia_id = ia_identifiers[0]
                    # Step B: Verify the actual PDF exists on Internet Archive metadata
                    ia_result = check_internet_archive_metadata(primary_ia_id, parsed.title)
                    if ia_result:
                        return ia_result, preview_link

            return None, preview_link

    except httpx.TimeoutException:
        logger.warning(f"Open Library query timed out for '{parsed.title}'.")
        return None, None
    except Exception as exc:
        logger.warning(f"Open Library error for '{parsed.title}': {exc}")
        return None, None


# ===========================================================================
# Source B: Internet Archive Metadata API
# ===========================================================================
def check_internet_archive_metadata(ia_identifier: str, expected_title: str) -> Optional[AvailabilityResult]:
    """
    Queries the Internet Archive Metadata API (https://archive.org/metadata/{identifier}).
    Confirms a real, downloadable PDF file exists and builds the direct URL:
    https://archive.org/download/{identifier}/{filename}
    """
    meta_url = f"https://archive.org/metadata/{ia_identifier}"
    headers = {"User-Agent": settings.USER_AGENT}

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(meta_url, headers=headers)
            if resp.status_code != 200:
                return None

            data = resp.json()
            # Double check item title if present in metadata
            item_meta = data.get("metadata", {})
            item_title = item_meta.get("title", expected_title)

            # Strict check: Reject borrow-only / loan-protected items
            is_restricted = bool(item_meta.get("access-restricted-item")) or any(
                term in str(item_meta.get("collection", [])).lower()
                for term in ["printdisabled", "inlibrary", "lendinglibrary"]
            )
            if is_restricted:
                return None

            # Confirm title similarity
            if not is_title_match(expected_title, item_title):
                return None

            files = data.get("files", [])
            # Prioritize Text PDF or standard readable PDF files
            for f in files:
                fname = f.get("name", "")
                format_type = f.get("format", "")
                size = int(f.get("size", 0)) if str(f.get("size", "")).isdigit() else 0

                # Ensure it's a PDF and not an encrypted / loan-protected file
                if fname.lower().endswith(".pdf") and "encrypted" not in fname.lower():
                    # Direct download URL
                    direct_url = f"https://archive.org/download/{ia_identifier}/{fname}"
                    preview_url = f"https://archive.org/details/{ia_identifier}"

                    return AvailabilityResult(
                        status="AVAILABLE",
                        source="internet_archive",
                        download_url=direct_url,
                        preview_url=preview_url,
                        book_id="",
                        parsed_title=item_title,
                        parsed_author=item_meta.get("creator", ""),
                        file_size_bytes=size if size > 0 else None,
                        reason="Confirmed public domain PDF on Internet Archive"
                    )

            return None

    except Exception as exc:
        logger.warning(f"Internet Archive metadata check failed for {ia_identifier}: {exc}")
        return None


def check_internet_archive_direct(parsed: ParsedBook) -> Tuple[Optional[AvailabilityResult], Optional[str]]:
    """
    Directly queries the Internet Archive Advanced Search API for texts matching title and author.
    Finds public domain / open digitized books with genuine downloadable PDF files.
    """
    if not parsed.title or len(parsed.title.strip()) < 3:
        return None, None
    search_url = "https://archive.org/advancedsearch.php"
    headers = {"User-Agent": settings.USER_AGENT}
    q_str = f'title:("{parsed.title}") AND mediatype:(texts)'
    params = {
        "q": q_str,
        "fl[]": "identifier,title,creator",
        "rows": 3,
        "output": "json"
    }
    preview_url = None
    try:
        with httpx.Client(timeout=3.5) as client:
            resp = client.get(search_url, params=params, headers=headers)
            if resp.status_code != 200:
                return None, None
            docs = resp.json().get("response", {}).get("docs", [])
            for d in docs:
                ia_id = d.get("identifier")
                cand_title = d.get("title", "")
                if not ia_id or not is_title_match(parsed.title, cand_title):
                    continue
                preview_url = f"https://archive.org/details/{ia_id}"
                meta_url = f"https://archive.org/metadata/{ia_id}"
                m_resp = client.get(meta_url, headers=headers, timeout=3.5)
                if m_resp.status_code == 200:
                    item_data = m_resp.json()
                    item_meta = item_data.get("metadata", {})
                    # Strict Check: Reject borrow-only / printdisabled / lending items
                    is_restricted = bool(item_meta.get("access-restricted-item")) or any(
                        term in str(item_meta.get("collection", [])).lower()
                        for term in ["printdisabled", "inlibrary", "lendinglibrary"]
                    )
                    if is_restricted:
                        continue  # Keep preview_url but do not treat as free download

                    files = item_data.get("files", [])
                    for f in files:
                        fname = f.get("name", "")
                        if fname.lower().endswith(".pdf") and "encrypted" not in fname.lower():
                            size = int(f.get("size", 0)) if str(f.get("size", "")).isdigit() else 0
                            return AvailabilityResult(
                                status="AVAILABLE",
                                source="internet_archive",
                                download_url=f"https://archive.org/download/{ia_id}/{fname}",
                                preview_url=preview_url,
                                book_id="",
                                parsed_title=cand_title,
                                parsed_author=d.get("creator", parsed.author),
                                file_size_bytes=size if size > 0 else None,
                                reason="Confirmed open PDF on Internet Archive"
                            ), preview_url
    except Exception as exc:
        logger.warning(f"Internet Archive direct search error for '{parsed.title}': {exc}")
    return None, preview_url


# ===========================================================================
# Source C: Google Books API
# ===========================================================================
def check_google_books(parsed: ParsedBook) -> Tuple[Optional[AvailabilityResult], Optional[str]]:
    """
    Queries Google Books API (https://www.googleapis.com/books/v1/volumes).

    Legal check rules:
    - accessInfo.pdf.isAvailable must be True
    - accessInfo.pdf.downloadLink must be present
    - Preview-only or snippet-only results must NOT be counted as AVAILABLE
    """
    base_url = "https://www.googleapis.com/books/v1/volumes"
    headers = {"User-Agent": settings.USER_AGENT}
    primary_author = parsed.author.split(',')[0].split('&')[0].split(' and ')[0].strip() if parsed.author else ""
    q = f'"{parsed.title}" {primary_author}'.strip() if primary_author else f'"{parsed.title}"'

    params: Dict[str, Any] = {
        "q": q,
        "maxResults": 5
    }

    # Append optional API key from config if the user configured one in .env
    if settings.GOOGLE_BOOKS_API_KEY:
        params["key"] = settings.GOOGLE_BOOKS_API_KEY

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(base_url, params=params, headers=headers)
            items = []
            if resp.status_code == 200:
                items = resp.json().get("items", [])

            # Relaxed fallback search if quoted title returned no items
            if not items and primary_author:
                params["q"] = f"{parsed.title} {primary_author}".strip()
                resp2 = client.get(base_url, params=params, headers=headers)
                if resp2.status_code == 200:
                    items = resp2.json().get("items", [])

            best_preview = None
            for item in items:
                vinfo = item.get("volumeInfo", {})
                ainfo = item.get("accessInfo", {})

                candidate_title = vinfo.get("title", "")
                if not is_title_match(parsed.title, candidate_title):
                    continue

                preview_link = vinfo.get("previewLink") or vinfo.get("infoLink")
                if preview_link and not best_preview:
                    best_preview = preview_link

                # Inspect PDF access strictly
                pdf_info = ainfo.get("pdf", {})
                is_available = pdf_info.get("isAvailable", False)
                download_link = pdf_info.get("downloadLink")

                # If available and download link is present:
                if is_available and download_link:
                    authors = vinfo.get("authors", [])
                    author_str = ", ".join(authors) if authors else parsed.author
                    return AvailabilityResult(
                        status="AVAILABLE",
                        source="google_books",
                        download_url=download_link,
                        preview_url=preview_link or best_preview,
                        book_id="",
                        parsed_title=candidate_title,
                        parsed_author=author_str,
                        reason="Free public download via Google Books"
                    ), preview_link or best_preview

            return None, best_preview

    except Exception as exc:
        logger.warning(f"Google Books API check error for '{parsed.title}': {exc}")
        return None, None


# ===========================================================================
# Source D: Gutendex (Project Gutenberg)
# ===========================================================================
def check_gutendex(parsed: ParsedBook) -> Tuple[Optional[AvailabilityResult], Optional[str]]:
    """
    Queries Gutendex (https://gutendex.com/books), the official open API
    for Project Gutenberg's 70,000+ public domain literary works.
    Only applies to works published before 1928 (public domain).
    """
    if parsed.year and parsed.year.isdigit() and int(parsed.year) > 1928:
        return None, None

    search_url = "https://gutendex.com/books"
    headers = {"User-Agent": settings.USER_AGENT}
    params = {"search": f"{parsed.title} {parsed.author}".strip()}

    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(search_url, params=params, headers=headers)
            if resp.status_code != 200:
                return None, None

            data = resp.json()
            results = data.get("results", [])

            for book in results:
                cand_title = book.get("title", "")
                if not is_title_match(parsed.title, cand_title):
                    continue

                formats = book.get("formats", {})
                pdf_url = formats.get("application/pdf")
                preview_url = formats.get("text/html") or f"https://www.gutenberg.org/ebooks/{book.get('id')}"

                if pdf_url:
                    authors_list = [a.get("name", "") for a in book.get("authors", [])]
                    author_name = "; ".join(authors_list)
                    return AvailabilityResult(
                        status="AVAILABLE",
                        source="gutendex",
                        download_url=pdf_url,
                        preview_url=preview_url,
                        book_id="",
                        parsed_title=cand_title,
                        parsed_author=author_name,
                        reason="Project Gutenberg Public Domain PDF"
                    ), preview_url

            return None, None

    except Exception:
        return None, None


# ===========================================================================
# Source E: DOAB / OAPEN (Directory of Open Access Books)
# ===========================================================================
def check_doab_oapen(parsed: ParsedBook) -> Tuple[Optional[AvailabilityResult], Optional[str]]:
    """
    Queries DOAB / OAPEN academic repository for open-access peer-reviewed books.
    """
    search_url = "https://directory.doabooks.org/rest/search"
    headers = {
        "User-Agent": settings.USER_AGENT,
        "Accept": "application/json"
    }
    params = {"query": parsed.clean_search_query}

    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(search_url, params=params, headers=headers)
            if resp.status_code != 200:
                return None, None

            items = resp.json()
            if isinstance(items, list):
                for item in items:
                    name = item.get("name", "")
                    if not is_title_match(parsed.title, name):
                        continue

                    handle = item.get("handle")
                    preview = f"https://directory.doabooks.org/handle/{handle}" if handle else None

                    bitstreams = item.get("bitstreams", [])
                    for bs in bitstreams:
                        bs_name = bs.get("name", "")
                        bs_url = bs.get("retrieveLink")
                        if bs_name.lower().endswith(".pdf") and bs_url:
                            full_url = f"https://directory.doabooks.org{bs_url}"
                            return AvailabilityResult(
                                status="AVAILABLE",
                                source="doab",
                                download_url=full_url,
                                preview_url=preview,
                                book_id="",
                                parsed_title=name,
                                parsed_author=parsed.author,
                                reason="DOAB Peer-Reviewed Open Access Book"
                            ), preview

            return None, None

    except Exception:
        return None, None


# ===========================================================================
# Master Coordinator Function
# ===========================================================================
def check_book_availability(raw_citation: str, use_cache: bool = True) -> AvailabilityResult:
    """
    Master availability pipeline:
    1. Checks local SQLite cache. If already checked, returns cached result instantly!
    2. Parses raw syllabus citation (title, author, edition, direct URLs).
    3. If citation has a direct valid PDF link, verifies and returns it.
    4. Runs availability checks in prioritized order:
       a. Open Library (public only)
       b. Internet Archive Metadata API
       c. Google Books API (free-ebooks download link)
       d. Gutendex (Project Gutenberg)
       e. DOAB / OAPEN (Open Access books)
    5. If ANY source confirms a legal PDF, stops and returns AVAILABLE.
    6. If all sources exhaust without a free legal PDF, returns NO_ACCESS.
    7. Automatically saves result to SQLite cache.
    """
    # Step 1: Cache check
    if use_cache:
        cached = get_cached_book(raw_citation)
        if cached:
            logger.info(f"Cache HIT for citation: {raw_citation[:40]}...")
            return AvailabilityResult(
                status=cached["status"],
                source=cached.get("source"),
                download_url=cached.get("download_url"),
                preview_url=cached.get("preview_url"),
                book_id=cached["book_id"],
                parsed_title=cached["parsed_title"],
                parsed_author=cached["parsed_author"],
                file_size_bytes=cached.get("file_size_bytes"),
                reason="Loaded from local cache"
            )

    # Step 2: Parse reference citation
    parsed = parse_reference_book(raw_citation)
    logger.info(f"Checking online availability for: Title='{parsed.title}', Author='{parsed.author}'")

    # Step 2b: Check if citation has a direct verified PDF URL
    if parsed.direct_url and parsed.direct_url.lower().endswith(".pdf"):
        try:
            with httpx.Client(timeout=4.0, follow_redirects=True) as client:
                probe = client.head(parsed.direct_url, headers={"User-Agent": settings.USER_AGENT})
                if probe.status_code == 200:
                    saved = save_book_cache(
                        raw_citation=raw_citation,
                        parsed_title=parsed.title,
                        parsed_author=parsed.author,
                        status="AVAILABLE",
                        source="direct_link",
                        download_url=parsed.direct_url,
                        preview_url=parsed.direct_url
                    )
                    return AvailabilityResult(
                        status="AVAILABLE",
                        source="direct_link",
                        download_url=parsed.direct_url,
                        preview_url=parsed.direct_url,
                        book_id=saved["book_id"],
                        parsed_title=parsed.title,
                        parsed_author=parsed.author,
                        reason="Direct open-access PDF link verified in syllabus citation"
                    )
        except Exception:
            pass

    best_preview_url: Optional[str] = parsed.direct_url

    # Step 3a: Primary Online Source 1 - Google Books API (uses GOOGLE_BOOKS_API_KEY)
    gb_result, gb_preview = check_google_books(parsed)
    if gb_preview and not best_preview_url:
        best_preview_url = gb_preview
    if gb_result:
        saved = save_book_cache(
            raw_citation=raw_citation,
            parsed_title=parsed.title,
            parsed_author=parsed.author,
            status="AVAILABLE",
            source=gb_result.source,
            download_url=gb_result.download_url,
            preview_url=gb_result.preview_url or best_preview_url,
            file_size_bytes=gb_result.file_size_bytes
        )
        gb_result.book_id = saved["book_id"]
        return gb_result

    # Step 3b: Primary Online Source 2 - Internet Archive Direct Text Search
    ia_result, ia_preview = check_internet_archive_direct(parsed)
    if ia_preview and not best_preview_url:
        best_preview_url = ia_preview
    if ia_result:
        saved = save_book_cache(
            raw_citation=raw_citation,
            parsed_title=parsed.title,
            parsed_author=parsed.author,
            status="AVAILABLE",
            source=ia_result.source,
            download_url=ia_result.download_url,
            preview_url=ia_result.preview_url or best_preview_url,
            file_size_bytes=ia_result.file_size_bytes
        )
        ia_result.book_id = saved["book_id"]
        return ia_result

    # Step 3c: Secondary Online Source 3 - Open Library Search
    ol_result, ol_preview = check_open_library(parsed)
    if ol_preview and not best_preview_url:
        best_preview_url = ol_preview
    if ol_result:
        saved = save_book_cache(
            raw_citation=raw_citation,
            parsed_title=parsed.title,
            parsed_author=parsed.author,
            status="AVAILABLE",
            source=ol_result.source,
            download_url=ol_result.download_url,
            preview_url=ol_result.preview_url or best_preview_url,
            file_size_bytes=ol_result.file_size_bytes
        )
        ol_result.book_id = saved["book_id"]
        return ol_result

    # Step 3d: Secondary Online Source 4 - Gutendex (Project Gutenberg)
    guten_result, guten_preview = check_gutendex(parsed)
    if guten_preview and not best_preview_url:
        best_preview_url = guten_preview
    if guten_result:
        saved = save_book_cache(
            raw_citation=raw_citation,
            parsed_title=parsed.title,
            parsed_author=parsed.author,
            status="AVAILABLE",
            source=guten_result.source,
            download_url=guten_result.download_url,
            preview_url=guten_result.preview_url or best_preview_url,
            file_size_bytes=guten_result.file_size_bytes
        )
        guten_result.book_id = saved["book_id"]
        return guten_result

    # Step 3e: Secondary Online Source 5 - DOAB / OAPEN
    doab_result, doab_preview = check_doab_oapen(parsed)
    if doab_preview and not best_preview_url:
        best_preview_url = doab_preview
    if doab_result:
        saved = save_book_cache(
            raw_citation=raw_citation,
            parsed_title=parsed.title,
            parsed_author=parsed.author,
            status="AVAILABLE",
            source=doab_result.source,
            download_url=doab_result.download_url,
            preview_url=doab_result.preview_url or best_preview_url,
            file_size_bytes=doab_result.file_size_bytes
        )
        doab_result.book_id = saved["book_id"]
        return doab_result

    # Step 3f: Local Reference Books Fallback (Strict Matching Only)
    local_ref_dir = os.path.join(BASE_DIR, "uploaded_reference_books")
    if os.path.isdir(local_ref_dir) and len(parsed.title) >= 5:
        ignore_words = {"the", "and", "for", "with", "from", "author", "unknown", "textbook", "reference", "edition"}
        clean_author_tokens = [w.lower() for w in re.split(r'[\s,.]+', parsed.author) if len(w) >= 4 and w.lower() not in ignore_words]
        for fname in os.listdir(local_ref_dir):
            if fname.lower().endswith(".pdf") and not fname.startswith("."):
                f_clean = fname.replace(".pdf", "").replace("-", " ").lower()
                author_match = any(re.search(r'\b' + re.escape(tok) + r'\b', f_clean) for tok in clean_author_tokens)
                title_match = is_title_match(parsed.title, f_clean)
                if (title_match and len(parsed.title) >= 6) or (author_match and title_match):
                    f_path = os.path.join(local_ref_dir, fname)
                    f_size = os.path.getsize(f_path) if os.path.isfile(f_path) else None
                    dl_url = f"/api/download-file?file={urllib.parse.quote(fname)}"
                    saved = save_book_cache(
                        raw_citation=raw_citation,
                        parsed_title=parsed.title,
                        parsed_author=parsed.author,
                        status="AVAILABLE",
                        source="local_reference_book",
                        download_url=dl_url,
                        preview_url=dl_url,
                        file_size_bytes=f_size
                    )
                    return AvailabilityResult(
                        status="AVAILABLE",
                        source="local_reference_book",
                        download_url=dl_url,
                        preview_url=dl_url,
                        book_id=saved["book_id"],
                        parsed_title=parsed.title,
                        parsed_author=parsed.author,
                        file_size_bytes=f_size,
                        reason=f"Available in your uploaded reference books: {fname}"
                    )

    # If no source has a free, legal PDF: return NO_ACCESS
    saved = save_book_cache(
        raw_citation=raw_citation,
        parsed_title=parsed.title,
        parsed_author=parsed.author,
        status="NO_ACCESS",
        source=None,
        download_url=None,
        preview_url=best_preview_url,
        file_size_bytes=None
    )

    return AvailabilityResult(
        status="NO_ACCESS",
        source=None,
        download_url=None,
        preview_url=best_preview_url,
        book_id=saved["book_id"],
        parsed_title=parsed.title,
        parsed_author=parsed.author,
        reason="No free, legal, public domain PDF confirmed online"
    )
