# GeoMeasure API

A REST API for uploading geospatial files (GeoJSON, Shapefile, GeoPackage) and computing geometric measurements — area, length, and centroid — via FastAPI.

---

## Quick Start

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Interactive docs available at `http://localhost:8000/docs`.

---

## Project Structure

```
geo-measure-api/
├── app/
│   ├── main.py              # FastAPI app and router registration
│   ├── api/
│   │   └── files.py         # Upload and query endpoints
│   ├── services/
│   │   ├── parser.py        # Geospatial file parsing (GeoPandas + pyogrio)
│   │   ├── crs.py           # CRS detection and reprojection (pyproj)
│   │   └── measurements.py  # Area, length, centroid computation (Shapely)
│   ├── models.py            # SQLAlchemy ORM models (SQLite)
│   └── schemas.py           # Pydantic request/response models
├── tests/
├── data/uploads/            # Uploaded files (git-ignored)
├── requirements.txt
└── README.md
```

---

## Design Decisions

**FastAPI over Django**
The API surface is small and focused. FastAPI provides automatic request validation via Pydantic, auto-generated OpenAPI docs, and async support without the overhead of Django's ORM and middleware stack.

**GeoPandas + pyogrio over Fiona**
`pyogrio` is a modern GDAL/OGR binding that is significantly faster than the older `fiona`-based I/O, has simpler installation (no separate GDAL wheel needed on most platforms), and is now the recommended engine for `geopandas.read_file()`.

**Synchronous processing at upload time**
File parsing and measurement computation happen synchronously in the request handler. This keeps the architecture simple for a development/demo context. In production, a task queue (e.g. Celery + Redis) would handle long-running geospatial operations in the background, returning a job ID for polling.

**SQLite via SQLAlchemy**
SQLite requires zero infrastructure to run locally and is sufficient for storing file metadata and cached measurement results. The SQLAlchemy abstraction makes swapping to PostgreSQL (or PostGIS) straightforward when scaling up.

---

## Running Tests

```bash
pytest
```

---

## Roadmap

| Phase | Goal |
|-------|------|
| 1 | File upload endpoint + parser service |
| 2 | Layer summary endpoint (feature count, CRS, geometry type) |
| 3 | Measurements endpoint (area, length, centroid) |
| 4 | CRS reprojection support |
| 5 | SQLite persistence for uploads and results |
