from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class BindingSpec(BaseModel):
    node_id: str
    field: str
    map: Optional[Dict[str, Any]] = None


class WorkflowMeta(BaseModel):
    title: str
    description: Optional[str] = None


class WorkflowMode(BaseModel):
    id: str
    label: str
    description: Optional[str] = None


class TextInputSpec(BaseModel):
    key: str
    label: str
    required: bool = False
    ui: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None
    binding: BindingSpec


class ImageInputSpec(BaseModel):
    key: str
    label: str
    required: bool = False
    multiple: bool = False
    max: Optional[int] = None
    modes: Optional[List[str]] = None
    binding: BindingSpec


class MaskInputSpec(BaseModel):
    key: str
    label: str
    depends_on: str
    required: bool = False
    ui: Optional[Dict[str, Any]] = None
    modes: Optional[List[str]] = None
    binding: BindingSpec


class ParamInputSpec(BaseModel):
    key: str
    type: str  # int, float, bool
    label: str
    default: Optional[Any] = None
    validation: Optional[Dict[str, Any]] = None
    binding: BindingSpec


class PreprocessingBlock(BaseModel):
    enabled: bool = False
    params: Optional[Dict[str, Any]] = None


class WorkflowOutput(BaseModel):
    key: str
    type: str
    primary: bool = False


class WorkflowRequirements(BaseModel):
    models: List[str] = []
    custom_nodes: List[str] = []


class WorkflowInputs(BaseModel):
    text: List[TextInputSpec] = []
    images: List[ImageInputSpec] = []
    mask: Optional[MaskInputSpec] = None
    params: List[ParamInputSpec] = []


class WorkflowSpecV2(BaseModel):
    version: str = Field("2.0", Literal=True)

    meta: WorkflowMeta
    modes: List[WorkflowMode]

    inputs: WorkflowInputs
    preprocessing: Optional[Dict[str, PreprocessingBlock]] = {}

    outputs: List[WorkflowOutput]
    requirements: Optional[WorkflowRequirements] = None
