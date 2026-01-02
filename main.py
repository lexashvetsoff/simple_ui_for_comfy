from fastapi import FastAPI
from core.config import settings
from core.logging import setup_logging
from loguru import logger


def create_app() -> FastAPI:
    setup_logging()
    
    app = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBAG
    )

    @app.get('/health', tags=['system'])
    def health_check():
        return {'status': 'Ok'}
    
    logger.info('Application started')
    return app


app = create_app()
