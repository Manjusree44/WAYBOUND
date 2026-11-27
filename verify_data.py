"""Audit WAYBOUND datasets for valid coordinates, source URLs, and referential integrity."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from discovery import (
    load_crafts,
    load_destinations,
    load_experiences,
    load_food,
    load_gi_products,
    load_media_assets,
    load_sources_reference,
    safe_places,
)

# Bounding box covering Andhra Pradesh and Telangana (with buffer)
REGIONAL_LAT_BOUNDS = (12.5, 20.5)
REGIONAL_LNG_BOUNDS = (76.5, 85.5)


def _is_http_url(value: str | None) -> bool:
    url = (value or "").strip()
    return url.startswith("https://") or url.startswith("http://")


def verify_all(data_dir: str | Path = "data", write_report: bool = True) -> dict:
    """Run coordinate, source-URL, verification-status, and foreign-key checks."""
    base = Path(data_dir)
    places = load_destinations(base / "destinations.csv")
    foods = load_food(base / "food.csv")
    crafts = load_crafts(base / "crafts.csv")
    experiences = load_experiences(base / "cultural_experiences.csv")
    gi_products = load_gi_products(base / "gi_products.csv")
    media = load_media_assets(base / "media_assets.csv")
    sources = load_sources_reference(base / "sources_reference.csv")

    dest_ids = {p["destination_id"] for p in places}
    food_ids = {f["food_id"] for f in foods}
    craft_ids = {c["craft_id"] for c in crafts}
    exp_ids = {e["experience_id"] for e in experiences}
    gi_ids = {g["gi_id"] for g in gi_products}
    media_ids = {m["media_id"] for m in media}

    id_sets_by_file = {
        "destinations.csv": dest_ids,
        "food.csv": food_ids,
        "crafts.csv": craft_ids,
        "cultural_experiences.csv": exp_ids,
        "gi_products.csv": gi_ids,
        "media_assets.csv": media_ids,
    }

    coordinate_issues: list[dict] = []
    missing_source_urls: list[dict] = []
    broken_links: list[dict] = []

    for p in places:
        did = p["destination_id"]
        lat, lng = p["latitude"], p["longitude"]
        if not (REGIONAL_LAT_BOUNDS[0] <= lat <= REGIONAL_LAT_BOUNDS[1]) or not (
            REGIONAL_LNG_BOUNDS[0] <= lng <= REGIONAL_LNG_BOUNDS[1]
        ):
            coordinate_issues.append(
                {"destination_id": did, "name": p["name"], "issue": "outside_ap_telangana_bounds", "lat": lat, "lng": lng}
            )
        if not _is_http_url(p.get("coordinate_source_url")):
            coordinate_issues.append(
                {"destination_id": did, "name": p["name"], "issue": "missing_coordinate_source_url"}
            )
        if not (p.get("coordinate_note") or "").strip():
            coordinate_issues.append(
                {"destination_id": did, "name": p["name"], "issue": "missing_coordinate_note"}
            )
        if not _is_http_url(p.get("source_url_primary")):
            missing_source_urls.append({"dataset": "destinations.csv", "id": did, "field": "source_url_primary"})

    for dataset_name, rows, id_col, url_col in [
        ("food.csv", foods, "food_id", "source_url_primary"),
        ("crafts.csv", crafts, "craft_id", "source_url_primary"),
        ("cultural_experiences.csv", experiences, "experience_id", "source_url_primary"),
        ("gi_products.csv", gi_products, "gi_id", "source_url"),
        ("media_assets.csv", media, "media_id", "source_page_url"),
    ]:
        for row in rows:
            if not _is_http_url(row.get(url_col)):
                missing_source_urls.append({"dataset": dataset_name, "id": row[id_col], "field": url_col})

    for c in crafts:
        if c.get("destination_id") and c["destination_id"] not in dest_ids:
            broken_links.append({"dataset": "crafts.csv", "id": c["craft_id"], "destination_id": c["destination_id"]})
        if c.get("gi_id") and c["gi_id"] not in gi_ids:
            broken_links.append({"dataset": "crafts.csv", "id": c["craft_id"], "gi_id": c["gi_id"]})

    for e in experiences:
        if e.get("destination_id") and e["destination_id"] not in dest_ids:
            broken_links.append({"dataset": "cultural_experiences.csv", "id": e["experience_id"], "destination_id": e["destination_id"]})
        if e.get("craft_id") and e["craft_id"] not in craft_ids:
            broken_links.append({"dataset": "cultural_experiences.csv", "id": e["experience_id"], "craft_id": e["craft_id"]})

    for f in foods:
        if f.get("gi_id") and f["gi_id"] not in gi_ids:
            broken_links.append({"dataset": "food.csv", "id": f["food_id"], "gi_id": f["gi_id"]})

    for g in gi_products:
        if g.get("destination_id") and g["destination_id"] not in dest_ids:
            broken_links.append({"dataset": "gi_products.csv", "id": g["gi_id"], "destination_id": g["destination_id"]})

    for m in media:
        if m.get("destination_id") and m["destination_id"] not in dest_ids:
            broken_links.append({"dataset": "media_assets.csv", "id": m["media_id"], "destination_id": m["destination_id"]})

    for s in sources:
        if not _is_http_url(s.get("source_url")):
            missing_source_urls.append({"dataset": "sources_reference.csv", "id": s["record_id"], "field": "source_url"})
        target_ids = id_sets_by_file.get(s.get("dataset_file", ""))
        if target_ids is None or s["record_id"] not in target_ids:
            broken_links.append(
                {"dataset": "sources_reference.csv", "record_id": s["record_id"], "dataset_file": s.get("dataset_file")}
            )
        if s.get("destination_id") and s["destination_id"] not in dest_ids:
            broken_links.append(
                {"dataset": "sources_reference.csv", "record_id": s["record_id"], "destination_id": s["destination_id"]}
            )

    safe = safe_places(places)
    report = {
        "counts": {
            "destinations_total": len(places),
            "destinations_safe": len(safe),
            "food": len(foods),
            "crafts": len(crafts),
            "cultural_experiences": len(experiences),
            "gi_products": len(gi_products),
            "media_assets": len(media),
            "sources_reference": len(sources),
        },
        "destination_record_kinds": dict(Counter(p["record_kind"] for p in places)),
        "verification_statuses": {
            "destinations": dict(Counter(p["verification_status"] for p in places)),
            "food": dict(Counter(f["verification_status"] for f in foods)),
            "crafts": dict(Counter(c["verification_status"] for c in crafts)),
            "cultural_experiences": dict(Counter(e["verification_status"] for e in experiences)),
            "gi_products": dict(Counter(g["verification_status"] for g in gi_products)),
            "media_assets": dict(Counter(m["verification_status"] for m in media)),
        },
        "coordinate_issues": coordinate_issues,
        "missing_source_urls": missing_source_urls,
        "broken_links": broken_links,
        "all_checks_passed": not (coordinate_issues or missing_source_urls or broken_links),
    }

    if write_report:
        report_path = base / "verification_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return report


if __name__ == "__main__":
    summary = verify_all()
    print(json.dumps(summary, indent=2))
