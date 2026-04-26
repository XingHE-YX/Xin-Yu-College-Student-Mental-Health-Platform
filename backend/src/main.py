"""FastAPI application entrypoint for the Xinyu backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.router import api_router
from src.api.routes.health import router as health_router
from src.core.database import (
    check_database_connection,
    create_database_engine,
    create_session_factory,
)
from src.core.security import AccessTokenService
from src.core.settings import Settings, get_settings
from src.services.deepseek_service import DeepSeekService
from src.services.wechat_session_service import WeChatSessionService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    runtime_settings = settings or get_settings()
    db_engine = create_database_engine(runtime_settings)
    db_session_factory = create_session_factory(db_engine)
    access_token_service = AccessTokenService(runtime_settings)
    deepseek_service = DeepSeekService(runtime_settings)
    wechat_session_service = WeChatSessionService(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if runtime_settings.app_env != "testing":
            check_database_connection(db_engine)

        try:
            yield
        finally:
            db_engine.dispose()

    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    app.state.access_token_service = access_token_service
    app.state.deepseek_service = deepseek_service
    app.state.wechat_session_service = wechat_session_service
    app.include_router(health_router)
    app.include_router(api_router, prefix=runtime_settings.api_v1_prefix)
    return app


app = create_app()
