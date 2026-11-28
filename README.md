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
- `PATCH /api/submissions/{id}/approve`, `PATCH /api/submissions/{id}/reject` *(fail-closed admin endpoints guarded by `ADMIN_TOKEN` via `X-Admin-Token`)*

## Admin Authentication (Local Development)

Admin review routes (`GET /api/submissions/pending`, `PATCH /api/submissions/{id}/approve`, `PATCH /api/submissions/{id}/reject`) fail closed with HTTP `503` whenever `ADMIN_TOKEN` is unset or blank. Public discovery, catalog, submission creation (`POST /api/submissions`), and `GET /api/submissions/approved` continue to work without a token.

To enable admin review locally, set `ADMIN_TOKEN` in your shell before starting Uvicorn (replace the placeholder with your own local secret):

```powershell
$env:ADMIN_TOKEN = "your-local-admin-token"
uvicorn main:app --reload
```

When opening **Admin Review** in the browser with `ADMIN_TOKEN` set, enter the token when prompted (kept in memory only). When `ADMIN_TOKEN` is unset, the Admin Review tab displays a disabled notice while public Explore and Submit views remain available.

## Run Tests

```powershell
python -m pytest -v
```
