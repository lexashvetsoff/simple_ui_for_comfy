from sqlalchemy import String, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

from app.db.base import Base


class Workflow(Base):
    __tablename__ = 'workflows'

    id: Mapped[str] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)

    category: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str] = mapped_column(String, default='1.0')

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_mask: Mapped[bool] = mapped_column(Boolean, default=False)

    spec_json: Mapped[dict] = mapped_column(JSON)
    workflow_json: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
