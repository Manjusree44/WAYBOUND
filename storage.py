"""Build local JSON exports and a SQLite database from the WAYBOUND CSV datasets.

No external database or Supabase is required; uses Python's built-in csv, json,
and sqlite3 modules.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

DATASET_FILES = {
    "destinations": "destinations.csv",
    "food": "food.csv",
    "crafts": "crafts.csv",
    "cultural_experiences": "cultural_experiences.csv",
    "gi_products": "gi_products.csv",
    "media_assets": "media_assets.csv",
    "sources_reference": "sources_reference.csv",
}

TABLE_PRIMARY_KEYS = {
    "destinations": "destination_id",
    "food": "food_id",
    "crafts": "craft_id",
    "cultural_experiences": "experience_id",
    "gi_products": "gi_id",
    "media_assets": "media_id",
}

INDEX_DEFINITIONS = [
    ("idx_destinations_state", "destinations", "state"),
    ("idx_destinations_district", "destinations", "district"),
    ("idx_destinations_safe", "destinations", "record_kind, verification_status"),
    ("idx_food_state", "food", "state"),
    ("idx_food_district", "food", "district"),
    ("idx_food_gi", "food", "gi_id"),
    ("idx_crafts_destination", "crafts", "destination_id"),
    ("idx_crafts_state", "crafts", "state"),
    ("idx_crafts_gi", "crafts", "gi_id"),
    ("idx_experiences_destination", "cultural_experiences", "destination_id"),
    ("idx_experiences_craft", "cultural_experiences", "craft_id"),
    ("idx_gi_destination", "gi_products", "destination_id"),
    ("idx_gi_state", "gi_products", "state_ut_normalised"),
    ("idx_media_destination", "media_assets", "destination_id"),
    ("idx_sources_record", "sources_reference", "dataset_file, record_id"),
    ("idx_sources_destination", "sources_reference", "destination_id"),
]


def _read_csv_rows(csv_path: Path, numeric_coords: bool = False) -> tuple[list[str], list[dict]]:
    """Read a UTF-8 CSV file and optionally convert latitude/longitude to floats."""
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        rows = list(reader)

    if numeric_coords:
        for row in rows:
            row["latitude"] = float(row["latitude"])
            row["longitude"] = float(row["longitude"])
    return columns, rows


def export_json(data_dir: str | Path = "data", out_dir: str | Path | None = None) -> dict[str, Path]:
    """Export each CSV dataset to individual JSON files and a combined bundle."""
    base_dir = Path(data_dir)
    json_dir = Path(out_dir) if out_dir else base_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    bundle: dict[str, object] = {"counts": {}, "datasets": {}}

    for name, filename in DATASET_FILES.items():
        _, rows = _read_csv_rows(base_dir / filename, numeric_coords=(name == "destinations"))
        target = json_dir / f"{name}.json"
        target.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written[name] = target
        bundle["counts"][name] = len(rows)
        bundle["datasets"][name] = rows

    submissions_path = base_dir / "submissions.json"
    submissions: list[dict] = []
    if submissions_path.exists():
        submissions = json.loads(submissions_path.read_text(encoding="utf-8"))
    submissions_target = json_dir / "submissions.json"
    submissions_target.write_text(
        json.dumps(submissions, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    written["submissions"] = submissions_target
    bundle["counts"]["submissions"] = len(submissions)
    bundle["datasets"]["submissions"] = submissions

    bundle_path = json_dir / "waybound_data.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written["bundle"] = bundle_path
    return written


def _sql_column_type(table: str, col: str) -> str:
    if table == "destinations" and col in ("latitude", "longitude"):
        return "REAL"
    return "TEXT"


def build_sqlite(data_dir: str | Path = "data", db_path: str | Path | None = None) -> Path:
    """Create and populate a local SQLite database from the WAYBOUND CSV datasets."""
    base_dir = Path(data_dir)
    target_db = Path(db_path) if db_path else base_dir / "waybound.db"
    target_db.parent.mkdir(parents=True, exist_ok=True)

    # Build into a fresh database so repeated runs stay idempotent.
    if target_db.exists():
        target_db.unlink()

    conn = sqlite3.connect(target_db)
    try:
        cur = conn.cursor()
        for name, filename in DATASET_FILES.items():
            columns, rows = _read_csv_rows(base_dir / filename, numeric_coords=(name == "destinations"))
            if not columns:
                continue

            pk = TABLE_PRIMARY_KEYS.get(name)
            col_defs = []
            if name == "sources_reference":
                col_defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")

            for col in columns:
                col_type = _sql_column_type(name, col)
                if col == pk:
                    col_defs.append(f'"{col}" {col_type} PRIMARY KEY')
                else:
                    col_defs.append(f'"{col}" {col_type}')

            cur.execute(f'CREATE TABLE "{name}" ({", ".join(col_defs)})')

            placeholders = ", ".join("?" for _ in columns)
            quoted_cols = ", ".join(f'"{c}"' for c in columns)
            values = [tuple(row.get(c, "") for c in columns) for row in rows]
            cur.executemany(f'INSERT INTO "{name}" ({quoted_cols}) VALUES ({placeholders})', values)

        for idx_name, table, cols in INDEX_DEFINITIONS:
            cur.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ({cols})')

        submissions_path = base_dir / "submissions.json"
        if submissions_path.exists():
            submissions = json.loads(submissions_path.read_text(encoding="utf-8"))
            if not isinstance(submissions, list):
                raise ValueError("submissions.json must contain a JSON list")
            cur.execute(
                'CREATE TABLE "submissions" '
                "(id TEXT PRIMARY KEY, name TEXT, description TEXT, submission_type TEXT, "
                "state TEXT, district TEXT, location TEXT, latitude REAL, longitude REAL, "
                "contact TEXT, source TEXT, status TEXT, created_at TEXT, updated_at TEXT)"
            )
            columns = (
                "id", "name", "description", "submission_type", "state", "district",
                "location", "latitude", "longitude", "contact", "source", "status",
                "created_at", "updated_at",
            )
            placeholders = ", ".join("?" for _ in columns)
            cur.executemany(
                f'INSERT INTO "submissions" ({", ".join(columns)}) VALUES ({placeholders})',
                [tuple(row.get(column) for column in columns) for row in submissions],
            )
            cur.execute('CREATE INDEX "idx_submissions_status" ON "submissions" (status)')

        conn.commit()
    finally:
        conn.close()

    return target_db


def get_connection(db_path: str | Path = "data/waybound.db") -> sqlite3.Connection:
    """Open a read-ready SQLite connection returning dict-like sqlite3.Row rows."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def build_all(data_dir: str | Path = "data") -> dict[str, object]:
    """Generate both JSON exports and the local SQLite database."""
    json_files = export_json(data_dir=data_dir)
    db_file = build_sqlite(data_dir=data_dir)
    return {"json_files": {k: str(v) for k, v in json_files.items()}, "sqlite_db": str(db_file)}


if __name__ == "__main__":
    result = build_all()
    print(json.dumps(result, indent=2))
