"""Data loading, filtering, search, relationship, and nearby-recommendation logic for WAYBOUND."""

from __future__ import annotations

import csv
from math import asin, cos, radians, sin, sqrt
from pathlib import Path


def load_csv(path: str | Path) -> list[dict]:
    """Load any UTF-8 CSV file into a list of dictionaries."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_destinations(path: str | Path = "data/destinations.csv") -> list[dict]:
    """Load destinations and convert latitude/longitude fields to floats."""
    places = load_csv(path)
    for p in places:  # CSV gives text, so turn lat/lng into numbers
        p["latitude"] = float(p["latitude"])
        p["longitude"] = float(p["longitude"])
    return places


def load_food(path: str | Path = "data/food.csv") -> list[dict]:
    """Load regional food records."""
    return load_csv(path)


def load_crafts(path: str | Path = "data/crafts.csv") -> list[dict]:
    """Load traditional craft records."""
    return load_csv(path)


def load_experiences(path: str | Path = "data/cultural_experiences.csv") -> list[dict]:
    """Load cultural experience records."""
    return load_csv(path)


def load_gi_products(path: str | Path = "data/gi_products.csv") -> list[dict]:
    """Load Geographical Indication (GI) product records."""
    return load_csv(path)


def load_media_assets(path: str | Path = "data/media_assets.csv") -> list[dict]:
    """Load media asset collection records."""
    return load_csv(path)


def load_sources_reference(path: str | Path = "data/sources_reference.csv") -> list[dict]:
    """Load normalized source-reference mapping rows."""
    return load_csv(path)


def safe_places(places: list[dict]) -> list[dict]:
    """Keep only single point destinations verified from an official source."""
    return [
        p
        for p in places
        if p["record_kind"] == "point_destination"
        and p["verification_status"] == "verified_official_source"
    ]


def _contains(haystack: str | None, needle: str | None) -> bool:
    if not needle:
        return True
    return needle.strip().lower() in (haystack or "").lower()


def _text_matches(row: dict, fields: tuple[str, ...], text: str | None) -> bool:
    if not text:
        return True
    combined = " ".join(str(row.get(field) or "") for field in fields).lower()
    return text.strip().lower() in combined


def filter_places(
    places: list[dict],
    state: str | None = None,
    district: str | None = None,
    category: str | None = None,
    text: str | None = None,
) -> list[dict]:
    """Filter destination records by state, district, category, and free-text query."""
    return [
        p
        for p in places
        if _contains(p.get("state"), state)
        and _contains(p.get("district"), district)
        and _contains(p.get("category"), category)
        and _text_matches(p, ("name", "description", "category", "district", "state"), text)
    ]


def filter_food(
    foods: list[dict],
    state: str | None = None,
    district: str | None = None,
    text: str | None = None,
    gi_only: bool = False,
) -> list[dict]:
    """Filter food records by state, district, optional GI status, and free text."""
    return [
        f
        for f in foods
        if _contains(f.get("state"), state)
        and _contains(f.get("district"), district)
        and (not gi_only or bool((f.get("gi_id") or "").strip()))
        and _text_matches(
            f,
            ("food_name", "origin_place", "ingredients", "description", "cultural_significance"),
            text,
        )
    ]


def filter_crafts(
    crafts: list[dict],
    state: str | None = None,
    district: str | None = None,
    destination_id: str | None = None,
    text: str | None = None,
) -> list[dict]:
    """Filter craft records by state, district, linked destination_id, and free text."""
    return [
        c
        for c in crafts
        if _contains(c.get("state"), state)
        and _contains(c.get("district"), district)
        and (not destination_id or c.get("destination_id") == destination_id)
        and _text_matches(
            c,
            ("craft_name", "origin_place", "materials", "techniques_process", "products", "history_note"),
            text,
        )
    ]


def filter_experiences(
    experiences: list[dict],
    state: str | None = None,
    district: str | None = None,
    destination_id: str | None = None,
    craft_id: str | None = None,
    experience_type: str | None = None,
    text: str | None = None,
) -> list[dict]:
    """Filter cultural experience records by location, links, type, and free text."""
    return [
        e
        for e in experiences
        if _contains(e.get("state"), state)
        and _contains(e.get("district"), district)
        and (not destination_id or e.get("destination_id") == destination_id)
        and (not craft_id or e.get("craft_id") == craft_id)
        and _contains(e.get("experience_type"), experience_type)
        and _text_matches(e, ("name", "experience_type", "description", "months_or_season"), text)
    ]


def filter_gi_products(
    gi_products: list[dict],
    state: str | None = None,
    district: str | None = None,
    destination_id: str | None = None,
    category: str | None = None,
    text: str | None = None,
) -> list[dict]:
    """Filter GI products by state, origin district, linked destination_id, category, and text."""
    return [
        g
        for g in gi_products
        if _contains(g.get("state_ut_normalised"), state)
        and _contains(g.get("origin_district"), district)
        and (not destination_id or g.get("destination_id") == destination_id)
        and _contains(g.get("goods_category"), category)
        and _text_matches(g, ("gi_name", "base_name", "origin_place", "origin_district", "goods_category"), text)
    ]


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return haversine straight-line distance in kilometres between two points."""
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def nearby(
    places: list[dict],
    lat: float,
    lng: float,
    radius_km: float = 50,
    exclude_id: str | None = None,
) -> list[dict]:
    """Return places within radius_km of (lat, lng), sorted nearest-first."""
    found = []
    for p in places:
        if p["destination_id"] == exclude_id:
            continue
        d = distance_km(lat, lng, p["latitude"], p["longitude"])
        if d <= radius_km:
            found.append({**p, "distance_km": round(d, 1)})
    return sorted(found, key=lambda x: x["distance_km"])


