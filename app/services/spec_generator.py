from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple


TEXT_NODE_TYPES = {
    "CLIPTextEncode",
    "CLIPTextEncodeSDXL",
    "TextEncode",
}


IMAGE_NODE_TYPES = {
    "LoadImage",
    "LoadImageFromPath",
}


MASK_NODE_TYPES = {
    "LoadMask",
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


def _schema_for_class(object_info: Dict[str, Any], class_type: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns (required_inputs, optional_inputs) for class_type from /object_info.
    Both are dicts, insertion order is important (widget order).
    """
    info = (object_info or {}).get(class_type) or {}
    inputs = info.get("input") or {}
    required = inputs.get("required") or {}
    optional = inputs.get("optional") or {}
    if not isinstance(required, dict):
        required = {}
    if not isinstance(optional, dict):
        optional = {}
    return required, optional


# def _widget_field_order(object_info: Dict[str, Any], class_type: str) -> List[str]:
#     """
#     Derives widgets_values order from /object_info schema order.
#     """
#     required, optional = _schema_for_class(object_info, class_type)

#     fields: List[str] = []
#     for k in required.keys():
#         fields.append(str(k))
#     for k in optional.keys():
#         ks = str(k)
#         if ks not in fields:
#             fields.append(ks)
#     return fields


def _is_widget_schema_entry(schema_entry: Any) -> bool:
    """
    True если поле реально представлено виджетом и присутствует в widgets_values.
    В ComfyUI sockets (MODEL/IMAGE/CONDITIONING/LATENT/CLIP/...) в widgets_values НЕ лежат.
    """
    if not isinstance(schema_entry, (list, tuple)) or not schema_entry:
        return False

    t0 = schema_entry[0]

    # COMBO
    if isinstance(t0, list):
        return True

    t = str(t0).upper()

    # Примитивные типы, которые реально дают виджеты
    if t in {"INT", "FLOAT", "BOOLEAN", "STRING"}:
        return True

    # Всё остальное (MODEL/IMAGE/CONDITIONING/LATENT/etc) — это сокеты, не виджеты
    return False


def _widget_field_order(object_info: Dict[str, Any], class_type: str) -> List[str]:
    """
    Derives widgets_values order from /object_info schema order,
    BUT only for fields that are actual widgets.
    """
    required, optional = _schema_for_class(object_info, class_type)

    fields: List[str] = []

    for k in required.keys():
        ks = str(k)
        entry = required.get(k)
        if _is_widget_schema_entry(entry):
            fields.append(ks)

    for k in optional.keys():
        ks = str(k)
        if ks in fields:
            continue
        entry = optional.get(k)
        if _is_widget_schema_entry(entry):
            fields.append(ks)

    return fields


def _schema_entry(object_info: Dict[str, Any], class_type: str, field: str) -> Any:
    required, optional = _schema_for_class(object_info, class_type)
    if field in required:
        return required[field]
    return optional.get(field)


def _is_required(object_info: Dict[str, Any], class_type: str, field: str) -> bool:
    required, _ = _schema_for_class(object_info, class_type)
    return field in required


def _infer_param_type_from_schema(schema_entry: Any, default_value: Any) -> Tuple[str, Optional[List[Any]]]:
    """
    Returns (param_type, choices).
      - param_type in {"int","float","bool","text"}
      - choices is list for COMBO, else None
    """
    if isinstance(schema_entry, (list, tuple)) and schema_entry:
        t0 = schema_entry[0]
        if isinstance(t0, list):  # COMBO
            return "text", list(t0)

        t = str(t0).upper()
        if t == "INT":
            return "int", None
        if t == "FLOAT":
            return "float", None
        if t == "BOOLEAN":
            return "bool", None
        return "text", None

    # fallback
    if isinstance(default_value, bool):
        return "bool", None
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        return "int", None
    if isinstance(default_value, float):
        return "float", None
    return "text", None


def _guess_view_mode(class_type: str, widget_name: Optional[str]) -> str:
    if class_type in NO_VIEW_NODE_TYPES:
        return "no_view"

    if widget_name in NO_VIEW_WIDGET_NAMES:
        return "no_view"

    if widget_name in HIDDEN_WIDGET_NAMES:
        return "hidden"

    if widget_name in ALWAYS_VIEW_WIDGET_NAMES:
        return "view"

    return "hidden"


def _coerce_default_from_schema(schema_entry: Any, value: Any) -> Any:
    """
    Приводим дефолт по типу из object_info.
    Для COMBO — оставляем как есть.
    """
    if value is None:
        return None

    if not isinstance(schema_entry, (list, tuple)) or not schema_entry:
        return value

    t0 = schema_entry[0]
    if isinstance(t0, list):
        return value  # COMBO

    t = str(t0).upper()
    try:
        if t == "INT":
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str) and value.strip() != "":
                return int(float(value))
            return value

        if t == "FLOAT":
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str) and value.strip() != "":
                return float(value)
            return value

        if t == "BOOLEAN":
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
            return bool(value)

        return str(value) if not isinstance(value, str) else value

    except Exception:
        return value


