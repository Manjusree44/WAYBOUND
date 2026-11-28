"""JSON-file storage for community submissions.

Records are stored in ``data/submissions.json`` and persist across restarts.

Safety rules:
- A missing or empty file is treated as an empty list.
- Invalid JSON is reported and left untouched, so a bad file is not
  replaced with an empty list.
- Updates are written to a temporary file and then renamed into place.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.submissions import ALL_TYPE_SPECIFIC_FIELDS, SubmissionStatus

# app/services/submission_service.py -> project root is two levels up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORAGE_PATH = PROJECT_ROOT / "data" / "submissions.json"

# One lock for this process. It keeps two requests from overwriting each other.
_LOCK = threading.Lock()


class SubmissionNotFoundError(Exception):
    """Raised when an id is not in the JSON file."""

    def __init__(self, submission_id: str):
        self.submission_id = submission_id
        super().__init__(f"No submission found with id '{submission_id}'.")


class SubmissionAlreadyProcessedError(Exception):
    """Raised when approve/reject is called on a submission that is not pending."""

    def __init__(self, submission_id: str, status: str, action: str):
        self.submission_id = submission_id
        self.status = status
        self.action = action
        super().__init__(
            f"Submission '{submission_id}' is already {status}. "
            f"Only pending submissions can be {action}."
        )


class InvalidCanonicalReferenceError(Exception):
    """Raised when an admin-supplied canonical_record_id does not match the entity type."""


class SubmissionStorageError(Exception):
    """Raised when the JSON file cannot be read or saved safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def enrich_approved_submission(record: dict) -> dict:
    """Attach additive public safety flags and strip private submitter contact."""
    public_record = {k: v for k, v in record.items() if k != "contact"}
    return {
        **public_record,
        "verification_status": "community_approved_unverified",
        "verified": False,
    }


class SubmissionStore:
    """Read and update the submissions JSON file."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_STORAGE_PATH

    def create(self, data: dict) -> dict:
        """Store one submission and force its status to pending."""
        with _LOCK:
            items = self._read()
            existing_ids = {str(item.get("id")) for item in items}
            record = {
                "id": _new_id(existing_ids),
                "name": data["name"],
                "description": data["description"],
                "submission_type": data["submission_type"],
                "state": data["state"],
                "district": data["district"],
                "location": data.get("location"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "contact": data.get("contact"),
                "source": data.get("source"),
                "status": SubmissionStatus.pending.value,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
            for field in sorted(ALL_TYPE_SPECIFIC_FIELDS):
                if data.get(field) is not None:
                    record[field] = data[field]
            items.append(record)
            self._write(items)
            return dict(record)

    def list_by_status(self, status: str) -> list[dict]:
        """Return submissions with exactly this status, newest first."""
        with _LOCK:
            items = self._read()
        matches = [dict(item) for item in items if item.get("status") == status]
        matches.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return matches

    def set_status(
        self,
        submission_id: str,
        new_status: str,
        action: str,
        canonical_record_id: str | None = None,
        canonical_validator: Callable[[str, str], None] | None = None,
    ) -> dict:
        """Move a pending submission to approved or rejected."""
        with _LOCK:
            items = self._read()
            for item in items:
                if str(item.get("id")) != submission_id:
                    continue
                current = item.get("status")
                if current != SubmissionStatus.pending.value:
                    if current in {
                        SubmissionStatus.approved.value,
                        SubmissionStatus.rejected.value,
                    }:
                        raise SubmissionAlreadyProcessedError(
                            submission_id, str(current), action
                        )
                    raise SubmissionStorageError(
                        f"Submission '{submission_id}' has an unexpected status "
                        f"'{current}'. The file was not changed."
                    )

                if canonical_record_id is not None:
                    if canonical_validator is not None:
                        canonical_validator(str(item.get("submission_type")), canonical_record_id)
                    item["canonical_record_id"] = canonical_record_id

                item["status"] = new_status
                item["updated_at"] = _utc_now()
                self._write(items)
                return dict(item)
            raise SubmissionNotFoundError(submission_id)

    def _read(self) -> list[dict]:
        path = self.path
        if not path.exists():
            return []

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SubmissionStorageError(
                f"Could not read submissions file: {exc}"
            ) from exc

        if not raw.strip():
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SubmissionStorageError(
                "The submissions file is not valid JSON, so it was left unchanged. "
                f"Fix or replace {path.name} before saving new submissions. "
                f"Details: {exc.msg} (line {exc.lineno})."
            ) from exc

        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise SubmissionStorageError(
                "The submissions file must contain a JSON list of objects. "
                "It was left unchanged so existing data is not overwritten."
            )
        return data

    def _write(self, items: list[dict]) -> None:
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            payload = json.dumps(items, indent=2, ensure_ascii=False) + "\n"
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise SubmissionStorageError(
                f"Could not save submissions: {exc}"
            ) from exc


def _new_id(existing_ids: set[str]) -> str:
    while True:
        candidate = "SUB-" + uuid.uuid4().hex[:12].upper()
        if candidate not in existing_ids:
            return candidate


def get_store() -> SubmissionStore:
    """FastAPI dependency. Tests can override this function."""
    return SubmissionStore()
