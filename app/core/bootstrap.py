from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.core.security import hash_password


async def create_initial_admin(session: AsyncSession):
    result = await session.execute(select(User).where(User.role == 'ADMIN'))
    # admin_exists = result.scalar_one_or_none()
    admin_exists = result.scalars().all()

    if admin_exists:
        return
    
    from app.core.config import settings

    if not settings.INITIAL_ADMIN_EMAIL or not settings.INITIAL_ADMIN_PASSWORD:
        return
    
    admin = User(
        email=settings.INITIAL_ADMIN_EMAIL,
        password_hash=hash_password(settings.INITIAL_ADMIN_PASSWORD),
        role='ADMIN',
        is_active=True
    )

    session.add(admin)
    await session.commit()
