"""FastAPI application entry point for the Backup API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.v1.router import api_router
from app.api.v1.endpoints.health import router as health_router
from app.core.config import get_settings
from app.core.database import Base, engine
from app import models  # noqa: F401  (register models on Base)


def init_observability(app: FastAPI) -> None:
    """Initialize OpenTelemetry instrumentation for the FastAPI app.

    Instrumentation is wrapped in a try/except so the service still runs when
    the optional OTel packages are not installed (e.g. in tests).

    Args:
        app: The FastAPI application to instrument.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:  # pragma: no cover - optional dependency
        pass


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle.

    Creates tables on startup using the declarative base when a connection is
    available. In production, prefer Alembic migrations.

    Args:
        app: The FastAPI application.

    Yields:
        None after startup work completes.
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:  # pragma: no cover - connection may be unavailable
        pass
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{'/docs'}",
    redoc_url=f"{'/redoc'}",
)

if settings.cors_origin_list != ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)

if settings.enable_metrics:
    app.mount("/metrics", make_asgi_app())

init_observability(app)