"""Read-only API for the catalog CSV datasets."""

import re

from fastapi import APIRouter

from app.data_access import DATASETS, load_dataset

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
            row for row in filtered
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
def get_catalog() -> dict[str, list[dict[str, str]]]:
    """Return all CSV datasets, keyed by their catalog names."""
    return {
        dataset_name: load_dataset(filename)
        for dataset_name, filename in DATASETS.items()
    }


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
            row for row in destinations
            if row.get("state", "").strip().casefold() == state_filter
        ]

    if district:
        district_filter = district.strip().casefold()
        destinations = [
            row for row in destinations
            if row.get("district", "").strip().casefold() == district_filter
        ]

    if category:
        category_filter = category.strip().casefold()
        destinations = [
            row for row in destinations
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
