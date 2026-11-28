"""Admin routes require X-Admin-Token only when ADMIN_TOKEN is set."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.submission_service import SubmissionStore, get_store
from main import app

BODY = {
    "name": "Auth Test Listing",
    "description": "Used to test admin protection.",
    "submission_type": "craft",
    "state": "Telangana",
    "district": "Jangaon",
}


@pytest.fixture
def client(tmp_path: Path):
    store = SubmissionStore(tmp_path / "submissions.json")
    app.dependency_overrides[get_store] = lambda: store
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_admin_open_when_token_not_configured(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert client.get("/api/submissions/pending").status_code == 200


def test_admin_routes_need_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-test-token")
    sub = client.post("/api/submissions", json=BODY).json()  # public submit stays open
    assert client.get("/api/submissions/pending").status_code == 401
    assert client.get("/api/submissions/pending", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.patch(f"/api/submissions/{sub['id']}/approve").status_code == 401
    assert client.patch(f"/api/submissions/{sub['id']}/reject").status_code == 401
    good = {"X-Admin-Token": "s3cret-test-token"}
    assert client.get("/api/submissions/pending", headers=good).status_code == 200
    assert client.patch(f"/api/submissions/{sub['id']}/approve", headers=good).json()["status"] == "approved"


def test_public_endpoints_stay_public_with_token_configured(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-test-token")
    assert client.get("/api/submissions/approved").status_code == 200
    assert client.get("/api/catalog").status_code == 200
