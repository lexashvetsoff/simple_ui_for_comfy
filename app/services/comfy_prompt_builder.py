from typing import Dict, Any, Tuple, List, Optional


class ComfyPromptBuildError(Exception):
    pass


def _node_class_type(node: dict) -> str:
    # UI-json: "type"
    # API-ish: "class_type"
    # fallback: properties["Node name for S&R"]
    ct = node.get("class_type") or node.get("type")
    if not ct:
        props = node.get("properties") or {}
        ct = props.get("Node name for S&R")
    return str(ct or "")


def _is_muted(node: dict) -> bool:
    # В воркфлоу mute обычно = 2
    return node.get("mode") == 2


def _is_bypass(node: dict) -> bool:
    # В воркфлоу bypass часто = 4
    return node.get("mode") == 4


def _extract_widget_names_from_inputs_list(node_inputs: list) -> List[str]:
    names: List[str] = []
    for item in node_inputs:
        if isinstance(item, dict):
            if item.get("link") is not None:
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def _extract_widget_names_from_ue_properties(node: dict) -> List[str]:
    props = node.get("properties") or {}
    ue = props.get("ue_properties") or {}
    w = ue.get("widget_ue_connectable") or {}
    if isinstance(w, dict):
        return [k for k in w.keys()]
    return []


def build_prompt_from_ui_workflow(workflow: dict) -> Dict[str, Any]:
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
        """
        Возвращает реальный источник для (src_id, src_slot),
        учитывая mute/bypass цепочки.
        """
        node = node_map.get(src_id)
        if not node:
            return None

        # muted: источника нет
        if _is_muted(node):
            return None

        # bypass: выход ноды = её "подходящий" вход
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
                    # стараемся подобрать вход того же типа, что и выход
                    if out_type and inp.get("type") == out_type:
                        passthrough_slot = i
                        break
                # fallback: первый связанный вход
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

        # обычная нода
        return (src_id, src_slot)

    # 4) build prompt graph
    prompt: Dict[str, Dict[str, Any]] = {}

    for node_id, node in node_map.items():
        if _is_muted(node):
            continue  # mute ноды вообще не включаем в prompt

        class_type = _node_class_type(node)
        if not class_type:
            raise ComfyPromptBuildError(f"Node {node_id} has no type/class_type")

        node_inputs = node.get("inputs", [])
        widgets_values = node.get("widgets_values", [])
        if widgets_values is None or not isinstance(widgets_values, list):
            widgets_values = []

        inputs: Dict[str, Any] = {}

        if isinstance(node_inputs, list):
            widget_names = _extract_widget_names_from_inputs_list(node_inputs)
            if not widget_names:
                widget_names = _extract_widget_names_from_ue_properties(node)

            widget_index = 0
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

                if widget_index < len(widget_names):
                    wname = widget_names[widget_index]
                else:
                    wname = f"widget_{widget_index}"

                inputs[str(wname)] = widgets_values[widget_index]
                widget_index += 1

        elif isinstance(node_inputs, dict):
            # редко, но поддержим
            for name, value in node_inputs.items():
                inputs[str(name)] = value

        else:
            raise ComfyPromptBuildError(
                f"Unsupported node.inputs type for node {node_id}: {type(node_inputs)}"
            )

        prompt[str(node_id)] = {
            "class_type": class_type,
            "inputs": inputs,
        }

    return {"prompt": prompt}
