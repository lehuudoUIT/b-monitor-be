from pydantic import BaseModel, Field, ConfigDict, EmailStr, computed_field
from datetime import datetime
from typing import Optional, List
from enum import Enum
from app.core.constant import MSCOCO_CLASS_NAME


class CameraType(str, Enum):
    local = "local"
    youtube = "youtube"


class AnomalyLevel(str, Enum):
    violations = "violations"
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


# Stream Control Schemas
class StopStreamRequest(BaseModel):
    session_id: str = Field(..., description="Session ID of the stream to stop")


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
    fps: Optional[int] = None
    resolution: Optional[str] = None


class CameraCreate(CameraBase):
    user_id: Optional[int] = None


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=255)
    thumbnail: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, max_length=20)
    url: Optional[str] = Field(None, max_length=500)
    type: Optional[CameraType] = None
    fps: Optional[int] = None
    resolution: Optional[str] = None


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
    frame_id: int = 0
    class_id: int = 0


class AnomalyCreate(AnomalyBase):
    cam_id: int


class AnomalyUpdate(BaseModel):
    type: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    level: Optional[AnomalyLevel] = None
    time: Optional[datetime] = None
    anomaly_score: Optional[float] = None
    bounding_box: Optional[str] = None
    frame_id: Optional[int] = None
    class_id: Optional[int] = None


class AnomalyResponse(AnomalyBase):
    id: int
    cam_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class AnomalyListResponse(BaseModel):
    items: List[AnomalyResponse] # This tells FastAPI: "Convert these DB objects using AnomalyResponse"
    total: int
    skip: int
    limit: int
    order: str
# By frame response schema
class AnomalyByFrameResponse(AnomalyBase):
    id: int
    cam_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    @computed_field
    def class_name(self) -> str:
        # Logic ánh xạ: lấy từ dict, nếu không có trả về "Unknown"
        return MSCOCO_CLASS_NAME.get(self.class_id, "Unknown")
    
class AnomalyByFrameListResponse(BaseModel):
    items: List[AnomalyByFrameResponse] # This tells FastAPI: "Convert these DB objects using AnomalyByFrameResponse"
    total: int

# By Camera response schema
class AnomalyByCameraResponse(AnomalyBase):
    id: int
    cam_id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    @computed_field
    def class_name(self) -> str:
        # Logic ánh xạ: lấy từ dict, nếu không có trả về "Unknown"
        return MSCOCO_CLASS_NAME.get(self.class_id, "Unknown")
    
class AnomalyByCameraListResponse(BaseModel):
    items: List[AnomalyByCameraResponse] # This tells FastAPI: "Convert these DB objects using AnomalyByCameraResponse"
    total: int

# Extended Response Schemas (with relationships)
class CameraWithRelations(CameraResponse):
    anomalies: List[AnomalyResponse] = []
    normal_features: List[NormalFeatureResponse] = []
    
    model_config = ConfigDict(from_attributes=True)


class UserWithCameras(UserResponse):
    cameras: List[CameraResponse] = []
    
    model_config = ConfigDict(from_attributes=True)


# Video Processing Schemas
class VideoProcessRequest(BaseModel):
    camera_id: int = Field(..., description="ID of the camera (must be type='local')")
    batch_size: int = Field(7, ge=3, le=30, description="Number of frames per batch")
    sliding_window: int = Field(1, ge=1, le=10, description="Sliding window step size")


class VideoProcessResponse(BaseModel):
    success: bool
    message: str
    camera_id: int
    video_info: dict
    total_frames: int
    total_batches: int
    anomalies_detected: int
    anomalies: List[AnomalyResponse]
