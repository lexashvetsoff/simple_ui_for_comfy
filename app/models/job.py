from sqlalchemy import Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

from app.db.base import Base


class Job(Base):
    __tablename__ = 'jobs'

    id: Mapped[str] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey('workflows.id'), index=True)

    mode: Mapped[str] = mapped_column(String)

    inputs: Mapped[dict] = mapped_column(JSON)
    files: Mapped[dict] = mapped_column(JSON)

    prepared_workflow: Mapped[dict] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String, default='QUEUED')     # QUEUED | RUNNING | DONE | ERROR

    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
