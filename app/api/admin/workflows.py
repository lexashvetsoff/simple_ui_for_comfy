import uuid
import json
from datetime import datetime
from fastapi import APIRouter, UploadFile, Depends, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, require_admin
from app.models.workflow import Workflow
from app.services.workflow_spec import generate_base_spec
from app.services.workflow_spec_validator import validate_workflow_spec
from app.schemas.workflow_upload import UploadWorkflowRequest


router = APIRouter(prefix='/admin/workflows', tags=['admin-workflows'])


# @router.post('/upload')
# async def upload_workflow(
#     file: UploadFile,
#     name: str = Form(...),
#     slug: str = Form(...),
#     category: str | None = Form(None),
#     requires_mask: bool = Form(False),
#     db: AsyncSession = Depends(get_db),
#     _: None = Depends(require_admin)
# ):
#     # Проверка файла
#     if not file.filename.endswith('.json'):
#         raise HTTPException(status_code=400, detail='Workflow file must be a .json')
    
#     try:
#         raw = await file.read()
#         workflow_json = json.loads(raw)
#     except Exception:
#         raise HTTPException(status_code=400, detail='Invalid JSON file')
    
#     # Проверка slug на уникальность
#     existing = await db.execute(select(Workflow).where(Workflow.slug == slug))
#     if existing.scalar_one_or_none():
#         raise HTTPException(status_code=409, detail='Workflow with slug already exists')
    
#     # Генерация базового spec
#     spec_json = generate_base_spec(workflow_json)
    

#     # Создание Workflow
#     workflow = Workflow(
#         id=str(uuid.uuid4()),
#         name=name,
#         slug=slug,
#         category=category,
#         version='1.0',
#         is_active=True,
#         requires_mask=requires_mask,
#         spec_json=spec_json,
#         workflow_json=workflow_json,
#         created_at=datetime.now()
#     )

#     db.add(workflow)
#     await db.commit()
#     await db.refresh(workflow)

#     return {
#         'id': workflow.id,
#         'slug': workflow.slug,
#         'version': workflow.version,
#         'requires_mask': workflow.requires_mask,
#         'spec': workflow.spec_json
#     }


@router.post('/upload')
async def upload_workflow(
    payload: UploadWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    # slug uniqueness check
    existing = await db.execute(select(Workflow).where(Workflow.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Workflow with this slug already exists"
        )

    # validate spec
    spec = validate_workflow_spec(payload.spec_json)

    workflow = Workflow(
        id=uuid.uuid4().hex,
        name=payload.name,
        slug=payload.slug,
        category=payload.category,
        version=spec.version,
        requires_mask=bool(spec.inputs.mask),
        spec_json=payload.spec_json,
        workflow_json=payload.workflow_json,
    )

    db.add(workflow)
    await db.commit()
    return workflow
