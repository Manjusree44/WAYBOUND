"""Nearby tourism discovery using the existing CSV catalog relationships."""

import math
from collections.abc import Callable
from typing import Any

from app.data_access import DATASETS, load_dataset

EARTH_RADIUS_KM = 6371.0


class DiscoveryError(ValueError):
    """An expected discovery request error with an HTTP status code."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Calculate the great-circle distance between two coordinate pairs."""
    radians = math.pi / 180
    delta_latitude = (latitude_b - latitude_a) * radians
    delta_longitude = (longitude_b - longitude_a) * radians
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude_a * radians)
        * math.cos(latitude_b * radians)
        * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, haversine)))


def _coordinates(record: dict[str, str]) -> tuple[float, float] | None:
    try:
        latitude = float(record.get("latitude", ""))
        longitude = float(record.get("longitude", ""))
    except (TypeError, ValueError):
        return None
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None
    return latitude, longitude


def _is_community_submission(record: dict[str, str]) -> bool:
    if record.get("user", "").strip().casefold() in {"true", "1", "yes"}:
        return True
    if any(record.get(field, "").strip().upper().startswith("USR-") for field in (
        "destination_id", "food_id", "craft_id", "experience_id", "gi_id"
    )):
        return True
    return "user submitted" in record.get("verification_status", "").casefold()


def _destination_links(
    record: dict[str, str],
    gi_destinations: dict[str, list[str]],
) -> list[str]:
    destination_id = record.get("destination_id", "").strip()
    if destination_id:
        return [destination_id]
    return gi_destinations.get(record.get("gi_id", "").strip(), [])


def _nearby_records(
    records: list[dict[str, str]],
    link_resolver: Callable[[dict[str, str]], list[str]],
    destinations_by_id: dict[str, dict[str, str]],
    center: tuple[float, float],
    radius_km: int,
) -> list[dict[str, Any]]:
    nearby = []
    for record in records:
        if _is_community_submission(record):
            continue

        candidates = []
        for destination_id in link_resolver(record):
            destination = destinations_by_id.get(destination_id)
            coordinates = _coordinates(destination) if destination else None
            if coordinates is None:
                continue
            distance = haversine_km(*center, *coordinates)
            if distance <= radius_km:
                candidates.append((distance, destination_id))

        if candidates:
            distance, location_destination_id = min(candidates)
            nearby.append({
                "record": record,
                "distance_km": round(distance, 3),
                "location_destination_id": location_destination_id,
            })
    return nearby


def discover_nearby(
    destination: str,
    radius_km: int = 10,
    category: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """Find public records within a radius of a destination or custom point."""
    destinations = [
        row for row in load_dataset(DATASETS["destinations"])
        if not _is_community_submission(row)
    ]
    search_key = destination.strip().casefold()
    matches = [
        row for row in destinations
        if row.get("destination_id", "").strip().casefold() == search_key
        or row.get("name", "").strip().casefold() == search_key
    ]
    if not matches:
        raise DiscoveryError(404, f"Destination '{destination}' was not found.")
    selected = matches[0]

    selected_coordinates = _coordinates(selected)
    if latitude is None and selected_coordinates is None:
        raise DiscoveryError(
            422,
            f"Destination '{destination}' does not have valid coordinates; "
            "provide both latitude and longitude for a custom search location.",
        )
    center = (
        (latitude, longitude)
        if latitude is not None and longitude is not None
        else selected_coordinates
    )
    if center is None:
        raise DiscoveryError(422, "A complete search location is required.")

    destinations_by_id = {
        row["destination_id"]: row
        for row in destinations
        if row.get("destination_id")
    }
    results: dict[str, list[dict[str, Any]]] = {
        "destinations": [],
        "food": [],
        "crafts": [],
        "cultural_experiences": [],
    }

    if category in (None, "attractions"):
        for row in destinations:
            coordinates = _coordinates(row)
            if coordinates is None:
                continue
            distance = haversine_km(*center, *coordinates)
            if distance <= radius_km:
                results["destinations"].append({
                    "record": row,
                    "distance_km": round(distance, 3),
                    "location_destination_id": row["destination_id"],
                })

    needs_food = category in (None, "food")
    needs_crafts = category in (None, "crafts", "culture")
    gi_destinations: dict[str, list[str]] = {}
    if needs_food or needs_crafts:
        for gi_record in load_dataset(DATASETS["gi_products"]):
            if not _is_community_submission(gi_record):
                gi_id = gi_record.get("gi_id", "").strip()
                destination_id = gi_record.get("destination_id", "").strip()
                if gi_id and destination_id:
                    gi_destinations.setdefault(gi_id, []).append(destination_id)

    crafts: list[dict[str, str]] = []
    if needs_crafts:
        crafts = [
            row for row in load_dataset(DATASETS["crafts"])
            if not _is_community_submission(row)
        ]

    if needs_food:
        results["food"] = _nearby_records(
            load_dataset(DATASETS["food"]),
            lambda record: gi_destinations.get(record.get("gi_id", "").strip(), []),
            destinations_by_id,
            center,
            radius_km,
        )

    if category in (None, "crafts"):
        results["crafts"] = _nearby_records(
            crafts,
            lambda record: _destination_links(record, gi_destinations),
            destinations_by_id,
            center,
            radius_km,
        )

    if category in (None, "culture"):
        crafts_by_id = {
            row.get("craft_id", "").strip(): row
            for row in crafts if row.get("craft_id")
        }

        def experience_links(record: dict[str, str]) -> list[str]:
            direct_destination = record.get("destination_id", "").strip()
            if direct_destination:
                return [direct_destination]
            craft = crafts_by_id.get(record.get("craft_id", "").strip())
            return _destination_links(craft, gi_destinations) if craft else []

        results["cultural_experiences"] = _nearby_records(
            [
                row for row in load_dataset(DATASETS["cultural_experiences"])
                if not _is_community_submission(row)
            ],
            experience_links,
            destinations_by_id,
            center,
            radius_km,
        )

    return {
        "selected_location": {
            "destination_id": selected.get("destination_id"),
            "name": selected.get("name"),
            "latitude": selected.get("latitude") or None,
            "longitude": selected.get("longitude") or None,
            "search_center": {
                "latitude": center[0],
                "longitude": center[1],
                "source": "custom" if latitude is not None else "destination",
            },
        },
        "radius_km": radius_km,
        "category": category,
        "results": results,
        "total_result_count": sum(len(items) for items in results.values()),
    }
