from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now():
    return datetime.now(timezone.utc)


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))  # PROCESSING | COMPLETED | FAILED
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    measurement_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    features: Mapped[list["FeatureRecord"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class FeatureRecord(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), index=True)
    index: Mapped[int] = mapped_column("feature_index", Integer)
    geometry_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    crs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)

    # measurement result for this feature
    measurement: Mapped[str | None] = mapped_column(String(16), nullable=True)  # area | length
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # OK | NOT_APPLICABLE | UNSUPPORTED | UNAVAILABLE
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped[FileRecord] = relationship(back_populates="features")
