import uuid
import json
from enum import Enum
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from starlette.status import HTTP_302_FOUND

from app.api.deps import get_db, require_admin
from app.core.templates import templates
from app.models.user import User
from app.models.user_limits import UserLimits
from app.models.comfy_node import ComfyNode
from app.models.workflow import Workflow
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.core.security import verify_password
from app.core.jwt import create_access_token, create_refresh_token
from app.services.auth_service import _clear_auth_cookies, _set_auth_cookies
from app.core.security import hash_password
from app.services.workflow_spec_validator import validate_workflow_spec
from app.services.spec_generator import generate_spec_v2
from app.services.parse_json import parse_json_field
from app.services.comfy_client import get_object_info


router = APIRouter(prefix='/admin', tags=['admin-ui'])


TOP_USERS_FOR_JOBS_GIST = 10
TOP_ACTIVE_USERS = 5


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"


@router.get('/', response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin)
):
    # ------------------------------------------------------------
    # 1. Количество запусков workflow (топ-10)
    # ------------------------------------------------------------
    stmt = (
        select(
            Workflow.id,
            Workflow.name,
            func.count(Job.id).label('count')
        )
        .join(Job, Workflow.id == Job.workflow_id)
        .group_by(Workflow.id, Workflow.name)
        .order_by(desc('count'))
        .limit(10)
    )
    result = await db.execute(stmt)
    workflow_counts = result.all() # list of (id, name, count)

    workflow_labels = [w.name for w in workflow_counts]
    workflow_data = [w.count for w in workflow_counts]

    # ------------------------------------------------------------
    # 2. Активность пользователей (% от общего числа job)
    # ------------------------------------------------------------
    # total_jobs = await db.execute(select(func.count(Job.id))) or 1
    total_jobs_result = await db.execute(select(func.count(Job.id)))
    total_jobs = total_jobs_result.scalar() or 1

    stmt = (
        select(
            User.email,
            func.count(Job.id).label('job_count')
        )
        .join(Job, User.id == Job.user_id)
        .group_by(User.email)
        .order_by(desc('job_count'))
    )
    result = await db.execute(stmt)
    user_jobs = result.all() # list of (email, job_count)

    # Для круговой диаграммы возьмём топ-10, остальное в "Other"
    if len(user_jobs) > TOP_USERS_FOR_JOBS_GIST:
        top_users = user_jobs[:TOP_USERS_FOR_JOBS_GIST]
        other_count = sum(u.job_count for u in user_jobs[TOP_USERS_FOR_JOBS_GIST:])
        user_labels = [u.email for u in top_users] + ['Other']
        user_data = [u.job_count for u in top_users] + [other_count]
    else:
        user_labels = [u.email for u in user_jobs]
        user_data = [u.job_count for u in user_jobs]
    
    # Проценты
    user_percentages = [round((c / total_jobs) * 100, 1) for c in user_data]

    # ------------------------------------------------------------
    # 3. Использование ComfyNode (количество выполнений на узле)
    # ------------------------------------------------------------
    stmt = (
        select(
            ComfyNode.name,
            func.count(JobExecution.id).label('exec_count')
        )
        .join(JobExecution, ComfyNode.id == JobExecution.node_id)
        .group_by(ComfyNode.name)
        .order_by(desc('exec_count'))
    )
    result = await db.execute(stmt)
    node_usage = result.all() # list of (name, exec_count)

    node_labels = [n.name for n in node_usage]
    node_data = [n.exec_count for n in node_usage]

    # ------------------------------------------------------------
    # 4. Статусы job (QUEUED, RUNNING, DONE, ERROR)
    # ------------------------------------------------------------
    stmt = (
        select(Job.status, func.count().label('count'))
        .group_by(Job.status)
    )
    result = await db.execute(stmt)
    status_counts = result.all() # list of (status, count)

    status_labels = [s.status for s in status_counts]
    status_data = [s.count for s in status_counts]

    # ------------------------------------------------------------
    # 5. Среднее время выполнения job_execution по workflow
    # ------------------------------------------------------------
    # Используем PostgreSQL: EXTRACT(EPOCH FROM ...)
    duration = func.extract('epoch', JobExecution.finished_at - JobExecution.started_at).label('duration')
    stmt = (
        select(
            Workflow.name,
            func.avg(duration).label('avg_duration')
        )
        .join(Job, JobExecution.job_id == Job.id)
        .join(Workflow, Job.workflow_id == Workflow.id)
        .where(JobExecution.finished_at.isnot(None), JobExecution.started_at.isnot(None))
        .group_by(Workflow.name)
        .order_by(desc('avg_duration'))
    )
    result = await db.execute(stmt)
    avg_durations = result.all() # list of (name, avg_duration)

    duration_labels = [d.name for d in avg_durations]
    # duration_data = [round(d.avg_duration, 2) for d in avg_durations]  # секунды
    duration_data = [float(d.avg_duration) if d.avg_duration is not None else 0 for d in avg_durations]  # секунды

    # ------------------------------------------------------------
    # 6. Топ-n активных пользователей
    # ------------------------------------------------------------
    # Сначала получаем топ-n пользователей по количеству job
    stmt = (
        select(User.id, User.email, func.count(Job.id).label('total_jobs'))
        .join(Job, User.id == Job.user_id)
        .group_by(User.id, User.email)
        .order_by(desc('total_jobs'))
        .limit(TOP_ACTIVE_USERS)
    )
    result = await db.execute(stmt)
    top_users_raw = result.all() # list of (id, email, total_jobs)

    top_active_users = []
    for uid, email, total in top_users_raw:
        # Самое частое workflow для этого пользователя
        stmt_wf = (
            select(Workflow.name, func.count().label('wf_count'))
            .join(Job, Workflow.id == Job.workflow_id)
            .where(Job.user_id == uid)
            .group_by(Workflow.name)
            .order_by(desc('wf_count'))
            .limit(1)
        )
        res_wf = await db.execute(stmt_wf)
        top_wf = res_wf.first()
        top_workflow_name = top_wf.name if top_wf else 'N/A'

        # Среднее время выполнения job этого пользователя
        stmt_dur = (
            select(func.avg(duration).label('avg_dur'))
            .select_from(JobExecution)
            .join(Job, JobExecution.job_id == Job.id)
            .where(
                Job.user_id == uid,
                JobExecution.finished_at.isnot(None),
                JobExecution.started_at.isnot(None)
            )
        )
        res_dur = await db.execute(stmt_dur)
        # avg_dur = res_dur.scalar()
        # avg_duration = round(avg_dur, 2) if avg_dur else None
        avg_dur = res_dur.scalar()
        avg_duration = float(avg_dur) if avg_dur is not None else None

        top_active_users.append({
            'email': email,
            'total_jobs': total,
            'top_workflow': top_workflow_name,
            'avg_duration': avg_duration
        })

    # ------------------------------------------------------------
    # Формируем контекст для шаблона
    # ------------------------------------------------------------
    context = {
        "request": request,
        "user": user,
        "workflow_chart": {
            "labels": workflow_labels,
            "data": workflow_data
        },
        "user_activity_chart": {
            "labels": user_labels,
            "data": user_percentages   # проценты
        },
        "node_usage_chart": {
            "labels": node_labels,
            "data": node_data
        },
        "job_status_chart": {
            "labels": status_labels,
            "data": status_data
        },
        "avg_duration_chart": {
            "labels": duration_labels,
            "data": duration_data
        },
        "top_users": top_active_users
    }

    return templates.TemplateResponse(
        '/admin/dashboard.html',
        context
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
    
    # Берём любую активную ноду
    node_res = await db.execute(
        select(ComfyNode)
        .where(ComfyNode.is_active == True)
        .order_by(ComfyNode.last_seen.desc())
        .limit(1)
    )
    node = node_res.scalars().first()

    object_info = {}
    if node:
        object_info = await get_object_info(node=node)
    
    # Генерация spec
    # spec = generate_spec_v2(workflow_data)
    spec = generate_spec_v2(workflow_data, object_info=object_info)

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
    # spec = generate_spec_v2(workflow.workflow_json)

    # Берём любую активную ноду
    node_res = await db.execute(
        select(ComfyNode)
        .where(ComfyNode.is_active == True)
        .order_by(ComfyNode.last_seen.desc())
        .limit(1)
    )
    node = node_res.scalars().first()

    object_info = {}
    if node:
        object_info = await get_object_info(node=node)
    
    # Генерация spec
    spec = generate_spec_v2(workflow.workflow_json, object_info=object_info)

    # Валидация (важно!)
    validate_workflow_spec(spec)

    workflow.spec_json = spec
    workflow.version = spec['meta']['version']
    workflow.requires_mask = bool(spec['inputs'].get('mask'))

    await db.commit()
    await db.refresh(workflow)

    return RedirectResponse(
        url=f'/admin/workflows/{workflow.id}/edit',
        status_code=HTTP_302_FOUND
    )
