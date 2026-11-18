from pydantic import BaseModel, conlist, Field
from typing import Dict, Any, Optional
from datetime import datetime


class UserRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserPatchRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class MetricLimit(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class DeviceRegisterRequest(BaseModel):
    device_id: str
    name: str
    status: bool
    thresholds: dict[str, MetricLimit]


class DevicePatchRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[bool] = None
    thresholds: Optional[dict[str, MetricLimit]] = None


class MeasurementsPostRequest(BaseModel):   
    timestamp: Optional[datetime] = None
    metrics: Dict[str, Any]
