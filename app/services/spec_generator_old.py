from typing import Dict, Any, List, Optional
from app.services.comfy_service import get_ui_widget_names


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

# Ноды, чьи widgets обычно "служебные" (пути/модели/девайсы) — не даём менять пользователю
NO_VIEW_NODE_TYPES = {
    "DualCLIPLoader",
    "CLIPLoader",
    "VAELoader",
    "UNETLoader",
    "CheckpointLoaderSimple",
    "CheckpointLoader",
}

# Поля/виджеты, которые считаем "важными" и показываем всегда
ALWAYS_VIEW_WIDGET_NAMES = {
    "steps",
    "denoise",
    "sampler_name",
    "scheduler",
    "cfg",
    "guidance",
    "noise_seed",
    "seed",
}

# Поля, которые чаще "настройки", но не обязательно трогать каждый раз
HIDDEN_WIDGET_NAMES = {
    "width",
    "height",
    "batch_size",
}

# Поля, которые лучше вообще не показывать (но дефолт будет жить в spec)
NO_VIEW_WIDGET_NAMES = {
    "unet_name",
    "weight_dtype",
    "vae_name",
    "clip_name",
    "clip_name1",
    "clip_name2",
    "type",
    "device",
    "randomize",
}


def _normalize_nodes(workflow_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(workflow_json, dict) and "nodes" in workflow_json:
        nodes = workflow_json["nodes"]
        if isinstance(nodes, list):
            return nodes

    if isinstance(workflow_json, list):
        return workflow_json

    raise ValueError("Invalid workflow format: nodes not found")


def _get_class_type(node: Dict[str, Any]) -> str:
    return str(node.get("class_type") or node.get("type") or "")


# def _get_widget_names(node: Dict[str, Any]) -> List[str]:
#     """
#     Пытаемся восстановить "имена" виджетов по максимуму:
#     1) properties.ue_properties.widget_ue_connectable (самый надёжный источник)
#     2) node.inputs (иногда содержит widget.name)
#     Возвращаем список имён виджетов в "порядке UI".
#     """
#     names: List[str] = []

#     props = node.get("properties") or {}
#     ue = props.get("ue_properties") or {}
#     connectable = ue.get("widget_ue_connectable") or {}

#     if isinstance(connectable, dict):
#         # порядок ключей в JSON сохраняется в Python 3.7+
#         for k in connectable.keys():
#             if isinstance(k, str) and k:
#                 names.append(k)

#     # Доп. попытка: просканить inputs на предмет widget.name
#     # (иногда этот список добавляет имена, которые не попали в connectable)
#     node_inputs = node.get("inputs")
#     if isinstance(node_inputs, list):
#         for item in node_inputs:
#             if isinstance(item, dict):
#                 w = item.get("widget")
#                 if isinstance(w, dict):
#                     wn = w.get("name")
#                     if isinstance(wn, str) and wn and wn not in names:
#                         names.append(wn)

#     return names


# def _get_widget_names(node: Dict[str, Any]) -> List[str]:
#     """
#     Надёжно восстанавливаем имена виджетов:
#     1) properties.ue_properties.widget_ue_connectable — база (полный список + порядок)
#     2) дополняем тем, что нашли в node.inputs[*].widget.name или item.name (если чего-то нет)
#     """
#     names: List[str] = []

#     props = node.get('properties') or {}
#     ue = props.get('ue_properties') or {}
#     connectable = ue.get('widget_ue_connectable') or {}

#     # 1) База: ue_properties (самое полное и правильный порядок)
#     if isinstance(connectable, dict):
#         for k in connectable.keys():
#             if isinstance(k, str) and k:
#                 names.append(k)
    
#     # 2) Дополнение: inputs (иногда там есть то, чего нет в connectable)
#     node_inputs = node.get('inputs')
#     if isinstance(node_inputs, list):
#         for item in node_inputs:
#             if not isinstance(item, dict):
#                 continue

#             # иногда имя лежит тут
#             nm = item.get('name')
#             if isinstance(nm, str) and nm and nm not in names and item.get('link') is None:
#                 names.append(nm)
            
#             # иногда имя лежит в widget.name
#             w = item.get('widget')
#             if isinstance(w, dict):
#                 wn = w.get('name')
#                 if isinstance(wn, str) and wn and wn not in names:
#                     names.append(wn)
    
#     return names


def _guess_view_mode(class_type: str, widget_name: Optional[str]) -> str:
    if class_type in NO_VIEW_NODE_TYPES:
        return "no_view"

    if widget_name in NO_VIEW_WIDGET_NAMES:
        return "no_view"

    if widget_name in HIDDEN_WIDGET_NAMES:
        return "hidden"

    if widget_name in ALWAYS_VIEW_WIDGET_NAMES:
        return "view"

    # дефолт для параметров — hidden (чтобы не забивать форму)
    return "hidden"


def _infer_param_type(widget_name: Optional[str], value: Any) -> str:
    """
    Подбираем тип для формы/spec.
    """
    # если имя явно намекает на int
    if widget_name in {"steps", "width", "height", "batch_size", "noise_seed", "seed"}:
        return "int"

    if isinstance(value, bool):
        return "bool"

    if isinstance(value, int):
        return "int"

    if isinstance(value, float):
        return "float"

    # строки — обычно текст
    return "text"


def _coerce_default(param_type: str, value: Any) -> Any:
    """
    Пробуем привести дефолт к нужному типу (на практике ComfyUI
    иногда хранит числа как строки).
    """
    if value is None:
        return None

    try:
        if param_type == "int":
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str) and value.strip() != "":
                return int(float(value))  # на случай "20" или "20.0"
            return value

        if param_type == "float":
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str) and value.strip() != "":
                return float(value)
            return value

        if param_type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                v = value.strip().lower()
                if v in {"true", "1", "yes", "y", "on"}:
                    return True
                if v in {"false", "0", "no", "n", "off"}:
                    return False
            return value

        # text
        return str(value) if not isinstance(value, str) else value

    except Exception:
        # если не смогли привести — оставим как есть
        return value


