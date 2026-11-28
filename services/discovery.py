"""Point-radius and route-corridor tourism discovery across canonical and community records."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.services.submission_service import (
    SubmissionStorageError,
    SubmissionStore,
    enrich_approved_submission,
    get_store,
)
from config import settings
from data_access import DATASETS, load_dataset

EARTH_RADIUS_KM = 6371.0
ROUTE_EARTH_RADIUS_KM = 6371.0088


def _is_http_url(value: Any) -> bool:
    url = str(value or "").strip()
    return url.startswith("https://") or url.startswith("http://")


def _load_low_visibility_evidence() -> dict[str, dict[str, Any]]:
    """Load optional low-visibility evidence annotations from the sidecar JSON file."""
    path = Path(settings.LOW_VISIBILITY_EVIDENCE_PATH)
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return {
        str(k): v
        for k, v in data.items()
        if isinstance(v, dict)
    }


def _apply_hidden_gem(
    record: dict[str, Any],
    record_id: str | None,
    evidence_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Mark hidden_gem=True only for non-community records with valid URL + note evidence."""
    if record.get("verified") is False:
        return record, False

    entry = evidence_map.get(str(record_id or "").strip(), {})
    url = str(
        entry.get("low_visibility_evidence_url")
        or record.get("low_visibility_evidence_url")
        or ""
    ).strip()
    note = str(
        entry.get("low_visibility_note")
        or record.get("low_visibility_note")
        or ""
    ).strip()

    if _is_http_url(url) and bool(note):
        enriched = {
            **record,
            "low_visibility_evidence_url": url,
            "low_visibility_note": note,
        }
        return enriched, True

    return record, False


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


def point_to_polyline_km(
    point_lat: float,
    point_lon: float,
    line_coords: list[list[float]],
) -> float:
    """Return minimum geometric distance (km) from a point to a GeoJSON LineString.

    Uses a local equirectangular metric projection centered at each segment's
    midpoint (Earth radius 6371.0088 km) with clamped point-to-segment projection.
    """
    lat_p = math.radians(point_lat)
    lon_p = math.radians(point_lon)
    best = float("inf")

    for (lon1_deg, lat1_deg), (lon2_deg, lat2_deg) in zip(line_coords, line_coords[1:]):
        lon1 = math.radians(lon1_deg)
        lat1 = math.radians(lat1_deg)
        lon2 = math.radians(lon2_deg)
        lat2 = math.radians(lat2_deg)

        lon0 = (lon1 + lon2) / 2.0
        phi0 = (lat1 + lat2) / 2.0
        cos_phi0 = math.cos(phi0)

        x1 = ROUTE_EARTH_RADIUS_KM * cos_phi0 * (lon1 - lon0)
        y1 = ROUTE_EARTH_RADIUS_KM * (lat1 - phi0)
        x2 = ROUTE_EARTH_RADIUS_KM * cos_phi0 * (lon2 - lon0)
        y2 = ROUTE_EARTH_RADIUS_KM * (lat2 - phi0)
        xp = ROUTE_EARTH_RADIUS_KM * cos_phi0 * (lon_p - lon0)
        yp = ROUTE_EARTH_RADIUS_KM * (lat_p - phi0)

        dx = x2 - x1
        dy = y2 - y1
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq == 0.0:
            dist = math.hypot(xp - x1, yp - y1)
        else:
            t = max(0.0, min(1.0, ((xp - x1) * dx + (yp - y1) * dy) / seg_len_sq))
            dist = math.hypot(xp - (x1 + t * dx), yp - (y1 + t * dy))

        if dist < best:
            best = dist

    return best


def _coordinates(record: dict[str, Any]) -> tuple[float, float] | None:
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
    if any(
        record.get(field, "").strip().upper().startswith("USR-")
        for field in ("destination_id", "food_id", "craft_id", "experience_id", "gi_id")
    ):
        return True
    return "user submitted" in record.get("verification_status", "").casefold()


def _destination_links(
    record: dict[str, Any],
    gi_destinations: dict[str, list[str]],
) -> list[str]:
    destination_id = str(record.get("destination_id") or "").strip()
    if destination_id:
        return [destination_id]
    return gi_destinations.get(str(record.get("gi_id") or "").strip(), [])


def _load_approved_submissions(store: SubmissionStore | None) -> list[dict[str, Any]]:
    active_store = store if store is not None else get_store()
    try:
        items = active_store.list_by_status("approved")
    except SubmissionStorageError as exc:
        raise DiscoveryError(500, str(exc)) from exc
    return [enrich_approved_submission(item) for item in items]


