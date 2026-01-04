import asyncio
from fastapi import FastAPI
from loguru import logger
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import AsyncSessionLocal
from app.core.bootstrap import create_initial_admin
from app.services.comfy_health import healthcheck_loop

from app.api.auth import router as auth_router
from app.api.admin.users import router as admin_router
from app.api.admin.user_limits import router as user_limits_router
from app.api.admin.comfy_nodes import router as comfy_nodes_router
from app.api.admin.health import router as health_router
from app.api.admin.workflows import router as workflows_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    async with AsyncSessionLocal() as session:
        await create_initial_admin(session)
    
    task = asyncio.create_task(healthcheck_loop())
    
    yield

    task.cancel()

    # SHUTDOWN
    # здесь можно закрывать соединения, если нужно


def create_app() -> FastAPI:
    setup_logging()
    
    app = FastAPI(
        title=settings.PROJECT_NAME,
        lifespan=lifespan,
        debug=settings.DEBAG
    )

    @app.get('/health', tags=['system'])
    def health_check():
        return {'status': 'Ok'}
    
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(user_limits_router)
    app.include_router(comfy_nodes_router)
    app.include_router(health_router)
    app.include_router(workflows_router)
    
    logger.info('Application started')
    return app


app = create_app()
