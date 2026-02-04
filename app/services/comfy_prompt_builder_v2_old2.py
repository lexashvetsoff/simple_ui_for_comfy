from __future__ import annotations
import random
from typing import Any, Dict, Tuple, Optional, List

from app.services.comfy_prompt_builder import (
    ComfyPromptBuildError,
    _node_class_type,
    _is_muted,
    _is_bypass
)


def _schema_for_class(object_info: Dict[str, Any], class_type: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    info = (object_info or {}).get(class_type) or {}
    inputs = info.get("input") or {}
    required = inputs.get("required") or {}
    optional = inputs.get("optional") or {}
    if not isinstance(required, dict):
        required = {}
    if not isinstance(optional, dict):
        optional = {}
    return required, optional


def _widget_field_order(object_info: Dict[str, Any], class_type: str) -> List[str]:
    required, optional = _schema_for_class(object_info, class_type)
    fields: List[str] = []
    for k in required.keys():
        fields.append(str(k))
    for k in optional.keys():
        ks = str(k)
        if ks not in fields:
            fields.append(ks)
    return fields




_SEED_MODES = {"randomize", "fixed", "increment", "decrement"}

def _align_widgets_values_for_fields(node_type: str, widget_fields: list[str], widgets_values: list):
    """Align UI `widgets_values` with `widget_fields` derived from /object_info.

    Some nodes include UI-only seed mode values (e.g. 'randomize' / 'fixed') inside widgets_values
    that are NOT present in /object_info input schema. This causes a 1-slot shift and type errors.

    Strategy:
      - If a seed-mode token sits immediately after the 'seed' field, drop it.
      - Else, if the last value looks like a seed-mode token, drop it.
      - After dropping, if mode was 'randomize' -> set seed to a new random int64.
    """
    if not isinstance(widgets_values, list) or not isinstance(widget_fields, list):
        return widgets_values

    if len(widgets_values) <= len(widget_fields):
        return widgets_values

    wv = list(widgets_values)

    # Best-effort: remove seed mode token located right after 'seed'
    seed_mode = None
    try:
        seed_i = widget_fields.index("seed")
    except ValueError:
        seed_i = None

    if seed_i is not None:
        mode_pos = seed_i + 1
        if mode_pos < len(wv) and isinstance(wv[mode_pos], str) and wv[mode_pos].strip().lower() in _SEED_MODES:
            seed_mode = wv[mode_pos].strip().lower()
            wv.pop(mode_pos)

    # Fallback: sometimes mode is the very last widget value
    if seed_mode is None and len(wv) > len(widget_fields):
        if isinstance(wv[-1], str) and wv[-1].strip().lower() in _SEED_MODES:
            seed_mode = wv[-1].strip().lower()
            wv.pop(-1)

    # Still too long? Trim tail (UI-only leftovers).
    while len(wv) > len(widget_fields):
        wv.pop(-1)

    # Apply randomize behavior
    if seed_mode == "randomize" and seed_i is not None and seed_i < len(wv):
        wv[seed_i] = random.randint(0, 2**63 - 1)

    return wv
def build_prompt_from_ui_workflow_v2(workflow: dict, object_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds ComfyUI API prompt from UI workflow JSON (nodes+links),
    using /object_info to map widgets_values -> correct input field names.
    """
    if "nodes" not in workflow or not isinstance(workflow["nodes"], list):
        raise ComfyPromptBuildError("workflow['nodes'] must be a list")

    nodes = workflow["nodes"]
    links = workflow.get("links", [])

    # 1) index nodes
    node_map: Dict[int, dict] = {}
    for node in nodes:
        nid = node.get("id")
        if nid is None:
            raise ComfyPromptBuildError("Node missing 'id'")
        node_map[int(nid)] = node

    # 2) link map: dst_node_id -> dst_input_slot -> (src_node_id, src_output_slot)
    link_map: Dict[int, Dict[int, Tuple[int, int]]] = {}
    for link in links:
        if not isinstance(link, list) or len(link) < 6:
            continue
        _, src_id, src_slot, dst_id, dst_slot, _ = link
        try:
            link_map.setdefault(int(dst_id), {})[int(dst_slot)] = (int(src_id), int(src_slot))
        except Exception:
            continue

    # 3) resolver: учитываем mute/bypass
    def resolve_source(src_id: int, src_slot: int) -> Optional[Tuple[int, int]]:
        node = node_map.get(src_id)
        if not node:
            return None

        if _is_muted(node):
            return None

        if _is_bypass(node):
            node_inputs = node.get("inputs") or []
            node_outputs = node.get("outputs") or []

            out_type = None
            if isinstance(node_outputs, list) and src_slot < len(node_outputs):
                out_type = (node_outputs[src_slot] or {}).get("type")

            passthrough_slot = None
            if isinstance(node_inputs, list):
                for i, inp in enumerate(node_inputs):
                    if not isinstance(inp, dict):
                        continue
                    if inp.get("link") is None:
                        continue
                    if out_type and inp.get("type") == out_type:
                        passthrough_slot = i
                        break
                if passthrough_slot is None:
                    for i, inp in enumerate(node_inputs):
                        if isinstance(inp, dict) and inp.get("link") is not None:
                            passthrough_slot = i
                            break

            if passthrough_slot is None:
                return None

            m = link_map.get(src_id, {})
            if passthrough_slot not in m:
                return None

            prev_src_id, prev_src_slot = m[passthrough_slot]
            return resolve_source(prev_src_id, prev_src_slot) or (prev_src_id, prev_src_slot)

        return (src_id, src_slot)

    # 4) build prompt graph
    prompt: Dict[str, Dict[str, Any]] = {}

    for node_id, node in node_map.items():
        if _is_muted(node):
            continue

        class_type = _node_class_type(node)
        if not class_type:
            raise ComfyPromptBuildError(f"Node {node_id} has no type/class_type")

        node_inputs = node.get("inputs", [])
        widgets_values = node.get("widgets_values", [])
        if widgets_values is None or not isinstance(widgets_values, list):
            widgets_values = []

        widget_fields = _widget_field_order(object_info, class_type)

        widgets_values = _align_widgets_values_for_fields(class_type, widget_fields, widgets_values)
        inputs: Dict[str, Any] = {}
        widget_index = 0

        if isinstance(node_inputs, list):
            for slot_index, item in enumerate(node_inputs):
                # linked
                if isinstance(item, dict) and item.get("link") is not None:
                    m = link_map.get(node_id, {})
                    if slot_index not in m:
                        continue

                    raw_src_id, raw_src_slot = m[slot_index]
                    resolved = resolve_source(raw_src_id, raw_src_slot)
                    if not resolved:
                        continue

                    src_id2, src_slot2 = resolved
                    in_name = item.get("name")
                    if not in_name:
                        continue

                    inputs[str(in_name)] = [str(src_id2), int(src_slot2)]
                    continue

                # widget literal
                if widget_index >= len(widgets_values):
                    break

                field_name = widget_fields[widget_index] if widget_index < len(widget_fields) else f"widget_{widget_index}"
                inputs[str(field_name)] = widgets_values[widget_index]
                widget_index += 1

        elif isinstance(node_inputs, dict):
            for name, value in node_inputs.items():
                inputs[str(name)] = value
        else:
            raise ComfyPromptBuildError(f"Unsupported node.inputs type for node {node_id}: {type(node_inputs)}")

        prompt[str(node_id)] = {"class_type": class_type, "inputs": inputs}

    return {"prompt": prompt}
