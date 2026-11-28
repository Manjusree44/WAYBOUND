"""Single FastAPI entry point for the WAYBOUND backend and integrated frontend."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers.submissions import router as submissions_router
from config import settings
from routers.catalog import router as catalog_router
from routers.discovery import router as discovery_router
from routers.health import router as health_router

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(catalog_router)
app.include_router(discovery_router)
app.include_router(submissions_router)

if FRONTEND_DIR.exists():
    @app.get("/", include_in_schema=False)
    def serve_frontend():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