def generate_spec_v2(workflow_json: Dict[str, Any]) -> Dict[str, Any]:
    nodes = _normalize_nodes(workflow_json)

    spec: Dict[str, Any] = {
        "meta": {
            "version": "2.0",
            "title": "Generated workflow",
            "description": "Auto-generated Spec v2 (edit me)",
        },
        "modes": [{"id": "default", "label": "Default"}],
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
        class_type = _get_class_type(node)

        widget_values = node.get("widgets_values", [])
        if not isinstance(widget_values, list):
            widget_values = []

        # widget_names = _get_widget_names(node)
        widget_names = get_ui_widget_names(node)

        # ---------------- TEXT INPUT ----------------
        # Для text node — обычно prompt живёт в widgets_values[0]
        if class_type in TEXT_NODE_TYPES:
            if widget_values and isinstance(widget_values[0], str):
                spec["inputs"]["text"].append(
                    {
                        "key": f"prompt_{node_id}",
                        "label": "Prompt",
                        "type": "text",
                        "required": True,
                        "default": widget_values[0],
                        "view": "view",
                        "binding": {
                            "node_id": node_id,
                            "field": "widget_0",
                        },
                    }
                )

        # ---------------- IMAGE INPUT ----------------
        if class_type in IMAGE_NODE_TYPES:
            # В текущей реализации маппер ожидает binding.field конкретного поля.
            # Для LoadImage/LoadImageFromPath реальный runtime input может отличаться,
            # bindings — оставляем как было.
            # spec["inputs"]["images"].append(
            #     {
            #         "key": f"image_{node_id}",
            #         "label": "Image",
            #         "modes": ["default"],
            #         "view": "view",
            #         "binding": {
            #             "node_id": node_id,
            #             "field": "image",
            #         },
            #     }
            # )
            spec["inputs"]["images"].append(
                {
                    "key": f"image_{node_id}",
                    "label": "Image",
                    "modes": ["default"],
                    "view": "view",
                    "binding": {
                        "node_id": node_id,
                        "field": "widget_0",
                    },
                }
            )

        # ---------------- PARAMS (widgets_values) ----------------
        # Генерим параметры по widgets_values.
        # ВАЖНО: если это TextEncode, НЕ добавляем widget_0 как param (чтобы не дублировать prompt).
        start_idx = 1 if (class_type in TEXT_NODE_TYPES and len(widget_values) > 0) else 0

        for idx in range(start_idx, len(widget_values)):
            value = widget_values[idx]

            # берем имя по индексу, если есть
            widget_name = widget_names[idx] if idx < len(widget_names) else None

            view_mode = _guess_view_mode(class_type, widget_name)

            param_type = _infer_param_type(widget_name, value)
            default_value = _coerce_default(param_type, value)

            # label — если знаем имя виджета, используем его
            if widget_name:
                label = widget_name.replace("_", " ").title()
            else:
                label = f"{class_type} param {idx + 1}"

            spec["inputs"]["params"].append(
                {
                    "key": f"param_{node_id}_{idx}",
                    "label": label,
                    "type": param_type,
                    "default": default_value,
                    "view": view_mode,
                    "binding": {
                        "node_id": node_id,
                        "field": f"widget_{idx}",
                    },
                }
            )

    # ---------------- OUTPUTS ----------------
    for node in nodes:
        node_id = str(node.get("id"))
        class_type = _get_class_type(node)

        if class_type in OUTPUT_NODE_TYPES:
            spec["outputs"].append(
                {
                    "key": "image",
                    "type": "image",
                    "binding": {"node_id": node_id, "field": "images"},
                }
            )

    return spec