def _food_matches_place(food_row: dict, place: dict) -> tuple[bool, bool]:
    """Return (matches_district_or_origin, is_statewide_specialty) for a food row and place."""
    place_state = (place.get("state") or "").lower()
    food_state = (food_row.get("state") or "").lower()
    if food_state and place_state and food_state not in place_state:
        return False, False

    food_district = (food_row.get("district") or "").strip().lower()
    if "statewide" in food_district:
        return False, True

    place_district = (place.get("district") or "").strip().lower()
    place_name = (place.get("name") or "").strip().lower()
    food_origin = (food_row.get("origin_place") or "").strip().lower()

    district_match = bool(place_district) and (
        place_district in food_district or food_district in place_district
    )
    origin_match = bool(place_name) and bool(food_origin) and (
        place_name in food_origin or food_origin in place_name
    )
    return (district_match or origin_match), False


def _load_bundle(data_dir: str | Path = "data") -> dict[str, list[dict]]:
    base = Path(data_dir)
    return {
        "destinations": load_destinations(base / "destinations.csv"),
        "food": load_food(base / "food.csv"),
        "crafts": load_crafts(base / "crafts.csv"),
        "experiences": load_experiences(base / "cultural_experiences.csv"),
        "gi_products": load_gi_products(base / "gi_products.csv"),
        "media_assets": load_media_assets(base / "media_assets.csv"),
        "sources_reference": load_sources_reference(base / "sources_reference.csv"),
    }


def things_at(destination_id: str, data_dir: str | Path = "data") -> dict[str, list[dict]]:
    """Return crafts, cultural experiences, GI products, media, sources, and food for a destination."""
    bundle = _load_bundle(data_dir)
    place = next((p for p in bundle["destinations"] if p["destination_id"] == destination_id), None)

    crafts = [c for c in bundle["crafts"] if c.get("destination_id") == destination_id]
    experiences = [e for e in bundle["experiences"] if e.get("destination_id") == destination_id]
    gi_products = [g for g in bundle["gi_products"] if g.get("destination_id") == destination_id]
    media = [m for m in bundle["media_assets"] if m.get("destination_id") == destination_id]
    sources = [s for s in bundle["sources_reference"] if s.get("destination_id") == destination_id]

    regional_food: list[dict] = []
    statewide_food: list[dict] = []
    if place is not None:
        for f in bundle["food"]:
            is_regional, is_statewide = _food_matches_place(f, place)
            if is_regional:
                regional_food.append(f)
            elif is_statewide:
                statewide_food.append(f)

    return {
        "crafts": crafts,
        "experiences": experiences,
        "gi_products": gi_products,
        "regional_food": regional_food,
        "statewide_food": statewide_food,
        "media": media,
        "sources": sources,
    }


