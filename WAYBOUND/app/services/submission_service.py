"""SQLite storage for community submissions."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.schemas.submissions import SubmissionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "waybound.db"
DEFAULT_LEGACY_JSON_PATH = PROJECT_ROOT / "Data" / "storage" / "submissions.json"
CONNECTION_TIMEOUT_SECONDS = 10
_INITIALIZED_DATABASES: set[tuple[Path, Path]] = set()


class SubmissionNotFoundError(Exception):
    """Raised when an id is not in the database."""

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


class SubmissionStorageError(Exception):
    """Raised when submissions cannot be read or saved safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _configured_path(environment_variable: str, default: Path) -> Path:
    configured = os.environ.get(environment_variable)
    path = Path(configured).expanduser() if configured else default
    return path if path.is_absolute() else PROJECT_ROOT / path


@contextmanager
def _transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


class SubmissionStore:
    """Create, list, and review community submissions in SQLite."""

    def __init__(
        self,
        path: Path | None = None,
        legacy_path: Path | None = None,
    ):
        self.path = (
            Path(path)
            if path is not None
            else _configured_path("WAYBOUND_SUBMISSIONS_DB", DEFAULT_DATABASE_PATH)
        )
        self.legacy_path = (
            Path(legacy_path)
            if legacy_path is not None
            else _configured_path(
                "WAYBOUND_SUBMISSIONS_JSON", DEFAULT_LEGACY_JSON_PATH
            )
        )

    def create(self, data: dict) -> dict:
        """Store one submission and force its status to pending."""
        self._initialize()
        created_at = _utc_now()
        record = {
            "id": _new_id(),
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
            "created_at": created_at,
            "updated_at": created_at,
        }
        try:
            with self._connection() as connection:
                with _transaction(connection):
                    connection.execute(
                        """
                        INSERT INTO submissions (
                            id, submission_type, status, title, location_name,
                            latitude, longitude, payload_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record["id"],
                            record["submission_type"],
                            record["status"],
                            record["name"],
                            record["location"],
                            record["latitude"],
                            record["longitude"],
                            json.dumps(record, ensure_ascii=False),
                            record["created_at"],
                            record["updated_at"],
                        ),
                    )
        except (OSError, sqlite3.Error) as exc:
            raise SubmissionStorageError(
                f"Could not save submission: {exc}"
            ) from exc
        return dict(record)

    def list_by_status(self, status: str) -> list[dict]:
        """Return submissions with exactly this status, newest first."""
        self._initialize()
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT payload_json FROM submissions
                    WHERE status = ?
                    ORDER BY created_at DESC
                    """,
                    (status,),
                ).fetchall()
        except (OSError, sqlite3.Error) as exc:
            raise SubmissionStorageError(
                f"Could not read submissions: {exc}"
            ) from exc
        try:
            return [json.loads(row["payload_json"]) for row in rows]
        except (json.JSONDecodeError, TypeError) as exc:
            raise SubmissionStorageError(
                f"Could not decode a stored submission: {exc}"
            ) from exc

    def set_status(self, submission_id: str, new_status: str, action: str) -> dict:
        """Atomically move a pending submission to approved or rejected."""
        self._initialize()
        try:
            with self._connection() as connection:
                with _transaction(connection):
                    row = connection.execute(
                        """
                        SELECT status, payload_json FROM submissions WHERE id = ?
                        """,
                        (submission_id,),
                    ).fetchone()
                    if row is None:
                        raise SubmissionNotFoundError(submission_id)

                    current = row["status"]
                    if current != SubmissionStatus.pending.value:
                        if current in {
                            SubmissionStatus.approved.value,
                            SubmissionStatus.rejected.value,
                        }:
                            raise SubmissionAlreadyProcessedError(
                                submission_id, current, action
                            )
                        raise SubmissionStorageError(
                            f"Submission '{submission_id}' has an unexpected status "
                            f"'{current}'. The database was not changed."
                        )

                    record = json.loads(row["payload_json"])
                    updated_at = _utc_now()
                    record["status"] = new_status
                    record["updated_at"] = updated_at
                    connection.execute(
                        """
                        UPDATE submissions
                        SET status = ?, updated_at = ?, payload_json = ?
                        WHERE id = ? AND status = ?
                        """,
                        (
                            new_status,
                            updated_at,
                            json.dumps(record, ensure_ascii=False),
                            submission_id,
                            SubmissionStatus.pending.value,
                        ),
                    )
            return record
        except (SubmissionNotFoundError, SubmissionAlreadyProcessedError):
            raise
        except (OSError, sqlite3.Error) as exc:
            raise SubmissionStorageError(
                f"Could not update submission: {exc}"
            ) from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise SubmissionStorageError(
                f"Could not decode a stored submission: {exc}"
            ) from exc

    def _initialize(self) -> None:
        """Create the schema and idempotently import legacy JSON records."""
        key = (self.path.resolve(), self.legacy_path.resolve())
        if key in _INITIALIZED_DATABASES:
            return
        try:
            with self._connection() as connection:
                _enable_wal_mode(connection)
                with _transaction(connection):
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS submissions (
                            id TEXT PRIMARY KEY NOT NULL,
                            submission_type TEXT NOT NULL,
                            status TEXT NOT NULL,
                            title TEXT NOT NULL,
                            location_name TEXT,
                            latitude REAL,
                            longitude REAL,
                            payload_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                        """
                    )
                    connection.execute(
                        """
                        CREATE INDEX IF NOT EXISTS
                            idx_submissions_status_created_at
                        ON submissions(status, created_at DESC)
                        """
                    )
                    self._migrate_legacy_json(connection)
        except SubmissionStorageError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise SubmissionStorageError(
                f"Could not initialize submissions database: {exc}"
            ) from exc
        _INITIALIZED_DATABASES.add(key)

    def _migrate_legacy_json(self, connection: sqlite3.Connection) -> None:
        path = self.legacy_path
        if not path.exists():
            return

        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SubmissionStorageError(
                f"Could not read submissions file: {exc}"
            ) from exc
        if not raw.strip():
            return

        try:
            records = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SubmissionStorageError(
                "The submissions file is not valid JSON, so it was left unchanged. "
                f"Fix or replace {path.name} before saving new submissions. "
                f"Details: {exc.msg} (line {exc.lineno})."
            ) from exc
        if not isinstance(records, list) or any(
            not isinstance(record, dict) for record in records
        ):
            raise SubmissionStorageError(
                "The submissions file must contain a JSON list of objects. "
                "It was left unchanged so existing data is not overwritten."
            )

        for record in records:
            submission_id = record.get("id")
            if not isinstance(submission_id, str) or not submission_id:
                raise SubmissionStorageError(
                    "Every legacy submission must have a non-empty string id. "
                    "The JSON file was left unchanged."
                )
            try:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO submissions (
                        id, submission_type, status, title, location_name,
                        latitude, longitude, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        submission_id,
                        str(record.get("submission_type", "")),
                        str(record.get("status", SubmissionStatus.pending.value)),
                        str(record.get("name", record.get("title", ""))),
                        record.get("location", record.get("location_name")),
                        record.get("latitude"),
                        record.get("longitude"),
                        json.dumps(record, ensure_ascii=False),
                        str(record.get("created_at") or _utc_now()),
                        str(
                            record.get("updated_at")
                            or record.get("created_at")
                            or _utc_now()
                        ),
                    ),
                )
            except (TypeError, ValueError) as exc:
                raise SubmissionStorageError(
                    f"Could not migrate submission '{submission_id}': {exc}"
                ) from exc

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=CONNECTION_TIMEOUT_SECONDS,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(
                f"PRAGMA busy_timeout = {CONNECTION_TIMEOUT_SECONDS * 1000}"
            )
            yield connection
        finally:
            connection.close()


def _new_id() -> str:
    return "SUB-" + uuid.uuid4().hex[:12].upper()


def _enable_wal_mode(connection: sqlite3.Connection) -> None:
    deadline = time.monotonic() + CONNECTION_TIMEOUT_SECONDS
    while True:
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


def get_store() -> SubmissionStore:
    """FastAPI dependency. Tests can override this function."""
    return SubmissionStore()
