"""Tests for the community submission and approval module.

Run from the WAYBOUND project folder:

    python -m pytest tests/test_submissions.py -q
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers.submissions import router
from app.services.submission_service import SubmissionStore, get_store


def _app(store: SubmissionStore) -> FastAPI:
    """A tiny app used only by tests. It does not touch app/main.py."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_store] = lambda: store
    return app


ADMIN_HEADERS = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture
def store(tmp_path: Path) -> SubmissionStore:
    return SubmissionStore(tmp_path / "submissions.json")


@pytest.fixture
def client(store: SubmissionStore, monkeypatch) -> TestClient:
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
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

    pending = client.get("/api/submissions/pending", headers=ADMIN_HEADERS)
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()] == [submission_id]

    approved_before = client.get("/api/submissions/approved")
    assert approved_before.status_code == 200
    assert approved_before.json() == []

    approved = client.patch(f"/api/submissions/{submission_id}/approve", headers=ADMIN_HEADERS)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    public = client.get("/api/submissions/approved")
    assert public.status_code == 200
    assert [item["id"] for item in public.json()] == [submission_id]
    assert public.json()[0]["status"] == "approved"

    pending_after = client.get("/api/submissions/pending", headers=ADMIN_HEADERS)
    assert pending_after.json() == []

    rejected_response = client.post("/api/submissions", json=FOOD)
    assert rejected_response.status_code == 201
    rejected_id = rejected_response.json()["id"]
    assert rejected_response.json()["status"] == "pending"

    reject = client.patch(f"/api/submissions/{rejected_id}/reject", headers=ADMIN_HEADERS)
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"

    public_after_reject = client.get("/api/submissions/approved")
    public_ids = [item["id"] for item in public_after_reject.json()]
    assert submission_id in public_ids
    assert rejected_id not in public_ids
    assert all(item["status"] == "approved" for item in public_after_reject.json())

    # A new store object is what a restarted server would use.
    reloaded = SubmissionStore(store.path)
    saved = reloaded.list_by_status("approved")
    saved_rejected = reloaded.list_by_status("rejected")
    assert [item["id"] for item in saved] == [submission_id]
    assert [item["id"] for item in saved_rejected] == [rejected_id]

    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert {item["id"] for item in on_disk} == {submission_id, rejected_id}


def test_unknown_id_returns_404(client: TestClient):
    missing = client.patch("/api/submissions/SUB-DOES-NOT-EXIST/approve", headers=ADMIN_HEADERS)
    assert missing.status_code == 404
    assert "No submission found" in missing.json()["detail"]


