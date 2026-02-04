from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from app.services.comfy_prompt_builder import ComfyPromptBuildError, _node_class_type

SEED_MODES = {"randomize", "fixed", "increment", "decrement"}


def _apply_florence2_model_override(prompt: dict) -> None:
    """Force Florence2 loader to use a local/base model without PEFT adapter.

    Some Florence2 workflows ship a PEFT LoRA adapter repo id in the `lora` input.
    When executed via API, ComfyUI may try to download adapter_config.json and fail.
    To make it deterministic, we can set:
      - lora = ""  (disable adapter)
      - model = "MiaoshouAI/Florence-2-base-PromptGen-v2.0"
    """
    if not isinstance(prompt, dict):
        return
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        if (node.get("class_type") or node.get("type")) != "DownloadAndLoadFlorence2Model":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {}
            node["inputs"] = inputs
        # inputs["lora"] = ""
        # inputs["model"] = "MiaoshouAI/Florence-2-base-PromptGen-v2.0"
        if len(inputs['lora'].strip()) > 0:
            value_input = inputs['lora']
            inputs["lora"] = ""
            inputs["model"] = value_input


def _normalize_extra_pnginfo(extra_pnginfo: Any) -> Optional[dict]:
    # Comfy API expects dict; UI export sometimes gives a list with one dict.
    if extra_pnginfo is None:
        return None
    if isinstance(extra_pnginfo, dict):
        return extra_pnginfo
    if isinstance(extra_pnginfo, list) and extra_pnginfo:
        first = extra_pnginfo[0]
        if isinstance(first, dict):
            return first
    return None


def _build_link_map(workflow: dict) -> Dict[int, Tuple[str, int]]:
    link_map: Dict[int, Tuple[str, int]] = {}
    for link in workflow.get("links", []) or []:
        if not isinstance(link, list) or len(link) < 3:
            continue
        link_id, from_node, from_slot = link[0], link[1], link[2]
        try:
            link_map[int(link_id)] = (str(from_node), int(from_slot))
        except Exception:
            continue
    return link_map


def _value_ports_in_order(node_inputs: Any) -> List[dict]:
    """
    Determine the input entries that correspond to widgets_values, in UI order.

    Include:
      - any input dict with "widget" metadata (even if linked)
      - OR any UNLINKED scalar-ish input types that sometimes omit "widget" (e.g. PEFTLORA)
    """
    if not isinstance(node_inputs, list):
        return []

    SIMPLE_VALUE_TYPES = {
        "INT", "FLOAT", "STRING", "BOOLEAN", "COMBO",
        "PEFTLORA", "IMAGEUPLOAD",
    }

    ports: List[dict] = []
    for item in node_inputs:
        if not isinstance(item, dict):
            continue

        has_widget_meta = item.get("widget") is not None
        is_unlinked_value = (item.get("link") is None) and (str(item.get("type") or "").upper() in SIMPLE_VALUE_TYPES)

        if has_widget_meta or is_unlinked_value:
            ports.append(item)

    return ports


def _align_widgets_values_for_seed_mode(ports: List[dict], values: List[Any]) -> List[Any]:
    """
    If values contains exactly one extra entry, and we can recognize it as seed-mode, drop it.

    Patterns observed:
      - seed is first value-port  => values[1] is seed-mode (KSampler, some text gens)
      - seed is last value-port   => values[-1] is seed-mode (Florence2Run)
    """
    if not ports or not isinstance(values, list):
        return values
    if len(values) != len(ports) + 1:
        return values

    def is_mode(v: Any) -> bool:
        return isinstance(v, str) and v.strip().lower() in SEED_MODES

    first_name = (ports[0].get("name") or "").strip().lower()
    last_name = (ports[-1].get("name") or "").strip().lower()

    if first_name == "seed" and len(values) >= 2 and is_mode(values[1]):
        return [values[0]] + values[2:]
    if last_name == "seed" and is_mode(values[-1]):
        return values[:-1]

    return values


def build_prompt_from_ui_workflow_v2(workflow: dict, object_info: dict | None = None) -> dict:
    """
    Public entry point used by scheduler.

    object_info is accepted for backward compatibility but is not required by this mapper.
    """
    if not isinstance(workflow, dict):
        raise ComfyPromptBuildError("workflow must be a dict")

    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise ComfyPromptBuildError("workflow['nodes'] must be a list")

    link_map = _build_link_map(workflow)
    prompt: Dict[str, Any] = {}

    for node in nodes:
        if not isinstance(node, dict):
            continue

        # UI node modes:
        # 0 normal, 2 muted, 4 bypass. We skip muted nodes.
        if node.get("mode") == 2:
            continue

        node_id = node.get("id")
        if node_id is None:
            continue
        node_id_str = str(node_id)

        class_type = _node_class_type(node)
        if not class_type:
            continue

        node_inputs = node.get("inputs")
        widgets_values = node.get("widgets_values")

        inputs_dict: Dict[str, Any] = {}

        # 1) Links (ports)
        if isinstance(node_inputs, list):
            for item in node_inputs:
                if not isinstance(item, dict):
                    continue
                link_id = item.get("link")
                if link_id is None:
                    continue
                name = item.get("name")
                if not name:
                    continue
                src = link_map.get(int(link_id))
                if src:
                    inputs_dict[str(name)] = [src[0], src[1]]

        # 2) Widgets / values
        ports = _value_ports_in_order(node_inputs)
        if isinstance(widgets_values, list) and ports:
            aligned = _align_widgets_values_for_seed_mode(ports, widgets_values)

            n = min(len(aligned), len(ports))
            for i in range(n):
                port = ports[i]
                name = port.get("name")
                if not name:
                    continue
                # Important: consume the value always, but set only if UI input is not linked.
                if port.get("link") is None:
                    inputs_dict[str(name)] = aligned[i]

        prompt[node_id_str] = {"class_type": class_type, "inputs": inputs_dict}

    payload: Dict[str, Any] = {"prompt": prompt}

    extra = _normalize_extra_pnginfo(workflow.get("extra_pnginfo"))
    if extra is not None:
        payload["extra_pnginfo"] = extra
    
    _apply_florence2_model_override(payload.get('prompt', {}))

    return payload
