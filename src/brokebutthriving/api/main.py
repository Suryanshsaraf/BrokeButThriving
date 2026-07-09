"""Main FastAPI module for running Broke But Thriving API Server."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brokebutthriving.api.routes.chat import router as chat_router
from brokebutthriving.api.routes.finance import router as finance_router
from brokebutthriving.api.routes.gamification import router as gamification_router
from brokebutthriving.api.routes.health import router as health_router
from brokebutthriving.api.routes.models import router as models_router
from brokebutthriving.api.routes.participants import router as participants_router
from brokebutthriving.core.config import settings
from brokebutthriving.core.database import create_db_and_tables


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize database schemas and tables on startup
    @app.on_event("startup")
    def on_startup() -> None:
        create_db_and_tables()

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(models_router, prefix=settings.api_prefix)
    app.include_router(participants_router, prefix=settings.api_prefix)
    app.include_router(finance_router, prefix=settings.api_prefix)
    app.include_router(gamification_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("brokebutthriving.api.main:app", host="127.0.0.1", port=8000, reload=True)
