# app/services/workflow_mapper.py
import re
import json
import random
from copy import deepcopy
from typing import Any, Dict

from fastapi import HTTPException

from app.schemas.workflow_spec_v2 import (
    WorkflowSpecV2,
    ParamInputSpec,
    BindingSpec,
)

from PIL import Image, ImageOps
from pathlib import Path


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def normalize_workflow_for_comfy(workflow: dict) -> dict:
    """
    Converts ComfyUI UI-exported workflow to API-ready prompt format.
    """
    for node in workflow.get("nodes", []):
        # UI uses "type", API requires "class_type"
        if "class_type" not in node:
            node["class_type"] = node.get("type")
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


def _find_widget_field_index_in_inputs_list(node_inputs: list, field_name: str) -> int | None:
    """
    Для UI-list inputs находим "индекс виджета" по имени поля.
    UI-list состоит из dict'ов (порты/виджеты) и иногда литералов.
    Нам нужен индекс среди ВИДЖЕТОВ (то есть dict без link, но с widget/name).
    """
    if not isinstance(field_name, str) or not field_name:
        return None

    widget_pos = 0
    for item in node_inputs:
        if not isinstance(item, dict):
            continue
        if item.get("link") is not None:
            continue

        name = item.get("name")
        if name == field_name:
            return widget_pos

        widget_pos += 1

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


def _node_type(node: dict) -> str:
    t = node.get("class_type") or node.get("type") or ""
    if not t:
        props = node.get("properties") or {}
        t = props.get("Node name for S&R") or ""
    return str(t)


def _is_empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _coerce_value(param: ParamInputSpec, raw_value: Any) -> Any:
    """
    - Empty values ("", None) do NOT overwrite defaults.
    - Coerce to param.type where possible.
    - If coercion fails -> fallback to default.
    """
    if _is_empty(raw_value):
        return param.default

    value = raw_value
    try:
        if param.type == "int":
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                return int(float(value.strip()))
            return int(value)

        if param.type == "float":
            if isinstance(value, bool):
                return float(int(value))
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                return float(value.strip())
            return float(value)

        if param.type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                s = value.strip().lower()
                if s in {"true", "1", "yes", "y", "on"}:
                    return True
                if s in {"false", "0", "no", "n", "off"}:
                    return False
                return True
            return bool(value)

        return value

    except Exception:
        return param.default


def _enforce_choices(param: ParamInputSpec, value: Any) -> Any:
    choices = getattr(param, "choices", None)
    if choices:
        if value not in choices:
            return param.default
    return value


def _ensure_inputs_dict(node: dict) -> dict:
    node_inputs = node.get("inputs")
    if not isinstance(node_inputs, dict):
        node["inputs"] = {}
        node_inputs = node["inputs"]
    return node_inputs


# # embed mask into alpha channel (for workflows where mask comes from LoadImage.MASK)
# def _embed_mask_into_alpha(base_path: str, mask_path: str) -> str:
#     base_p = Path(base_path)
#     out_path = base_p.with_name(base_p.stem + "__masked.png")

#     with Image.open(base_path) as im_base:
#         im_base = im_base.convert("RGBA")

#         with Image.open(mask_path) as im_mask:
#             # mask editor exports black bg + white stroke → luminance works
#             im_mask_l = im_mask.convert("L")

#         if im_mask_l.size != im_base.size:
#             im_mask_l = im_mask_l.resize(im_base.size, resample=Image.NEAREST)

#         r, g, b, _a = im_base.split()
#         im_out = Image.merge("RGBA", (r, g, b, im_mask_l))
#         im_out.save(out_path, format="PNG")

#     return str(out_path)


def _embed_mask_into_alpha(base_path: str, mask_path: str) -> str:
    base_p = Path(base_path)
    out_path = base_p.with_name(base_p.stem + "__masked.png")

    with Image.open(base_path) as im_base:
        im_base = im_base.convert("RGBA")

        with Image.open(mask_path) as im_mask:
            # инверсия маски
            im_mask_l = ImageOps.invert(im_mask.convert("L"))

        if im_mask_l.size != im_base.size:
            im_mask_l = im_mask_l.resize(im_base.size, resample=Image.NEAREST)

        r, g, b, _a = im_base.split()
        im_out = Image.merge("RGBA", (r, g, b, im_mask_l))
        im_out.save(out_path, format="PNG")

    return str(out_path)


# ------------------------------------------------------------
# Binding application
# ------------------------------------------------------------

def apply_binding(workflow: dict, binding: BindingSpec, value: Any) -> None:
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

    if isinstance(field, str) and field.startswith("widget_"):
        widx = _widget_index(field)
        if widx is None:
            return

        if not isinstance(widgets_values, list):
            node["widgets_values"] = []
            widgets_values = node["widgets_values"]

        _ensure_list_size(widgets_values, widx)
        widgets_values[widx] = value

        if isinstance(node_inputs, list):
            _try_set_nth_literal_in_inputs(node_inputs, widx, value)

        return

    if isinstance(node_inputs, dict):
        node_inputs[str(field)] = value
        return

    if isinstance(node_inputs, list):
        widx = _widget_index(field)
        if widx is None:
            if isinstance(field, str):
                widx = _find_widget_field_index_in_inputs_list(node_inputs, field)
            if widx is None:
                return

        if not isinstance(widgets_values, list):
            node["widgets_values"] = []
            widgets_values = node["widgets_values"]

        _ensure_list_size(widgets_values, widx)
        widgets_values[widx] = value

        _try_set_nth_literal_in_inputs(node_inputs, widx, value)
        return

    return


