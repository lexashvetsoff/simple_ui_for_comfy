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


def _normalize_nodes(workflow_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(workflow_json, dict) and "nodes" in workflow_json:
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
        class_type = node.get("class_type") or node.get("type") or ""

        # ---------- TEXT INPUT ----------
        if class_type in TEXT_NODE_TYPES:
            widgets = node.get("widgets_values", [])
            if widgets and isinstance(widgets[0], str):
                spec["inputs"]["text"].append({
                    "key": f"prompt_{node_id}",
                    "label": "Prompt",
                    "type": "text",
                    "required": True,
                    "default": widgets[0],
                    "binding": {
                        "node_id": node_id,
                        "field": "widget_0",
                    },
                })

        # ---------- IMAGE INPUT ----------
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

        # ---------- PARAMS (widgets_values) ----------
        widgets = node.get("widgets_values", [])
        if isinstance(widgets, list):
            for idx, value in enumerate(widgets):
                if isinstance(value, (int, float, str)):
                    spec["inputs"]["params"].append({
                        "key": f"param_{node_id}_{idx}",
                        "label": f"{class_type} param {idx + 1}",
                        "type": (
                            "int" if isinstance(value, int)
                            else "float" if isinstance(value, float)
                            else "text"
                        ),
                        "default": value,
                        "binding": {
                            "node_id": node_id,
                            "field": f"widget_{idx}",
                        },
                    })

    # ---------- OUTPUTS ----------
    for node in nodes:
        node_id = str(node.get("id"))
        class_type = node.get("class_type") or node.get("type") or ""

        if class_type in OUTPUT_NODE_TYPES:
            spec["outputs"].append({
                "key": "image",
                "type": "image",
                "binding": {
                    "node_id": node_id,
                    "field": "images",
                },
            })

    return spec
