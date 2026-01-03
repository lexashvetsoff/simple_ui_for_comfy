from sqlalchemy.ext.asyncio import AsyncSession
from app.services.scheduler import select_node
from app.models.job import Job


async def create_job(
        db: AsyncSession,
        user_id: int,
        workflow_id: int
):
    node = await select_node(db)

    job = Job(
        user_id=user_id,
        workflow_id=workflow_id,
        node_id=node.id,
        status='QUEUED'
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job
