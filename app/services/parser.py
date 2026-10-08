import json
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely


class ParseError(Exception):
    """Raised when an uploaded file can't be read as valid geospatial data."""


MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # zip-bomb guard


# ---------- zip handling ----------

def _safe_extract(zip_path: Path, dest: Path) -> None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.infolist()
            if sum(m.file_size for m in members) > MAX_UNCOMPRESSED_BYTES:
                raise ParseError("Zip contents too large when uncompressed")

            dest_root = dest.resolve()
            for m in members:  # zip-slip guard: no member may escape dest
                target = (dest / m.filename).resolve()
                if not target.is_relative_to(dest_root):
                    raise ParseError("Zip contains an unsafe file path")

            zf.extractall(dest)
    except zipfile.BadZipFile:
        raise ParseError("File is not a valid zip archive")


# ---------- readers ----------

def _read_shapefile_zip(zip_path: Path) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _safe_extract(zip_path, tmp_dir)

        shp_files = [
            p for p in tmp_dir.rglob("*.shp")
            if "__MACOSX" not in p.parts and not p.name.startswith("._")
        ]
        if not shp_files:
            raise ParseError("No .shp file found inside the zip")

        frames = []
        for shp in shp_files:
            try:
                frames.append(gpd.read_file(shp, engine="pyogrio"))
            except Exception as exc:
                raise ParseError(f"Could not read {shp.name}: {exc}")
        return _combine(frames)  # read fully into memory before tmp dir is deleted


def _read_kml(kml_path: Path) -> gpd.GeoDataFrame:
    try:
        layers = pyogrio.list_layers(kml_path)  # KML folders show up as layers
    except Exception as exc:
        raise ParseError(f"Could not read KML: {exc}")

    frames = []
    for name, _geom_type in layers:
        try:
            gdf = gpd.read_file(kml_path, layer=name, engine="pyogrio")
        except Exception as exc:
            raise ParseError(f"Could not read KML layer '{name}': {exc}")
        if len(gdf):
            gdf["layer"] = name  # remember which folder it came from
            frames.append(gdf)
    return _combine(frames)


def _combine(frames: list[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    if not frames:
        raise ParseError("File contains no features")
    base_crs = frames[0].crs
    if base_crs is not None:
        frames = [f.to_crs(base_crs) if f.crs is not None else f for f in frames]
    combined = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=base_crs)


# ---------- public API ----------

def load_geodataframe(path: Path, suffix: str) -> gpd.GeoDataFrame:
    if suffix == ".zip":
        gdf = _read_shapefile_zip(path)
    elif suffix == ".kml":
        gdf = _read_kml(path)
    else:
        raise ParseError(f"Unsupported file type: {suffix}")

    if gdf.empty:
        raise ParseError("File contains no features")

    gdf["geometry"] = gdf.geometry.force_2d()  # KML often carries Z values
    return gdf.reset_index(drop=True)


def crs_label(crs) -> str | None:
    if crs is None:
        return None
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else crs.name


def to_features(gdf: gpd.GeoDataFrame) -> list[dict]:
    label = crs_label(gdf.crs)

    # pandas handles NaN -> null and Timestamps -> ISO strings for us
    props = json.loads(
        gdf.drop(columns="geometry").to_json(orient="records", date_format="iso")
    )

    features = []
    for i, geom in enumerate(gdf.geometry):
        missing = geom is None
        features.append({
            "index": i,
            "geometry_type": None if missing else geom.geom_type,
            "geometry": None if missing else json.loads(shapely.to_geojson(geom)),
            "crs": label,
            "properties": props[i],
        })
    return features
