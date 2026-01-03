from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta

from app.models.comfy_node import ComfyNode
from app.models.job import Job


class NoAvailableNode(Exception):
    pass


async def get_node_loads(db: AsyncSession):
    result = await db.execute(
        select(ComfyNode, func.count(Job.id).label('load'))
        .outerjoin(
            Job,
            (Job.node_id == ComfyNode.id)
            & Job.status.in_(['QUEUED', 'RUNNING'])
        )
        .where(ComfyNode.is_active == True)
        .group_by(ComfyNode.id)
    )

    return result.all()


async def select_node(db: AsyncSession) -> ComfyNode:
    await db.execute("LOCK TABLE jobs IN SHARE ROW EXCLUSIVE MODE")
    
    nodes = await get_node_loads(db)

    if not nodes:
        raise NoAvailableNode('No active nodes')
    
    candidates = []

    for node, load in nodes:
        if load < node.max_queue:
            score = (
                node.priority * 10 - load * 5
            )
            candidates.append((score, node))
    
    if not candidates:
        raise NoAvailableNode('All nodes overloaded')
    
    # выбираем ноду с максимальным score
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]
