import math
from dataclasses import dataclass

import geopandas as gpd
from pyproj import CRS

from app.services.parser import crs_label


class CrsError(Exception):
    """Raised when a usable measurement CRS can't be determined."""


@dataclass(frozen=True)
class MeasurementCRS:
    crs: CRS
    label: str
    strategy: str  # "source_projected" | "utm"


# Web Mercator variants: projected and metric, but wrong for area measurement
_WEB_MERCATOR_EPSG = {3857, 900913, 102100, 102113}


def _is_web_mercator(crs: CRS) -> bool:
    if crs.to_epsg() in _WEB_MERCATOR_EPSG:
        return True
    op = crs.coordinate_operation
    return bool(op and "popular visualisation" in op.method_name.lower())


def _is_metric_projected(crs: CRS) -> bool:
    return (
        crs.is_projected
        and not _is_web_mercator(crs)
        and all(a.unit_name in ("metre", "meter") for a in crs.axis_info)
    )


def _utm_epsg(lon: float, lat: float) -> int:
    if lat > 84:
        return 32661  # UPS North (UTM isn't defined this far north)
    if lat < -80:
        return 32761  # UPS South
    zone = min(int((lon + 180) // 6) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone  # 326xx north, 327xx south


def select_measurement_crs(gdf: gpd.GeoDataFrame) -> MeasurementCRS:
    src = gdf.crs
    if src is None:
        raise CrsError("File has no CRS defined; measurements are unavailable")

    if _is_metric_projected(src):
        return MeasurementCRS(src, crs_label(src), "source_projected")

    if not (src.is_geographic or src.is_projected):
        raise CrsError(f"Unsupported CRS type: {src.name}")

    # Need lon/lat to choose a UTM zone. Bounds midpoint avoids the
    # "centroid in a geographic CRS" warning and ignores null geometries.
    minx, miny, maxx, maxy = gdf.geometry.to_crs(4326).total_bounds
    bounds = (minx, miny, maxx, maxy)
    if not all(math.isfinite(v) for v in bounds):
        raise CrsError("File has no valid geometries to measure")
    if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
        raise CrsError(
            "Coordinates are outside valid longitude/latitude range; "
            "the file's declared CRS doesn't match its data"
        )

    epsg = _utm_epsg((minx + maxx) / 2, (miny + maxy) / 2)
    return MeasurementCRS(CRS.from_epsg(epsg), f"EPSG:{epsg}", "utm")


def to_measurement_crs(
    gdf: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, MeasurementCRS]:
    target = select_measurement_crs(gdf)
    return gdf.to_crs(target.crs), target
