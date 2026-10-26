"""
config.py
=============================================================================
CONFIGURATION & ENVIRONMENT SETTINGS

Mentor Explanation:
In professional software, we never hardcode settings (like API keys, URLs,
or file paths) directly inside our business logic. Why?
1. Security: If you push code to GitHub with your secret keys, anyone can steal them.
2. Flexibility: You can change a timeout or database location without touching
   the code that actually does the work.

We use 'python-dotenv' to automatically read a file named '.env' in your project
folder. If a setting is defined in '.env', Python loads it. If not, it falls
back to a sensible, beginner-safe default.
=============================================================================
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Load the .env file
# ---------------------------------------------------------------------------
# Path(__file__) gives the exact location of THIS file (config.py).
# .resolve().parent gives the directory containing it (your project root).
# This guarantees .env is found even if you run Python from another folder.
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# load_dotenv reads key-value pairs from .env and adds them to os.environ.
# If .env does not exist yet, load_dotenv simply skips it without crashing.
load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    """
    Central settings class holding all application configuration.
    Using a class keeps our settings organized and provides auto-complete
    in modern code editors like VS Code.
    """

    # -----------------------------------------------------------------------
    # Network & API Settings
    # -----------------------------------------------------------------------
    # User-Agent header: Major free APIs (Open Library, Internet Archive, etc.)
    # request that clients identify themselves with a polite User-Agent string.
    # Without this, your requests may be blocked with an HTTP 403 Forbidden error.
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "SyllabusBookFinder/1.0 (Educational Project; contact: student@example.edu)"
    )

    # Optional Google Books API Key:
    # Google Books allows basic queries without a key, but having a free key
    # gives you higher rate limits and avoids HTTP 429 'Too Many Requests' errors.
    GOOGLE_BOOKS_API_KEY: str = os.getenv("GOOGLE_BOOKS_API_KEY", "")

    # Request timeout in seconds:
    # When contacting an external library API, we do not want our server to hang
    # indefinitely if their servers are slow or down. After 10 seconds, httpx will
    # stop waiting and raise a TimeoutException so we can gracefully try the next source.
    REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10.0"))

    # -----------------------------------------------------------------------
    # Storage & Cache Settings
    # -----------------------------------------------------------------------
    # Location of the local SQLite cache database file.
    # Storing this in the project root makes it easy to inspect or delete to reset.
    DATABASE_PATH: Path = BASE_DIR / "book_availability_cache.db"

    # Temporary directory to stage downloaded PDFs if local streaming requires it
    DOWNLOAD_TEMP_DIR: Path = BASE_DIR / "downloads_cache"

    # -----------------------------------------------------------------------
    # PDF Validation Thresholds
    # -----------------------------------------------------------------------
    # Minimum valid PDF size: 50 Kilobytes (50 * 1024 bytes).
    # Why? If a server returns an error page, a captcha, or an HTML 'Page Not Found'
    # under HTTP status 200, the file is usually tiny (1 KB - 5 KB). A real academic
    # book or classic literature PDF is virtually always larger than 50 KB.
    MIN_PDF_BYTES: int = 50 * 1024

    # Maximum allowed PDF size: 150 Megabytes (150 * 1024 * 1024 bytes).
    # Why? Protects your server and user device from accidentally downloading
    # gigantic uncompressed 2 GB scans that could freeze the browser.
    MAX_PDF_BYTES: int = 150 * 1024 * 1024

    # Magic byte sequence that must appear at the beginning of every valid PDF file.
    # Every valid PDF specification begins with the ASCII bytes '%PDF'.
    PDF_MAGIC_BYTES: bytes = b"%PDF"


# Create a single global instance for other modules to import:
# from config import settings
settings = Settings()

# Automatically create the temporary downloads directory if it doesn't exist
settings.DOWNLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
