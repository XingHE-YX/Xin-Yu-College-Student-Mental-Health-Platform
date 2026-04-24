"""FastAPI application entrypoint for the Xinyu backend."""

from fastapi import FastAPI

from src.api.router import api_router
from src.api.routes.health import router as health_router
from src.core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    runtime_settings = settings or get_settings()

    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = runtime_settings
    app.include_router(health_router)
    app.include_router(api_router, prefix=runtime_settings.api_v1_prefix)
    return app


app = create_app()
