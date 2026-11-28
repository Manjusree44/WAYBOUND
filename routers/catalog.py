"""Read-only API for the catalog CSV datasets and approved community listings."""

import re

from fastapi import APIRouter, Depends, HTTPException

from app.services.submission_service import (
    SubmissionStorageError,
    SubmissionStore,
    enrich_approved_submission,
    get_store,
)
from data_access import DATASETS, load_dataset

router = APIRouter(prefix="/api", tags=["Catalog"])


def filter_records(
    records: list[dict[str, str]],
    filters: list[tuple[str | None, str, bool]],
) -> list[dict[str, str]]:
    """Apply case-insensitive filters against CSV columns."""
    filtered = records
    for value, column, split_values in filters:
        if value is None:
            continue
        expected = value.strip().casefold()
        filtered = [
            row
            for row in filtered
            if (
                any(
                    item.strip().casefold() == expected
                    for item in row.get(column, "").split(";")
                )
                if split_values
                else row.get(column, "").strip().casefold() == expected
            )
        ]
    return filtered


@router.get("/catalog")
def get_catalog(store: SubmissionStore = Depends(get_store)) -> dict[str, list[dict]]:
    """Return all canonical CSV datasets plus approved community submissions."""
    catalog: dict[str, list[dict]] = {
        dataset_name: load_dataset(filename)
        for dataset_name, filename in DATASETS.items()
    }
    try:
        approved = store.list_by_status("approved")
    except SubmissionStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    catalog["approved_community_submissions"] = [
        enrich_approved_submission(item) for item in approved
    ]
    return catalog


@router.get("/destinations")
def get_destinations(
    state: str | None = None,
    district: str | None = None,
    category: str | None = None,
) -> list[dict[str, str]]:
    """Return all destinations, optionally filtered by CSV fields."""
    destinations = load_dataset(DATASETS["destinations"])

    if state:
        state_filter = state.strip().casefold()
        destinations = [
            row
            for row in destinations
            if row.get("state", "").strip().casefold() == state_filter
        ]

    if district:
        district_filter = district.strip().casefold()
        destinations = [
            row
            for row in destinations
            if row.get("district", "").strip().casefold() == district_filter
        ]

    if category:
        category_filter = category.strip().casefold()
        destinations = [
            row
            for row in destinations
            if any(
                item.strip().casefold() == category_filter
                for item in re.split(r"[;,/|]+", row.get("category", ""))
            )
        ]

    return destinations


@router.get("/food")
def get_food(
    state: str | None = None,
    district: str | None = None,
) -> list[dict[str, str]]:
    """Return food records, optionally filtered by state or district."""
    return filter_records(
        load_dataset(DATASETS["food"]),
        [(state, "state", False), (district, "district", False)],
    )


@router.get("/crafts")
def get_crafts(
    state: str | None = None,
    district: str | None = None,
) -> list[dict[str, str]]:
    """Return craft records, optionally filtered by state or district."""
    return filter_records(
        load_dataset(DATASETS["crafts"]),
        [(state, "state", False), (district, "district", False)],
    )


@router.get("/cultural-experiences")
def get_cultural_experiences(
    state: str | None = None,
    district: str | None = None,
    experience_type: str | None = None,
) -> list[dict[str, str]]:
    """Return cultural experiences, optionally filtered by CSV fields."""
    return filter_records(
        load_dataset(DATASETS["cultural_experiences"]),
        [
            (state, "state", False),
            (district, "district", False),
            (experience_type, "experience_type", False),
        ],
    )


@router.get("/gi-products")
def get_gi_products(
    state: str | None = None,
    district: str | None = None,
    category: str | None = None,
) -> list[dict[str, str]]:
    """Return GI products, optionally filtered by origin and goods category."""
    return filter_records(
        load_dataset(DATASETS["gi_products"]),
        [
            (state, "states_in_phase1", True),
            (district, "origin_district", False),
            (category, "goods_category", False),
        ],
    )
