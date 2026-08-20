"""Application configuration helpers.

This module is intentionally small: extraction scripts need Gemini/OCR settings,
while the API container only needs the database URL. Keeping those two loading
paths separate prevents the API from requiring a Gemini key at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    """Runtime settings used by local extraction scripts."""

    project_root: Path
    gemini_api_key: str
    gemini_model: str
    ocr_languages: str
    debug_dir: Path
    database_url: str


def get_project_root() -> Path:
    """Return the repository root from any import location inside src/."""

    return Path(__file__).resolve().parents[2]


def load_database_url() -> str:
    """Load the SQLAlchemy database URL without requiring extraction settings."""

    project_root = get_project_root()
    load_dotenv(project_root / ".env")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    # Compose and local development can also provide discrete POSTGRES_* values.
    user = os.getenv("POSTGRES_USER", "deeds")
    password = os.getenv("POSTGRES_PASSWORD", "deeds")
    db = os.getenv("POSTGRES_DB", "belgian_deed_pipeline")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def load_settings() -> Settings:
    """Load full extraction settings and fail fast if Gemini is not configured."""

    project_root = get_project_root()
    load_dotenv(project_root / ".env")

    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_api_key or gemini_api_key == "your_key_here":
        raise ValueError(
            "GEMINI_API_KEY is not configured. Set it in the project .env file."
        )

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    ocr_languages = os.getenv("OCR_LANGUAGES", "fra+nld").strip()
    # Debug artifacts are only used by the one-PDF spike.
    debug_dir = project_root / "outputs" / "debug"
    database_url = load_database_url()

    return Settings(
        project_root=project_root,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        ocr_languages=ocr_languages,
        debug_dir=debug_dir,
        database_url=database_url,
    )
