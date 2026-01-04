def generate_base_spec(workflow_json: dict) -> dict:
    inputs = []

    for node_id, node in workflow_json.get('nodes', {}).items():
        if node.get('type') == 'CLIPTextEncode':
            inputs.append({
                "key": "prompt",
                "type": "text",
                "label": "Prompt",
                "required": True
            })
        
        if node.get("type") == "LoadImage":
            inputs.append({
                "key": "init_image",
                "type": "image",
                "label": "Base image",
                "required": True
            })

        if node.get("type") == "LoadMask":
            inputs.append({
                "key": "mask",
                "type": "mask",
                "label": "Mask",
                "required": False
            })
    return {'inputs': inputs}