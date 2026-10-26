"""
downloader.py
=============================================================================
STREAMING PDF DOWNLOADER WITH STRICT MAGIC-BYTE VALIDATION

Mentor Explanation:
Why is streaming essential for file downloads?
A typical textbook PDF can be anywhere from 10 MB to 100 MB.
If your server reads the entire file into a Python variable with:
    pdf_bytes = resp.content  # <-- DANGEROUS IN PRODUCTION!
then if 10 students download books simultaneously, your server would consume
over 1 GB of RAM just holding files in memory!
Instead, we use STREAMING (chunk-by-chunk transfer):
Our server fetches 64 KB from the remote library and immediately forwards
those 64 KB to the student's browser. Memory usage stays under 1 MB total!

Validation Before Download:
1. HTTP Content-Type Check: Must be 'application/pdf' or 'application/octet-stream'.
2. Content-Length Check: Must be within sensible bounds (50 KB to 150 MB).
3. Magic Bytes Verification: The first 4 bytes of any genuine PDF must be b'%PDF'.
   If a remote server sent back an HTML error page, captive portal, or Cloudflare
   challenge, the first bytes would be b'<!DO' or b'<htm'. Our validator catches
   this and rejects it immediately!
=============================================================================
"""

import re
import httpx
import logging
from typing import Generator, Tuple, Optional
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from config import settings
from cache import get_cached_book_by_id

logger = logging.getLogger("downloader")


def sanitize_filename(title: str) -> str:
    """
    Cleans a book title so it can be safely used as a filename on Windows, Mac, and Linux.
    Replaces slashes, colons, quotes, and invalid filesystem characters with underscores.
    """
    # Remove any characters that are illegal in Windows or Linux filenames: \ / : * ? " < > |
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    # Collapse multiple spaces or underscores
    safe_title = re.sub(r"\s+", " ", safe_title).strip()
    if not safe_title:
        safe_title = "textbook"
    # Truncate to 80 characters to keep file names neat
    return f"{safe_title[:80]}.pdf"


def validate_pdf_stream_header(client: httpx.Client, download_url: str) -> Tuple[httpx.Response, bytes]:
    """
    Performs initial pre-flight streaming validation on the target download URL:
    1. Sends a GET request with stream=True so headers arrive without the body.
    2. Inspects Content-Type.
    3. Inspects Content-Length if provided by the remote server.
    4. Reads ONLY the first chunk (1024 bytes) to inspect the %PDF magic byte header.

    Returns:
        (response_object, first_chunk_bytes)
    Raises:
        HTTPException(400 or 404) if validation fails.
    """
    headers = {"User-Agent": settings.USER_AGENT}

    try:
        # stream=True opens the HTTP socket without downloading the entire body into RAM
        resp = client.send(
            client.build_request("GET", download_url, headers=headers),
            stream=True
        )

        if resp.status_code != 200:
            resp.close()
            logger.error(f"Remote server returned HTTP {resp.status_code} for URL: {download_url}")
            raise HTTPException(
                status_code=404,
                detail=f"The book file could not be retrieved from the host library (HTTP {resp.status_code})."
            )

        # 1. Content-Type check
        content_type = resp.headers.get("Content-Type", "").lower()
        valid_types = ["application/pdf", "application/octet-stream", "binary/octet-stream", "application/x-pdf"]
        if not any(vt in content_type for vt in valid_types):
            resp.close()
            logger.error(f"Invalid Content-Type received: '{content_type}'. Expected PDF.")
            raise HTTPException(
                status_code=400,
                detail=f"Verification failed: Remote server served '{content_type}' instead of a valid PDF."
            )

        # 2. Content-Length check (if the server specified it)
        content_len_header = resp.headers.get("Content-Length")
        if content_len_header and content_len_header.isdigit():
            size_bytes = int(content_len_header)
            if size_bytes < settings.MIN_PDF_BYTES:
                resp.close()
                logger.error(f"File size too small ({size_bytes} bytes). Likely an error stub.")
                raise HTTPException(
                    status_code=400,
                    detail=f"Verification failed: File is too small ({size_bytes} bytes) to be a complete book."
                )
            if size_bytes > settings.MAX_PDF_BYTES:
                resp.close()
                logger.error(f"File size too large ({size_bytes} bytes). Exceeds safe limit.")
                raise HTTPException(
                    status_code=400,
                    detail="Verification failed: File size exceeds maximum allowed safety limit (150 MB)."
                )

        # 3. Magic-bytes check on initial chunk
        # iter_bytes(1024) pulls just the first kilobyte from the network stream
        stream_iter = resp.iter_bytes(chunk_size=1024)
        first_chunk = next(stream_iter, b"")

        # Every genuine PDF file begins with '%PDF' (hex: 25 50 44 46)
        if not first_chunk.startswith(settings.PDF_MAGIC_BYTES):
            resp.close()
            logger.error(f"Magic bytes mismatch! First 10 bytes: {first_chunk[:10]!r}")
            raise HTTPException(
                status_code=400,
                detail="Verification failed: File does not contain standard PDF magic header (%PDF)."
            )

        return resp, first_chunk

    except httpx.TimeoutException:
        logger.error(f"Timeout while attempting to stream from {download_url}")
        raise HTTPException(status_code=504, detail="Connection to the external book archive timed out.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Unexpected streaming validation failure: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to stream book: {str(exc)}")


