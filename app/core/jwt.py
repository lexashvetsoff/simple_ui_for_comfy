from jose import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import settings


def create_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    to_encode['exp'] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_access_token(user_id: int) -> str:
    return create_token(
        {'sub': str(user_id), 'type': 'access'},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    return create_token(
        {'sub': str(user_id), 'type': 'refresh'},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
