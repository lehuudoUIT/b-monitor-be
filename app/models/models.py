from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class CameraType(str, enum.Enum):
    local = "local"
    youtube = "youtube"


class AnomalyLevel(str, enum.Enum):
    violations = "violations"
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)  # Hashed password
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    cameras = relationship("Camera", back_populates="user", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(255))
    thumbnail = Column(String(255))  # Path to thumbnail image
    status = Column(String(20), default="inactive")  # active, inactive, etc.
    url = Column(String(500), nullable=False)
    type = Column(SQLEnum(CameraType), nullable=False, default=CameraType.local)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="cameras")
    normal_features = relationship("NormalFeature", back_populates="camera", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="camera", cascade="all, delete-orphan")


class NormalFeature(Base):
    __tablename__ = "normal_features"
    
    id = Column(Integer, primary_key=True, index=True)
    cam_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    url = Column(String(500), nullable=False)  # Path to feature file
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    camera = relationship("Camera", back_populates="normal_features")


class Anomaly(Base):
    __tablename__ = "anomalies"
    
    id = Column(Integer, primary_key=True, index=True)
    time = Column(DateTime, nullable=False, default=datetime.utcnow)
    type = Column(String(100), nullable=False)  # Type of anomaly (e.g., "traffic jam", "accident")
    description = Column(Text)
    level = Column(SQLEnum(AnomalyLevel), nullable=False, default=AnomalyLevel.medium)
    cam_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    camera = relationship("Camera", back_populates="anomalies")