def _split_community_records(
    approved: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[tuple[str, str], list[dict[str, Any]]]]:
    """Separate standalone community records from canonical-duplicate contributions."""
    standalone: dict[str, list[dict[str, Any]]] = {
        "destination": [],
        "food": [],
        "craft": [],
        "cultural_experience": [],
    }
    contributions: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for item in approved:
        sub_type = str(item.get("submission_type") or "")
        canonical_id = str(item.get("canonical_record_id") or "").strip()
        if canonical_id:
            contributions.setdefault((sub_type, canonical_id), []).append(
                {
                    "submission_id": item["id"],
                    "submission_type": sub_type,
                    "name": item.get("name"),
                    "status": item.get("status", "approved"),
                    "verification_status": item.get(
                        "verification_status", "community_approved_unverified"
                    ),
                    "verified": False,
                }
            )
        elif sub_type in standalone:
            standalone[sub_type].append(item)

    return standalone, contributions


def _with_contributions(
    record: dict[str, Any],
    contributions: dict[tuple[str, str], list[dict[str, Any]]],
    sub_type: str,
    id_field: str,
) -> dict[str, Any]:
    record_id = str(record.get(id_field) or "").strip()
    linked = contributions.get((sub_type, record_id))
    if not linked:
        return record
    return {**record, "community_contributions": linked}


def _load_canonical_catalog() -> dict[str, Any]:
    destinations = [
        row
        for row in load_dataset(DATASETS["destinations"])
        if not _is_community_submission(row)
    ]
    destinations_by_id = {
        row["destination_id"]: row for row in destinations if row.get("destination_id")
    }

    gi_destinations: dict[str, list[str]] = {}
    for gi_record in load_dataset(DATASETS["gi_products"]):
        if not _is_community_submission(gi_record):
            gi_id = gi_record.get("gi_id", "").strip()
            destination_id = gi_record.get("destination_id", "").strip()
            if gi_id and destination_id:
                gi_destinations.setdefault(gi_id, []).append(destination_id)

    crafts = [
        row for row in load_dataset(DATASETS["crafts"]) if not _is_community_submission(row)
    ]
    crafts_by_id = {
        row.get("craft_id", "").strip(): row for row in crafts if row.get("craft_id")
    }
    food = [
        row for row in load_dataset(DATASETS["food"]) if not _is_community_submission(row)
    ]
    experiences = [
        row
        for row in load_dataset(DATASETS["cultural_experiences"])
        if not _is_community_submission(row)
    ]
    return {
        "destinations": destinations,
        "destinations_by_id": destinations_by_id,
        "gi_destinations": gi_destinations,
        "crafts": crafts,
        "crafts_by_id": crafts_by_id,
        "food": food,
        "experiences": experiences,
    }


def _community_anchor_candidates(
    item: dict[str, Any],
    sub_type: str,
    destinations_by_id: dict[str, dict[str, str]],
    crafts_by_id: dict[str, dict[str, str]],
    gi_destinations: dict[str, list[str]],
) -> list[tuple[tuple[float, float], str | None]]:
    """Resolve spatial anchor coordinates for a standalone community submission."""
    own_coords = _coordinates(item)
    dest_id = str(item.get("destination_id") or "").strip() or None
    if own_coords is not None:
        return [(own_coords, item.get("id") if sub_type == "destination" else dest_id)]

    if sub_type == "destination":
        return []

    candidate_dest_ids: list[str] = []
    if dest_id:
        candidate_dest_ids.append(dest_id)
    elif sub_type == "cultural_experience":
        craft_id = str(item.get("craft_id") or "").strip()
        craft = crafts_by_id.get(craft_id) if craft_id else None
        if craft:
            candidate_dest_ids.extend(_destination_links(craft, gi_destinations))

    anchors: list[tuple[tuple[float, float], str | None]] = []
    for candidate_id in candidate_dest_ids:
        dest = destinations_by_id.get(candidate_id)
        coords = _coordinates(dest) if dest else None
        if coords is not None:
            anchors.append((coords, candidate_id))
    return anchors


