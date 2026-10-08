# Geospatial File Measurement API

A FastAPI service that accepts a Shapefile (.zip) or KML, extracts every feature, and returns area (polygons) and length (lines), calculated in a projected CRS, never in raw degrees.

## Setup

```bash
git clone <repo-url> && cd GeoSpatialAPI
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Interactive docs: http://localhost:8000/docs

Run the tests: `pytest -q`

Try it with the included samples:

```bash
curl -F "file=@samples/survey.kml" http://localhost:8000/api/files/
curl -F "file=@samples/survey_shapefile.zip" http://localhost:8000/api/files/
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/files/` | Upload and process a `.zip` (Shapefile) or `.kml` |
| GET | `/api/files/{id}/` | File summary and status |
| GET | `/api/files/{id}/measurements/` | Per-feature measurements (`limit`, `offset`) |
| GET | `/api/files/{id}/features/` | Per-feature geometry, CRS, properties (extra) |

### POST /api/files/  → 201
```json
{
  "id": "82aa8c0086304267af273e527a063d38",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "status": "COMPLETED",
  "error": null
}
```

### GET /api/files/{id}/measurements/
```json
{
  "id": "82aa8c0086304267af273e527a063d38",
  "measurement_crs": "EPSG:32643",
  "strategy": "utm",
  "total": 3,
  "limit": 100,
  "offset": 0,
  "measurements": [
    {
      "index": 0,
      "geometry_type": "Polygon",
      "measurement": "area",
      "value": 1169894.6226,
      "unit": "m²",
      "status": "OK",
      "reason": null,
      "properties": {"Name": "Plot A"}
    },
    {
      "index": 1,
      "geometry_type": "LineString",
      "measurement": "length",
      "value": 3060.8103,
      "unit": "m",
      "status": "OK",
      "reason": null,
      "properties": {"Name": "Road 1"}
    },
    {
      "index": 2,
      "geometry_type": "Point",
      "measurement": null,
      "value": null,
      "unit": null,
      "status": "NOT_APPLICABLE",
      "reason": null,
      "properties": {"Name": "Well"}
    }
  ]
}
```

Per-feature `status`: `OK`, `NOT_APPLICABLE` (points), `UNSUPPORTED` (null/empty geometry, GeometryCollection), `UNAVAILABLE` (file has no CRS).

### Errors
Every failure uses one shape:
```json
{
  "error": {
    "status": 422,
    "code": "UNPROCESSABLE_FILE",
    "message": "No .shp file found inside the zip",
    "file_id": "abc123"
  }
}
```

| Status | code |
|---|---|
| 413 | FILE_TOO_LARGE |
| 415 | UNSUPPORTED_FILE_TYPE |
| 422 | UNPROCESSABLE_FILE, VALIDATION_ERROR |
| 404 | NOT_FOUND |
| 409 | CONFLICT (data requested for a FAILED file) |
| 500 | INTERNAL_ERROR |

## Architecture

```
app/
├── main.py              app wiring, lifespan, error handlers
├── api/files.py         HTTP endpoints, upload orchestration
├── services/
│   ├── parser.py        safe unzip, read Shapefile/KML, GeoDataFrame -> features
│   ├── crs.py           choose the measurement CRS
│   └── measurements.py  area/length with per-feature status
├── models.py, db.py     SQLAlchemy models (SQLite)
├── schemas.py           Pydantic response models
└── errors.py            unified error envelope
```

**File-processing flow:** stream upload to disk (size-limited) → create `PROCESSING` record → safe-extract zip / read all KML layers → build feature records → compute measurements → persist → mark `COMPLETED` → delete the raw file. Any failure marks the record `FAILED` and returns a structured error.

**Measurement flow:** select measurement CRS → reproject a copy of the data → `geom.area` / `geom.length` in metres → record result and status per feature. The geometry returned to clients stays in the file's original CRS.

**CRS handling:**

| Source CRS | Action |
|---|---|
| Missing | Measurements `UNAVAILABLE`, no guessing |
| Projected, metric, not Web Mercator | Kept as-is |
| Geographic or Web Mercator | Reproject to the UTM zone of the bbox centre |
| Coordinates outside valid lon/lat for the declared CRS | Treated as mismatched, measurements `UNAVAILABLE` |

Correctness is checked against pyproj's geodesic calculations on the WGS84 ellipsoid (`tests/test_measurements.py`), agreeing within 0.5%.

## Design Decisions

- **FastAPI over Django:** small API surface, built-in validation and Swagger.
- **GeoPandas + pyogrio over Fiona:** faster, easier to install.
- **UTM over an equal-area projection:** accurate for both length and area within a zone; equal-area distorts length.
- **One CRS per file (zone from bbox centre):** simple and predictable. Limitation: files spanning several zones lose accuracy at the edges. Upgrade: choose the zone per feature.
- **Refuse rather than guess when CRS is missing:** a wrong assumption gives confidently wrong numbers.
- **Invalid geometries are measured and flagged, not repaired:** repairing would silently change user data.
- **Per-feature status instead of errors:** clients can tell "no measurement needed" from "cannot measure".
- **SQLite with JSON columns:** zero setup. Alternative: PostgreSQL + PostGIS for spatial queries; not needed here.
- **Synchronous processing:** simple, final status in the upload response. Alternative: Celery/RQ worker with polling; the `status` field already supports it.
- **Measurements stored at upload:** fast, reproducible reads; old uploads do not update if logic changes.
- **Security:** zip-slip and zip-bomb guards, size limit enforced while streaming, generated file names, no internals leaked in 500s.

## Known Limitations
- A crash mid-processing can leave a record in `PROCESSING`.
- No authentication or rate limiting.
- Very large geometries are stored whole in JSON columns.

## Assumptions
- Multiple shapefiles in one zip are merged into a single feature set.
- Files with no CRS are stored but not measured.
- KML altitude (Z) is ignored; measurements are planar.
