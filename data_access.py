"""Shared access to the configured catalog CSV datasets."""

import csv
from pathlib import Path

from fastapi import HTTPException

from app.config import settings

DATASETS = {
    "destinations": "destinations.csv",
    "food": "food.csv",
    "gi_products": "gi_products.csv",
    "crafts": "crafts.csv",
    "cultural_experiences": "cultural_experiences.csv",
    "media_assets": "media_assets.csv",
    "sources_reference": "sources_reference.csv",
}


class MalformedCSVError(ValueError):
    """Raised when a CSV cannot be represented as header-keyed records."""


def read_csv_records(path: Path) -> list[dict[str, str]]:
    """Read CSV rows without changing their headers or field values."""
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.reader(csv_file, strict=True)
        try:
            headers = next(reader)
        except StopIteration as error:
            raise MalformedCSVError("missing header row") from error

        if not headers or any(not header.strip() for header in headers):
            raise MalformedCSVError("header row contains an empty column name")
        if len(headers) != len(set(headers)):
            raise MalformedCSVError("header row contains duplicate column names")

        records = []
        for record_number, values in enumerate(reader, start=2):
            if not values:
                continue
            if len(values) != len(headers):
                raise MalformedCSVError(
                    f"record {record_number} has {len(values)} fields; "
                    f"expected {len(headers)}"
                )
            records.append(dict(zip(headers, values)))

    return records


def load_dataset(filename: str) -> list[dict[str, str]]:
    """Read one configured dataset and translate file errors into API errors."""
    path = settings.DATA_DIR / filename
    try:
        return read_csv_records(path)
    except OSError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Catalog dataset '{filename}' is unavailable.",
        ) from error
    except (UnicodeDecodeError, csv.Error, MalformedCSVError) as error:
        raise HTTPException(
            status_code=500,
            detail=f"Catalog dataset '{filename}' is malformed: {error}",
        ) from error
