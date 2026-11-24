"""FastAPI application entrypoint, startup schema seeding, and router mounting."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.overview import router as overview_router
from app.api.recommendations import router as recommendations_router
from app.api.resources import router as resources_router
from app.api.simulate import router as simulate_router
from app.api.traffic import router as traffic_router
from app.core import database
from app.services.repository import seed_database


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize database tables and idempotently seed telemetry data on startup."""
    database.create_tables(database.engine)
    with database.SessionLocal() as session:
        seed_database(session)
    yield


app = FastAPI(
    title="AWSense API",
    description="Backend API for AWSense Cloud Management Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(overview_router)
app.include_router(resources_router)
app.include_router(alerts_router)
app.include_router(traffic_router)
app.include_router(recommendations_router)
app.include_router(simulate_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "message": "Welcome to AWSense API"}


@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