def _states_overlap(state_a: str | None, state_b: str | None) -> bool:
    parts_a = {s.strip().lower() for s in (state_a or "").split("/") if s.strip()}
    parts_b = {s.strip().lower() for s in (state_b or "").split("/") if s.strip()}
    return bool(parts_a & parts_b)


def recommend_nearby(
    destination_id: str,
    radius_km: float = 100,
    limit: int = 5,
    safe_only: bool = True,
    same_state_only: bool = False,
    data_dir: str | Path = "data",
) -> list[dict]:
    """Recommend nearby attractions for a destination, enriched with linked crafts and experiences."""
    bundle = _load_bundle(data_dir)
    places = bundle["destinations"]
    origin = next((p for p in places if p["destination_id"] == destination_id), None)
    if origin is None:
        return []

    candidates = safe_places(places) if safe_only else places
    if same_state_only:
        candidates = [c for c in candidates if _states_overlap(origin.get("state"), c.get("state"))]

    matches = nearby(
        candidates,
        origin["latitude"],
        origin["longitude"],
        radius_km=radius_km,
        exclude_id=destination_id,
    )[:limit]

    crafts_by_dest: dict[str, list[dict]] = {}
    for c in bundle["crafts"]:
        crafts_by_dest.setdefault(c.get("destination_id") or "", []).append(c)

    exp_by_dest: dict[str, list[dict]] = {}
    for e in bundle["experiences"]:
        exp_by_dest.setdefault(e.get("destination_id") or "", []).append(e)

    recommendations = []
    for item in matches:
        did = item["destination_id"]
        linked_crafts = crafts_by_dest.get(did, [])
        linked_exp = exp_by_dest.get(did, [])
        recommendations.append(
            {
                **item,
                "craft_count": len(linked_crafts),
                "experience_count": len(linked_exp),
                "crafts": [c["craft_name"] for c in linked_crafts],
                "experiences": [e["name"] for e in linked_exp],
            }
        )
    return recommendations


def get_destination_details(
    destination_id: str,
    radius_km: float = 100,
    nearby_limit: int = 5,
    safe_only: bool = True,
    data_dir: str | Path = "data",
) -> dict | None:
    """Return a destination with its related items and nearby recommendations."""
    bundle = _load_bundle(data_dir)
    place = next((p for p in bundle["destinations"] if p["destination_id"] == destination_id), None)
    if place is None:
        return None

    return {
        "destination": place,
        "related": things_at(destination_id, data_dir=data_dir),
        "nearby_recommendations": recommend_nearby(
            destination_id,
            radius_km=radius_km,
            limit=nearby_limit,
            safe_only=safe_only,
            data_dir=data_dir,
        ),
    }


def search_all(
    query: str | None = None,
    state: str | None = None,
    district: str | None = None,
    safe_only: bool = True,
    data_dir: str | Path = "data",
) -> dict[str, list[dict]]:
    """Search across destinations, food, crafts, cultural experiences, and GI products."""
    bundle = _load_bundle(data_dir)
    places = safe_places(bundle["destinations"]) if safe_only else bundle["destinations"]

    return {
        "destinations": filter_places(places, state=state, district=district, text=query),
        "food": filter_food(bundle["food"], state=state, district=district, text=query),
        "crafts": filter_crafts(bundle["crafts"], state=state, district=district, text=query),
        "experiences": filter_experiences(bundle["experiences"], state=state, district=district, text=query),
        "gi_products": filter_gi_products(bundle["gi_products"], state=state, district=district, text=query),
    }
