import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FeatureRecord, FileRecord
from app.schemas import (
    FeatureItem,
    FeaturesResponse,
    FileInfo,
    MeasurementItem,
    MeasurementsResponse,
)
from app.services.measurements import compute_measurements
from app.services.parser import ParseError, crs_label, load_geodataframe, to_features

log = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".zip", ".kml"}
MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _get_file_or_404(db: Session, file_id: str) -> FileRecord:
    record = db.get(FileRecord, file_id)
    if record is None:
        raise HTTPException(404, "File not found")
    return record


def _require_completed(record: FileRecord) -> None:
    if record.status != "COMPLETED":
        raise HTTPException(409, f"File status is {record.status}; no data available")


def _mark_failed(db: Session, record: FileRecord, message: str) -> None:
    db.rollback()  # discard any half-written feature rows first
    record.status = "FAILED"
    record.error = message
    db.commit()


def _persist(db: Session, record: FileRecord, gdf, features, result) -> None:
    db.add_all(
        FeatureRecord(
            file_id=record.id,
            index=f["index"],
            geometry_type=f["geometry_type"],
            geometry=f["geometry"],
            crs=f["crs"],
            properties=f["properties"],
            measurement=m["measurement"],
            value=m["value"],
            unit=m["unit"],
            status=m["status"],
            reason=m["reason"],
        )
        for f, m in zip(features, result["measurements"], strict=True)
    )
    record.status = "COMPLETED"
    record.feature_count = len(features)
    record.crs = crs_label(gdf.crs)
    record.measurement_crs = result["measurement_crs"]
    record.measurement_strategy = result["strategy"]
    db.commit()


def _save_upload(file: UploadFile, dest: Path) -> None:
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "File too large (max 50 MB)")
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise


@router.post("/", status_code=201, response_model=FileInfo)
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    started = time.perf_counter()
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Only .zip (Shapefile) and .kml files are supported")

    file_id = uuid.uuid4().hex
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    _save_upload(file, dest)

    record = FileRecord(id=file_id, filename=filename, status="PROCESSING")
    db.add(record)
    db.commit()
    log.info("file=%s received name=%r", file_id, filename)

    try:
        gdf = load_geodataframe(dest, suffix)
        features = to_features(gdf)
        result = compute_measurements(gdf)
        _persist(db, record, gdf, features, result)
    except ParseError as exc:
        log.warning("file=%s rejected: %s", file_id, exc)
        _mark_failed(db, record, str(exc))
        raise HTTPException(422, detail={"id": file_id, "error": str(exc)})
    except Exception:
        log.exception("file=%s unexpected failure", file_id)
        message = "Unexpected error while processing file"
        _mark_failed(db, record, message)
        raise HTTPException(500, detail={"id": file_id, "error": message})
    finally:
        dest.unlink(missing_ok=True)  # data now lives in the database

    log.info(
        "file=%s completed features=%d measurement_crs=%s in %.2fs",
        file_id, record.feature_count, record.measurement_crs,
        time.perf_counter() - started,
    )
    return record


@router.get("/{file_id}/", response_model=FileInfo)
def get_file(file_id: str, db: Session = Depends(get_db)):
    return _get_file_or_404(db, file_id)


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(
    file_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    record = _get_file_or_404(db, file_id)
    _require_completed(record)
    rows = db.scalars(
        select(FeatureRecord)
        .where(FeatureRecord.file_id == file_id)
        .order_by(FeatureRecord.index)
        .offset(offset)
        .limit(limit)
    ).all()
    return MeasurementsResponse(
        id=file_id,
        measurement_crs=record.measurement_crs,
        strategy=record.measurement_strategy,
        total=record.feature_count,
        limit=limit,
        offset=offset,
        measurements=[MeasurementItem.model_validate(r) for r in rows],
    )


@router.get("/{file_id}/features/", response_model=FeaturesResponse)
def get_features(
    file_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    record = _get_file_or_404(db, file_id)
    _require_completed(record)
    rows = db.scalars(
        select(FeatureRecord)
        .where(FeatureRecord.file_id == file_id)
        .order_by(FeatureRecord.index)
        .offset(offset)
        .limit(limit)
    ).all()
    return FeaturesResponse(
        id=file_id,
        total=record.feature_count,
        limit=limit,
        offset=offset,
        features=[FeatureItem.model_validate(r) for r in rows],
    )