def _nearby_records(
    records: list[dict[str, str]],
    link_resolver: Callable[[dict[str, str]], list[str]],
    destinations_by_id: dict[str, dict[str, str]],
    center: tuple[float, float],
    radius_km: int,
    contributions: dict[tuple[str, str], list[dict[str, Any]]],
    sub_type: str,
    id_field: str,
) -> list[dict[str, Any]]:
    nearby = []
    for record in records:
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
            nearby.append(
                {
                    "record": _with_contributions(record, contributions, sub_type, id_field),
                    "distance_km": round(distance, 3),
                    "location_destination_id": location_destination_id,
                }
            )
    return nearby


def discover_nearby(
    destination: str,
    radius_km: int = 10,
    category: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    store: SubmissionStore | None = None,
) -> dict[str, Any]:
    """Find public records within a radius of a destination or custom point."""
    catalog = _load_canonical_catalog()
    destinations = catalog["destinations"]
    destinations_by_id = catalog["destinations_by_id"]
    gi_destinations = catalog["gi_destinations"]
    crafts = catalog["crafts"]
    crafts_by_id = catalog["crafts_by_id"]

    approved = _load_approved_submissions(store)
    standalone, contributions = _split_community_records(approved)
    community_destinations = [
        item for item in standalone["destination"] if _coordinates(item) is not None
    ]

    search_key = destination.strip().casefold()
    matches = [
        row
        for row in destinations
        if row.get("destination_id", "").strip().casefold() == search_key
        or row.get("name", "").strip().casefold() == search_key
    ]
    if not matches:
        matches = [
            row
            for row in community_destinations
            if str(row.get("id") or "").strip().casefold() == search_key
            or str(row.get("name") or "").strip().casefold() == search_key
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
                results["destinations"].append(
                    {
                        "record": _with_contributions(
                            row, contributions, "destination", "destination_id"
                        ),
                        "distance_km": round(distance, 3),
                        "location_destination_id": row["destination_id"],
                    }
                )
        for item in community_destinations:
            coordinates = _coordinates(item)
            if coordinates is None:
                continue
            distance = haversine_km(*center, *coordinates)
            if distance <= radius_km:
                results["destinations"].append(
                    {
                        "record": item,
                        "distance_km": round(distance, 3),
                        "location_destination_id": item["id"],
                    }
                )

    if category in (None, "food"):
        results["food"] = _nearby_records(
            catalog["food"],
            lambda record: gi_destinations.get(record.get("gi_id", "").strip(), []),
            destinations_by_id,
            center,
            radius_km,
            contributions,
            "food",
            "food_id",
        )
        _append_community_nearby(
            results["food"],
            standalone["food"],
            "food",
            destinations_by_id,
            crafts_by_id,
            gi_destinations,
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
            contributions,
            "craft",
            "craft_id",
        )
        _append_community_nearby(
            results["crafts"],
            standalone["craft"],
            "craft",
            destinations_by_id,
            crafts_by_id,
            gi_destinations,
            center,
            radius_km,
        )

    if category in (None, "culture"):
        def experience_links(record: dict[str, str]) -> list[str]:
            direct_destination = record.get("destination_id", "").strip()
            if direct_destination:
                return [direct_destination]
            craft = crafts_by_id.get(record.get("craft_id", "").strip())
            return _destination_links(craft, gi_destinations) if craft else []

        results["cultural_experiences"] = _nearby_records(
            catalog["experiences"],
            experience_links,
            destinations_by_id,
            center,
            radius_km,
            contributions,
            "cultural_experience",
            "experience_id",
        )
        _append_community_nearby(
            results["cultural_experiences"],
            standalone["cultural_experience"],
            "cultural_experience",
            destinations_by_id,
            crafts_by_id,
            gi_destinations,
            center,
            radius_km,
        )

    return {
        "selected_location": {
            "destination_id": selected.get("destination_id") or selected.get("id"),
            "name": selected.get("name"),
            "latitude": str(selected["latitude"]) if selected.get("latitude") is not None else None,
            "longitude": str(selected["longitude"]) if selected.get("longitude") is not None else None,
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


def _append_community_nearby(
    target: list[dict[str, Any]],
    items: list[dict[str, Any]],
    sub_type: str,
    destinations_by_id: dict[str, dict[str, str]],
    crafts_by_id: dict[str, dict[str, str]],
    gi_destinations: dict[str, list[str]],
    center: tuple[float, float],
    radius_km: int,
) -> None:
    for item in items:
        anchors = _community_anchor_candidates(
            item, sub_type, destinations_by_id, crafts_by_id, gi_destinations
        )
        within = [
            (haversine_km(*center, lat, lon), loc_id)
            for (lat, lon), loc_id in anchors
        ]
        within = [(d, loc_id) for d, loc_id in within if d <= radius_km]
        if within:
            distance, location_destination_id = min(within, key=lambda pair: pair[0])
            target.append(
                {
                    "record": item,
                    "distance_km": round(distance, 3),
                    "location_destination_id": location_destination_id,
                }
            )


def _matches_destination_categories(
    record: dict[str, Any],
    requested_categories: list[str] | None,
) -> bool:
    if not requested_categories:
        return True
    wanted = [c.strip().casefold() for c in requested_categories if c.strip()]
    if not wanted:
        return True
    raw_category = str(record.get("category") or "")
    tokens = [
        tok.strip().casefold()
        for tok in re.split(r"[;,/|]+", raw_category)
        if tok.strip()
    ]
    return any(
        req == tok or req in tok
        for req in wanted
        for tok in tokens
    )


def _corridor_records(
    records: list[dict[str, str]],
    link_resolver: Callable[[dict[str, str]], list[str]],
    destinations_by_id: dict[str, dict[str, str]],
    line_coords: list[list[float]],
    half_width_km: float,
    contributions: dict[tuple[str, str], list[dict[str, Any]]],
    sub_type: str,
    id_field: str,
    evidence_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    matched = []
    for record in records:
        candidates = []
        for destination_id in link_resolver(record):
            destination = destinations_by_id.get(destination_id)
            coordinates = _coordinates(destination) if destination else None
            if coordinates is None:
                continue
            dist = point_to_polyline_km(coordinates[0], coordinates[1], line_coords)
            if dist <= half_width_km:
                candidates.append((dist, destination_id))

        if candidates:
            dist, location_destination_id = min(candidates, key=lambda pair: pair[0])
            enriched_record = _with_contributions(record, contributions, sub_type, id_field)
            enriched_record, is_hidden_gem = _apply_hidden_gem(
                enriched_record, record.get(id_field), evidence_map
            )
            matched.append(
                {
                    "record": enriched_record,
                    "distance_to_route_km": round(dist, 3),
                    "location_destination_id": location_destination_id,
                    "popularity_status": "not_assessed",
                    "hidden_gem": is_hidden_gem,
                }
            )
    return matched


def _append_community_corridor(
    target: list[dict[str, Any]],
    items: list[dict[str, Any]],
    sub_type: str,
    destinations_by_id: dict[str, dict[str, str]],
    crafts_by_id: dict[str, dict[str, str]],
    gi_destinations: dict[str, list[str]],
    line_coords: list[list[float]],
    half_width_km: float,
) -> None:
    for item in items:
        anchors = _community_anchor_candidates(
            item, sub_type, destinations_by_id, crafts_by_id, gi_destinations
        )
        within = [
            (point_to_polyline_km(lat, lon, line_coords), loc_id)
            for (lat, lon), loc_id in anchors
        ]
        within = [(d, loc_id) for d, loc_id in within if d <= half_width_km]
        if within:
            dist, location_destination_id = min(within, key=lambda pair: pair[0])
            target.append(
                {
                    "record": item,
                    "distance_to_route_km": round(dist, 3),
                    "location_destination_id": location_destination_id,
                    "popularity_status": "not_assessed",
                    "hidden_gem": False,
                }
            )


def discover_along_route(
    starting_town_name: str,
    popular_destination_id: str,
    popular_destination_name: str | None,
    line_coords: list[list[float]],
    corridor_width_km: float,
    experience_categories: list[str] | None = None,
    destination_categories: list[str] | None = None,
    store: SubmissionStore | None = None,
) -> dict[str, Any]:
    """Discover canonical and approved community listings along a route corridor."""
    catalog = _load_canonical_catalog()
    destinations = catalog["destinations"]
    destinations_by_id = catalog["destinations_by_id"]
    gi_destinations = catalog["gi_destinations"]
    crafts = catalog["crafts"]
    crafts_by_id = catalog["crafts_by_id"]

    dest_key = popular_destination_id.strip().casefold()
    canonical_dest = next(
        (
            row
            for row in destinations
            if row.get("destination_id", "").strip().casefold() == dest_key
        ),
        None,
    )
    if canonical_dest is None:
        raise DiscoveryError(
            404,
            f"Destination '{popular_destination_id}' was not found.",
        )

    if popular_destination_name is not None and popular_destination_name.strip():
        if (
            popular_destination_name.strip().casefold()
            != canonical_dest.get("name", "").strip().casefold()
        ):
            raise DiscoveryError(
                422,
                f"popular_destination.name '{popular_destination_name}' does not match "
                f"canonical destination '{canonical_dest.get('name', '')}' "
                f"({canonical_dest.get('destination_id')}).",
            )

    approved = _load_approved_submissions(store)
    standalone, contributions = _split_community_records(approved)
    evidence_map = _load_low_visibility_evidence()

    half_width_km = corridor_width_km / 2.0
    active_exp_cats = (
        set(experience_categories)
        if experience_categories is not None
        else {"food", "crafts", "culture"}
    )

    results: dict[str, list[dict[str, Any]]] = {
        "destinations": [],
        "food": [],
        "crafts": [],
        "cultural_experiences": [],
    }

    for row in destinations:
        if not _matches_destination_categories(row, destination_categories):
            continue
        coords = _coordinates(row)
        if coords is None:
            continue
        dist = point_to_polyline_km(coords[0], coords[1], line_coords)
        if dist <= half_width_km:
            enriched_record = _with_contributions(
                row, contributions, "destination", "destination_id"
            )
            enriched_record, is_hidden_gem = _apply_hidden_gem(
                enriched_record, row.get("destination_id"), evidence_map
            )
            results["destinations"].append(
                {
                    "record": enriched_record,
                    "distance_to_route_km": round(dist, 3),
                    "location_destination_id": row["destination_id"],
                    "popularity_status": "not_assessed",
                    "hidden_gem": is_hidden_gem,
                }
            )

    for item in standalone["destination"]:
        if not _matches_destination_categories(item, destination_categories):
            continue
        coords = _coordinates(item)
        if coords is None:
            continue
        dist = point_to_polyline_km(coords[0], coords[1], line_coords)
        if dist <= half_width_km:
            results["destinations"].append(
                {
                    "record": item,
                    "distance_to_route_km": round(dist, 3),
                    "location_destination_id": item["id"],
                    "popularity_status": "not_assessed",
                    "hidden_gem": False,
                }
            )

    if "food" in active_exp_cats:
        results["food"] = _corridor_records(
            catalog["food"],
            lambda record: gi_destinations.get(record.get("gi_id", "").strip(), []),
            destinations_by_id,
            line_coords,
            half_width_km,
            contributions,
            "food",
            "food_id",
            evidence_map,
        )
        _append_community_corridor(
            results["food"],
            standalone["food"],
            "food",
            destinations_by_id,
            crafts_by_id,
            gi_destinations,
            line_coords,
            half_width_km,
        )

    if "crafts" in active_exp_cats:
        results["crafts"] = _corridor_records(
            crafts,
            lambda record: _destination_links(record, gi_destinations),
            destinations_by_id,
            line_coords,
            half_width_km,
            contributions,
            "craft",
            "craft_id",
            evidence_map,
        )
        _append_community_corridor(
            results["crafts"],
            standalone["craft"],
            "craft",
            destinations_by_id,
            crafts_by_id,
            gi_destinations,
            line_coords,
            half_width_km,
        )

    if "culture" in active_exp_cats:
        def experience_links(record: dict[str, str]) -> list[str]:
            direct_destination = record.get("destination_id", "").strip()
            if direct_destination:
                return [direct_destination]
            craft = crafts_by_id.get(record.get("craft_id", "").strip())
            return _destination_links(craft, gi_destinations) if craft else []

        results["cultural_experiences"] = _corridor_records(
            catalog["experiences"],
            experience_links,
            destinations_by_id,
            line_coords,
            half_width_km,
            contributions,
            "cultural_experience",
            "experience_id",
            evidence_map,
        )
        _append_community_corridor(
            results["cultural_experiences"],
            standalone["cultural_experience"],
            "cultural_experience",
            destinations_by_id,
            crafts_by_id,
            gi_destinations,
            line_coords,
            half_width_km,
        )

    for items in results.values():
        items.sort(key=lambda item: item["distance_to_route_km"])

    total_result_count = sum(len(items) for items in results.values())
    return {
        "route": {
            "starting_town": starting_town_name.strip(),
            "popular_destination": {
                "destination_id": canonical_dest["destination_id"],
                "name": canonical_dest["name"],
            },
            "corridor_width_km": corridor_width_km,
            "distance_method": "local_equirectangular_point_to_segment",
        },
        "coverage_status": "matches_found" if total_result_count > 0 else "no_catalog_matches",
        "results": results,
        "total_result_count": total_result_count,
    }
