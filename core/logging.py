import sys
from loguru import logger


def setup_logging():
    logger.remove()
    logger.add(
        sys.stdout,
        level='INFO',
        format='<green>{time}</green> | <level>{level}</level> | <cyan>{message}</cyan>'
    )
