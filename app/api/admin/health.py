from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.services.comfy_health import check_all_nodes


router = APIRouter(prefix='/admin/health', tags=['admin-health'])


@router.post('/comfy')
async def manual_healthcheck(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    await check_all_nodes(db)
    return {'status': 'Ok'}
