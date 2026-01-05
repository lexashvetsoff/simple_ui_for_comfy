from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime


class JobCreateRequest(BaseModel):
    workflow_slug: str
    mode: str
    inputs: Dict[str, Any] = {}
    files: Dict[str, Any] = {}


class JobResponse(BaseModel):
    id: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
