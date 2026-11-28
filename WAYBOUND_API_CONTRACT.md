# WAYBOUND API Contract (Proposal)

**Audience:** frontend and backend developers  
**Status:** Existing routes describe the integrated backend as inspected. Items marked **Proposed** are not implemented yet. This document does not change application code or data.

## Compatibility rules

1. Keep the existing `GET /api/discover` query parameters and response keys.
2. Add route-polyline discovery as a separate endpoint, `POST /api/discover/route`.
3. Keep the existing submission endpoints and common submission fields.
4. Do not accept client-supplied approval or verification status.
5. Treat “approved by an admin” as different from “factually verified.” Community information remains unverified unless independently checked.

## 1. Route discovery

### Existing point-radius endpoint

`GET /api/discover` currently accepts:

| Parameter | Required | Current behavior |
|---|---:|---|
| `destination` | Yes | Canonical destination ID or name; also accepts an approved community destination ID/name when it has coordinates. |
| `radius_km` | No | Defaults to `10`; accepted values are `5`, `10`, `25`, `50`. |
| `category` | No | `attractions`, `food`, `crafts`, or `culture`. `culture` returns `cultural_experiences`. |
| `latitude`, `longitude` | No | Must be supplied together; overrides the search center, but `destination` is still required. |

This is a search around **one point**, not a journey route. It does not accept a starting town and ending destination as a pair or receive road-route geometry.

Example:

```http
GET /api/discover?destination=DST-TG-0001&radius_km=10&category=attractions
```

Existing response shape:

```json
{
  "selected_location": {
    "destination_id": "DST-TG-0001",
    "name": "Pembarthi",
    "latitude": "17.6895",
    "longitude": "79.11758",
    "search_center": {
      "latitude": 17.6895,
      "longitude": 79.11758,
      "source": "destination"
    }
  },
  "radius_km": 10,
  "category": "attractions",
  "results": {
    "destinations": [
      {
        "record": {
          "destination_id": "DST-TG-0001",
          "name": "Pembarthi",
          "record_kind": "point_destination",
          "verification_status": "verified_official_source"
        },
        "distance_km": 0.0,
        "location_destination_id": "DST-TG-0001"
      }
    ],
    "food": [],
    "crafts": [],
    "cultural_experiences": []
  },
  "total_result_count": 1
}
```

The abbreviated `record` above represents a CSV row; the current API returns its full row.

### Proposed route endpoint (additive)

`POST /api/discover/route`

The frontend supplies the start and selected destination, plus a road-route `LineString` from a routing provider. The backend does not calculate or geocode a road route. The `popular_destination` name below reflects the product’s selected endpoint; the API does not independently verify popularity.

`popular_destination.destination_id` is **required** and must resolve to a canonical destination. `name` is optional display text; when supplied it must match the canonical row’s name, and the backend uses the canonical row. A name alone is not sufficient for lookup. A mismatched optional name returns proposed `422`.

`corridor_width_km` is the **full** corridor width. A result qualifies when its geometric distance to the supplied route line is at most half that width. This is geometric proximity, not road distance, driving time, or detour distance.

Request:

```json
{
  "starting_town": {"name": "Starting town"},
  "popular_destination": {
    "destination_id": "DST-AP-0003"
  },
  "route_geometry": {
    "type": "LineString",
    "coordinates": [
      [78.0, 17.0],
      [82.0, 18.0]
    ]
  },
  "corridor_width_km": 25,
  "experience_categories": ["food", "crafts", "culture"],
  "destination_categories": ["Nature", "Heritage"]
}
```

The coordinate numbers above are **format placeholders**, not a real route or destination data.

**Proposed request fields**

- `starting_town.name`: required display label. Its coordinate is the first point in `route_geometry`; the frontend obtains route geometry from a routing provider.
- `popular_destination.destination_id`: required canonical destination ID. Optional `name` is display-only and must match the canonical record; mismatch returns proposed `422`.
- `route_geometry`: required GeoJSON `LineString`; each position contains exactly two finite numbers in `[longitude, latitude]` order. Proposed validation: 2–500 points inclusive; longitude `-180..180`, latitude `-90..90`; reject a line whose segments are all zero-length.
- `corridor_width_km`: required positive number. **Proposed limit:** `1..100 km` inclusive, interpreted as full width; the distance threshold is `corridor_width_km / 2`.
- `experience_categories`: optional subset of `food`, `crafts`, `culture`; defaults to all three.
- `destination_categories`: optional category tokens matched against the existing free-text `category` column. Matching/normalization is proposed; preserve the CSV value in responses.

