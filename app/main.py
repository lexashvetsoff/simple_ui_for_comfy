import asyncio
from loguru import logger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import AsyncSessionLocal
from app.core.bootstrap import create_initial_admin
from app.services.comfy_health import healthcheck_loop

from app.api.auth import router as auth_router
from app.api.admin.users import router as admin_users_router
from app.api.admin.user_limits import router as user_limits_router
from app.api.admin.comfy_nodes import router as comfy_nodes_router
from app.api.admin.health import router as health_router
from app.api.admin.workflows import router as workflows_router
from app.admin.router import router as admin_router
from app.admin.jobs_router import router as admin_jobs_router
from app.user.router import router as user_router
from app.ui.router import router as ui_router
from app.user.workflows_router import router as user_workflow_router
from app.user.jobs_router import router as user_jobs_router


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

    app.mount('/static', StaticFiles(directory='app/static'), name='static')
    app.mount('/storage', StaticFiles(directory=settings.STORAGE_ROOT), name='storage')

    @app.get('/health', tags=['system'])
    def health_check():
        return {'status': 'Ok'}
    
    app.include_router(ui_router)
    app.include_router(user_router)
    app.include_router(auth_router)
    app.include_router(admin_users_router, prefix=settings.API_V1_STR)
    app.include_router(user_limits_router, prefix=settings.API_V1_STR)
    app.include_router(comfy_nodes_router, prefix=settings.API_V1_STR)
    app.include_router(health_router, prefix=settings.API_V1_STR)
    app.include_router(workflows_router, prefix=settings.API_V1_STR)
    app.include_router(admin_router)
    app.include_router(admin_jobs_router)
    app.include_router(user_workflow_router)
    app.include_router(user_jobs_router)
    
    logger.info('Application started')
    return app


app = create_app()
