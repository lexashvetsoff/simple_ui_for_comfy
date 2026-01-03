from fastapi import FastAPI
from loguru import logger
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import AsyncSessionLocal
from app.core.bootstrap import create_initial_admin

from app.api.auth import router as auth_router
from app.api.admin.users import router as admin_router
from app.api.admin.user_limits import router as user_limits_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    async with AsyncSessionLocal() as session:
        await create_initial_admin(session)
    
    yield

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
    
    logger.info('Application started')
    return app


app = create_app()
