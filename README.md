# WAYBOUND — Integrated Backend & Frontend

Route-based cultural & regional tourism discovery and community-powered listings for Andhra Pradesh and Telangana (**no Supabase used**).

## Setup & Run (from `WAYBOUND/`)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000` in your browser (Swagger docs at `http://127.0.0.1:8000/docs`).

## Key Endpoints (`WAYBOUND_API_CONTRACT.md`)

- `GET /health` — Server health check
- `GET /api/catalog` — Canonical CSV datasets + `approved_community_submissions` (marked `community_approved_unverified`, `verified: false`)
- `GET /api/discover` — Point-radius discovery (`destination`, `radius_km`, `category`, optional `latitude`/`longitude`)
- `POST /api/discover/route` — Route-corridor discovery along a client-supplied GeoJSON `LineString` (`local_equirectangular_point_to_segment`)
- `POST /api/submissions` — Submit a community `destination`, `food`, `craft`, or `cultural_experience` (`pending` status)
- `GET /api/submissions/pending`, `GET /api/submissions/approved`
- `PATCH /api/submissions/{id}/approve`, `PATCH /api/submissions/{id}/reject` *(prototype admin endpoints; no authentication)*

## Run Tests

```powershell
python -m pytest -v
```
