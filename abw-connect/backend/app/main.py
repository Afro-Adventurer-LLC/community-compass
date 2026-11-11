"""FastAPI entrypoint. Structured so the same app can run behind API Gateway via Mangum."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .routes.api import router

app = FastAPI(
    title="ABW Connect",
    description="Source-backed assistant for AWS All Builders Welcome grant recipients and alumni advisors.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"service": "abw-connect", "docs": "/docs", "health": "/api/health"}


# AWS Lambda (API Gateway HTTP API or REST) via Mangum.
try:
    from mangum import Mangum

    handler = Mangum(app, lifespan="off")
except Exception:  # pragma: no cover - mangum is optional for pure local-dev
    handler = None