def apply_random_seed_if_needed(workflow: dict):
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return

    for node in nodes:
        if not isinstance(node, dict):
            continue

        if _node_type(node) != "RandomNoise":
            continue

        widgets = node.get("widgets_values")
        if not isinstance(widgets, list) or len(widgets) < 2:
            continue

        mode = widgets[1]
        if isinstance(mode, str) and mode.lower() == "randomize":
            widgets[0] = random.randint(0, 2**63 - 1)


def apply_param(workflow: dict, param: ParamInputSpec, value: Any) -> None:
    if not param.binding:
        return

    nodes = workflow.get("nodes", [])
    try:
        nid = int(param.binding.node_id)
    except Exception:
        return

    node = _find_node(nodes, nid)
    if not node:
        return

    param_name = getattr(param, "name", None)
    if isinstance(param_name, str) and param_name:
        node_inputs = _ensure_inputs_dict(node)
        node_inputs[param_name] = value

    apply_binding(workflow, param.binding, value)


# ------------------------------------------------------------
# Main mapper
# ------------------------------------------------------------

def map_inputs_to_workflow(
    *,
    workflow_json: dict,
    spec: WorkflowSpecV2,
    text_inputs: dict,
    param_inputs: dict,
    uploaded_files: dict,
    mode: str = "default",
) -> dict:
    workflow = deepcopy(workflow_json)

    modes = {m.id for m in spec.modes}
    if mode not in modes:
        raise HTTPException(status_code=400, detail=f'Invalid mode "{mode}", available: {modes}')

    protected = set()
    for t in spec.inputs.text:
        if t.binding:
            protected.add((str(t.binding.node_id), str(t.binding.field)))

    # 1) PARAMS
    for param in spec.inputs.params:
        if not param.binding:
            continue

        raw = param_inputs.get(param.key, None)
        value = _coerce_value(param, raw)
        value = _enforce_choices(param, value)

        if param.binding.map:
            if mode not in param.binding.map:
                raise HTTPException(status_code=400, detail=f'Mode "{mode}" not supported for "{param.key}"')
            value = param.binding.map[mode]

        bkey = (str(param.binding.node_id), str(param.binding.field))
        if bkey in protected:
            continue

        apply_param(workflow, param, value)

    # 2.5) MASK PRE-PROCESS (embed into base image alpha when needed)
    if spec.inputs.mask:
        mask = spec.inputs.mask
        depends_key = getattr(mask, "depends_on", None)

        if (
            isinstance(depends_key, str)
            and depends_key in uploaded_files
            and mask.key in uploaded_files
            and mask.binding
        ):
            img_spec = next((i for i in spec.inputs.images if i.key == depends_key), None)

            # if mask.binding points to the same place as base image binding → it MUST be embedded
            if img_spec and img_spec.binding:
                same_target = (
                    str(img_spec.binding.node_id) == str(mask.binding.node_id)
                    and str(img_spec.binding.field) == str(mask.binding.field)
                )
                if same_target:
                    merged = _embed_mask_into_alpha(uploaded_files[depends_key], uploaded_files[mask.key])

                    # replace base image file with merged and drop mask from upload mapping
                    uploaded_files[depends_key] = merged
                    uploaded_files.pop(mask.key, None)

    # 2) IMAGES
    for img in spec.inputs.images:
        if img.modes and mode not in img.modes:
            continue
        if img.key not in uploaded_files:
            continue
        if not img.binding:
            continue
        apply_binding(workflow, img.binding, uploaded_files[img.key])

    # For LoadImage nodes: widget_1 = upload mode
    for img in spec.inputs.images:
        if img.key not in uploaded_files:
            continue
        if not img.binding:
            continue
        try:
            nid = int(img.binding.node_id)
        except Exception:
            continue
        node = _find_node(workflow.get("nodes", []), nid)
        if node and (node.get("type") == "LoadImage" or node.get("class_type") == "LoadImage"):
            apply_binding(workflow, BindingSpec(node_id=str(nid), field="widget_1"), "image")

    # 3) MASK (normal case: separate LoadMask node etc.)
    if spec.inputs.mask:
        mask = spec.inputs.mask
        if mask.key in uploaded_files and mask.binding:
            apply_binding(workflow, mask.binding, uploaded_files[mask.key])

    # 4) TEXT
    for inp in spec.inputs.text:
        if inp.key not in text_inputs:
            continue
        if not inp.binding:
            continue
        apply_binding(workflow, inp.binding, text_inputs[inp.key])

    apply_random_seed_if_needed(workflow)
    return workflow
