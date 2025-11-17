from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from .database import Base


class Bulletin(Base):
    __tablename__ = "bulletins"

    id = Column(Integer, primary_key=True, index=True)
    date_bulletin = Column(Date, unique=True, nullable=False, index=True)
    source_pdf = Column(String, nullable=True)
    map1_image = Column(String, nullable=True)
    map2_image = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    station_reports = relationship(
        "StationReport",
        back_populates="bulletin",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    normalized_name = Column(String, unique=True, nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    x_rel = Column(Float, nullable=True)
    y_rel = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    reports = relationship("StationReport", back_populates="station")


class StationReport(Base):
    __tablename__ = "station_reports"

    id = Column(Integer, primary_key=True, index=True)
    bulletin_id = Column(Integer, ForeignKey("bulletins.id"), nullable=False)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)

    Tmin_obs = Column(Integer, nullable=True)
    Tmax_obs = Column(Integer, nullable=True)
    temps_obs = Column(String, nullable=True)

    Tmin_prev = Column(Integer, nullable=True)
    Tmax_prev = Column(Integer, nullable=True)
    temps_prev = Column(String, nullable=True)

    interpretation_moore = Column(String, nullable=True)
    interpretation_dioula = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    bulletin = relationship("Bulletin", back_populates="station_reports")
    station = relationship(
        "Station",
        back_populates="reports",
        lazy="joined",
    )
