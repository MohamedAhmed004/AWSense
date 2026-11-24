
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.overview import router as overview_router
from app.api.recommendations import router as recommendations_router
from app.api.resources import router as resources_router
from app.api.simulate import router as simulate_router
from app.api.traffic import router as traffic_router

app = FastAPI(
    title="AWSense API",
    description="Backend API for AWSense Cloud Management Platform",
    version="1.0.0",
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
def read_root():
    return {"status": "ok", "message": "Welcome to AWSense API"}


@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy"}
