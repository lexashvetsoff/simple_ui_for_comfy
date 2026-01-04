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


def apply_binding(
        workflow: dict,
        binding: BindingSpec,
        value: Any
):
    try:
        workflow['nodes'][binding.node_id]['inputs'][binding.field] = value
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid binding: node '{binding.node_id}' "
                f"or field '{binding.field}' not found in workflow"
            )
        )


def map_inputs_to_workflow(
        *,
        workflow_json: dict,
        spec: WorkflowSpecV2,
        user_inputs: Dict[str, Any],
        uploaded_files: Dict[str, Any],
        mode: str
) -> dict:
    """
    Создаёт новый workflow_json с подставленными значениями
    на основе Spec v2 и пользовательского ввода.

    uploaded_files:
        image_key -> filepath (или список путей)
    """
    # 1. Клонируем workflow (оригинал НЕ ТРОГАЕМ)
    workflow = deepcopy(workflow_json)

    # 2. Проверка mode
    available_modes = {m.id for m in spec.modes}
    if mode not in available_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{mode}', available: {available_modes}")
    
    # 3. TEXT inputs
    for text_input in spec.inputs.text:
        if text_input.key not in user_inputs:
            continue

        if not hasattr(text_input, 'binding') or text_input.binding is None:
            continue

        apply_binding(
            workflow,
            text_input.binding,
            user_inputs[text_input.key]
        )
    
    # 4. PARAM inputs (int / float / bool)
    for param in spec.inputs.params:
        if param.key in user_inputs:
            value = user_inputs[param.key]
        else:
            value = param.default
        
        if value is None:
            continue

        if not hasattr(param, 'binding') or param.binding is None:
            continue

        # mode → Any Switch mapping
        if param.binding.map:
            if mode not in param.binding.map:
                raise HTTPException(status_code=400, detail=f"Mode '{mode}' not supported for '{param.key}'")
            value = param.binding.map[mode]
        
        apply_binding(
            workflow,
            param.binding,
            value
        )
    
    # 5. IMAGE inputs
    for image_input in spec.inputs.images:
        if image_input.modes and mode not in image_input.modes:
            continue

        if image_input.key not in uploaded_files:
            continue

        if not hasattr(image_input, 'binding') or image_input.binding is None:
            continue

        value = uploaded_files[image_input.key]

        apply_binding(
            workflow,
            image_input.binding,
            value
        )
    
    # 6. MASK input
    if spec.inputs.mask:
        mask = spec.inputs.mask

        if mask.modes and mode not in mask.modes:
            pass
        elif mask.key in uploaded_files:
            if not hasattr(mask, 'binding') or mask.binding is None:
                pass
            else:
                apply_binding(
                    workflow,
                    mask.binding,
                    uploaded_files[mask.key]
                )
    
    return workflow
