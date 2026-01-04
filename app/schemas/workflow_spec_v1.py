from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict


class InputSpec(BaseModel):
    key: str
    type: str
    label: str
    required: bool = False
    default: Optional[Any] = None

    ui: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None
    depends_on: Optional[Dict[str, Any]] = None


class WorkflowSpec(BaseModel):
    inputs: List[InputSpec]
