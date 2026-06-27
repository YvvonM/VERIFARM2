"""
VeriFarm — FastAPI Application Entry Point
==========================================
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.farmers import router as farmers_router
from app.api.onboarding import router as onboarding_router
from app.services.neo4j_client import close_driver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VeriFarm API",
    description="Farmer onboarding, verification, and scoring API",
    version="0.3.0",
)

# CORS — read from env, default to local dev origins
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(farmers_router)
app.include_router(onboarding_router)


@app.on_event("shutdown")
async def shutdown_event():
    """Close Neo4j driver on app shutdown."""
    logger.info("Shutting down — closing Neo4j driver")
    await close_driver()


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.3.0"}