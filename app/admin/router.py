import uuid
import json
from enum import Enum
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.status import HTTP_302_FOUND

from app.api.deps import get_db, require_admin
from app.core.templates import templates
from app.models.user import User
from app.models.user_limits import UserLimits
from app.models.comfy_node import ComfyNode
from app.models.workflow import Workflow
from app.core.security import verify_password
from app.core.jwt import create_access_token, create_refresh_token
from app.services.auth_service import _clear_auth_cookies, _set_auth_cookies
from app.core.security import hash_password
from app.services.workflow_spec_validator import validate_workflow_spec
from app.services.spec_generator import generate_spec_v2
from app.services.parse_json import parse_json_field


router = APIRouter(prefix='/admin', tags=['admin-ui'])


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"


@router.get('/', response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    user: User = Depends(require_admin)
):
    return templates.TemplateResponse(
        '/admin/dashboard.html',
        {'request': request, 'user': user}
    )


@router.get('/login', response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse(
        '/admin/login.html',
        {'request': request}
    )


@router.post('/login')
async def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if (
        not user
        or not verify_password(password, user.password_hash)
        or not user.is_active
        or user.role != 'ADMIN'
    ):
        return templates.TemplateResponse(
            '/admin/login.html',
            {'request': request, 'error': 'Invalid credintials or not admin'},
            status_code=400,
        )
    
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    response = RedirectResponse(
        url='/admin',
        status_code=HTTP_302_FOUND
    )

    _set_auth_cookies(response, access_token, refresh_token)

    return response


@router.get('/logout')
async def admin_logout():
    response = RedirectResponse(url='/admin/login', status_code=302)
    _clear_auth_cookies(response)
    return response


@router.get('/users', response_class=HTMLResponse)
async def admin_users_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin)
):
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()

    return templates.TemplateResponse(
        '/admin/users/list.html',
        {
            'request': request,
            'user': user,
            'users': users
        }
    )


@router.post('/users/{user_id}/toggle')
async def admin_toggle_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    
    target.is_active = not target.is_active
    await db.commit()

    return RedirectResponse(
        url='/admin/users',
        status_code=HTTP_302_FOUND
    )


@router.get('/users/{user_id}/limits', response_class=HTMLResponse)
async def admin_user_limits(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    user_result = await db.execute(select(User).where(User.id == user_id))
    target = user_result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    
    limits_result = await db.execute(select(UserLimits).where(UserLimits.user_id == user_id))
    limits = limits_result.scalar_one_or_none()

    if not limits:
        limits = UserLimits(user_id=user_id)
        db.add(limits)
        await db.commit()
        await db.refresh(limits)
    
    return templates.TemplateResponse(
        '/admin/users/limits.html',
        {
            'request': request,
            'user': admin,
            'target': target,
            'limits': limits
        }
    )


@router.post('/users/{user_id}/limits')
async def admin_user_limits_save(
    user_id: int,
    max_concurrent_jobs: int = Form(...),
    max_jobs_per_day: int = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(UserLimits).where(UserLimits.user_id == user_id))
    limits = result.scalar_one_or_none()

    if not limits:
        limits = UserLimits(user_id=user_id)
        db.add(limits)
    
    limits.max_concurrent_jobs = max_concurrent_jobs
    limits.max_jobs_per_day = max_jobs_per_day

    await db.commit()

    return RedirectResponse(
        url='/admin/users',
        status_code=HTTP_302_FOUND
    )


@router.get('/users/create', response_class=HTMLResponse)
async def admin_user_create_page(
    request: Request,
    admin: User = Depends(require_admin)
):
    return templates.TemplateResponse(
        '/admin/users/create.html',
        {'request': request, 'user': admin}
    )


@router.post('/users/create')
async def admin_user_create(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    # проверка уникальности email
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse(
            '/admin/users/create.html',
            {
                'request': request,
                'error': 'User with this email already exists'
            },
            status_code=400
        )
    
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=UserRole(role).value,
        is_active=True
    )
    db.add(user)
    await db.flush()

    limit = UserLimits(user_id=user.id)
    db.add(limit)

    await db.commit()

    return RedirectResponse(
        url='/admin/users',
        status_code=HTTP_302_FOUND
    )


@router.get('/nodes', response_class=HTMLResponse)
async def admin_nodes_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode).order_by(ComfyNode.id))
    nodes = result.scalars().all()

    return templates.TemplateResponse(
        '/admin/nodes/list.html',
        {
            'request': request,
            'user': admin,
            'nodes': nodes
        }
    )


@router.get('/nodes/create', response_class=HTMLResponse)
async def admin_node_create_page(
    request: Request,
    admin: User = Depends(require_admin)
):
    return templates.TemplateResponse(
        '/admin/nodes/form.html',
        {
            'request': request,
            'user': admin,
            'node': None
        }
    )


