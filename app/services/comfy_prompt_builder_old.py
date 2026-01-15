from typing import Dict, Any, Tuple, List


class ComfyPromptBuildError(Exception):
    pass


def _extract_widget_names_from_inputs_list(node_inputs: list) -> List[str]:
    """
    Из UI формата node["inputs"] (list) пытаемся извлечь имена виджетов в правильном порядке.
    В ComfyUI UI-json виджетные элементы часто выглядят как dict с {"name": "...", "widget": {...}, "link": null}
    """
    names: List[str] = []
    for item in node_inputs:
        if isinstance(item, dict):
            # link != None => это связанный вход, не виджет
            if item.get("link") is not None:
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def _extract_widget_names_from_ue_properties(node: dict) -> List[str]:
    """
    Fallback: берём имена виджетов из node["properties"]["ue_properties"]["widget_ue_connectable"].
    Обычно порядок ключей соответствует widgets_values.
    """
    props = node.get("properties") or {}
    ue = props.get("ue_properties") or {}
    w = ue.get("widget_ue_connectable") or {}
    if isinstance(w, dict):
        return [k for k in w.keys()]
    return []


def build_prompt_from_ui_workflow(workflow: dict) -> Dict[str, Any]:
    """
    Converts ComfyUI UI-workflow JSON into execution Prompt Graph.

    Returns:
      {"prompt": { "<node_id>": {"class_type": "...", "inputs": {...}}, ... }}
    """
    if "nodes" not in workflow or not isinstance(workflow["nodes"], list):
        raise ComfyPromptBuildError("workflow['nodes'] must be a list")

    nodes = workflow["nodes"]
    links = workflow.get("links", [])

    # ------------------------------------------------------------
    # 1) Index nodes by id
    # ------------------------------------------------------------
    node_map: Dict[int, dict] = {}
    for node in nodes:
        nid = node.get("id")
        if nid is None:
            raise ComfyPromptBuildError("Node missing 'id'")
        if "class_type" not in node:
            raise ComfyPromptBuildError(f"Node {nid} missing 'class_type'")
        node_map[int(nid)] = node

    # ------------------------------------------------------------
    # 2) Build link map: dst_node_id -> dst_input_slot -> (src_node_id, src_output_slot)
    # links: [link_id, src_id, src_slot, dst_id, dst_slot, type]
    # ------------------------------------------------------------
    link_map: Dict[int, Dict[int, Tuple[int, int]]] = {}
    for link in links:
        if not isinstance(link, list) or len(link) < 6:
            continue
        _, src_id, src_slot, dst_id, dst_slot, _ = link
        try:
            link_map.setdefault(int(dst_id), {})[int(dst_slot)] = (int(src_id), int(src_slot))
        except Exception:
            continue

    # ------------------------------------------------------------
    # 3) Build prompt graph
    # ------------------------------------------------------------
    prompt: Dict[str, Dict[str, Any]] = {}

    for node_id, node in node_map.items():
        node_inputs = node.get("inputs", [])
        widgets_values = node.get("widgets_values", [])

        if widgets_values is None:
            widgets_values = []
        if not isinstance(widgets_values, list):
            widgets_values = []

        inputs: Dict[str, Any] = {}

        # ----------------------------
        # 3.1 UI format: inputs is list
        # ----------------------------
        if isinstance(node_inputs, list):
            # именование виджетов:
            widget_names = _extract_widget_names_from_inputs_list(node_inputs)
            if not widget_names:
                widget_names = _extract_widget_names_from_ue_properties(node)

            widget_index = 0

            for slot_index, item in enumerate(node_inputs):
                # Linked input
                if isinstance(item, dict) and item.get("link") is not None:
                    # должен быть в link_map
                    m = link_map.get(node_id, {})
                    if slot_index not in m:
                        continue
                    src_id, src_slot = m[slot_index]
                    in_name = item.get("name")
                    if not in_name:
                        continue
                    inputs[str(in_name)] = [str(src_id), int(src_slot)]
                    continue

                # Widget / literal input (занимает widgets_values[widget_index])
                if widget_index >= len(widgets_values):
                    break

                # Берём имя для этого виджета
                if widget_index < len(widget_names):
                    wname = widget_names[widget_index]
                else:
                    # крайний fallback — но лучше не доводить до этого
                    wname = f"widget_{widget_index}"

                inputs[str(wname)] = widgets_values[widget_index]
                widget_index += 1

        # ----------------------------
        # 3.2 inputs already dict (редко)
        # ----------------------------
        elif isinstance(node_inputs, dict):
            for name, value in node_inputs.items():
                # linked dict input
                if isinstance(value, dict) and value.get("link") is not None:
                    # здесь надо бы тоже ссылку восстановить, но в твоих workflow это обычно list-формат
                    continue
                inputs[str(name)] = value

        else:
            # неизвестный формат inputs
            raise ComfyPromptBuildError(f"Unsupported node.inputs type for node {node_id}: {type(node_inputs)}")

        prompt[str(node_id)] = {
            "class_type": node["class_type"],
            "inputs": inputs,
        }

    return {"prompt": prompt}
