from pydantic import BaseModel, HttpUrl, AnyUrl
from datetime import datetime


class ComfyNodeBase(BaseModel):
    name: str
    base_url: str
    max_queue: int = 1
    priority: int = 10
    is_active: bool = True


class ComfyNodeCreate(ComfyNodeBase):
    pass


class ComfyNodeUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    max_queue: int | None = None
    priority: int | None = None
    is_active: bool | None = None


class ComfyNodeOut(ComfyNodeBase):
    id: int
    last_seen: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
