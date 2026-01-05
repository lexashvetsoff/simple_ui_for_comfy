from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

from app.db.base import Base


class JobExecution(Base):
    __tablename__ = 'job_executions' 

    id: Mapped[int] = mapped_column(primary_key=True)

    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id'), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey('comfy_nodes.id'), nullable=True)

    status: Mapped[str] = mapped_column(String)   # QUEUED | RUNNING | DONE | ERROR

    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    prompt_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