@router.post('/nodes/create')
async def admin_node_create(
    name: str = Form(...),
    base_url: str = Form(...),
    max_queue: int = Form(...),
    priority: int = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    node = ComfyNode(
        name=name,
        base_url=base_url,
        is_active=True,
        max_queue=max_queue,
        priority=priority
    )
    db.add(node)
    await db.commit()

    return RedirectResponse(
        url='/admin/nodes',
        status_code=HTTP_302_FOUND
    )


@router.get('/nodes/{node_id}/edit', response_class=HTMLResponse)
async def admin_node_edit_page(
    node_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode).where(ComfyNode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail='Node not found')
    
    return templates.TemplateResponse(
        '/admin/nodes/form.html',
        {
            'request': request,
            'user': admin,
            'node': node
        }
    )


@router.post('/nodes/{node_id}/edit')
async def admin_node_edit(
    node_id: int,
    name: str = Form(...),
    base_url: str = Form(...),
    max_queue: int = Form(...),
    priority: int = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode).where(ComfyNode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail='Node not found')
    
    node.name = name
    node.base_url = base_url
    node.max_queue = max_queue
    node.priority = priority
    await db.commit()

    return RedirectResponse(
        url='/admin/nodes',
        status_code=HTTP_302_FOUND
    )


@router.post('/nodes/{node_id}/toggle')
async def admin_node_toggle(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(ComfyNode).where(ComfyNode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail='Node not found')
    
    node.is_active = not node.is_active
    await db.commit()

    return RedirectResponse(
        url='/admin/nodes',
        status_code=HTTP_302_FOUND
    )


@router.get('/workflows', response_class=HTMLResponse)
async def admin_workflow_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    workflows = result.scalars().all()

    return templates.TemplateResponse(
        '/admin/workflows/list.html',
        {
            'request': request,
            'user': admin,
            'workflows': workflows 
        }
    )


@router.post('/workflows/{workflow_id}/toggle')
async def admin_workflow_toggle(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    workflow.is_active = not workflow.is_active
    await db.commit()

    return RedirectResponse(
        url='/admin/workflows',
        status_code=HTTP_302_FOUND
    )


@router.get('/workflows/upload', response_class=HTMLResponse)
async def admin_workflow_upload_page(
    request: Request,
    admin: User = Depends(require_admin)
):
    return templates.TemplateResponse(
        '/admin/workflows/upload.html',
        {
            'request': request,
            'user': admin
        }
    )


@router.post('/workflows/upload')
async def admin_workflow_upload(
    name: str = Form(...),
    slug: str = Form(...),
    category: str = Form(...),
    spec_json: str = Form(...),
    workflow_json: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    try:
        spec = json.loads(spec_json)
        workflow_data = json.loads(workflow_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='Invalid JSON')
    
    parsed_spec = validate_workflow_spec(spec)

    workflow = Workflow(
        id=uuid.uuid4().hex,
        name=name,
        slug=slug,
        category=category,
        version=parsed_spec.version,
        is_active=True,
        requires_mask=bool(parsed_spec.inputs.mask),
        spec_json=spec,
        workflow_json=workflow_data
    )

    db.add(workflow)
    await db.commit()

    return RedirectResponse(
        url='/admin/workflows',
        status_code=HTTP_302_FOUND
    )


@router.get('/workflows/{workflow_id}/edit', response_class=HTMLResponse)
async def admin_workflow_edit_page(
    workflow_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return templates.TemplateResponse(
        '/admin/workflows/edit.html',
        {
            'request': request,
            'user': admin,
            'workflow': workflow
        }
    )


@router.post('/workflows/{workflow_id}/edit')
async def admin_workflow_edit(
    workflow_id: str,
    spec_json: str = Form(...),
    name: str = Form(...),
    slug: str = Form(...),
    category: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='Invalid JSON')
    
    parced_spec = validate_workflow_spec(spec)

    workflow.name = name
    workflow.slug = slug
    workflow.category = category
    workflow.spec_json = spec
    workflow.version = parced_spec.version
    workflow.requires_mask = bool(parced_spec.inputs.mask)

    await db.commit()

    return RedirectResponse(
        url='/admin/workflows',
        status_code=HTTP_302_FOUND
    )


@router.post('/workflows/upload/generate_spec', response_class=HTMLResponse)
async def admin_workflow_upload_generate_spec(
    request: Request,
    workflow_json: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    try:
        workflow_data = json.loads(workflow_json)
    except json.JSONDecodeError:
        return templates.TemplateResponse(
            '/admin/workflows/upload.html',
            {
                'request': request,
                'user': admin,
                'error': 'Invalid workflow JSON',
                'workflow_json': workflow_json,
            },
            status_code=400
        )
    
    # Генерация spec
    spec = generate_spec_v2(workflow_data)

    workflow_obj = parse_json_field(workflow_json, 'workflow_json')

    try:
        validate_workflow_spec(spec)
    except HTTPException as e:
        return templates.TemplateResponse(
            '/admin/workflows/upload.html',
            {
                'request': request,
                'user': admin,
                'error': e.detail,
                'workflow_json': workflow_obj,
                'spec_json': json.dumps(spec, indent=2),
            },
            status_code=400
        )
    print('validate spec')
    
    return templates.TemplateResponse(
        '/admin/workflows/upload.html',
        {
            'request': request,
            'user': admin,
            'workflow_json': workflow_obj,
            # 'spec_json': json.dumps(spec, indent=2),
            'spec_json': spec,
        }
    )


@router.post('/workflows/{workflow_id}/generate_spec')
async def admin_workflow_generate_spec(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    # Генерация Spec v2
    spec = generate_spec_v2(workflow.workflow_json)

    # Валидация (важно!)
    validate_workflow_spec(spec)

    workflow.spec_json = spec
    workflow.version = spec['meta']['version']
    workflow.requires_mask = bool(spec['inputs'].get('mask'))

    await db.commit()

    return RedirectResponse(
        url=f'/admin/workflows/{workflow.id}/edit',
        status_code=HTTP_302_FOUND
    )
