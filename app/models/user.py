from sqlalchemy import String, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default='USER')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    daily_limit: Mapped[int] = mapped_column(Integer, default=1000)
    concurrent_limit: Mapped[int] = mapped_column(Integer, default=1)
