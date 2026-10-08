import geopandas as gpd
import pytest
from pyproj import Geod
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.services.measurements import compute_measurements

GEOD = Geod(ellps="WGS84")


def _gdf(geoms, crs="EPSG:4326"):
    return gpd.GeoDataFrame(geometry=geoms, crs=crs)


def _by_index(result):
    return {m["index"]: m for m in result["measurements"]}


def test_polygon_area_matches_geodesic():
    poly = box(74.20, 18.23, 74.21, 18.24)
    m = compute_measurements(_gdf([poly]))["measurements"][0]
    reference = abs(GEOD.geometry_area_perimeter(poly)[0])
    assert m["status"] == "OK" and m["unit"] == "m²"
    assert m["value"] == pytest.approx(reference, rel=0.005)  # within 0.5%


def test_line_length_matches_geodesic():
    line = LineString([(74.20, 18.23), (74.22, 18.25)])
    m = compute_measurements(_gdf([line]))["measurements"][0]
    assert m["value"] == pytest.approx(GEOD.geometry_length(line), rel=0.005)


def test_polygon_with_hole_subtracts_hole():
    outer = [(74.20, 18.20), (74.30, 18.20), (74.30, 18.30), (74.20, 18.30)]
    hole = [(74.22, 18.22), (74.28, 18.22), (74.28, 18.28), (74.22, 18.28)]
    solid = compute_measurements(_gdf([Polygon(outer)]))["measurements"][0]["value"]
    holed = compute_measurements(_gdf([Polygon(outer, [hole])]))["measurements"][0]["value"]
    assert holed < solid


def test_multipolygon_sums_parts():
    a, b = box(74.20, 18.23, 74.21, 18.24), box(74.30, 18.23, 74.31, 18.24)
    single = compute_measurements(_gdf([a]))["measurements"][0]["value"]
    multi = compute_measurements(_gdf([MultiPolygon([a, b])]))["measurements"][0]["value"]
    assert multi == pytest.approx(2 * single, rel=0.01)


def test_point_is_not_applicable():
    m = compute_measurements(_gdf([Point(74.2, 18.2)]))["measurements"][0]
    assert m["status"] == "NOT_APPLICABLE" and m["value"] is None


def test_unsupported_and_null_geometries_dont_crash():
    gdf = _gdf([GeometryCollection([Point(74.2, 18.2)]), None, box(74.2, 18.2, 74.3, 18.3)])
    by = _by_index(compute_measurements(gdf))
    assert by[0]["status"] == "UNSUPPORTED"
    assert by[1]["status"] == "UNSUPPORTED"
    assert by[2]["status"] == "OK"


def test_missing_crs_marks_everything_unavailable():
    result = compute_measurements(_gdf([box(0, 0, 1, 1)], crs=None))
    assert result["measurement_crs"] is None
    assert result["measurements"][0]["status"] == "UNAVAILABLE"


def test_projected_source_is_measured_in_place():
    result = compute_measurements(_gdf([box(500000, 2000000, 500100, 2000100)], "EPSG:32643"))
    assert result["strategy"] == "source_projected"
    assert result["measurements"][0]["value"] == pytest.approx(10_000)
