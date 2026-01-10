import asyncio
from loguru import logger

from app.db.session import AsyncSessionLocal
from app.services.scheduler import scheduler_tick, poll_running_executions


async def scheduler_loop():
    logger.info('Scheduler loop started')

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await scheduler_tick(db=db)
                await poll_running_executions(db=db)
        except asyncio.CancelledError:
            logger.info('Scheduler loop cancelled')
            break
        except Exception as e:
            logger.exception(f'Scheduler loop error: {e}')
        
        await asyncio.sleep(1)