def stream_pdf_generator(resp: httpx.Response, first_chunk: bytes, chunk_size: int = 65536) -> Generator[bytes, None, None]:
    """
    Python generator that streams the PDF bytes to the client in chunks.

    Syntax explanation:
    - 'yield first_chunk': Since we already read the first 1 KB during the magic-byte
      validation, we must yield it first so the user receives the complete file without
      missing its beginning!
    - 'yield chunk': Produces successive 64 KB slices as they arrive over the wire.
    - 'finally: resp.close()': Ensures the network socket is closed when the client
      finishes downloading or cancels the download.
    """
    try:
        yield first_chunk
        for chunk in resp.iter_bytes(chunk_size=chunk_size):
            if chunk:
                yield chunk
    finally:
        resp.close()


def create_book_download_response(book_id: str) -> StreamingResponse:
    """
    Main download dispatcher:
    1. Fetches book record from SQLite cache by book_id.
    2. Confirms status is 'AVAILABLE'.
    3. Validates the PDF stream headers and %PDF magic bytes.
    4. Returns a FastAPI StreamingResponse with 'Content-Disposition: attachment'.
       This tells the user's web browser: 'Download this file directly to the user's device!'
    """
    book_record = get_cached_book_by_id(book_id)
    if not book_record:
        raise HTTPException(
            status_code=404,
            detail=f"Book ID '{book_id}' not found in cache. Please check availability first."
        )

    if book_record.get("status") != "AVAILABLE" or not book_record.get("download_url"):
        raise HTTPException(
            status_code=403,
            detail="This book is marked as NO_ACCESS (no free, legal PDF available for download)."
        )

    download_url = book_record["download_url"]
    filename = sanitize_filename(book_record.get("parsed_title") or "textbook")

    # Open an httpx Client to manage the connection
    # follow_redirects=True is vital because many archive mirrors redirect to regional CDNs!
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    resp, first_chunk = validate_pdf_stream_header(client, download_url)

    # Set up HTTP headers for clean browser download
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "application/pdf"
    }

    # Pass remote Content-Length to the browser if known so the user sees a progress bar!
    if "Content-Length" in resp.headers:
        headers["Content-Length"] = resp.headers["Content-Length"]

    return StreamingResponse(
        content=stream_pdf_generator(resp, first_chunk),
        media_type="application/pdf",
        headers=headers
    )
