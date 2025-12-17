from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

from app.core.database import init_db

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database
    await init_db()
    print("Database initialized successfully!")
    yield
    # Shutdown: Clean up resources if needed
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Traffic Anomaly Detection API",
    description="Backend API for traffic monitoring and anomaly detection system",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Traffic Anomaly Detection API",
        "version": "1.0.0",
        "status": "running"
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Import and include routers here (once created)
# from app.routers import users, cameras, anomalies, normal_features
# app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
# app.include_router(cameras.router, prefix="/api/v1/cameras", tags=["Cameras"])
# app.include_router(anomalies.router, prefix="/api/v1/anomalies", tags=["Anomalies"])
# app.include_router(normal_features.router, prefix="/api/v1/normal-features", tags=["Normal Features"])
