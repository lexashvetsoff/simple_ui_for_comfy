from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, require_admin
from app.models.comfy_node import ComfyNode
from app.schemas.comfy_node import (
    ComfyNodeCreate,
    ComfyNodeUpdate,
    ComfyNodeOut
)


router = APIRouter(prefix='/admin/comfy_nodes', tags=['admin-comfy-nodes'])


@router.get('/', response_model=list[ComfyNodeOut])
async def list_nodes(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode))
    return result.scalars().all()


@router.post('/', response_model=ComfyNodeOut)
async def create_node(
    data: ComfyNodeCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode).where(ComfyNode.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail='Node with this name already exists')
    
    node = ComfyNode(**data.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    
    return node


@router.patch('/{node_id}', response_model=ComfyNodeOut)
async def update_node(
    node_id: int,
    data: ComfyNodeUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode).where(ComfyNode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail='Node not found')
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(node, field, value)
    
    await db.commit()
    await db.refresh(node)

    return node


@router.delete('/{node_id}')
async def deactivate_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode).where(ComfyNode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail='Node not found')
    
    node.is_active = False
    await db.commit()

    return {'status': 'disabled'}