# def _patch_widget_fields_for_known_nodes(
#     class_type: str,
#     widget_values: List[Any],
#     widget_fields: List[str],
# ) -> List[str]:
#     # KSampler: widgets_values обычно: [seed, control_after_generate, steps, cfg, sampler_name, scheduler, denoise, ...]
#     if class_type == "KSampler":
#         if len(widget_values) >= 2:
#             v1 = widget_values[1]
#             if isinstance(v1, str) and v1.lower() in {"randomize", "fixed", "increment", "decrement"}:
#                 # Если schema не содержит это поле, вставляем его на позицию 1
#                 if len(widget_fields) >= 2 and widget_fields[1] != "control_after_generate":
#                     widget_fields = list(widget_fields)
#                     widget_fields.insert(1, "control_after_generate")
#                 # Если widget_fields слишком короткий/пустой — тоже вставим
#                 elif len(widget_fields) == 1:
#                     widget_fields = list(widget_fields)
#                     widget_fields.insert(1, "control_after_generate")
#     return widget_fields


def _schema_kind(schema_entry: Any) -> str:
    """
    returns: 'combo'|'int'|'float'|'bool'|'string'|'other'
    """
    if not isinstance(schema_entry, (list, tuple)) or not schema_entry:
        return "other"
    t0 = schema_entry[0]
    if isinstance(t0, list):
        return "combo"
    t = str(t0).upper()
    if t == "INT":
        return "int"
    if t == "FLOAT":
        return "float"
    if t == "BOOLEAN":
        return "bool"
    if t == "STRING":
        return "string"
    return "other"


def _matches_schema(schema_entry: Any, value: Any) -> bool:
    kind = _schema_kind(schema_entry)

    if kind == "combo":
        # Comfy часто кладёт строку
        # return isinstance(value, str)
        if not isinstance(value, str):
            return False
        choices = schema_entry[0] if isinstance(schema_entry, (list, tuple)) and schema_entry and isinstance(schema_entry[0], list) else None
        return (value in choices) if choices else True
    if kind == "int":
        # допускаем int или строку числа
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, str):
            s = value.strip()
            return s.isdigit()
        return False
    if kind == "float":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if isinstance(value, str):
            try:
                float(value.strip())
                return True
            except Exception:
                return False
        return False
    if kind == "bool":
        return isinstance(value, bool) or (isinstance(value, str) and value.strip().lower() in {"true","false","0","1","yes","no","on","off"})
    if kind == "string":
        return isinstance(value, str)
    return True  # если schema непонятная — не блокируем


