"""Integration tests for catalog, point-radius discovery, route discovery, and frontend serving."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.submission_service import SubmissionStore, get_store
from main import app


@pytest.fixture
def store(tmp_path: Path) -> SubmissionStore:
    return SubmissionStore(tmp_path / "submissions.json")


@pytest.fixture
def client(store: SubmissionStore):
    app.dependency_overrides[get_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_and_frontend_served(client: TestClient):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "WAYBOUND API"}

    home = client.get("/")
    assert home.status_code == 200
    assert "Waybound" in home.text


def test_catalog_includes_only_approved_unverified_submissions(client: TestClient):
    pending = client.post(
        "/api/submissions",
        json={
            "name": "Pending Weaver Stall",
            "description": "Local handloom demonstration.",
            "submission_type": "craft",
            "state": "Telangana",
            "district": "Jangaon",
        },
    ).json()

    approved_sub = client.post(
        "/api/submissions",
        json={
            "name": "Pembarthi Brass Co-op",
            "description": "Community-submitted workshop near Pembarthi.",
            "submission_type": "craft",
            "state": "Telangana",
            "district": "Jangaon",
            "destination_id": "DST-TG-0001",
        },
    ).json()
    assert client.patch(f"/api/submissions/{approved_sub['id']}/approve").status_code == 200

    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    body = catalog.json()
    assert len(body["destinations"]) == 45
    assert len(body["food"]) == 15
    assert len(body["crafts"]) == 20
    assert len(body["cultural_experiences"]) == 13

    community = body["approved_community_submissions"]
    ids = [item["id"] for item in community]
    assert approved_sub["id"] in ids
    assert pending["id"] not in ids
    assert community[0]["verification_status"] == "community_approved_unverified"
    assert community[0]["verified"] is False


def test_existing_point_discovery_and_community_destination(client: TestClient):
    # Canonical check preserves existing structure
    resp = client.get("/api/discover?destination=DST-TG-0001&radius_km=10&category=attractions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_location"]["destination_id"] == "DST-TG-0001"
    assert data["results"]["destinations"][0]["distance_km"] == 0.0

    # Add an approved community destination near Pembarthi
    sub = client.post(
        "/api/submissions",
        json={
            "name": "Pembarthi Artisan Lane",
            "description": "Community-submitted lane.",
            "submission_type": "destination",
            "state": "Telangana",
            "district": "Jangaon",
            "latitude": 17.6900,
            "longitude": 79.1180,
        },
    ).json()
    assert client.patch(f"/api/submissions/{sub['id']}/approve").status_code == 200

    after = client.get("/api/discover?destination=DST-TG-0001&radius_km=10&category=attractions")
    assert after.status_code == 200
    dest_records = [item["record"] for item in after.json()["results"]["destinations"]]
    community_hits = [r for r in dest_records if r.get("id") == sub["id"]]
    assert len(community_hits) == 1
    assert community_hits[0]["verification_status"] == "community_approved_unverified"
    assert community_hits[0]["verified"] is False


def test_route_discovery_corridor_anchors_duplicates_and_filters(client: TestClient):
    # 1. Approved community craft anchored via destination_id (no own coordinates)
    craft_sub = client.post(
        "/api/submissions",
        json={
            "name": "Pembarthi Community Brass",
            "description": "Vendor workshop in Pembarthi.",
            "submission_type": "craft",
            "state": "Telangana",
            "district": "Jangaon",
            "destination_id": "DST-TG-0001",
        },
    ).json()
    assert client.patch(f"/api/submissions/{craft_sub['id']}/approve").status_code == 200

    # 2. Approved cultural experience anchored via canonical craft_id (CRF-TG-0001 -> DST-TG-0001)
    exp_sub = client.post(
        "/api/submissions",
        json={
            "name": "Weekend Metal Embossing Demo",
            "description": "Community demo linked through CRF-TG-0001.",
            "submission_type": "cultural_experience",
            "state": "Telangana",
            "district": "Jangaon",
            "craft_id": "CRF-TG-0001",
        },
    ).json()
    assert client.patch(f"/api/submissions/{exp_sub['id']}/approve").status_code == 200

    # 3. Unlocated community listing (no coordinates and no destination_id/craft_id)
    unlocated_sub = client.post(
        "/api/submissions",
        json={
            "name": "Unlocated Sweet Stall",
            "description": "No spatial anchor.",
            "submission_type": "food",
            "state": "Telangana",
            "district": "Jangaon",
        },
    ).json()
    assert client.patch(f"/api/submissions/{unlocated_sub['id']}/approve").status_code == 200

    # 4. Confirmed duplicate of canonical destination DST-TG-0001
    dup_sub = client.post(
        "/api/submissions",
        json={
            "name": "Pembarthi Metal Village Duplicate",
            "description": "Duplicate of Pembarthi.",
            "submission_type": "destination",
            "state": "Telangana",
            "district": "Jangaon",
            "latitude": 17.6895,
            "longitude": 79.11758,
        },
    ).json()
    assert (
        client.patch(
            f"/api/submissions/{dup_sub['id']}/approve",
            json={"canonical_record_id": "DST-TG-0001"},
        ).status_code
        == 200
    )

    # Line passing directly through Pembarthi (79.11758, 17.6895) toward Araku (82.8667, 18.3333)
    route_payload = {
        "starting_town": {"name": "Hyderabad"},
        "popular_destination": {"destination_id": "DST-AP-0003", "name": "Araku Valley"},
        "route_geometry": {
            "type": "LineString",
            "coordinates": [
                [78.4867, 17.3850],
                [79.11758, 17.6895],
                [82.8667, 18.3333],
            ],
        },
        "corridor_width_km": 25,
    }
    resp = client.post("/api/discover/route", json=route_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["route"]["starting_town"] == "Hyderabad"
    assert data["route"]["popular_destination"] == {
        "destination_id": "DST-AP-0003",
        "name": "Araku Valley",
    }
    assert data["route"]["corridor_width_km"] == 25
    assert data["route"]["distance_method"] == "local_equirectangular_point_to_segment"
    assert data["coverage_status"] == "matches_found"
    assert data["total_result_count"] > 0

    dest_results = data["results"]["destinations"]
    dest_ids = [item["record"].get("destination_id") or item["record"].get("id") for item in dest_results]
    assert "DST-TG-0001" in dest_ids
    assert dup_sub["id"] not in dest_ids

    pembarthi_item = next(item for item in dest_results if item["record"].get("destination_id") == "DST-TG-0001")
    assert pembarthi_item["distance_to_route_km"] == 0.0
    assert pembarthi_item["popularity_status"] == "not_assessed"
    assert pembarthi_item["record"]["community_contributions"][0]["submission_id"] == dup_sub["id"]

    craft_ids = [item["record"].get("craft_id") or item["record"].get("id") for item in data["results"]["crafts"]]
    assert "CRF-TG-0001" in craft_ids
    assert craft_sub["id"] in craft_ids

    exp_ids = [item["record"].get("experience_id") or item["record"].get("id") for item in data["results"]["cultural_experiences"]]
    assert exp_sub["id"] in exp_ids

    food_ids = [item["record"].get("food_id") or item["record"].get("id") for item in data["results"]["food"]]
    assert unlocated_sub["id"] not in food_ids

    # Category filters
    filtered = client.post(
        "/api/discover/route",
        json={
            **route_payload,
            "experience_categories": ["crafts"],
            "destination_categories": ["Heritage"],
        },
    )
    assert filtered.status_code == 200
    f_res = filtered.json()["results"]
    assert f_res["food"] == []
    assert f_res["cultural_experiences"] == []
    assert len(f_res["crafts"]) >= 1
    assert all("heritage" in item["record"]["category"].lower() for item in f_res["destinations"])


def test_route_discovery_empty_coverage_and_validation(client: TestClient):
    # Valid route outside AP/Telangana returns 200 with no_catalog_matches
    outside = client.post(
        "/api/discover/route",
        json={
            "starting_town": {"name": "Delhi"},
            "popular_destination": {"destination_id": "DST-AP-0003"},
            "route_geometry": {
                "type": "LineString",
                "coordinates": [[77.2090, 28.6139], [77.5000, 28.9000]],
            },
            "corridor_width_km": 10,
        },
    )
    assert outside.status_code == 200
    assert outside.json()["coverage_status"] == "no_catalog_matches"
    assert outside.json()["total_result_count"] == 0

    # Zero-length geometry -> 422
    zero_len = client.post(
        "/api/discover/route",
        json={
            "starting_town": {"name": "Hyderabad"},
            "popular_destination": {"destination_id": "DST-AP-0003"},
            "route_geometry": {
                "type": "LineString",
                "coordinates": [[78.4867, 17.3850], [78.4867, 17.3850]],
            },
            "corridor_width_km": 25,
        },
    )
    assert zero_len.status_code == 422

    # Mismatched popular_destination.name -> 422
    mismatch = client.post(
        "/api/discover/route",
        json={
            "starting_town": {"name": "Hyderabad"},
            "popular_destination": {"destination_id": "DST-AP-0003", "name": "Wrong Name"},
            "route_geometry": {
                "type": "LineString",
                "coordinates": [[78.4867, 17.3850], [82.8667, 18.3333]],
            },
            "corridor_width_km": 25,
        },
    )
    assert mismatch.status_code == 422

    # Unknown popular_destination.destination_id -> 404
    unknown = client.post(
        "/api/discover/route",
        json={
            "starting_town": {"name": "Hyderabad"},
            "popular_destination": {"destination_id": "DST-MISSING"},
            "route_geometry": {
                "type": "LineString",
                "coordinates": [[78.4867, 17.3850], [82.8667, 18.3333]],
            },
            "corridor_width_km": 25,
        },
    )
    assert unknown.status_code == 404
