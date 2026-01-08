import re
from typing import Dict, Any, List


TEXT_NODE_TYPES = {
    "CLIPTextEncode",
    "CLIPTextEncodeSDXL",
    "TextEncode",
}


IMAGE_NODE_TYPES = {
    "LoadImage",
    "LoadImageFromPath",
}


OUTPUT_NODE_TYPES = {
    "SaveImage",
    "PreviewImage",
}


IGNORED_FIELDS = {
    "model",
    "clip",
    "vae",
    "samples",
    "latent",
    "conditioning",
}


# def _normalize_nodes(workflow_json: Dict[str, Any]) -> List[Dict[str, Any]]:
#     """
#     ComfyUI workflow may store nodes as:
#     - list (real-world case)
#     - dict (theoretical / old case)

#     We normalize everything to a list of node dicts.
#     """
#     nodes = workflow_json.get('nodes', [])

#     if isinstance(nodes, list):
#         return nodes
    
#     if isinstance(nodes, dict):
#         return [
#             {'id': k, **v} for k, v in nodes.items()
#         ]
    
#     return []


def _normalize_nodes(workflow_json: dict) -> list[dict]:
    """
    Normalize ComfyUI workflow into list of nodes
    """
    if isinstance(workflow_json, dict):
        if "nodes" in workflow_json:
            return workflow_json["nodes"]

    if isinstance(workflow_json, list):
        return workflow_json

    raise ValueError("Invalid workflow format: nodes not found")



def generate_spec_v2(workflow_json: Dict[str, Any]) -> Dict[str, Any]:
    nodes = _normalize_nodes(workflow_json)

    spec = {
        "meta": {
            "version": "2.0",
            "title": "Generated workflow",
            "description": "Auto-generated Spec v2 (edit me)",
        },
        "modes": [
            {"id": "default", "label": "Default"}
        ],
        "inputs": {
            "text": [],
            "params": [],
            "images": [],
            "mask": None,
        },
        "outputs": [],
    }

    for node in nodes:
        node_id = str(node.get("id"))
        # class_type = node.get("type") or node.get("class_type", "")
        class_type = node.get("class_type") or node.get("type") or ""
        inputs = node.get("inputs", {})

        # IMPORTANT: only dict-inputs are UI-relevant
        if not isinstance(inputs, dict):
            continue

        # TEXT INPUT
        if class_type in TEXT_NODE_TYPES and "text" in inputs:
            spec["inputs"]["text"].append({
                "key": f"prompt_{node_id}",
                "label": "Prompt",
                "type": "text",
                "required": True,
                "binding": {
                    "node_id": node_id,
                    "field": "text",
                },
            })

        # IMAGE INPUT
        if class_type in IMAGE_NODE_TYPES:
            spec["inputs"]["images"].append({
                "key": f"image_{node_id}",
                "label": "Image",
                "modes": ["default"],
                "binding": {
                    "node_id": node_id,
                    "field": "image",
                },
            })

        # PARAMS
        for field, value in inputs.items():
            if field in IGNORED_FIELDS:
                continue

            if isinstance(value, int):
                spec["inputs"]["params"].append({
                    "key": f"{field}_{node_id}",
                    "label": field.replace("_", " ").title(),
                    "type": "int",
                    "default": value,
                    "binding": {
                        "node_id": node_id,
                        "field": field,
                    },
                })

            elif isinstance(value, float):
                spec["inputs"]["params"].append({
                    "key": f"{field}_{node_id}",
                    "label": field.replace("_", " ").title(),
                    "type": "float",
                    "default": value,
                    "binding": {
                        "node_id": node_id,
                        "field": field,
                    },
                })

            elif isinstance(value, str):
                spec["inputs"]["params"].append({
                    "key": f"{field}_{node_id}",
                    "label": field.replace("_", " ").title(),
                    "type": "text",
                    "default": value,
                    "binding": {
                        "node_id": node_id,
                        "field": field,
                    },
                })

    # OUTPUTS
    for node in nodes:
        node_id = str(node.get("id"))
        if node.get("type") in OUTPUT_NODE_TYPES:
            spec["outputs"].append({
                "key": "image",
                "type": "image",
                "binding": {
                    "node_id": node_id,
                    "field": "images",
                },
            })

    return spec
