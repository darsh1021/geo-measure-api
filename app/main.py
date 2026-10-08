from fastapi import FastAPI
from app.api import files

app = FastAPI(
    title="GeoMeasure API",
    description="Upload geospatial files and compute measurements (area, length, centroid).",
    version="0.1.0",
)

app.include_router(files.router, prefix="/files", tags=["files"])


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
