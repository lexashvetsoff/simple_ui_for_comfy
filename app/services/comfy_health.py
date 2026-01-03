import asyncio
from loguru import logger
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.comfy_node import ComfyNode


COMFY_PING_ENDPOINT = '/system_stats'


async def ping_node(node: ComfyNode) -> bool:
    try:
        async with httpx.AsyncClient(
            timeout=settings.COMFY_HEALTHCHECK_TIMEOUT
        ) as client:
            r = await client.get(node.base_url + COMFY_PING_ENDPOINT)
            return r.status_code == 200
    except Exception:
        return False


async def check_all_nodes(db: AsyncSession):
    now = datetime.now()

    result = await db.execute(select(ComfyNode))
    nodes = result.scalars().all()

    for node in nodes:
        alive = await ping_node(node)

        if alive:
            node.last_seen = now
            node.is_active = True
        else:
            if node.last_seen and (
                now - node.last_seen > timedelta(seconds=settings.COMFY_DEAD_AFTER)
            ):
                node.is_active = False
    
    await db.commit()


async def healthcheck_loop():
    while True:
        async with AsyncSessionLocal() as db:
            await check_all_nodes(db)
        logger.info('Comfy nodes health checked')
        await asyncio.sleep(settings.COMFY_HEALTHCHECK_INTERVAL)
