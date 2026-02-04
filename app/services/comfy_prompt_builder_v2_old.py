from __future__ import annotations
import random
from typing import Any, Dict, Tuple, Optional, List

from app.services.comfy_prompt_builder import (
    ComfyPromptBuildError,
    _node_class_type,
    _is_muted,
    _is_bypass,
)

SEED_MODES = {"randomize", "fixed", "increment", "decrement"}


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


def _schema_input_keys(object_info: Dict[str, Any], class_type: str) -> set[str]:
    required, optional = _schema_for_class(object_info, class_type)
    keys = set()
    for k in required.keys():
        keys.add(str(k))
    for k in optional.keys():
        keys.add(str(k))
    return keys


def _schema_input_expected_type(object_info: Dict[str, Any], class_type: str, field: str) -> Optional[str]:
    """
    Extract expected type token from /object_info for a given input key.
    Usually it's like: "seed": ["INT", {...}] or ["FLOAT", {...}] or ["BOOLEAN", ...] or ["COMBO", {...}]
    """
    required, optional = _schema_for_class(object_info, class_type)
    spec = None
    if field in required:
        spec = required.get(field)
    elif field in optional:
        spec = optional.get(field)

    if isinstance(spec, list) and spec:
        t = spec[0]
        if isinstance(t, str):
            return t.upper()

    if isinstance(spec, str):
        return spec.upper()

    return None


def build_prompt_from_ui_workflow_v2(workflow: dict, object_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds ComfyUI API prompt from UI workflow JSON (nodes+links).
    Key fixes:
      1) Linked inputs may still reserve a widgets_values slot -> we must consume it to keep alignment.
      2) Some nodes have UI-only seed_mode (randomize/fixed/increment/decrement) that is not present in schema.
         We detect and skip it when it mismatches expected type, and apply it to seed.
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

    # 3) resolver (mute/bypass aware)
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

        schema_keys = _schema_input_keys(object_info, class_type)

        inputs: Dict[str, Any] = {}
        widget_index = 0

        # we may detect a seed_mode token while scanning widgets_values
        detected_seed_mode: Optional[str] = None
        detected_seed_field: Optional[str] = None  # usually "seed"

        if isinstance(node_inputs, list):
            for slot_index, item in enumerate(node_inputs):
                if not isinstance(item, dict):
                    continue

                in_name = item.get("name")
                if not in_name:
                    continue
                in_name = str(in_name)

                # Linked input
                if item.get("link") is not None:
                    m = link_map.get(node_id, {})
                    if slot_index in m:
                        raw_src_id, raw_src_slot = m[slot_index]
                        resolved = resolve_source(raw_src_id, raw_src_slot)
                        if resolved:
                            src_id2, src_slot2 = resolved
                            inputs[in_name] = [str(src_id2), int(src_slot2)]

                    # IMPORTANT FIX:
                    # UI often still reserves a widgets_values slot for a linked input if it has a widget descriptor.
                    # Example: PollinationsTextGen prompt input is linked but widgets_values starts with "".
                    if isinstance(item.get("widget"), dict):
                        if widget_index < len(widgets_values):
                            widget_index += 1
                    continue

                # Widget (non-linked) input
                if widget_index >= len(widgets_values):
                    break

                expected_t = _schema_input_expected_type(object_info, class_type, in_name)

                # consume value, but allow skipping UI-only seed_mode tokens that appear in widgets_values
                def _peek() -> Any:
                    return widgets_values[widget_index] if widget_index < len(widgets_values) else None

                def _is_seed_mode_token(v: Any) -> bool:
                    return isinstance(v, str) and v.strip().lower() in SEED_MODES

                # Heuristic: if current value is seed_mode token but current field expects INT/FLOAT/BOOLEAN -> skip it
                v = _peek()
                if _is_seed_mode_token(v) and expected_t in {"INT", "FLOAT", "BOOLEAN"}:
                    detected_seed_mode = v.strip().lower()
                    # We can't be 100% sure it belongs to seed, but in practice it is always seed-mode UI widget.
                    detected_seed_field = "seed"
                    widget_index += 1
                    if widget_index >= len(widgets_values):
                        break
                    v = _peek()

                # write only schema-recognized inputs
                if in_name in schema_keys:
                    inputs[in_name] = v

                widget_index += 1

        elif isinstance(node_inputs, dict):
            # API-ish workflows
            for name, value in node_inputs.items():
                inputs[str(name)] = value
        else:
            raise ComfyPromptBuildError(f"Unsupported node.inputs type for node {node_id}: {type(node_inputs)}")

        # Apply detected seed mode to seed when possible
        if detected_seed_mode and detected_seed_field and detected_seed_field in inputs:
            try:
                seed_val = int(inputs.get(detected_seed_field))
            except Exception:
                seed_val = None

            if seed_val is not None:
                if detected_seed_mode == "randomize":
                    inputs[detected_seed_field] = random.randint(0, 2**63 - 1)
                elif detected_seed_mode == "increment":
                    inputs[detected_seed_field] = seed_val + 1
                elif detected_seed_mode == "decrement":
                    inputs[detected_seed_field] = max(0, seed_val - 1)
                # fixed -> leave as is

        prompt[str(node_id)] = {"class_type": class_type, "inputs": inputs}

    return {"prompt": prompt}
