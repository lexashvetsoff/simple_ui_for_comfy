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


def normalize_workflow_for_comfy(workflow: dict) -> dict:
    """
    Converts ComfyUI UI-exported workflow to API-ready prompt format.
    """
    for node in workflow.get('nodes', []):
        # UI uses "type", API requires "class_type"
        if 'class_type' not in node:
            node['class_type'] = node.get('type')
    
    return workflow


def _find_node(nodes: list[dict], node_id: int) -> dict | None:
    return next((n for n in nodes if n.get("id") == node_id), None)


def _ensure_list_size(lst: list, index: int) -> None:
    while len(lst) <= index:
        lst.append(None)


def _widget_index(field: Any) -> int | None:
    """
    Accepts:
      - "widget_0"
      - "0"
      - 0
    Returns int index or None.
    """
    if isinstance(field, int):
        return field

    if isinstance(field, str):
        if field.isdigit():
            return int(field)
        m = re.match(r"^widget_(\d+)$", field.strip())
        if m:
            return int(m.group(1))

    return None


def _try_set_nth_literal_in_inputs(node_inputs: list, widget_idx: int, value: Any) -> None:
    """
    In some ComfyUI UI-workflows, widget values are duplicated as literals
    inside node["inputs"] list (e.g. ["red car", {...}]).
    But inputs list can also contain dicts for linked ports.
    We map widget index to the Nth literal item (non-dict) in inputs.
    """
    literal_positions = [i for i, v in enumerate(node_inputs) if not isinstance(v, dict)]
    if widget_idx < 0 or widget_idx >= len(literal_positions):
        return
    pos = literal_positions[widget_idx]
    node_inputs[pos] = value


def apply_binding(workflow: dict, binding: BindingSpec, value: Any) -> None:
    """
    Apply a BindingSpec onto ComfyUI UI-workflow structure.

    Supports:
      - node["inputs"] as dict (API-ish style)
      - node["inputs"] as list (UI style)
      - widget bindings: field = "widget_N" -> writes into node["widgets_values"][N]
    """
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise HTTPException(status_code=400, detail="workflow['nodes'] must be a list")

    try:
        node_id_int = int(binding.node_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid node_id in binding: {binding.node_id}")

    node = _find_node(nodes, node_id_int)
    if node is None:
        raise HTTPException(status_code=400, detail=f"Node with id={node_id_int} not found")

    field = binding.field

    node_inputs = node.get("inputs")
    widgets_values = node.get("widgets_values")

    # ------------------------------------------------------------
    # 1) widget binding: write into widgets_values[widget_idx]
    # ------------------------------------------------------------
    if isinstance(field, str) and field.startswith("widget_"):
        widx = _widget_index(field)
        if widx is None:
            return

        if not isinstance(widgets_values, list):
            node["widgets_values"] = []
            widgets_values = node["widgets_values"]

        _ensure_list_size(widgets_values, widx)
        widgets_values[widx] = value

        # optional: also update literal duplication in node_inputs list
        if isinstance(node_inputs, list):
            _try_set_nth_literal_in_inputs(node_inputs, widx, value)

        return

    # ------------------------------------------------------------
    # 2) dict inputs: simple field name set
    # ------------------------------------------------------------
    if isinstance(node_inputs, dict):
        # binding.field must be the actual input name ("text", "width", etc)
        node_inputs[str(field)] = value
        return

    # ------------------------------------------------------------
    # 3) list inputs: can be:
    #    - literals
    #    - dicts describing ports with link/widget metadata
    #    Here, "0"/0 means widget index, not port index.
    # ------------------------------------------------------------
    if isinstance(node_inputs, list):
        widx = _widget_index(field)
        if widx is None:
            # if someone passed non-widget field for list-inputs — ignore safely
            return

        # Prefer widgets_values if present (UI truth source)
        if isinstance(widgets_values, list):
            _ensure_list_size(widgets_values, widx)
            widgets_values[widx] = value

        # Also try update literal duplication
        _try_set_nth_literal_in_inputs(node_inputs, widx, value)
        return

    # unknown structure
    return


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

    # ------------------------------------------------------------
    # 0) Build protected bindings: anything that is TEXT must not be overwritten by PARAMS
    # ------------------------------------------------------------
    protected = set()
    for t in spec.inputs.text:
        if t.binding:
            protected.add((str(t.binding.node_id), str(t.binding.field)))

    # ------------------------------------------------------------
    # 1) PARAMS (first) — but don't overwrite TEXT bindings
    # ------------------------------------------------------------
    for param in spec.inputs.params:
        value = param_inputs.get(param.key, param.default)
        if value is None or not param.binding:
            continue

        # map by mode if needed
        if param.binding.map:
            if mode not in param.binding.map:
                raise HTTPException(status_code=400, detail=f'Mode "{mode}" not supported for "{param.key}"')
            value = param.binding.map[mode]

        bkey = (str(param.binding.node_id), str(param.binding.field))
        if bkey in protected:
            # This param targets the same place as a TEXT input (e.g., node 6 widget_0)
            # Skip it so TEXT controls this binding.
            continue

        apply_binding(workflow, param.binding, value)

    # ------------------------------------------------------------
    # 2) IMAGES
    # ------------------------------------------------------------
    for img in spec.inputs.images:
        if img.modes and mode not in img.modes:
            continue
        if img.key not in uploaded_files:
            continue
        if not img.binding:
            continue
        apply_binding(workflow, img.binding, uploaded_files[img.key])

    # ------------------------------------------------------------
    # 3) MASK
    # ------------------------------------------------------------
    if spec.inputs.mask:
        mask = spec.inputs.mask
        if mask.key in uploaded_files and mask.binding:
            apply_binding(workflow, mask.binding, uploaded_files[mask.key])

    # ------------------------------------------------------------
    # 4) TEXT (last) — final authority
    # ------------------------------------------------------------
    for inp in spec.inputs.text:
        if inp.key not in text_inputs:
            continue
        if not inp.binding:
            continue
        apply_binding(workflow, inp.binding, text_inputs[inp.key])

    return workflow
