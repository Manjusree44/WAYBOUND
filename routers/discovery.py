"""Nearby tourism discovery endpoint."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.services.discovery import DiscoveryError, discover_nearby

router = APIRouter(prefix="/api", tags=["Discovery"])


@router.get("/discover")
def get_discoveries(
    destination: str,
    radius_km: int = Query(default=10, ge=5, le=50),
    category: Literal["attractions", "food", "crafts", "culture"] | None = None,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    """Return nearby destination, food, craft, and cultural records."""
    if radius_km not in (5, 10, 25, 50):
        raise HTTPException(
            status_code=422,
            detail="radius_km must be one of 5, 10, 25, or 50.",
        )
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422,
            detail="Provide both latitude and longitude for a custom search location.",
        )

    try:
        return discover_nearby(
            destination=destination,
            radius_km=radius_km,
            category=category,
            latitude=latitude,
            longitude=longitude,
        )
    except DiscoveryError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=error.detail,
        ) from error