def generate_spec_v2(workflow_json: Dict[str, Any], object_info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Если object_info передан:
      - маппим widgets_values индексы на реальные поля (по порядку schema),
      - определяем типы/COMBO/required из schema,
      - получаем корректные labels.
    """
    nodes = _normalize_nodes(workflow_json)

    spec: Dict[str, Any] = {
        "meta": {
            "version": "2.0",
            "title": "Generated workflow",
            "description": "Auto-generated Spec v2 (edit me)",
        },
        "modes": [{"id": "default", "label": "Default"}],
        "inputs": {"text": [], "params": [], "images": [], "mask": None},
        "outputs": [],
    }

    for node in nodes:
        node_id = str(node.get("id"))
        class_type = _get_class_type(node)

        widget_values = node.get("widgets_values", [])
        if not isinstance(widget_values, list):
            widget_values = []

        widget_fields: List[str] = _widget_field_order(object_info, class_type) if object_info else []
        # if object_info:
        #     widget_fields = _patch_widget_fields_for_known_nodes(class_type, widget_values, widget_fields)

        # TEXT
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
                        "binding": {"node_id": node_id, "field": "widget_0"},
                    }
                )

        # IMAGE
        if class_type in IMAGE_NODE_TYPES:
            spec["inputs"]["images"].append(
                {
                    "key": f"image_{node_id}",
                    "label": "Image",
                    "modes": ["default"],
                    "view": "view",
                    "binding": {"node_id": node_id, "field": "widget_0"},
                }
            )
            # важно: НЕ добавляем param_204_* и т.п.
            continue

        # MASK
        if class_type in MASK_NODE_TYPES:
            spec["inputs"]["mask"] = {
                "key": f"mask_{node_id}",
                "label": "Mask",
                "modes": ["default"],
                "view": "view",
                "required": True,  # можно сделать False, но для LoadMask логичнее True
                "binding": {"node_id": node_id, "field": "widget_0"},
            }
            # важно: НЕ добавляем параметры этого узла
            continue

        # PARAMS
        # start_idx = 1 if (class_type in TEXT_NODE_TYPES and len(widget_values) > 0) else 0

        # for idx in range(start_idx, len(widget_values)):
        #     value = widget_values[idx]

        #     field_name: Optional[str] = widget_fields[idx] if (widget_fields and idx < len(widget_fields)) else None

        #     schema_entry = (
        #         _schema_entry(object_info or {}, class_type, field_name)
        #         if (object_info and field_name)
        #         else None
        #     )

        #     param_type, choices = _infer_param_type_from_schema(schema_entry, value)
        #     default_value = _coerce_default_from_schema(schema_entry, value) if schema_entry is not None else value

        #     view_mode = _guess_view_mode(class_type, field_name)

        #     label = field_name.replace("_", " ").title() if field_name else f"{class_type} param {idx + 1}"

        #     item: Dict[str, Any] = {
        #         "key": f"param_{node_id}_{idx}",
        #         "label": label,
        #         "type": param_type,
        #         "default": default_value,
        #         "view": view_mode,
        #         "binding": {"node_id": node_id, "field": f"widget_{idx}"},
        #     }

        #     # дополнительные поля (для формы)
        #     if field_name:
        #         item["name"] = field_name
        #     if choices:
        #         item["choices"] = choices
        #     if field_name and object_info:
        #         item["required"] = _is_required(object_info, class_type, field_name)

        #     spec["inputs"]["params"].append(item)

        # PARAMS
        start_idx = 1 if (class_type in TEXT_NODE_TYPES and len(widget_values) > 0) else 0
        j = 0  # индекс по widget_fields (schema widgets)

        for idx in range(start_idx, len(widget_values)):
            value = widget_values[idx]

            field_name: Optional[str] = None
            schema_entry = None

            if object_info and widget_fields and j < len(widget_fields):
                candidate = widget_fields[j]
                candidate_schema = _schema_entry(object_info or {}, class_type, candidate)

                # если текущий widgets_values[idx] похож на ожидаемый тип — привязываем
                if _matches_schema(candidate_schema, value):
                    field_name = candidate
                    schema_entry = candidate_schema
                    j += 1
                else:
                    # это "лишний" виджет в widgets_values (UI вставка)
                    field_name = None
                    schema_entry = None
            
            param_type, choices = _infer_param_type_from_schema(schema_entry, value)
            default_value = _coerce_default_from_schema(schema_entry, value) if schema_entry is not None else value

            view_mode = _guess_view_mode(class_type, field_name)
            label = field_name.replace("_", " ").title() if field_name else f"{class_type} param {idx + 1}"

            item: Dict[str, Any] = {
                "key": f"param_{node_id}_{idx}",
                "label": label,
                "type": param_type,
                "default": default_value,
                "view": view_mode,
                "binding": {"node_id": node_id, "field": f"widget_{idx}"},
            }

            if field_name:
                item["name"] = field_name
                if choices:
                    item["choices"] = choices
                if object_info:
                    item["required"] = _is_required(object_info, class_type, field_name)
            
            spec["inputs"]["params"].append(item)

    # OUTPUTS
    for node in nodes:
        node_id = str(node.get("id"))
        class_type = _get_class_type(node)

        if class_type in OUTPUT_NODE_TYPES:
            spec["outputs"].append(
                {"key": "image", "type": "image", "binding": {"node_id": node_id, "field": "images"}}
            )

    return spec
