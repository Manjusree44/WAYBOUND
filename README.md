# WAYBOUND — Data & Discovery Logic (Backend)

Local data pipeline, JSON & SQLite storage, search/filtering, nearby attraction recommendations, and source/location verification for WAYBOUND (**no Supabase used**).

## Files

- `data/*.csv` — Verified destination, food, craft, cultural experience, GI product, media, and source-reference CSV datasets.
- `storage.py` — Exports all CSVs to `data/json/*.json` (plus `data/json/waybound_data.json`) and builds a local SQLite database at `data/waybound.db`.
- `discovery.py` — Loaders, safety filters, multi-entity search/filtering, relationship lookups (`things_at`, `get_destination_details`), and haversine nearby attraction recommendations (`nearby`, `recommend_nearby`).
- `verify_data.py` — Audits geographic bounds, coordinate source URLs, primary source URLs, verification statuses, and foreign-key integrity (`data/verification_report.json`).
- `tests/test_waybound.py` — Unit tests covering counts, search/filtering, recommendations, JSON/SQLite builds, and data verification.

## Quick Commands (run from `WAYBOUND/`)

```powershell
# Build JSON exports (data/json/) and SQLite database (data/waybound.db)
python storage.py

# Run coordinate, source URL, and foreign-key audit (data/verification_report.json)
python verify_data.py

# Run test suite
python -m unittest discover -s tests -v
```

## Available Imports for Person 1 (`discovery.py` & `storage.py`)

- **Loaders**: `load_destinations`, `load_food`, `load_crafts`, `load_experiences`, `load_gi_products`, `load_media_assets`, `load_sources_reference`
- **Safety filter**: `safe_places` (returns verified single-point destinations only)
- **Search & filtering**: `filter_places`, `filter_food`, `filter_crafts`, `filter_experiences`, `filter_gi_products`, `search_all`
- **Relationships & recommendations**: `things_at`, `get_destination_details`, `distance_km`, `nearby`, `recommend_nearby`
- **SQLite helper**: `storage.get_connection("data/waybound.db")`

> Note: Run the backend server from the `WAYBOUND` directory so relative `data/` paths resolve cleanly. Never display fees, opening hours, or phone numbers listed under `unverified_fields`.
