"""Tests for evidence-gated hidden_gem route discovery behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.submission_service import SubmissionStore, get_store
from config import settings
from main import app

ROUTE_PAYLOAD = {
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


def _all_route_items(body: dict) -> list[dict]:
    res = body["results"]
    return (
        res["destinations"]
        + res["food"]
        + res["crafts"]
        + res["cultural_experiences"]
    )


def test_hidden_gem_false_by_default_with_empty_sidecar(client: TestClient):
    resp = client.post("/api/discover/route", json=ROUTE_PAYLOAD)
    assert resp.status_code == 200
    items = _all_route_items(resp.json())
    assert len(items) > 0
    assert all(item["hidden_gem"] is False for item in items)


def test_hidden_gem_remains_false_when_evidence_incomplete_or_invalid_url(
    client: TestClient, tmp_path: Path, monkeypatch
):
    evidence_file = tmp_path / "low_visibility_evidence.json"
    evidence_file.write_text(
        json.dumps(
            {
                # Note only (missing URL)
                "DST-TG-0001": {
                    "low_visibility_note": "Low footfall noted in district survey.",
                },
                # Non-HTTP URL + note
                "CRF-TG-0001": {
                    "low_visibility_evidence_url": "not-a-valid-url",
                    "low_visibility_note": "Documented workshop with limited visitors.",
                },
                # URL only (whitespace note)
                "CEX-TG-0001": {
                    "low_visibility_evidence_url": "https://example.org/survey",
                    "low_visibility_note": "   ",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "LOW_VISIBILITY_EVIDENCE_PATH", evidence_file)

    resp = client.post("/api/discover/route", json=ROUTE_PAYLOAD)
    assert resp.status_code == 200
    items = _all_route_items(resp.json())
    assert len(items) > 0
    assert all(item["hidden_gem"] is False for item in items)


def test_hidden_gem_true_only_when_both_evidence_fields_are_filled(
    client: TestClient, tmp_path: Path, monkeypatch
):
    evidence_file = tmp_path / "low_visibility_evidence.json"
    evidence_file.write_text(
        json.dumps(
            {
                "DST-TG-0001": {
                    "low_visibility_evidence_url": "https://tourism.telangana.gov.in/example-survey",
                    "low_visibility_note": "Official state survey notes limited tourist footfall.",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "LOW_VISIBILITY_EVIDENCE_PATH", evidence_file)

    resp = client.post("/api/discover/route", json=ROUTE_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()
    items = _all_route_items(body)

    pembarthi = next(
        item for item in body["results"]["destinations"]
        if item["record"].get("destination_id") == "DST-TG-0001"
    )
    assert pembarthi["hidden_gem"] is True
    assert pembarthi["record"]["low_visibility_evidence_url"] == "https://tourism.telangana.gov.in/example-survey"
    assert pembarthi["record"]["low_visibility_note"] == "Official state survey notes limited tourist footfall."

    others = [item for item in items if item is not pembarthi]
    assert len(others) > 0
    assert all(item["hidden_gem"] is False for item in others)


def test_community_listings_always_stay_hidden_gem_false(
    client: TestClient, tmp_path: Path, monkeypatch
):
    sub = client.post(
        "/api/submissions",
        json={
            "name": "Community Workshop Near Pembarthi",
            "description": "Vendor-submitted brass workshop.",
            "submission_type": "craft",
            "state": "Telangana",
            "district": "Jangaon",
            "destination_id": "DST-TG-0001",
        },
    ).json()
    assert client.patch(f"/api/submissions/{sub['id']}/approve").status_code == 200

    # Even if an entry exists for a community ID, unverified listings must stay hidden_gem=False.
    evidence_file = tmp_path / "low_visibility_evidence.json"
    evidence_file.write_text(
        json.dumps(
            {
                sub["id"]: {
                    "low_visibility_evidence_url": "https://example.org/claim",
                    "low_visibility_note": "Unverified community claim.",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "LOW_VISIBILITY_EVIDENCE_PATH", evidence_file)

    resp = client.post("/api/discover/route", json=ROUTE_PAYLOAD)
    assert resp.status_code == 200
    craft_item = next(
        item for item in resp.json()["results"]["crafts"]
        if item["record"].get("id") == sub["id"]
    )
    assert craft_item["record"]["verified"] is False
    assert craft_item["hidden_gem"] is False
