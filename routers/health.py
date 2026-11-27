"""
Health check endpoint.

A simple endpoint that confirms the server is running.
No authentication, no data access — just a pulse check.

Used by:
  - Developers verifying the backend is reachable.
  - The frontend to test connectivity.
  - Monitoring tools in production.
"""

from fastapi import APIRouter

# Create a router for health-related endpoints.
# `tags` groups this endpoint in the Swagger UI docs.
router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Health check",
    description="Returns a simple status object to confirm the API is running.",
)
def health_check():
    """
    Return server health status.

    This endpoint does not access any data or perform any
    computation. If you get a 200 response, the server is alive.
    """
    return {
        "status": "ok",
        "service": "WAYBOUND API",
    }
