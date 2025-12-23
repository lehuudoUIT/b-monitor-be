from pydantic import BaseModel, Field, ConfigDict, EmailStr
from datetime import datetime
from typing import Optional, List
from enum import Enum


class CameraType(str, Enum):
    local = "local"
    youtube = "youtube"


class AnomalyLevel(str, Enum):
    violations = "violations"
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


# User Schemas
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Auth Schemas
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


# Camera Schemas
class CameraBase(BaseModel):
    name: str = Field(..., max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    thumbnail: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field("inactive", max_length=20)
    url: str = Field(..., max_length=500)
    type: CameraType = CameraType.local


class CameraCreate(CameraBase):
    user_id: int


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    thumbnail: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, max_length=20)
    url: Optional[str] = Field(None, max_length=500)
    type: Optional[CameraType] = None


class CameraResponse(CameraBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class CameraListResponse(BaseModel):
    items: List[CameraResponse] # This tells FastAPI: "Convert these DB objects using CameraResponse"
    total: int
    skip: int
    limit: int

# NormalFeature Schemas
class NormalFeatureBase(BaseModel):
    url: str = Field(..., max_length=500)


class NormalFeatureCreate(NormalFeatureBase):
    cam_id: int


class NormalFeatureUpdate(BaseModel):
    url: Optional[str] = Field(None, max_length=500)


class NormalFeatureResponse(NormalFeatureBase):
    id: int
    cam_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Anomaly Schemas
class AnomalyBase(BaseModel):
    type: str = Field(..., max_length=100)
    description: Optional[str] = None
    level: AnomalyLevel = AnomalyLevel.medium
    time: Optional[datetime] = None
    anomaly_score: float = 0.0
    bounding_box: Optional[str] = ""


class AnomalyCreate(AnomalyBase):
    cam_id: int


class AnomalyUpdate(BaseModel):
    type: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    level: Optional[AnomalyLevel] = None
    time: Optional[datetime] = None
    anomaly_score: Optional[float] = None
    bounding_box: Optional[str] = None


class AnomalyResponse(AnomalyBase):
    id: int
    cam_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Extended Response Schemas (with relationships)
class CameraWithRelations(CameraResponse):
    anomalies: List[AnomalyResponse] = []
    normal_features: List[NormalFeatureResponse] = []
    
    model_config = ConfigDict(from_attributes=True)


class UserWithCameras(UserResponse):
    cameras: List[CameraResponse] = []
    
    model_config = ConfigDict(from_attributes=True)
