"""Point-radius and route-corridor tourism discovery endpoints."""

from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.submission_service import SubmissionStore, get_store
from services.discovery import DiscoveryError, discover_along_route, discover_nearby

router = APIRouter(prefix="/api", tags=["Discovery"])


class StartingTown(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)


class PopularDestinationRef(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    destination_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=200)


class RouteGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["LineString"]
    coordinates: list[list[float]] = Field(min_length=2, max_length=500)

    @field_validator("coordinates")
    @classmethod
    def validate_linestring(cls, coords: list[list[float]]) -> list[list[float]]:
        cleaned: list[list[float]] = []
        for idx, pos in enumerate(coords):
            if not isinstance(pos, list) or len(pos) != 2:
                raise ValueError(
                    f"Coordinate at index {idx} must be a [longitude, latitude] pair."
                )
            lon, lat = pos
            if (
                isinstance(lon, bool)
                or isinstance(lat, bool)
                or not math.isfinite(lon)
                or not math.isfinite(lat)
            ):
                raise ValueError(
                    f"Coordinate at index {idx} must contain finite numbers."
                )
            if not -180.0 <= lon <= 180.0 or not -90.0 <= lat <= 90.0:
                raise ValueError(
                    f"Coordinate at index {idx} is out of range (lon -180..180, lat -90..90)."
                )
            cleaned.append([float(lon), float(lat)])

        has_nonzero_segment = any(
            a[0] != b[0] or a[1] != b[1] for a, b in zip(cleaned, cleaned[1:])
        )
        if not has_nonzero_segment:
            raise ValueError(
                "route_geometry must contain at least one non-zero-length segment."
            )
        return cleaned


class RouteDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_town: StartingTown
    popular_destination: PopularDestinationRef
    route_geometry: RouteGeometry
    corridor_width_km: float = Field(ge=1.0, le=100.0)
    experience_categories: list[Literal["food", "crafts", "culture"]] | None = None
    destination_categories: list[str] | None = None

    @field_validator("corridor_width_km")
    @classmethod
    def check_finite_width(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("corridor_width_km must be a finite number.")
        return float(value)


@router.get("/discover")
def get_discoveries(
    destination: str,
    radius_km: int = Query(default=10, ge=5, le=50),
    category: Literal["attractions", "food", "crafts", "culture"] | None = None,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    store: SubmissionStore = Depends(get_store),
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
            store=store,
        )
    except DiscoveryError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=error.detail,
        ) from error


@router.post("/discover/route")
def post_route_discoveries(
    body: RouteDiscoveryRequest,
    store: SubmissionStore = Depends(get_store),
):
    """Return canonical and approved community listings within a route corridor."""
    try:
        return discover_along_route(
            starting_town_name=body.starting_town.name,
            popular_destination_id=body.popular_destination.destination_id,
            popular_destination_name=body.popular_destination.name,
            line_coords=body.route_geometry.coordinates,
            corridor_width_km=body.corridor_width_km,
            experience_categories=body.experience_categories,
            destination_categories=body.destination_categories,
            store=store,
        )
    except DiscoveryError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=error.detail,
        ) from error
