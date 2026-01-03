from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

from app.db.base import Base


class Job(Base):
    __tablename__ = 'jobs'

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    workflow_id: Mapped[int] = mapped_column(ForeignKey('workflows.id'))
    node_id: Mapped[int] = mapped_column(ForeignKey('comfy_nodes.id'), nullable=True)

    status: Mapped[str] = mapped_column(String, default='QUEUED')   # QUEUED | RUNNING | DONE | ERROR

    prompt_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