All route geometry is supplied by the client; the API does not provide routing or geocoding. The limits above are **proposed**, not current behavior. The route geometry is authoritative; the backend validates its shape and ranges but cannot confirm it is a real road route or that it connects the displayed town names to the selected destination. The frontend/routing provider must supply a route connecting those selections. A valid route outside the area represented by catalog coordinates is not an error: return `200` with empty result arrays and proposed `coverage_status: "no_catalog_matches"`. If some records match, return them with `coverage_status: "matches_found"`; this only means results were found and does not claim complete geographic coverage. The project has no defined coverage polygon.

#### Proposed point-to-route calculation

For each candidate anchor coordinate and every consecutive pair in the `LineString`:

1. Project the candidate and both segment endpoints into a local equirectangular metric plane centered at that segment’s midpoint, using Earth radius `6371.0088 km` and `x = R cos(φ₀)(λ − λ₀)`, `y = R(φ − φ₀)` (angles in radians).
2. Find the nearest point on the projected segment using a clamped point-to-segment projection (`t` limited to `[0, 1]`); measure Euclidean distance to it.
3. Use the minimum distance across all segments as `distance_to_route_km`, in kilometres, rounded to three decimal places.

This regional approximation measures geometric distance to the polyline, not a route-network distance. It must not be shown as driving distance, travel time, or detour.

Proposed response:

```json
{
  "route": {
    "starting_town": "Hyderabad",
    "popular_destination": {
      "destination_id": "DST-AP-0003",
      "name": "Araku Valley"
    },
    "corridor_width_km": 25,
    "distance_method": "local_equirectangular_point_to_segment"
  },
  "coverage_status": "matches_found",
  "results": {
    "destinations": [
      {
        "record": {
          "destination_id": "DST-AP-0016",
          "name": "Durgi",
          "category": "Craft village; stone carving; heritage",
          "record_kind": "craft_or_experience_cluster",
          "verification_status": "verified_official_source",
          "source_url_primary": "https://palnadu.ap.gov.in/odop/",
          "unverified_fields": "current workshop visitor hours;booking;artisan contact"
        },
        "distance_to_route_km": 3.4,
        "location_destination_id": "DST-AP-0016",
        "popularity_status": "not_assessed"
      }
    ],
    "food": [],
    "crafts": [
      {
        "record": {
          "id": "SUB-EXAMPLE",
          "name": "Illustrative community craft listing",
          "submission_type": "craft",
          "status": "approved",
          "destination_id": "DST-AP-0016",
          "verification_status": "community_approved_unverified",
          "verified": false
        },
        "distance_to_route_km": 3.4,
        "location_destination_id": "DST-AP-0016",
        "popularity_status": "not_assessed"
      }
    ],
    "cultural_experiences": []
  },
  "total_result_count": 2
}
```

`distance_to_route_km`, `distance_method`, `coverage_status`, and `popularity_status` are **proposed**. The Durgi row/source/status above are from the canonical dataset. `SUB-EXAMPLE`, its association, and both distances are placeholders only—not a stored submission or measured route result. `not_assessed` means no comparable popularity evidence is available. Preserve source URLs, `verification_status`, and `unverified_fields` from canonical records.

### Current relationship behavior

- Canonical food is associated with destinations through `food.gi_id` → `gi_products.destination_id`. This currently links only a subset of food rows.
- Crafts use `destination_id`, falling back to GI-product destination links.
- Cultural experiences use `destination_id`, falling back through `craft_id` to a craft’s destination.
- Route discovery should retain those canonical relationships and use the destination coordinates as the spatial anchor. Community records without coordinates or a supported relationship cannot be placed in a route corridor.

### Community-listing spatial anchors (proposed)

Use the following precedence for route discovery: a valid community coordinate pair first; otherwise a supported canonical relationship. `location` text, state, and district alone are not spatial anchors.

| Submission type | Anchor precedence |
|---|---|
| `destination` | Its own latitude/longitude pair. If it is a confirmed duplicate, use the canonical record linked by admin-set `canonical_record_id` instead of emitting a second destination. |
| `food` | Its own latitude/longitude pair; otherwise proposed `destination_id` pointing to the canonical destination where it is offered. A confirmed duplicate uses its canonical food record’s existing relationship. |
| `craft` | Its own latitude/longitude pair; otherwise proposed `destination_id` pointing to the canonical destination. A confirmed duplicate uses its canonical craft record’s existing relationship. |
| `cultural_experience` | Its own latitude/longitude pair; otherwise proposed `destination_id`, or proposed `craft_id` resolved through the canonical craft’s destination. A confirmed duplicate uses its canonical experience record’s existing relationship. |

