"""Community submission and admin approval routes.

Do not register this router from inside this file. The main application
owner should add it in app/main.py:

    from app.routers.submissions import router as submissions_router

    app.include_router(submissions_router)

Admin routes in this module have no authentication. They are for a local
hackathon prototype and are not production-secure.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.submissions import SubmissionCreate, SubmissionRead, SubmissionStatus
from app.services.submission_service import (
    SubmissionAlreadyProcessedError,
    SubmissionNotFoundError,
    SubmissionStorageError,
    SubmissionStore,
    get_store,
)

ADMIN_NOTICE = (
    "PROTOTYPE ONLY: this admin endpoint has no authentication and is not "
    "production-secure. Anyone who can reach the server can call it."
)

router = APIRouter(prefix="/api/submissions", tags=["Community submissions"])


def _storage_error(exc: SubmissionStorageError) -> HTTPException:
    return HTTPException(status_code=500, detail=str(exc))


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
    """Save a destination, food, craft, or cultural experience.

    The new record is always stored with status ``pending``. Callers cannot
    choose the status.
    """
    try:
        record = store.create(body.model_dump(mode="json"))
    except SubmissionStorageError as exc:
        raise _storage_error(exc) from exc
    return SubmissionRead.model_validate(record)


@router.get(
    "/pending",
    response_model=list[SubmissionRead],
    summary="List submissions waiting for review",
    description=ADMIN_NOTICE,
)
def list_pending(
    store: SubmissionStore = Depends(get_store),
) -> list[SubmissionRead]:
    """Return only submissions whose status is pending.

    This is an admin endpoint. It has no authentication.
    """
    return _list_status(store, SubmissionStatus.pending)


@router.get(
    "/approved",
    response_model=list[SubmissionRead],
    summary="List publicly approved submissions",
)
def list_approved(
    store: SubmissionStore = Depends(get_store),
) -> list[SubmissionRead]:
    """Return only approved submissions.

    Pending and rejected submissions are never included.
    """
    return _list_status(store, SubmissionStatus.approved)


@router.patch(
    "/{submission_id}/approve",
    response_model=SubmissionRead,
    summary="Approve a pending submission",
    description=ADMIN_NOTICE,
)
def approve_submission(
    submission_id: str,
    store: SubmissionStore = Depends(get_store),
) -> SubmissionRead:
    """Mark one pending submission as approved.

    This admin endpoint has no authentication and is not production-secure.
    Unknown ids return 404. A submission that is already approved or rejected
    returns 409 and is left unchanged.
    """
    return _change_status(
        store,
        submission_id,
        SubmissionStatus.approved,
        action="approved",
    )


@router.patch(
    "/{submission_id}/reject",
    response_model=SubmissionRead,
    summary="Reject a pending submission",
    description=ADMIN_NOTICE,
)
def reject_submission(
    submission_id: str,
    store: SubmissionStore = Depends(get_store),
) -> SubmissionRead:
    """Mark one pending submission as rejected.

    This admin endpoint has no authentication and is not production-secure.
    Unknown ids return 404. A submission that is already approved or rejected
    returns 409 and is left unchanged. Rejected records stay out of
    GET /api/submissions/approved.
    """
    return _change_status(
        store,
        submission_id,
        SubmissionStatus.rejected,
        action="rejected",
    )


def _list_status(store: SubmissionStore, status: SubmissionStatus) -> list[SubmissionRead]:
    try:
        records = store.list_by_status(status.value)
    except SubmissionStorageError as exc:
        raise _storage_error(exc) from exc
    # Filter again so this response cannot include another status.
    return [
        SubmissionRead.model_validate(record)
        for record in records
        if record.get("status") == status.value
    ]


def _change_status(
    store: SubmissionStore,
    submission_id: str,
    status: SubmissionStatus,
    action: str,
) -> SubmissionRead:
    try:
        record = store.set_status(submission_id, status.value, action)
    except SubmissionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubmissionAlreadyProcessedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SubmissionStorageError as exc:
        raise _storage_error(exc) from exc
    return SubmissionRead.model_validate(record)
