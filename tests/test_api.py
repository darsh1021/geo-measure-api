import shutil

import geopandas as gpd
import pytest
from shapely.geometry import box

SAMPLE_KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Plot A</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
74.20,18.23,0 74.21,18.23,0 74.21,18.24,0 74.20,18.24,0 74.20,18.23,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Road 1</name><LineString><coordinates>74.20,18.23 74.22,18.25</coordinates></LineString></Placemark>
<Placemark><name>Well</name><Point><coordinates>74.205,18.235</coordinates></Point></Placemark>
</Document></kml>"""


def _upload_kml(client):
    return client.post("/api/files/", files={"file": ("survey.kml", SAMPLE_KML)})


def test_upload_and_file_info(client):
    r = _upload_kml(client)
    assert r.status_code == 201
    file_id = r.json()["id"]

    info = client.get(f"/api/files/{file_id}/").json()
    assert info["filename"] == "survey.kml"
    assert info["feature_count"] == 3
    assert info["crs"] == "EPSG:4326"
    assert info["status"] == "COMPLETED"


def test_measurements_endpoint(client):
    file_id = _upload_kml(client).json()["id"]
    body = client.get(f"/api/files/{file_id}/measurements/").json()

    assert body["measurement_crs"] == "EPSG:32643"
    by_type = {m["geometry_type"]: m for m in body["measurements"]}
    assert 1_100_000 < by_type["Polygon"]["value"] < 1_250_000
    assert by_type["Polygon"]["unit"] == "m²"
    assert by_type["LineString"]["measurement"] == "length"
    assert by_type["Point"]["status"] == "NOT_APPLICABLE"


def test_measurements_pagination(client):
    file_id = _upload_kml(client).json()["id"]
    body = client.get(f"/api/files/{file_id}/measurements/?limit=2&offset=2").json()
    assert body["total"] == 3
    assert len(body["measurements"]) == 1


def test_features_endpoint_returns_geometry_and_properties(client):
    file_id = _upload_kml(client).json()["id"]
    body = client.get(f"/api/files/{file_id}/features/").json()
    first = body["features"][0]
    assert first["geometry"]["type"] == "Polygon"
    assert first["properties"]["Name"] == "Plot A"
    assert first["crs"] == "EPSG:4326"


def test_shapefile_zip_upload(client, tmp_path):
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    gdf = gpd.GeoDataFrame(
        {"owner": ["Ravi"]}, geometry=[box(74.2, 18.23, 74.21, 18.24)], crs="EPSG:4326"
    )
    gdf.to_file(shp_dir / "plots.shp")
    zip_path = shutil.make_archive(str(tmp_path / "plots"), "zip", shp_dir)

    with open(zip_path, "rb") as fh:
        r = client.post("/api/files/", files={"file": ("plots.zip", fh)})
    assert r.status_code == 201
    assert r.json()["feature_count"] == 1


def test_unknown_id_is_404(client):
    assert client.get("/api/files/doesnotexist/").status_code == 404
    assert client.get("/api/files/doesnotexist/measurements/").status_code == 404


def test_wrong_extension_is_415(client):
    r = client.post("/api/files/", files={"file": ("notes.txt", b"hello")})
    assert r.status_code == 415


def test_corrupt_zip_is_422_and_recorded_as_failed(client):
    r = client.post("/api/files/", files={"file": ("bad.zip", b"not a zip")})
    assert r.status_code == 422
    file_id = r.json()["error"]["file_id"]

    info = client.get(f"/api/files/{file_id}/").json()
    assert info["status"] == "FAILED"
    assert info["error"]
    assert client.get(f"/api/files/{file_id}/measurements/").status_code == 409
