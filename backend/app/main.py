"""FastAPI application entry point."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .logger import logger
from .middleware.rate_limit import SecurityRateLimitMiddleware
from .api.v1 import auth_routes, interview, documents, readiness, billing

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started")
    yield
    logger.info("Application stopped")

app = FastAPI(
    title="AI Interview Prep Assistant",
    version="0.1.0",
    description="Backend API for AI Interview Prep Assistant with Supabase Auth",
    lifespan=lifespan,
)

# OWASP Security & Sliding Window Rate Limiting
app.add_middleware(SecurityRateLimitMiddleware, enabled=True)

# CORS — allow frontend and Vercel preview/production deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_routes.router, prefix="/api/v1")
app.include_router(interview.router, prefix="/api/v1", tags=["interview"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(readiness.router, prefix="/api/v1", tags=["readiness"])
app.include_router(billing.router, prefix="/api/v1", tags=["billing"])


@app.get("/health")
async def health_check():
    """Health check endpoint for liveness probes."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint for traffic routing."""
    return {
        "status": "ready",
        "service": "ai-interview-prep-assistant",
        "version": "0.1.0",
        "supabase_configured": bool(settings.supabase_url and "placeholder" not in settings.supabase_url),
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.reload)
