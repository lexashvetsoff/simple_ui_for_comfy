from typing import Dict, Any, Tuple, List


class ComfyPromptBuildError(Exception):
    pass


# slot_index -> input_name
NODE_INPUT_SLOTS: Dict[str, list[str]] = {
    "CLIPTextEncode": ["clip", "text"],
    "BasicScheduler": ["model", "scheduler", "steps", "denoise"],
    "BasicGuider": ["model", "conditioning"],
    "SamplerCustomAdvanced": ["noise", "guider", "sampler", "sigmas", "latent_image"],
    "KSamplerSelect": ["sampler_name"],
    "RandomNoise": ["noise_seed"],
    "EmptyLatentImage": ["width", "height", "batch_size"],
    "VAELoader": ["vae_name"],
    "VAEDecode": ["samples", "vae"],
    "UNETLoader": ["unet_name", "weight_dtype"],
    "DualCLIPLoader": ["clip_name1", "clip_name2", "type", "device"],
    "PreviewImage": ["images"],
}


def build_prompt_from_ui_workflow(workflow: dict) -> Dict[str, Any]:
    """
    Converts ComfyUI UI-workflow JSON into execution Prompt Graph.

    Output:
    {
        "prompt": {
            "node_id": {
                "class_type": "...",
                "inputs": { "name": value | [node_id, slot_index] }
            }
        }
    }
    """
    if "nodes" not in workflow or not isinstance(workflow["nodes"], list):
        raise ComfyPromptBuildError("workflow['nodes'] must be a list")

    nodes = workflow["nodes"]
    links = workflow.get("links", [])

    # 1) Index nodes by id
    node_map: Dict[int, dict] = {}
    for node in nodes:
        node_id = node.get("id")
        class_type = node.get("class_type")

        if node_id is None:
            raise ComfyPromptBuildError("Node missing 'id'")
        if not class_type:
            raise ComfyPromptBuildError(f"Node {node_id} missing 'class_type'")

        node_map[int(node_id)] = node

    # 2) Build link map: dst_node_id -> dst_slot -> (src_node_id, src_output_slot)
    link_map: Dict[int, Dict[int, Tuple[int, int]]] = {}
    for link in links:
        # [link_id, src_node_id, src_slot, dst_node_id, dst_slot, type]
        if not isinstance(link, list) or len(link) < 6:
            continue
        _, src_id, src_slot, dst_id, dst_slot, _ = link
        link_map.setdefault(int(dst_id), {})[int(dst_slot)] = (int(src_id), int(src_slot))

    # 3) Build prompt graph
    prompt: Dict[str, Dict[str, Any]] = {}

    for node_id, node in node_map.items():
        class_type = node["class_type"]
        slot_names = NODE_INPUT_SLOTS.get(class_type)

        if not slot_names:
            raise ComfyPromptBuildError(f"Unknown input schema for node class '{class_type}'")

        inputs: Dict[str, Any] = {}
        widget_values = node.get("widgets_values", [])
        if widget_values is None:
            widget_values = []
        if not isinstance(widget_values, list):
            widget_values = []

        # 3.1) Linked inputs first (authoritative)
        dst_links = link_map.get(node_id, {})
        for dst_slot, (src_id, src_slot) in dst_links.items():
            if dst_slot >= len(slot_names):
                raise ComfyPromptBuildError(
                    f"Slot index {dst_slot} out of range for {class_type}"
                )
            input_name = slot_names[dst_slot]
            inputs[input_name] = [str(src_id), src_slot]

        # 3.2) Widget/literal inputs:
        # IMPORTANT: widgets_values correspond ONLY to the remaining (non-linked) inputs, sequentially.
        remaining_names: List[str] = [n for n in slot_names if n not in inputs]

        for value, input_name in zip(widget_values, remaining_names):
            inputs[input_name] = value

        # 3.3) Final node assembly
        prompt[str(node_id)] = {
            "class_type": class_type,
            "inputs": inputs,
        }

    if not prompt:
        raise ComfyPromptBuildError("Prompt graph is empty")

    return {"prompt": prompt}
