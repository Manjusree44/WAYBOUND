"""
WAYBOUND application settings.

All configuration values live here in one place.
Other files import `settings` and use its attributes
instead of hardcoding paths or values.

We use pydantic-settings so that any value can be
overridden by an environment variable if needed later.
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the WAYBOUND backend."""

    # --- Application metadata ---
    APP_TITLE: str = "WAYBOUND API"
    APP_DESCRIPTION: str = (
        "Discover beyond the famous. Experience the local. "
        "Community-powered tourism discovery for regional "
        "destinations, food, traditional crafts, "
        "festivals and cultural experiences."
    )
    APP_VERSION: str = "0.1.0"

    # --- Data directory ---
    # Points to the folder that contains the CSV files.
    # Path is resolved relative to the project root.
    DATA_DIR: Path = Path(__file__).resolve().parent / "data"
    LOW_VISIBILITY_EVIDENCE_PATH: Path = (
        Path(__file__).resolve().parent / "metadata" / "low_visibility_evidence.json"
    )

    # --- CORS (Cross-Origin Resource Sharing) ---
    # Which frontend origins are allowed to call this API.
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


# Create a single settings instance that the whole app imports.
settings = Settings()
