"""FastAPI application entry point."""

from fastapi import FastAPI

from app.routers.submissions import router as submissions_router

app = FastAPI(title="WAYBOUND")
app.include_router(submissions_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Waybound API is running"}
