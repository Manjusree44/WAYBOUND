"""Tests for the community submission and approval module.

Run from the WAYBOUND project folder:

    python -m pytest tests/test_submissions.py -q
"""

import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app as main_app
from app.routers.submissions import router
from app.services.submission_service import (
    SubmissionAlreadyProcessedError,
    SubmissionStore,
    get_store,
)


def _app(store: SubmissionStore) -> FastAPI:
    """A tiny app used only by tests. It does not touch app/main.py."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_store] = lambda: store
    return app


def test_main_application_registers_submissions_router():
    paths = main_app.openapi()["paths"]

    assert {
        "/",
        "/api/submissions",
        "/api/submissions/pending",
        "/api/submissions/approved",
        "/api/submissions/{submission_id}/approve",
        "/api/submissions/{submission_id}/reject",
    } <= paths.keys()
    assert "post" in paths["/api/submissions"]
    response = TestClient(main_app).get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Waybound API is running"}


@pytest.fixture
def store(tmp_path: Path) -> SubmissionStore:
    return SubmissionStore(
        tmp_path / "submissions.db",
        legacy_path=tmp_path / "legacy-submissions.json",
    )


@pytest.fixture
def client(store: SubmissionStore) -> TestClient:
    return TestClient(_app(store))


DESTINATION = {
    "name": "Gandikota",
    "description": "A historic fort above the Pennar gorge.",
    "submission_type": "destination",
    "state": "Andhra Pradesh",
    "district": "YSR Kadapa",
    "location": "Gandikota village",
    "latitude": 14.813433,
    "longitude": 78.284757,
    "source": "https://kadapa.ap.gov.in/tourist-place/gandikota/",
}

FOOD = {
    "name": "Bandar Laddu",
    "description": "A regional sweet associated with Machilipatnam.",
    "submission_type": "food",
    "state": "Andhra Pradesh",
    "district": "Krishna",
    "contact": "example-shop@example.com",
}


def test_submit_review_and_persist(client: TestClient, store: SubmissionStore):
    created = client.post("/api/submissions", json=DESTINATION)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["name"] == "Gandikota"
    assert body["id"].startswith("SUB-")
    submission_id = body["id"]

    pending = client.get("/api/submissions/pending")
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()] == [submission_id]

    approved_before = client.get("/api/submissions/approved")
    assert approved_before.status_code == 200
    assert approved_before.json() == []

    approved = client.patch(f"/api/submissions/{submission_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    public = client.get("/api/submissions/approved")
    assert public.status_code == 200
    assert [item["id"] for item in public.json()] == [submission_id]
    assert public.json()[0]["status"] == "approved"

    pending_after = client.get("/api/submissions/pending")
    assert pending_after.json() == []

    rejected_response = client.post("/api/submissions", json=FOOD)
    assert rejected_response.status_code == 201
    rejected_id = rejected_response.json()["id"]
    assert rejected_response.json()["status"] == "pending"

    reject = client.patch(f"/api/submissions/{rejected_id}/reject")
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"

    public_after_reject = client.get("/api/submissions/approved")
    public_ids = [item["id"] for item in public_after_reject.json()]
    assert submission_id in public_ids
    assert rejected_id not in public_ids
    assert all(item["status"] == "approved" for item in public_after_reject.json())

    # A new store object is what a restarted server would use.
    reloaded = SubmissionStore(store.path, legacy_path=store.legacy_path)
    saved = reloaded.list_by_status("approved")
    saved_rejected = reloaded.list_by_status("rejected")
    assert [item["id"] for item in saved] == [submission_id]
    assert [item["id"] for item in saved_rejected] == [rejected_id]

    with sqlite3.connect(store.path) as connection:
        persisted_ids = {
            row[0] for row in connection.execute("SELECT id FROM submissions")
        }
    assert persisted_ids == {submission_id, rejected_id}


def test_unknown_id_returns_404(client: TestClient):
    missing = client.patch("/api/submissions/SUB-DOES-NOT-EXIST/approve")
    assert missing.status_code == 404
    assert "No submission found" in missing.json()["detail"]


def test_already_processed_returns_409(client: TestClient):
    created = client.post("/api/submissions", json=DESTINATION)
    submission_id = created.json()["id"]
    assert client.patch(f"/api/submissions/{submission_id}/approve").status_code == 200

    again = client.patch(f"/api/submissions/{submission_id}/approve")
    assert again.status_code == 409
    assert "already approved" in again.json()["detail"]

    reject_after_approve = client.patch(f"/api/submissions/{submission_id}/reject")
    assert reject_after_approve.status_code == 409
    assert "already approved" in reject_after_approve.json()["detail"]


def test_client_cannot_set_status(client: TestClient):
    payload = {**DESTINATION, "status": "approved"}
    response = client.post("/api/submissions", json=payload)
    assert response.status_code == 422


def test_invalid_coordinates_are_rejected(client: TestClient):
    payload = {**DESTINATION, "longitude": None}
    response = client.post("/api/submissions", json=payload)
    assert response.status_code == 422


def test_cultural_experience_alias_is_accepted(client: TestClient):
    payload = {
        "name": "Dhimsa evening",
        "description": "A folk dance performance in the Araku region.",
        "submission_type": "cultural experience",
        "state": "Andhra Pradesh",
        "district": "Alluri Sitharama Raju",
    }
    response = client.post("/api/submissions", json=payload)
    assert response.status_code == 201
    assert response.json()["submission_type"] == "cultural_experience"
    assert response.json()["status"] == "pending"


def test_invalid_json_file_is_not_overwritten(store: SubmissionStore):
    store.legacy_path.write_text("{ this is not json", encoding="utf-8")
    original = store.legacy_path.read_text(encoding="utf-8")

    client = TestClient(_app(store))
    response = client.post("/api/submissions", json=DESTINATION)
    assert response.status_code == 500
    assert "left unchanged" in response.json()["detail"]
    assert store.legacy_path.read_text(encoding="utf-8") == original


def test_empty_file_is_treated_as_no_submissions(store: SubmissionStore):
    store.legacy_path.write_text("   \n", encoding="utf-8")
    client = TestClient(_app(store))
    response = client.post("/api/submissions", json=FOOD)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert store.list_by_status("pending")[0]["name"] == FOOD["name"]
    assert store.legacy_path.read_text(encoding="utf-8") == "   \n"


def test_legacy_json_is_migrated_without_overwriting_or_modifying_source(
    tmp_path: Path,
):
    legacy_path = tmp_path / "legacy.json"
    legacy_record = {
        "id": "SUB-LEGACY123",
        "name": "Legacy place",
        "description": "Imported from JSON.",
        "submission_type": "destination",
        "state": "Andhra Pradesh",
        "district": "Krishna",
        "location": "Old town",
        "latitude": 16.2,
        "longitude": 81.1,
        "contact": "legacy@example.com",
        "source": "legacy reference",
        "status": "pending",
        "created_at": "2024-01-02T03:04:05+00:00",
        "updated_at": "2024-01-02T03:04:05+00:00",
        "extra_field": {"kept": True},
    }
    original = json.dumps([legacy_record], indent=2)
    legacy_path.write_text(original, encoding="utf-8")
    store = SubmissionStore(
        tmp_path / "submissions.db",
        legacy_path=legacy_path,
    )

    migrated = store.list_by_status("pending")
    assert migrated == [legacy_record]

    approved = store.set_status("SUB-LEGACY123", "approved", "approved")
    assert approved["status"] == "approved"
    assert store.list_by_status("approved") == [approved]
    assert store.list_by_status("pending") == []
    assert legacy_path.read_text(encoding="utf-8") == original


def test_concurrent_writes_from_independent_stores_are_not_lost(tmp_path: Path):
    database_path = tmp_path / "concurrent.db"
    legacy_path = tmp_path / "missing-legacy.json"

    def create_submission(index: int) -> str:
        store = SubmissionStore(database_path, legacy_path=legacy_path)
        data = {**FOOD, "name": f"Concurrent submission {index}"}
        return store.create(data)["id"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        submission_ids = list(executor.map(create_submission, range(32)))

    assert len(set(submission_ids)) == 32
    store = SubmissionStore(database_path, legacy_path=legacy_path)
    saved = store.list_by_status("pending")
    assert len(saved) == 32
    assert {item["id"] for item in saved} == set(submission_ids)


def test_concurrent_status_transitions_are_atomic(store: SubmissionStore):
    submission_id = store.create(FOOD)["id"]

    def transition(status: str):
        try:
            return store.set_status(submission_id, status, status)
        except SubmissionAlreadyProcessedError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(transition, ["approved", "rejected"]))

    assert sum(result is not None for result in results) == 1
    final_statuses = [
        status for status in ("approved", "rejected")
        if store.list_by_status(status)
    ]
    assert len(final_statuses) == 1


def test_database_schema_has_queryable_submission_columns(store: SubmissionStore):
    store.list_by_status("pending")

    with sqlite3.connect(store.path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(submissions)")
        }
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert {
        "id",
        "submission_type",
        "status",
        "title",
        "location_name",
        "latitude",
        "longitude",
        "payload_json",
        "created_at",
        "updated_at",
    } <= columns
    assert journal_mode.lower() == "wal"


def test_database_and_legacy_paths_can_be_configured_with_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    database_path = tmp_path / "configured.db"
    legacy_path = tmp_path / "configured.json"
    monkeypatch.setenv("WAYBOUND_SUBMISSIONS_DB", str(database_path))
    monkeypatch.setenv("WAYBOUND_SUBMISSIONS_JSON", str(legacy_path))

    configured_store = get_store()
    assert configured_store.path == database_path
    assert configured_store.legacy_path == legacy_path
