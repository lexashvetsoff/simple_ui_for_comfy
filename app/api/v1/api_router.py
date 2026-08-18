
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.jwt import create_api_token
from app.api.deps import get_db, get_current_client
from app.schemas.auth import TokenRequest, TokenResponse
from app.services.api_service import execute_workflow


router = APIRouter(prefix='/api', tags=['api'])


@router.get('/api_health')
async def api_healthcheck():
    return {'status': 'Ok'}


@router.post('/get_token', response_model=TokenResponse)
async def issue_token(request: TokenRequest):
    expected = settings.VALID_CLIENTS.get(request.client_id)
    if not expected or expected != request.client_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid client credentials'
        )

    return TokenResponse(
        access_token=create_api_token(request.client_id),
        expire_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get('/test_token')
async def test_token(
    _: str = Depends(get_current_client)
):
    return {'status': 'ok'}


@router.post('/remove_bg')
async def remove_bg(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_client)
):
    result = await execute_workflow('remove_bg_v2', image, db)
    return Response(
         content=result.get('content'),
         media_type=result.get('content_type')
    )


@router.post('/remove_crop_bg')
async def remove_crop_bg(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_client)
):
    result = await execute_workflow('remove_bg_and_crop_v2', image, db)
    return Response(
            content=result.get('content'),
            media_type=result.get('content_type')
    )
