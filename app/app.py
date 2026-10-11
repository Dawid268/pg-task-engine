"""Reference application assembly adapted from touchpoint-taxonomy."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pg_task_engine import __version__

from .modules.base.api import router as base_router
from .settings import Settings, get_settings


def setup_routing(app: FastAPI) -> FastAPI:
    """Collect domain routers in one place, as in the source boilerplate."""
    global_router = APIRouter()
    global_router.include_router(base_router)
    app.include_router(global_router)
    return app


def setup_middlewares(app: FastAPI, settings: Settings) -> FastAPI:
    """Enable cross-origin access only for explicitly configured origins."""
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=False,
            allow_methods=["GET"],
        )
    return app


def app_factory() -> FastAPI:
    """Construct an independent API without workers, database connections or logging setup."""
    settings = get_settings()
    application = FastAPI(
        title=settings.APP_NAME,
        description="Reference API scaffold. Task execution is not implemented yet.",
        version=__version__,
        debug=settings.DEBUG,
        root_path=settings.APP_ROOT_PATH,
    )
    setup_routing(application)
    setup_middlewares(application, settings)
    return application