If a listing has neither coordinates nor a supported relationship, accept and retain it in the approved public listing/catalog, but omit it from route results. A proposed `spatial_status: "unlocated"` may explain the omission. Do not infer a location from district/state text.

## 2. Community submissions

### Existing request contract

`POST /api/submissions` accepts all four `submission_type` values:

- `destination`
- `food`
- `craft`
- `cultural_experience`

All types currently use the same schema. The following fields are **required for every type**:

| Field | Constraints |
|---|---|
| `name` | String, 1–200 characters |
| `description` | String, 1–4000 characters |
| `submission_type` | One of the four values above |
| `state` | String, 1–80 characters |
| `district` | String, 1–80 characters |

Current optional fields for every type:

| Field | Constraints |
|---|---|
| `location` | String, up to 300 characters |
| `latitude`, `longitude` | Optional pair; latitude `-90..90`, longitude `-180..180` |
| `contact` | String, up to 300 characters |
| `source` | String, up to 500 characters |

`status`, `verification_status`, and other unknown fields are rejected from the request. New submissions always start as `pending`. The schema accepts the alias “cultural experience” but serializes it as `cultural_experience`.

The following is an illustrative request body using the current shared schema; it is not a canonical dataset row or an existing submission:

```json
{
  "name": "Etikoppaka Toy Workshop",
  "description": "A local workshop producing turned-wood lacquer toys.",
  "submission_type": "destination",
  "state": "Andhra Pradesh",
  "district": "Anakapalli",
  "location": "Etikoppaka",
  "latitude": 17.4921,
  "longitude": 82.7543,
  "contact": "vendor@example.org",
  "source": "https://anakapalli.ap.gov.in/odop-anakapalli/"
}
```

The same schema accepts `"food"`, `"craft"`, or `"cultural_experience"` as `submission_type`; provide the corresponding listing name and description. These values are illustrative. The current schema does not distinguish their type-specific attributes.

Example `201 Created` response:

```json
{
  "id": "SUB-7DA2D80A3CD5",
  "name": "Etikoppaka Toy Workshop",
  "description": "A local workshop producing turned-wood lacquer toys.",
  "submission_type": "destination",
  "state": "Andhra Pradesh",
  "district": "Anakapalli",
  "location": "Etikoppaka",
  "latitude": 17.4921,
  "longitude": 82.7543,
  "contact": "vendor@example.org",
  "source": "https://anakapalli.ap.gov.in/odop-anakapalli/",
  "status": "pending",
  "created_at": "2026-11-28T00:00:00+00:00",
  "updated_at": "2026-11-28T00:00:00+00:00"
}
```

### Proposed type-specific optional fields

These are drawn from existing canonical CSV columns, but are **not accepted by the current submission schema** (`extra="forbid"`). They require a schema/API change before clients may send them. Keep them optional for a hackathon intake form; retain the shared required fields above.

| Type | Proposed optional fields |
|---|---|
| `destination` | `category` |
| `food` | `origin_place`, `ingredients`, `cultural_significance`, `gi_id` |
| `craft` | `origin_place`, `destination_id`, `gi_id`, `materials`, `techniques_process`, `products`, `artisan_community` |
| `cultural_experience` | `experience_type`, `destination_id`, `craft_id`, `months_or_season`, `availability_status`, `availability_note`, `price` |

Do not let submitters set verification or approval fields. Any source, contact, schedule, price, or claim supplied by a submitter remains community-provided and unverified.

### Minimum fields for route discovery (proposed eligibility rules)

The existing common required fields above are sufficient to create a pending submission. To appear in route results, the listing also needs a spatial anchor:

| Type | Minimum route-discovery anchor |
|---|---|
| `destination` | A latitude/longitude pair. Coordinates are optional in the current schema, so an approved destination without them remains public but is not spatially discoverable. |
| `food` | A latitude/longitude pair, or proposed `destination_id`. |
| `craft` | A latitude/longitude pair, or proposed `destination_id`. |
| `cultural_experience` | A latitude/longitude pair, proposed `destination_id`, or proposed `craft_id` that resolves to a canonical craft with a destination link. |

Coordinates are already accepted as an optional pair for every submission type. `destination_id` and `craft_id` are **proposed additions** to `SubmissionCreate`; they are not accepted today. The type-specific descriptive fields in the preceding table remain optional for the hackathon. `location` text alone does not satisfy the anchor rule.

