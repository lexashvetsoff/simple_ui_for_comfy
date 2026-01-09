import re
from copy import deepcopy
from typing import Dict, Any
from fastapi import HTTPException
from app.schemas.workflow_spec_v2 import (
    WorkflowSpecV2,
    TextInputSpec,
    ImageInputSpec,
    MaskInputSpec,
    ParamInputSpec,
    BindingSpec
)


# def apply_binding(
#         workflow: dict,
#         binding: BindingSpec,
#         value: Any
# ):
#     try:
#         workflow['nodes'][binding.node_id]['inputs'][binding.field] = value
#     except KeyError:
#         raise HTTPException(
#             status_code=400,
#             detail=(
#                 f"Invalid binding: node '{binding.node_id}' "
#                 f"or field '{binding.field}' not found in workflow"
#             )
#         )


def apply_binding(
        workflow: dict,
        binding: BindingSpec,
        value: Any
):
    """
    Универсальное применение binding к ComfyUI workflow.
    Поддерживает:
    - nodes: list
    - inputs: dict | list
    - field: str | int | widget_*
    """
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("workflow['nodes'] must be a list")

    node_id = int(binding.node_id)

    node = next((n for n in nodes if n.get("id") == node_id), None)
    if node is None:
        raise KeyError(f"Node with id={node_id} not found")

    inputs = node.get("inputs")
    if inputs is None:
        return  # nothing to bind

    field = binding.field

    # ───────────── dict inputs ─────────────
    if isinstance(inputs, dict):
        inputs[str(field)] = value
        return

    # ───────────── list inputs ─────────────
    if isinstance(inputs, list):
        index = None

        # field = int
        if isinstance(field, int):
            index = field

        # field = "0"
        elif isinstance(field, str) and field.isdigit():
            index = int(field)

        # field = "widget_0"
        elif isinstance(field, str):
            m = re.search(r'(\d+)$', field)
            if m:
                index = int(m.group(1))

        # если индекс определить нельзя — это не runtime input
        if index is None:
            return

        # расширяем список при необходимости
        while len(inputs) <= index:
            inputs.append(None)

        inputs[index] = value
        return

    raise TypeError(f"Unsupported inputs type: {type(inputs)}")


def map_inputs_to_workflow(
        *,
        workflow_json: dict,
        spec: WorkflowSpecV2,
        text_inputs: dict,
        param_inputs: dict,
        uploaded_files: dict,
        mode: str = 'default'
) -> dict:
    workflow = deepcopy(workflow_json)

    # validate mode
    modes = {m.id for m in spec.modes}
    if mode not in modes:
        raise HTTPException(status_code=400, detail=f'Invalid mode "{mode}", available: {modes}')
    
    # TEXT
    for inp in spec.inputs.text:
        if inp.key not in text_inputs:
            continue
        if not inp.binding:
            continue

        apply_binding(workflow, inp.binding, text_inputs[inp.key])
    
    # PARAMS
    for param in spec.inputs.params:
        value = param_inputs.get(param.key, param.default)
        if value is None or not param.binding:
            continue

        # map by mode if needed
        if param.binding.map:
            if mode not in param.binding.map:
                raise HTTPException(status_code=400, detail=f'Mode "{mode}" not supported for "{param.key}"')
            value = param.binding.map[mode]
        
        apply_binding(workflow, param.binding, value)
    
    # IMAGES
    for img in spec.inputs.images:
        if img.modes and mode not in img.modes:
            continue
        if img.key not in uploaded_files:
            continue
        if not img.binding:
            continue

        apply_binding(workflow, img.binding, uploaded_files[img.key])
    
    # MASK
    if spec.inputs.mask:
        mask = spec.inputs.mask
        if mask.key in uploaded_files and mask.binding:
            apply_binding(workflow, mask.binding, uploaded_files[mask.key])
    
    return workflow


# def map_inputs_to_workflow(
#         *,
#         workflow_json: dict,
#         spec: WorkflowSpecV2,
#         user_inputs: Dict[str, Any],
#         uploaded_files: Dict[str, Any],
#         mode: str
# ) -> dict:
#     """
#     Создаёт новый workflow_json с подставленными значениями
#     на основе Spec v2 и пользовательского ввода.

#     uploaded_files:
#         image_key -> filepath (или список путей)
#     """
#     # 1. Клонируем workflow (оригинал НЕ ТРОГАЕМ)
#     workflow = deepcopy(workflow_json)

#     # 2. Проверка mode
#     available_modes = {m.id for m in spec.modes}
#     if mode not in available_modes:
#         raise HTTPException(status_code=400, detail=f"Invalid mode '{mode}', available: {available_modes}")
    
#     # 3. TEXT inputs
#     for text_input in spec.inputs.text:
#         if text_input.key not in user_inputs:
#             continue

#         if not hasattr(text_input, 'binding') or text_input.binding is None:
#             continue

#         apply_binding(
#             workflow,
#             text_input.binding,
#             user_inputs[text_input.key]
#         )
    
#     # 4. PARAM inputs (int / float / bool)
#     for param in spec.inputs.params:
#         if param.key in user_inputs:
#             value = user_inputs[param.key]
#         else:
#             value = param.default
        
#         if value is None:
#             continue

#         if not hasattr(param, 'binding') or param.binding is None:
#             continue

#         # mode → Any Switch mapping
#         if param.binding.map:
#             if mode not in param.binding.map:
#                 raise HTTPException(status_code=400, detail=f"Mode '{mode}' not supported for '{param.key}'")
#             value = param.binding.map[mode]
        
#         apply_binding(
#             workflow,
#             param.binding,
#             value
#         )
    
#     # 5. IMAGE inputs
#     for image_input in spec.inputs.images:
#         if image_input.modes and mode not in image_input.modes:
#             continue

#         if image_input.key not in uploaded_files:
#             continue

#         if not hasattr(image_input, 'binding') or image_input.binding is None:
#             continue

#         value = uploaded_files[image_input.key]

#         apply_binding(
#             workflow,
#             image_input.binding,
#             value
#         )
    
#     # 6. MASK input
#     if spec.inputs.mask:
#         mask = spec.inputs.mask

#         if mask.modes and mode not in mask.modes:
#             pass
#         elif mask.key in uploaded_files:
#             if not hasattr(mask, 'binding') or mask.binding is None:
#                 pass
#             else:
#                 apply_binding(
#                     workflow,
#                     mask.binding,
#                     uploaded_files[mask.key]
#                 )
    
#     return workflow
