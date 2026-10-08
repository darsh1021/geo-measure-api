from fastapi import APIRouter

router = APIRouter()

# TODO (Phase 1): POST /files/upload  — accept GeoJSON / Shapefile / GeoPackage
# TODO (Phase 2): GET  /files/{file_id} — return parsed layer summary
# TODO (Phase 3): GET  /files/{file_id}/measurements — return area, length, centroid