## 3. Admin workflow

The existing endpoints are:

| Operation | Endpoint | Success |
|---|---|---|
| List pending | `GET /api/submissions/pending` | `200`, array of pending submissions |
| Approve | `PATCH /api/submissions/{submission_id}/approve` | `200`, updated submission |
| Reject | `PATCH /api/submissions/{submission_id}/reject` | `200`, updated submission |

Examples:

```http
GET /api/submissions/pending
```

```json
[
  {
    "id": "SUB-7DA2D80A3CD5",
    "name": "Etikoppaka Toy Workshop",
    "description": "A local workshop producing turned-wood lacquer toys.",
    "submission_type": "craft",
    "state": "Andhra Pradesh",
    "district": "Anakapalli",
    "location": "Etikoppaka",
    "latitude": 17.4921,
    "longitude": 82.7543,
    "contact": null,
    "source": null,
    "status": "pending",
    "created_at": "2026-11-28T00:00:00+00:00",
    "updated_at": "2026-11-28T00:00:00+00:00"
  }
]
```

Approve:

```http
PATCH /api/submissions/SUB-7DA2D80A3CD5/approve
```

**Proposed duplicate-link option:** keep the existing bodyless request valid. An admin may optionally provide `canonical_record_id` when approving a confirmed duplicate:

```http
PATCH /api/submissions/SUB-EXAMPLE/approve
Content-Type: application/json

{"canonical_record_id":"DST-AP-0016"}
```

`canonical_record_id` points to the same entity in the canonical dataset and must match its entity type. It is assigned by the admin, never by the submitter. For example, it can identify the canonical destination a duplicate destination submission represents.

The example assumes `SUB-EXAMPLE` is a pending destination submission. The canonical ID shown is an example of a destination ID, not a claim that this submission exists.

This is different from `destination_id`: that field is a proposed location relationship for a food, craft, or experience (the place where it is offered), not a duplicate/entity identity. A community food listing may have `destination_id: "DST-AP-0016"` while remaining a separate listing; it should not have `canonical_record_id` unless it duplicates a canonical food record.

Reject:

```http
PATCH /api/submissions/SUB-7DA2D80A3CD5/reject
```

Both return the same submission object with `status` changed to `approved` or `rejected`. Only pending submissions can transition. These admin endpoints currently have **no authentication**; do not expose them as production-secure admin functions without adding authentication/authorization.

## 4. Public discovery and duplicate handling

### Existing behavior

- `GET /api/submissions/approved` returns all approved submissions.
- `GET /api/catalog` includes `approved_community_submissions`; those entries have `verification_status: "community_approved_unverified"` and `verified: false`.
- `GET /api/discover` currently adds approved community **destinations with both coordinates** to destination results. Approved food, craft, and cultural-experience submissions do not currently enter their corresponding discovery result arrays.
- Approved submissions without coordinates can appear in the approved list/catalog but cannot be placed by the current spatial discovery logic.
- Current code does not deduplicate approved community destinations against canonical records.

### Proposed public behavior

1. Keep canonical CSV rows as canonical records. Add approved community records to the matching result group only when they have usable coordinates or a supported canonical relationship.
2. Return community entries with `status: "approved"`, `verification_status: "community_approved_unverified"`, and `verified: false`. Approval is not factual verification.
3. Preserve their supplied source/contact and type-specific fields as community-supplied values; do not overwrite canonical fields or present unverified prices/schedules/contacts as verified.
4. **Proposed duplicate control:** allow an admin to set `canonical_record_id` in the optional approval body when a reviewer confirms that a submission duplicates a specific canonical entity. The ID must identify an entity of the same type as the submission. This field is not currently supported.
   - If set, do not emit a second entity result; attach the submission under a proposed `community_contributions` array on the canonical result.
   - If not set, return it as a separate community listing. Do not auto-merge on name alone.
   - A distinct vendor or experience at a canonical destination is not a duplicate. A proposed `destination_id` relationship locates it; `canonical_record_id` is reserved for the same entity. `destination_id` and `craft_id` are proposed submission fields; neither substitutes for duplicate identity.

Proposed additive public metadata:

```json
{
  "verification_status": "community_approved_unverified",
  "verified": false,
  "community_contributions": [
    {
      "submission_id": "SUB-7DA2D80A3CD5",
      "submission_type": "craft",
      "status": "approved"
    }
  ]
}
```

