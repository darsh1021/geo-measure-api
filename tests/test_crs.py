import geopandas as gpd
import pytest
from shapely.geometry import box

from app.services.crs import CrsError, select_measurement_crs, to_measurement_crs


def _gdf(geom, crs):
    return gpd.GeoDataFrame(geometry=[geom], crs=crs)


def test_geographic_picks_utm_north():
    gdf = _gdf(box(74.20, 18.23, 74.21, 18.24), "EPSG:4326")
    assert select_measurement_crs(gdf).label == "EPSG:32643"


def test_southern_hemisphere_picks_327xx():
    gdf = _gdf(box(151.2, -33.9, 151.3, -33.8), "EPSG:4326")
    assert select_measurement_crs(gdf).label == "EPSG:32756"


def test_metric_projected_is_kept():
    gdf = _gdf(box(500000, 2000000, 500100, 2000100), "EPSG:32643")
    result = select_measurement_crs(gdf)
    assert result.strategy == "source_projected"


def test_web_mercator_is_reprojected():
    gdf = _gdf(box(8260000, 2100000, 8261000, 2101000), "EPSG:3857")
    assert select_measurement_crs(gdf).strategy == "utm"


def test_missing_crs_raises():
    with pytest.raises(CrsError):
        select_measurement_crs(_gdf(box(0, 0, 1, 1), None))


def test_coordinates_that_dont_match_declared_crs_raise():
    with pytest.raises(CrsError):
        select_measurement_crs(_gdf(box(500000, 2000000, 500100, 2000100), "EPSG:4326"))


@pytest.mark.filterwarnings("ignore")
def test_projected_copy_is_in_metres():
    gdf = _gdf(box(74.20, 18.23, 74.21, 18.24), "EPSG:4326")
    projected, target = to_measurement_crs(gdf)
    assert 1_100_000 < projected.geometry.area.iloc[0] < 1_250_000  # ~1.17 km²
    assert gdf.geometry.area.iloc[0] < 0.001  # raw degrees: meaningless
