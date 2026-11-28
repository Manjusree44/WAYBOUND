"""Community submission and admin approval routes."""

import hmac
import os

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from app.schemas.submissions import (
    ApproveSubmissionRequest,
    SubmissionApprovedRead,
    SubmissionCreate,
    SubmissionRead,
    SubmissionStatus,
)
from app.services.submission_service import (
    InvalidCanonicalReferenceError,
    SubmissionAlreadyProcessedError,
    SubmissionNotFoundError,
    SubmissionStorageError,
    SubmissionStore,
    enrich_approved_submission,
    get_store,
)
from data_access import DATASETS, load_dataset

ADMIN_NOTICE = (
    "PROTOTYPE ONLY: protected by a shared ADMIN_TOKEN header only when the ADMIN_TOKEN "
    "environment variable is set; open otherwise. Not production-grade security."
)

CANONICAL_ENTITY_TABLE = {
    "destination": ("destinations", "destination_id"),
    "food": ("food", "food_id"),
    "craft": ("crafts", "craft_id"),
    "cultural_experience": ("cultural_experiences", "experience_id"),
}

router = APIRouter(prefix="/api/submissions", tags=["Community submissions"])


def require_admin(x_admin_token: str = Header(default="")) -> None:
    """Protect admin routes when ADMIN_TOKEN is set in the environment.

    If ADMIN_TOKEN is not set, behaviour is unchanged (open prototype mode),
    so local development and existing tests keep working.
    """
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected:
        return
    if not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Admin token required.")


def _storage_error(exc: SubmissionStorageError) -> HTTPException:
    return HTTPException(status_code=500, detail=str(exc))


def _validate_canonical_record(submission_type: str, canonical_record_id: str) -> None:
    dataset_info = CANONICAL_ENTITY_TABLE.get(submission_type)
    if dataset_info is None:
        raise InvalidCanonicalReferenceError(
            f"Unsupported submission_type '{submission_type}' for canonical linking."
        )
    dataset_key, id_column = dataset_info
    rows = load_dataset(DATASETS[dataset_key])
    valid_ids = {row.get(id_column, "").strip() for row in rows if row.get(id_column)}
    if canonical_record_id not in valid_ids:
        raise InvalidCanonicalReferenceError(
            f"canonical_record_id '{canonical_record_id}' was not found in "
            f"{DATASETS[dataset_key]} for submission_type '{submission_type}'."
        )


@router.post(
    "",
    response_model=SubmissionRead,
    status_code=201,
    summary="Submit a community suggestion",
)
def create_submission(
    body: SubmissionCreate,
    store: SubmissionStore = Depends(get_store),
) -> SubmissionRead:
    """Save a destination, food, craft, or cultural experience as pending."""
    try:
        record = store.create(body.model_dump(mode="json"))
    except SubmissionStorageError as exc:
        raise _storage_error(exc) from exc
    return SubmissionRead.model_validate(record)


@router.get(
    "/pending",
    dependencies=[Depends(require_admin)],
    response_model=list[SubmissionRead],
    summary="List submissions waiting for review",
    description=ADMIN_NOTICE,
)
def list_pending(
    store: SubmissionStore = Depends(get_store),
) -> list[SubmissionRead]:
    """Return only submissions whose status is pending."""
    return [
        SubmissionRead.model_validate(record)
        for record in _raw_list_status(store, SubmissionStatus.pending)
    ]


@router.get(
    "/approved",
    response_model=list[SubmissionApprovedRead],
    summary="List publicly approved submissions",
)
def list_approved(
    store: SubmissionStore = Depends(get_store),
) -> list[SubmissionApprovedRead]:
    """Return approved submissions marked as community-approved and unverified."""
    return [
        SubmissionApprovedRead.model_validate(enrich_approved_submission(record))
        for record in _raw_list_status(store, SubmissionStatus.approved)
    ]


@router.patch(
    "/{submission_id}/approve",
    dependencies=[Depends(require_admin)],
    response_model=SubmissionRead,
    summary="Approve a pending submission",
    description=ADMIN_NOTICE,
)
def approve_submission(
    submission_id: str,
    body: ApproveSubmissionRequest | None = Body(default=None),
    store: SubmissionStore = Depends(get_store),
) -> SubmissionRead:
    """Mark one pending submission as approved, optionally linking canonical_record_id."""
    canonical_record_id = body.canonical_record_id if body is not None else None
    return _change_status(
        store,
        submission_id,
        SubmissionStatus.approved,
        action="approved",
        canonical_record_id=canonical_record_id,
    )


@router.patch(
    "/{submission_id}/reject",
    dependencies=[Depends(require_admin)],
    response_model=SubmissionRead,
    summary="Reject a pending submission",
    description=ADMIN_NOTICE,
)
def reject_submission(
    submission_id: str,
    store: SubmissionStore = Depends(get_store),
) -> SubmissionRead:
    """Mark one pending submission as rejected."""
    return _change_status(
        store,
        submission_id,
        SubmissionStatus.rejected,
        action="rejected",
    )


def _raw_list_status(store: SubmissionStore, status: SubmissionStatus) -> list[dict]:
    try:
        records = store.list_by_status(status.value)
    except SubmissionStorageError as exc:
        raise _storage_error(exc) from exc
    return [record for record in records if record.get("status") == status.value]


def _change_status(
    store: SubmissionStore,
    submission_id: str,
    status: SubmissionStatus,
    action: str,
    canonical_record_id: str | None = None,
) -> SubmissionRead:
    try:
        record = store.set_status(
            submission_id,
            status.value,
            action,
            canonical_record_id=canonical_record_id,
            canonical_validator=_validate_canonical_record,
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubmissionAlreadyProcessedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidCanonicalReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SubmissionStorageError as exc:
        raise _storage_error(exc) from exc
    return SubmissionRead.model_validate(record)
