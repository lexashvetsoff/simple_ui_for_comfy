from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import setup_logging
from loguru import logger

from app.api.auth import router as auth_router


def create_app() -> FastAPI:
    setup_logging()
    
    app = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBAG
    )

    @app.get('/health', tags=['system'])
    def health_check():
        return {'status': 'Ok'}
    
    app.include_router(auth_router)
    
    logger.info('Application started')
    return app


app = create_app()
