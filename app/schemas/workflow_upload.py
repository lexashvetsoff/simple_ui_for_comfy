from pydantic import BaseModel, Field
from typing import Dict, Any, Optional


class UploadWorkflowRequest(BaseModel):
    name: str = Field(..., example="Qwen Image Edit")
    slug: str = Field(..., example="qwen-image-edit")

    category: Optional[str] = Field(
        None,
        example="image-editing"
    )

    spec_json: Dict[str, Any] = Field(
        ...,
        description="Workflow UI Spec v2"
    )

    workflow_json: Dict[str, Any] = Field(
        ...,
        description="Original ComfyUI workflow JSON"
    )