`canonical_record_id` and `community_contributions` are **proposed**, not current API fields. Existing response keys must remain unchanged. When an admin supplies `canonical_record_id`, include it in the approval response as an additive field.

## 5. Public listing endpoints

### Approved submissions

`GET /api/submissions/approved` is currently public and returns the `SubmissionRead` array. Proposed additive safety metadata for this endpoint is shown below; current responses do not include these two fields (the catalog endpoint does).

```json
[
  {
    "id": "SUB-7DA2D80A3CD5",
    "name": "Etikoppaka Toy Workshop",
    "description": "A local workshop producing turned-wood lacquer toys.",
    "submission_type": "craft",
    "state": "Andhra Pradesh",
    "district": "Anakapalli",
    "location": "Etikoppaka",
    "latitude": 17.4921,
    "longitude": 82.7543,
    "contact": "vendor@example.org",
    "source": null,
    "status": "approved",
    "created_at": "2026-11-28T00:00:00+00:00",
    "updated_at": "2026-11-28T00:00:00+00:00",
    "verification_status": "community_approved_unverified",
    "verified": false
  }
]
```

### Aggregate catalog

`GET /api/catalog` currently returns canonical arrays keyed by `destinations`, `food`, `gi_products`, `crafts`, `cultural_experiences`, `media_assets`, and `sources_reference`, plus `approved_community_submissions`.

```json
{
  "destinations": [],
  "food": [],
  "gi_products": [],
  "crafts": [],
  "cultural_experiences": [],
  "media_assets": [],
  "sources_reference": [],
  "approved_community_submissions": [
    {
      "id": "SUB-7DA2D80A3CD5",
      "name": "Etikoppaka Toy Workshop",
      "description": "A local workshop producing turned-wood lacquer toys.",
      "submission_type": "craft",
      "state": "Andhra Pradesh",
      "district": "Anakapalli",
      "status": "approved",
      "verification_status": "community_approved_unverified",
      "verified": false
    }
  ]
}
```

The empty canonical arrays keep this example concise; production responses contain the CSV records.

## 6. Error responses

Existing errors use FastAPI’s `{"detail": ...}` format, except request validation, which returns `422` with a `detail` array.

| Case | Status | Example |
|---|---:|---|
| Invalid/missing body field or out-of-range coordinate | `422` | `{"detail":[{"loc":["body"],"msg":"Provide both latitude and longitude, or leave both empty.","type":"value_error"}]}` |
| Unsupported discovery category | `422` | FastAPI query validation response with a `detail` array. |
| Unsupported discovery radius | `422` | `{"detail":"radius_km must be one of 5, 10, 25, or 50."}` |
| Only one custom discovery coordinate supplied | `422` | `{"detail":"Provide both latitude and longitude for a custom search location."}` |
| Destination not found | `404` | `{"detail":"Destination 'Unknown' was not found."}` |
| Submission ID not found | `404` | `{"detail":"No submission found with id 'SUB-MISSING'."}` |
| Approve/reject already processed submission | `409` | `{"detail":"Submission 'SUB-7DA2D80A3CD5' is already approved. Only pending submissions can be approved."}` |
| Corrupt/unreadable submissions file | `500` | `{"detail":"The submissions file is not valid JSON, so it was left unchanged. ..."}` |
| Canonical dataset unavailable | `503` | `{"detail":"Catalog dataset 'destinations.csv' is unavailable."}` |
| Malformed canonical CSV | `500` | `{"detail":"Catalog dataset 'destinations.csv' is malformed: ..."}` |

The proposed route endpoint should return `422` for malformed geometry, invalid coordinates, or invalid corridor width, and `404` when its destination cannot be resolved. These route-specific errors are **proposed**.

## Existing implementation references

- Single app registration: [main.py](./main.py).
- Current route endpoint and validation: [routers/discovery.py](./routers/discovery.py), `get_discoveries`.
- Current discovery and relationship logic: [services/discovery.py](./services/discovery.py), `discover_nearby`, `_destination_links`, `_nearby_records`.
- Current submission request/response schemas: [app/schemas/submissions.py](./app/schemas/submissions.py), `SubmissionCreate`, `SubmissionRead`, `SubmissionType`.
- Current submission routes: [app/routers/submissions.py](./app/routers/submissions.py).
- JSON persistence and status transitions: [app/services/submission_service.py](./app/services/submission_service.py), `SubmissionStore`.
- Public aggregate catalog: [routers/catalog.py](./routers/catalog.py), `get_catalog`.
