from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal


ViewMode = Literal['view', 'hidden', 'no_view']


class BindingSpec(BaseModel):
    node_id: str
    field: str
    map: Optional[Dict[str, Any]] = None


class BaseInputSpec(BaseModel):
    key: str
    label: str | None = None
    view: ViewMode = "view"


class TextInputSpec(BaseInputSpec):
    type: Literal["text"] = "text"
    required: bool = False
    default: Optional[str] = None
    binding: Optional[BindingSpec] = None


class ParamInputSpec(BaseInputSpec):
    type: Literal["int", "float", "bool", "text"]
    default: Optional[Any] = None
    binding: Optional[BindingSpec] = None


class ImageInputSpec(BaseInputSpec):
    modes: Optional[List[str]] = None
    binding: Optional[BindingSpec] = None


class MaskInputSpec(BaseInputSpec):
    depends_on: str
    modes: Optional[List[str]] = None
    binding: Optional[BindingSpec] = None


class InputsSpec(BaseModel):
    text: List[TextInputSpec] = Field(default_factory=list)
    params: List[ParamInputSpec] = Field(default_factory=list)
    images: List[ImageInputSpec] = Field(default_factory=list)
    mask: Optional[MaskInputSpec] = None


class ModeSpec(BaseModel):
    id: str
    label: str


class MetaSpec(BaseModel):
    version: str
    title: str
    description: str


class OutputBindingSpec(BaseModel):
    node_id: str
    field: str


class OutputSpec(BaseModel):
    key: str
    type: str
    binding: OutputBindingSpec


class WorkflowSpecV2(BaseModel):
    version: str = Field("2.0", Literal=True)
    meta: MetaSpec
    modes: List[ModeSpec]
    inputs: InputsSpec
    outputs: List[OutputSpec]
