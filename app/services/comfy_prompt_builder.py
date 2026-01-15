from typing import Dict, Any, Tuple, List, Set


class ComfyPromptBuildError(Exception):
    pass


UI_ONLY_NODE_TYPES: Set[str] = {
    "Fast Groups Muter (rgthree)",
    "Image Comparer (rgthree)",
    "Note",
    "MarkdownNote",
}


def _get_class_type(node: dict) -> str:
    """
    UI workflow uses 'type'. Some exports can include 'class_type'.
    For execution prompt we need 'class_type'.
    """
    ct = node.get("class_type") or node.get("type") or ""
    return str(ct)


def _extract_widget_names_from_inputs_list(node_inputs: list) -> List[str]:
    """
    From UI format node["inputs"] (list) try to extract widget names in correct order.
    Widget items in UI-json often look like:
      {"name": "...", "widget": {...}, "link": null}
    """
    names: List[str] = []
    for item in node_inputs:
        if isinstance(item, dict):
            # link != None => connected input, not widget
            if item.get("link") is not None:
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def _extract_widget_names_from_ue_properties(node: dict) -> List[str]:
    """
    Fallback: take widget names from node["properties"]["ue_properties"]["widget_ue_connectable"].
    Often key order matches widgets_values order (Python 3.7+ preserves dict order).
    """
    props = node.get("properties") or {}
    ue = props.get("ue_properties") or {}
    w = ue.get("widget_ue_connectable") or {}
    if isinstance(w, dict):
        return [k for k in w.keys()]
    return []


def _sanitize_ui_workflow(workflow: dict) -> dict:
    """
    Remove UI-only nodes to avoid ComfyUI validation failures,
    and drop links that refer to removed nodes.
    """
    if "nodes" not in workflow or not isinstance(workflow["nodes"], list):
        raise ComfyPromptBuildError("workflow['nodes'] must be a list")

    nodes_in = workflow["nodes"]
    links_in = workflow.get("links", [])

    kept_nodes: List[dict] = []
    kept_ids: Set[int] = set()

    for n in nodes_in:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if nid is None:
            continue
        try:
            nid_int = int(nid)
        except Exception:
            continue

        ct = _get_class_type(n)
        if ct in UI_ONLY_NODE_TYPES:
            continue

        kept_nodes.append(n)
        kept_ids.add(nid_int)

    kept_links: List[list] = []
    if isinstance(links_in, list):
        for link in links_in:
            # links: [link_id, src_id, src_slot, dst_id, dst_slot, type]
            if not isinstance(link, list) or len(link) < 6:
                continue
            try:
                _, src_id, _, dst_id, _, _ = link
                if int(src_id) not in kept_ids or int(dst_id) not in kept_ids:
                    continue
                kept_links.append(link)
            except Exception:
                continue

    out = dict(workflow)
    out["nodes"] = kept_nodes
    out["links"] = kept_links
    return out


def build_prompt_from_ui_workflow(workflow: dict) -> Dict[str, Any]:
    """
    Converts ComfyUI UI-workflow JSON into execution Prompt Graph.

    Returns:
      {"prompt": { "<node_id>": {"class_type": "...", "inputs": {...}}, ... }}
    """
    workflow = _sanitize_ui_workflow(workflow)

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

        ct = _get_class_type(node)
        if not ct:
            raise ComfyPromptBuildError(f"Node {nid} missing 'type/class_type'")

        node_map[int(nid)] = node

    # ------------------------------------------------------------
    # 2) Build link map: dst_node_id -> dst_input_slot -> (src_node_id, src_output_slot)
    # links: [link_id, src_id, src_slot, dst_id, dst_slot, type]
    # ------------------------------------------------------------
    link_map: Dict[int, Dict[int, Tuple[int, int]]] = {}
    if isinstance(links, list):
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

        if widgets_values is None or not isinstance(widgets_values, list):
            widgets_values = []

        inputs: Dict[str, Any] = {}

        # ----------------------------
        # 3.1 UI format: inputs is list
        # ----------------------------
        if isinstance(node_inputs, list):
            widget_names = _extract_widget_names_from_inputs_list(node_inputs)
            if not widget_names:
                widget_names = _extract_widget_names_from_ue_properties(node)

            widget_index = 0

            for slot_index, item in enumerate(node_inputs):
                # Linked input
                if isinstance(item, dict) and item.get("link") is not None:
                    m = link_map.get(node_id, {})
                    if slot_index not in m:
                        # connected in UI but link missing after sanitize -> just skip
                        continue
                    src_id, src_slot = m[slot_index]
                    in_name = item.get("name") or item.get("localized_name") or ""
                    if not in_name:
                        continue
                    inputs[str(in_name)] = [str(src_id), int(src_slot)]
                    continue

                # Widget / literal input (occupies widgets_values[widget_index])
                if widget_index >= len(widgets_values):
                    break

                if widget_index < len(widget_names):
                    wname = widget_names[widget_index]
                else:
                    wname = f"widget_{widget_index}"

                inputs[str(wname)] = widgets_values[widget_index]
                widget_index += 1

        # ----------------------------
        # 3.2 inputs already dict (rare)
        # ----------------------------
        elif isinstance(node_inputs, dict):
            for name, value in node_inputs.items():
                # if someone stores {"link": ...} here, we'd need more logic
                if isinstance(value, dict) and value.get("link") is not None:
                    continue
                inputs[str(name)] = value

        else:
            raise ComfyPromptBuildError(
                f"Unsupported node.inputs type for node {node_id}: {type(node_inputs)}"
            )

        prompt[str(node_id)] = {
            "class_type": _get_class_type(node),
            "inputs": inputs,
        }

    return {"prompt": prompt}
