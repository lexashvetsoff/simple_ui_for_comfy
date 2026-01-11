from typing import Any, Dict, List


def extract_images_from_outputs(outputs: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    ComfyUI history outputs format:
    {
      "12": {"images": [{"filename": "...", "subfolder": "", "type": "temp"}]}
    }
    """
    if not isinstance(outputs, dict):
        return []
    
    images: List[Dict[str, str]] = []
    for _node_id, node_out in outputs.items():
        if not isinstance(node_out, dict):
            continue

        imgs = node_out.get('images')
        if isinstance(imgs, list):
            for it in imgs:
                if not isinstance(it, dict):
                    continue
                fn = it.get('filename')
                if not fn:
                    continue
                images.append({
                    'filename': str(fn),
                    'subfolder': str(it.get('subfolder') or ''),
                    'type': str(it.get('type') or 'output')
                })
        # "gifs", "videos" и т.п. — добавим позже при необходимости
    return images
