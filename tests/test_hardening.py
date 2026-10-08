import shutil
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon, box

from app.services.measurements import compute_measurements
from app.services.parser import ParseError, _safe_extract, load_geodataframe

POINT_KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Well</name><Point><coordinates>74.205,18.235</coordinates></Point></Placemark>
</Document></kml>"""


def _upload_kml(client, content=POINT_KML, name="a.kml"):
    return client.post("/api/files/", files={"file": (name, content)})


def _zip_shapefiles(tmp_path, **layers):
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    for name, gdf in layers.items():
        gdf.to_file(shp_dir / f"{name}.shp")
    return shutil.make_archive(str(tmp_path / "bundle"), "zip", shp_dir)


def _upload_zip(client, zip_path):
    with open(zip_path, "rb") as fh:
        return client.post("/api/files/", files={"file": ("bundle.zip", fh)})


# ---------- security ----------

@pytest.mark.parametrize("member", ["../evil.txt", "nested/../../evil.txt"])
def test_zip_slip_is_rejected(tmp_path, member):
    zp = tmp_path / "evil.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr(member, "pwned")
    dest = tmp_path / "out"
    dest.mkdir()

    with pytest.raises(ParseError, match="unsafe"):
        _safe_extract(zp, dest)
    assert not (tmp_path / "evil.txt").exists()


def test_zip_bomb_guard(tmp_path, monkeypatch):
    zp = tmp_path / "big.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.bin", b"0" * 10_000)
    monkeypatch.setattr("app.services.parser.MAX_UNCOMPRESSED_BYTES", 1_000)
    dest = tmp_path / "out"
    dest.mkdir()

    with pytest.raises(ParseError, match="too large"):
        _safe_extract(zp, dest)
    assert list(dest.iterdir()) == []


# ---------- data edge cases ----------

def test_shapefile_without_prj_marks_measurements_unavailable(client, tmp_path):
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[box(74.2, 18.2, 74.3, 18.3)], crs=None)
    r = _upload_zip(client, _zip_shapefiles(tmp_path, plots=gdf))
    assert r.status_code == 201
    file_id = r.json()["id"]

    assert client.get(f"/api/files/{file_id}/").json()["crs"] is None
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    assert body["measurement_crs"] is None
    assert body["measurements"][0]["status"] == "UNAVAILABLE"
    assert "CRS" in body["measurements"][0]["reason"]


def test_multiple_shapefiles_in_one_zip_are_merged(client, tmp_path):
    polys = gpd.GeoDataFrame({"name": ["p"]}, geometry=[box(74.2, 18.2, 74.3, 18.3)], crs="EPSG:4326")
    lines = gpd.GeoDataFrame(
        {"road": ["r"]}, geometry=[LineString([(74.2, 18.2), (74.3, 18.3)])], crs="EPSG:4326"
    )
    r = _upload_zip(client, _zip_shapefiles(tmp_path, polys=polys, lines=lines))
    assert r.status_code == 201
    file_id = r.json()["id"]
    assert r.json()["feature_count"] == 2

    body = client.get(f"/api/files/{file_id}/measurements/").json()
    assert {m["geometry_type"] for m in body["measurements"]} == {"Polygon", "LineString"}
    assert all(m["status"] == "OK" for m in body["measurements"])


def test_kml_altitude_is_dropped(tmp_path):
    kml = POINT_KML.replace(b"74.205,18.235", b"74.205,18.235,550")
    path = tmp_path / "z.kml"
    path.write_bytes(kml)
    gdf = load_geodataframe(path, ".kml")
    assert not gdf.geometry.has_z.any()


def test_kml_folders_are_all_read(tmp_path):
    kml = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Folder><name>Plots</name><Placemark><name>P1</name><Point><coordinates>74.2,18.2</coordinates></Point></Placemark></Folder>
<Folder><name>Wells</name><Placemark><name>W1</name><Point><coordinates>74.3,18.3</coordinates></Point></Placemark></Folder>
</Document></kml>"""
    path = tmp_path / "folders.kml"
    path.write_bytes(kml)
    gdf = load_geodataframe(path, ".kml")
    assert len(gdf) == 2
    assert set(gdf["layer"]) == {"Plots", "Wells"}


def test_invalid_polygon_is_measured_but_flagged():
    bowtie = Polygon([(74.20, 18.23), (74.21, 18.24), (74.21, 18.23), (74.20, 18.24)])
    gdf = gpd.GeoDataFrame(geometry=[bowtie], crs="EPSG:4326")
    m = compute_measurements(gdf)["measurements"][0]
    assert m["status"] == "OK"
    assert "Invalid" in m["reason"]


# ---------- upload failures ----------

@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not xml at all",
        b"<kml><Document>",
        b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>',
    ],
)
def test_bad_or_empty_kml_is_422(client, content):
    r = _upload_kml(client, content)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "UNPROCESSABLE_FILE"


def test_oversize_upload_is_413_and_leaves_nothing_behind(client, upload_dir, monkeypatch):
    monkeypatch.setattr("app.api.files.MAX_BYTES", 10)
    r = client.post("/api/files/", files={"file": ("big.kml", b"x" * 100)})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert list(upload_dir.iterdir()) == []


def test_unexpected_error_is_500_and_hides_internals(client, monkeypatch):
    def boom(gdf):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("app.api.files.compute_measurements", boom)
    r = _upload_kml(client)
    assert r.status_code == 500
    assert "secret" not in r.text
    file_id = r.json()["error"]["file_id"]
    assert client.get(f"/api/files/{file_id}/").json()["status"] == "FAILED"


def test_upload_dir_is_empty_after_success_and_failure(client, upload_dir):
    assert _upload_kml(client).status_code == 201
    assert client.post("/api/files/", files={"file": ("bad.zip", b"nope")}).status_code == 422
    assert list(upload_dir.iterdir()) == []


# ---------- error shape ----------

def test_validation_error_uses_common_shape(client):
    r = client.post("/api/files/")  # no file field
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR" and err["details"]


def test_unknown_route_uses_common_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