def test_already_processed_returns_409(client: TestClient):
    created = client.post("/api/submissions", json=DESTINATION)
    submission_id = created.json()["id"]
    assert client.patch(f"/api/submissions/{submission_id}/approve", headers=ADMIN_HEADERS).status_code == 200

    again = client.patch(f"/api/submissions/{submission_id}/approve", headers=ADMIN_HEADERS)
    assert again.status_code == 409
    assert "already approved" in again.json()["detail"]

    reject_after_approve = client.patch(f"/api/submissions/{submission_id}/reject", headers=ADMIN_HEADERS)
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
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{ this is not json", encoding="utf-8")
    original = store.path.read_text(encoding="utf-8")

    client = TestClient(_app(store))
    response = client.post("/api/submissions", json=DESTINATION)
    assert response.status_code == 500
    assert "left unchanged" in response.json()["detail"]
    assert store.path.read_text(encoding="utf-8") == original


def test_empty_file_is_treated_as_no_submissions(store: SubmissionStore):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("   \n", encoding="utf-8")
    client = TestClient(_app(store))
    response = client.post("/api/submissions", json=FOOD)
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    saved = json.loads(store.path.read_text(encoding="utf-8"))
    assert len(saved) == 1


def test_approved_endpoint_marks_community_unverified(client: TestClient):
    created = client.post("/api/submissions", json=DESTINATION)
    submission_id = created.json()["id"]
    assert client.patch(f"/api/submissions/{submission_id}/approve", headers=ADMIN_HEADERS).status_code == 200

    approved = client.get("/api/submissions/approved")
    assert approved.status_code == 200
    items = approved.json()
    assert len(items) == 1
    assert items[0]["verification_status"] == "community_approved_unverified"
    assert items[0]["verified"] is False


def test_type_specific_fields_and_forbidden_client_fields(client: TestClient):
    craft_payload = {
        "name": "Etikoppaka Lacquer Toy",
        "description": "Turned wood toy finished with natural lacquer.",
        "submission_type": "craft",
        "state": "Andhra Pradesh",
        "district": "Anakapalli",
        "destination_id": "DST-AP-0016",
        "materials": "Ankudu wood and natural dyes",
        "artisan_community": "Etikoppaka artisans",
    }
    ok_resp = client.post("/api/submissions", json=craft_payload)
    assert ok_resp.status_code == 201
    assert ok_resp.json()["materials"] == "Ankudu wood and natural dyes"
    assert ok_resp.json()["destination_id"] == "DST-AP-0016"

    bad_type_field = {**FOOD, "materials": "Wood"}
    assert client.post("/api/submissions", json=bad_type_field).status_code == 422

    bad_client_verify = {**DESTINATION, "verification_status": "verified_official_source"}
    assert client.post("/api/submissions", json=bad_client_verify).status_code == 422

    bad_client_canonical = {**DESTINATION, "canonical_record_id": "DST-AP-0001"}
    assert client.post("/api/submissions", json=bad_client_canonical).status_code == 422


def test_approve_with_canonical_record_id_validation(client: TestClient):
    dest_resp = client.post("/api/submissions", json=DESTINATION)
    dest_id = dest_resp.json()["id"]

    # Wrong entity ID for destination submission must fail with 422 and keep it pending
    wrong_id = client.patch(
        f"/api/submissions/{dest_id}/approve",
        headers=ADMIN_HEADERS,
        json={"canonical_record_id": "FOD-AP-0001"},
    )
    assert wrong_id.status_code == 422

    # Valid canonical destination ID succeeds
    ok = client.patch(
        f"/api/submissions/{dest_id}/approve",
        headers=ADMIN_HEADERS,
        json={"canonical_record_id": "DST-AP-0001"},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"
    assert ok.json()["canonical_record_id"] == "DST-AP-0001"


def test_contact_visible_only_on_pending_and_absent_from_approved(client: TestClient):
    created = client.post(
        "/api/submissions",
        json={**FOOD, "contact": "submitter-private@example.com"},
    )
    assert created.status_code == 201
    sub_id = created.json()["id"]

    pending = client.get("/api/submissions/pending", headers=ADMIN_HEADERS)
    assert pending.status_code == 200
    assert pending.json()[0]["contact"] == "submitter-private@example.com"

    assert client.patch(f"/api/submissions/{sub_id}/approve", headers=ADMIN_HEADERS).status_code == 200

    approved = client.get("/api/submissions/approved")
    assert approved.status_code == 200
    assert len(approved.json()) == 1
    assert "contact" not in approved.json()[0]


def test_submission_rejects_nonexistent_canonical_references(client: TestClient):
    bad_dest = client.post(
        "/api/submissions",
        json={**FOOD, "destination_id": "DST-XX-9999"},
    )
    assert bad_dest.status_code == 422
    assert "destination_id" in bad_dest.json()["detail"]

    bad_craft = client.post(
        "/api/submissions",
        json={
            "name": "Fake Craft Link",
            "description": "Invalid craft reference.",
            "submission_type": "cultural_experience",
            "state": "Telangana",
            "district": "Jangaon",
            "craft_id": "CRF-XX-9999",
        },
    )
    assert bad_craft.status_code == 422
    assert "craft_id" in bad_craft.json()["detail"]

    bad_gi = client.post(
        "/api/submissions",
        json={**FOOD, "gi_id": "GI-99999"},
    )
    assert bad_gi.status_code == 422
    assert "gi_id" in bad_gi.json()["detail"]

    ok_dest = client.post("/api/submissions", json={**FOOD, "destination_id": "DST-TG-0001"})
    assert ok_dest.status_code == 201

    ok_craft = client.post(
        "/api/submissions",
        json={
            "name": "Valid Craft Link",
            "description": "Valid craft reference.",
            "submission_type": "cultural_experience",
            "state": "Telangana",
            "district": "Jangaon",
            "craft_id": "CRF-TG-0001",
        },
    )
    assert ok_craft.status_code == 201

    ok_gi = client.post("/api/submissions", json={**FOOD, "gi_id": "GI-0002"})
    assert ok_gi.status_code == 201

    ok_blank = client.post("/api/submissions", json={**FOOD, "destination_id": "   "})
    assert ok_blank.status_code == 201
    assert ok_blank.json()["destination_id"] is None

