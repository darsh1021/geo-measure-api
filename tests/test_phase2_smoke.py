"""Phase 2 smoke tests — run with: .venv\\Scripts\\pytest tests/test_phase2_smoke.py -v"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLE_KML = Path(__file__).parent / "sample.kml"


def test_upload_kml_happy_path():
    with SAMPLE_KML.open("rb") as f:
        r = client.post(
            "/api/files/",
            files={"file": ("sample.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert r.status_code == 201
    body = r.json()
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    assert body["measurement_crs"] == "EPSG:32643"  # UTM zone 43N for India
    assert body["status"] == "COMPLETED"


def test_upload_wrong_extension():
    r = client.post(
        "/api/files/",
        files={"file": ("data.geojson", b"{}", "application/json")},
    )
    assert r.status_code == 415


def test_upload_bad_zip():
    r = client.post(
        "/api/files/",
        files={"file": ("notreal.zip", b"this is not a zip", "application/zip")},
    )
    assert r.status_code == 422
    error = r.json()["error"]
    assert "valid zip" in error["message"]
