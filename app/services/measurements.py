import geopandas as gpd

from app.services.crs import CrsError, to_measurement_crs

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
NO_MEASURE_TYPES = {"Point", "MultiPoint"}


def _record(index, geom_type, *, status, kind=None, value=None, unit=None, reason=None):
    return {
        "index": index,
        "geometry_type": geom_type,
        "measurement": kind,   # "area" | "length" | None
        "value": value,
        "unit": unit,
        "status": status,      # OK | NOT_APPLICABLE | UNSUPPORTED | UNAVAILABLE
        "reason": reason,
    }


def compute_measurements(gdf: gpd.GeoDataFrame) -> dict:
    source_types = [None if g is None else g.geom_type for g in gdf.geometry]

    try:
        projected, target = to_measurement_crs(gdf)
    except CrsError as exc:
        return {
            "measurement_crs": None,
            "strategy": None,
            "measurements": [
                _record(i, t, status="UNAVAILABLE", reason=str(exc))
                for i, t in enumerate(source_types)
            ],
        }

    records = []
    for i, geom in enumerate(projected.geometry):
        gtype = source_types[i]

        if geom is None:
            records.append(_record(i, gtype, status="UNSUPPORTED", reason="Null geometry"))
        elif geom.is_empty:
            records.append(_record(i, gtype, status="UNSUPPORTED", reason="Empty geometry"))
        elif gtype in AREA_TYPES:
            records.append(_record(
                i, gtype, status="OK", kind="area",
                value=round(geom.area, 4), unit="m²",
                reason=None if geom.is_valid else "Invalid geometry (e.g. self-intersection); area may be unreliable",
            ))
        elif gtype in LENGTH_TYPES:
            records.append(_record(
                i, gtype, status="OK", kind="length",
                value=round(geom.length, 4), unit="m",
            ))
        elif gtype in NO_MEASURE_TYPES:
            records.append(_record(i, gtype, status="NOT_APPLICABLE"))
        else:
            records.append(_record(
                i, gtype, status="UNSUPPORTED",
                reason=f"Measurement not supported for {gtype}",
            ))

    return {
        "measurement_crs": target.label,
        "strategy": target.strategy,
        "measurements": records,
    }
