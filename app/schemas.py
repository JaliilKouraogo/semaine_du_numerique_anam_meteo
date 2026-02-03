from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class StationBase(BaseModel):
    name: str = Field(..., min_length=1, alias="nom")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    x_rel: Optional[float] = Field(None, ge=0, le=1)
    y_rel: Optional[float] = Field(None, ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True)


class StationCreate(StationBase):
    pass


class StationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, alias="nom")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    x_rel: Optional[float] = Field(None, ge=0, le=1)
    y_rel: Optional[float] = Field(None, ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True)


class StationOut(StationBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    Tmin_obs: Optional[int] = None
    Tmax_obs: Optional[int] = None
    temps_obs: Optional[str] = None
    Tmin_prev: Optional[int] = None
    Tmax_prev: Optional[int] = None
    temps_prev: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class StationReportBase(BaseModel):
    Tmin_obs: Optional[int] = Field(None, ge=-50, le=70)
    Tmax_obs: Optional[int] = Field(None, ge=-50, le=70)
    temps_obs: Optional[str] = None
    Tmin_prev: Optional[int] = Field(None, ge=-50, le=70)
    Tmax_prev: Optional[int] = Field(None, ge=-50, le=70)
    temps_prev: Optional[str] = None
    interpretation_moore: Optional[str] = None
    interpretation_dioula: Optional[str] = None


class StationReportPayload(StationReportBase, StationBase):
    pass


class StationReportOut(StationReportBase):
    id: int
    bulletin_id: int
    date_bulletin: Optional[date] = None
    station: StationOut
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BulletinBase(BaseModel):
    date_bulletin: date
    source_pdf: Optional[str] = None
    map1_image: Optional[str] = None
    map2_image: Optional[str] = None
    notes: Optional[str] = None


class BulletinImport(BulletinBase):
    stations: List[StationReportPayload]
    replace_existing: bool = False


class BulletinSummary(BulletinBase):
    id: int
    station_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BulletinDetail(BulletinSummary):
    stations: List[StationReportOut]


class DeleteResponse(BaseModel):
    deleted: bool
    detail: str
