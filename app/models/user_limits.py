from sqlalchemy import Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.db.base import Base


class UserLimits(Base):
    __tablename__ = 'user_limits'

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)

    max_concurrent_jobs: Mapped[int] = mapped_column(Integer, default=1)
    max_jobs_per_day: Mapped[int] = mapped_column(Integer, default=100)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
