"""
main.py
=============================================================================
FASTAPI BACKEND ROUTES: BOOK AVAILABILITY & DIRECT PDF DOWNLOAD

Mentor Explanation:
Why FastAPI instead of Flask?
1. Automatic Data Validation: With Pydantic models, FastAPI checks that incoming
   JSON is correctly formed before your function even runs. If the client sends
   malformed data, FastAPI automatically returns a helpful 422 Unprocessable Entity error.
2. Async & High Performance: Built on Starlette (ASGI) and AnyIO, FastAPI can handle
   thousands of concurrent requests without blocking.
3. Interactive API Documentation: Visit http://localhost:8000/docs in your browser,
   and FastAPI provides a complete, interactive Swagger UI to test your endpoints!
4. Native Streaming: Streaming large PDF files with StreamingResponse is built-in
   and memory-efficient.

Endpoints Provided:
- POST /api/check-book  -> Checks if a legal PDF exists; returns JSON status & metadata
- GET  /api/download/{id} -> Validates and streams the PDF directly to the user's computer
=============================================================================
"""

import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import our custom modular components
from config import settings
from cache import init_db, get_cached_book_by_id
from availability import check_book_availability
from downloader import create_book_download_response

# Configure logger
logger = logging.getLogger("main_api")

# ---------------------------------------------------------------------------
# 1. Initialize FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Syllabus Reference Book Legal PDF Finder",
    description="Finds legal, free public-domain & open-access textbook PDFs from syllabus citations.",
    version="1.0.0"
)

# ---------------------------------------------------------------------------
# 2. Configure CORS (Cross-Origin Resource Sharing)
# ---------------------------------------------------------------------------
# When your front end runs on one port (e.g. 3000 or 8000) and makes requests,
# web browsers enforce security checks. Adding CORSMiddleware ensures your
# front end can make requests without getting blocked by browser CORS security.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # In production, replace '*' with your specific domain
    allow_credentials=True,
    allow_methods=["*"],           # Allow GET, POST, OPTIONS, etc.
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 3. Pydantic Request & Response Schemas
# ---------------------------------------------------------------------------
class BookCheckRequest(BaseModel):
    """
    Schema for the incoming POST request to /api/check-book.
    Pydantic automatically validates that 'citation' is a string and non-empty.
    """
    citation: str = Field(
        ...,
        min_length=3,
        description="The citation string from the syllabus (e.g. Bach 'The Design of the Unix Operating System')",
        examples=["Maurice J. Bach, The Design of the Unix Operating System"]
    )
    bypass_cache: bool = Field(
        False,
        description="Set to true if you wish to force a re-check against online APIs"
    )


class BookCheckResponse(BaseModel):
    """
    Schema for the response sent back to the front end.
    """
    book_id: str
    status: str
    parsed_title: str
    parsed_author: str
    source: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    download_endpoint: Optional[str] = None
    file_size_bytes: Optional[int] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# 4. Startup Event: Ensure Database Schema Exists
# ---------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    """Runs once when the server boots up to guarantee the SQLite cache table exists."""
    logger.info("Initializing SQLite book cache database...")
    init_db()
    logger.info("Database initialized successfully.")


# ---------------------------------------------------------------------------
# 5. Route: POST /api/check-book
# ---------------------------------------------------------------------------
@app.post(
    "/api/check-book",
    response_model=BookCheckResponse,
    summary="Check Book PDF Availability",
    description="Checks Open Library, Internet Archive, Google Books, Gutendex, and DOAB in order."
)
def api_check_book(payload: BookCheckRequest):
    """
    Endpoint called when a student clicks a book in the syllabus results:
    1. Checks if the book was already checked in SQLite cache.
    2. If not, checks Open Library -> IA -> Google Books -> Gutendex -> DOAB.
    3. Returns JSON with status 'AVAILABLE' or 'NO_ACCESS'.
    """
    citation = payload.citation.strip()
    if not citation:
        raise HTTPException(status_code=400, detail="Citation cannot be empty.")

    try:
        # Run our master availability engine
        result = check_book_availability(
            raw_citation=citation,
            use_cache=not payload.bypass_cache
        )

        # Build our internal download route URL if AVAILABLE
        download_ep = f"/api/download/{result.book_id}" if result.status == "AVAILABLE" else None

        return BookCheckResponse(
            book_id=result.book_id,
            status=result.status,
            parsed_title=result.parsed_title,
            parsed_author=result.parsed_author,
            source=result.source,
            download_url=result.download_url,
            preview_url=result.preview_url,
            download_endpoint=download_ep,
            file_size_bytes=result.file_size_bytes,
            reason=result.reason
        )

    except Exception as exc:
        logger.exception(f"Error checking availability for citation '{citation}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while checking book availability: {str(exc)}"
        )


# ---------------------------------------------------------------------------
# 6. Route: GET /api/download/{book_id}
# ---------------------------------------------------------------------------
@app.get(
    "/api/download/{book_id}",
    summary="Stream and Download Verified Book PDF",
    description="Validates Content-Type, Content-Length, and %PDF magic bytes, then streams the file."
)
def api_download_book(book_id: str):
    """
    Endpoint that streams the verified PDF to the student's browser:
    - Verifies the book exists in the cache and is AVAILABLE.
    - Validates the first 4 bytes (%PDF).
    - Streams chunk-by-chunk to save server memory.
    - Triggers the browser's download window automatically!
    """
    return create_book_download_response(book_id)


# ---------------------------------------------------------------------------
# 7. Route: GET /api/health
# ---------------------------------------------------------------------------
@app.get("/api/health", summary="Health Check")
def health_check():
    """Simple health check endpoint returning server status."""
    return {"status": "ok", "service": "syllabus-book-checker"}


# ---------------------------------------------------------------------------
# Development Server Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # uvicorn runs our ASGI FastAPI server on port 8000
    # reload=True automatically restarts the server when you edit code!
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
