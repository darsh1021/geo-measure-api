from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    status: int
    code: str
    message: str
    file_id: str | None = None
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class FileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int
    crs: str | None
    measurement_crs: str | None
    status: str
    error: str | None


class MeasurementItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str | None
    measurement: str | None
    value: float | None
    unit: str | None
    status: str
    reason: str | None
    properties: dict[str, Any]


class MeasurementsResponse(BaseModel):
    id: str
    measurement_crs: str | None
    strategy: str | None
    total: int
    limit: int
    offset: int
    measurements: list[MeasurementItem]


class FeatureItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str | None
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any]


class FeaturesResponse(BaseModel):
    id: str
    total: int
    limit: int
    offset: int
    features: list[FeatureItem]
