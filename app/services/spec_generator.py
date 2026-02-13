from __future__ import annotations

from collections import deque
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


SWITCH_UI_NODE_TYPES = {
    "Any Switch (rgthree)",
}


SWITCH_INPUT_PRIORITY = ("any_01", "any_02", "any_03", "any_04", "any_05")


def _is_muted_ui_node(node: Dict[str, Any]) -> bool:
    """
    ComfyUI node.mode:
      0 - normal
      2 - muted
      4 - bypassed/disabled (в UI часто фиолетовая подсветка)
    """
    return node.get("mode") in (2, 4)


# def _build_graph_indexes(nodes: List[Dict[str, Any]], links: List[Any]):
#     node_by_id: Dict[int, Dict[str, Any]] = {}
#     for n in nodes:
#         try:
#             node_by_id[int(n.get("id"))] = n
#         except Exception:
#             continue

#     in_edges: Dict[int, List[int]] = {}
#     out_edges: Dict[int, List[int]] = {}

#     # link: [link_id, src_id, src_slot, dst_id, dst_slot, type]
#     for l in (links or []):
#         if not isinstance(l, list) or len(l) < 6:
#             continue
#         _, src_id, _, dst_id, _, _ = l
#         try:
#             src_id = int(src_id)
#             dst_id = int(dst_id)
#         except Exception:
#             continue
#         out_edges.setdefault(src_id, []).append(dst_id)
#         in_edges.setdefault(dst_id, []).append(src_id)

#     return node_by_id, in_edges, out_edges


def _build_graph_indexes(nodes: List[Dict[str, Any]], links: List[Any]):
    node_by_id: Dict[int, Dict[str, Any]] = {}
    for n in nodes:
        try:
            node_by_id[int(n.get("id"))] = n
        except Exception:
            continue

    # link: [link_id, src_id, src_slot, dst_id, dst_slot, type]
    in_edges: Dict[int, List[int]] = {}
    out_edges: Dict[int, List[int]] = {}
    link_by_id: Dict[int, Tuple[int, int, int, int, str]] = {}  # link_id -> (src_id, src_slot, dst_id, dst_slot, type)

    for l in (links or []):
        if not isinstance(l, list) or len(l) < 6:
            continue
        link_id, src_id, src_slot, dst_id, dst_slot, ltype = l
        try:
            link_id = int(link_id)
            src_id = int(src_id)
            dst_id = int(dst_id)
            src_slot = int(src_slot)
            dst_slot = int(dst_slot)
        except Exception:
            continue

        link_by_id[link_id] = (src_id, src_slot, dst_id, dst_slot, str(ltype))
        out_edges.setdefault(src_id, []).append(dst_id)
        in_edges.setdefault(dst_id, []).append(src_id)

    return node_by_id, in_edges, out_edges, link_by_id


def _pick_switch_source_node_id(
        node: Dict[str, Any],
        link_by_id: Dict[int, Tuple[int, int, int, int, str]]
) -> Optional[int]:
    """
    Поведение как в sanitize_prompt_for_comfy:
    выбираем первую подключённую ветку any_01 -> any_02 -> ...
    """
    node_inputs = node.get("inputs") or []
    if not isinstance(node_inputs, list):
        return None

    # соберём map name -> link_id
    name_to_link: Dict[str, int] = {}
    for inp in node_inputs:
        if not isinstance(inp, dict):
            continue
        name = inp.get("name")
        link_id = inp.get("link")
        if isinstance(name, str) and name and link_id is not None:
            try:
                name_to_link[name] = int(link_id)
            except Exception:
                continue

    for k in SWITCH_INPUT_PRIORITY:
        link_id = name_to_link.get(k)
        if not link_id:
            continue
        src = link_by_id.get(link_id)
        if not src:
            continue
        src_id, _, _, _, _ = src
        return int(src_id)

    # fallback: первая вообще подключенная (если имена не any_0X)
    for link_id in name_to_link.values():
        src = link_by_id.get(link_id)
        if not src:
            continue
        src_id, _, _, _, _ = src
        return int(src_id)

    return None


# def _collect_active_nodes_to_outputs(nodes: List[Dict[str, Any]], links: List[Any]) -> set[int]:
#     node_by_id, in_edges, _ = _build_graph_indexes(nodes, links)

#     output_ids: List[int] = []
#     for n in nodes:
#         if _is_muted_ui_node(n):
#             continue
#         ct = _get_class_type(n)
#         if ct in OUTPUT_NODE_TYPES:
#             try:
#                 output_ids.append(int(n["id"]))
#             except Exception:
#                 pass

#     active: set[int] = set()
#     q = deque(output_ids)

#     while q:
#         nid = q.popleft()
#         if nid in active:
#             continue
#         n = node_by_id.get(nid)
#         if not n or _is_muted_ui_node(n):
#             continue

#         active.add(nid)

#         for src in in_edges.get(nid, []):
#             if src not in active:
#                 q.append(src)

#     return active


def _collect_active_nodes_to_outputs(nodes: List[Dict[str, Any]], links: List[Any]) -> set[int]:
    node_by_id, in_edges, _, link_by_id = _build_graph_indexes(nodes, links)

    # стартуем от output-нод
    output_ids: List[int] = []
    for n in nodes:
        if _is_muted_ui_node(n):
            continue
        ct = _get_class_type(n)
        if ct in OUTPUT_NODE_TYPES:
            try:
                output_ids.append(int(n["id"]))
            except Exception:
                pass

    active: set[int] = set()
    q = deque(output_ids)

    while q:
        nid = q.popleft()
        if nid in active:
            continue

        n = node_by_id.get(nid)
        if not n:
            continue
        if _is_muted_ui_node(n):
            continue

        active.add(nid)

        ct = _get_class_type(n)

        # ВАЖНО: switch учитываем “как санитайзер” — идём только по одной активной ветке
        if ct in SWITCH_UI_NODE_TYPES:
            src_id = _pick_switch_source_node_id(n, link_by_id)
            if src_id is not None and src_id not in active:
                q.append(src_id)
            continue

        # обычная нода: идём по всем входящим
        for src in in_edges.get(nid, []):
            if src not in active:
                q.append(src)

    return active


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
    info = (object_info or {}).get(class_type) or {}
    inputs = info.get("input") or {}
    required = inputs.get("required") or {}
    optional = inputs.get("optional") or {}
    if not isinstance(required, dict):
        required = {}
    if not isinstance(optional, dict):
        optional = {}
    return required, optional


def _is_widget_schema_entry(schema_entry: Any) -> bool:
    if not isinstance(schema_entry, (list, tuple)) or not schema_entry:
        return False

    t0 = schema_entry[0]
    if isinstance(t0, list):  # COMBO
        return True

    t = str(t0).upper()
    return t in {"INT", "FLOAT", "BOOLEAN", "STRING"}


def _widget_field_order(object_info: Dict[str, Any], class_type: str) -> List[str]:
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


def _schema_kind(schema_entry: Any) -> str:
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
        if not isinstance(value, str):
            return False
        choices = schema_entry[0] if isinstance(schema_entry, (list, tuple)) and isinstance(schema_entry[0], list) else None
        return (value in choices) if choices else True

    if kind == "int":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if isinstance(value, str):
            return value.strip().isdigit()
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
        return isinstance(value, bool) or (isinstance(value, str) and value.strip().lower() in {"true", "false", "0", "1", "yes", "no", "on", "off"})

    if kind == "string":
        return isinstance(value, str)

    return True


def _pick_mask_depends_on(nodes: List[Dict[str, Any]], active_ids: set[int]) -> Optional[str]:
    """
    Возвращает key image-input, к которому логичнее всего привязать mask.
    1) первая активная LoadImage/LoadImageFromPath (по порядку nodes)
    2) иначе первая вообще
    """
    first_any: Optional[str] = None

    for n in nodes:
        if _is_muted_ui_node(n):
            continue
        ct = _get_class_type(n)
        if ct not in IMAGE_NODE_TYPES:
            continue
        nid = str(n.get("id"))
        key = f"image_{nid}"
        if first_any is None:
            first_any = key
        try:
            if int(nid) in active_ids:
                return key
        except Exception:
            continue

    return first_any


def generate_spec_v2(workflow_json: Dict[str, Any], object_info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    nodes = _normalize_nodes(workflow_json)
    links = workflow_json.get("links", []) if isinstance(workflow_json, dict) else []
    active_ids = _collect_active_nodes_to_outputs(nodes, links)

    mask_depends_on = _pick_mask_depends_on(nodes, active_ids)

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

        if _is_muted_ui_node(node):
            continue

        widget_values = node.get("widgets_values", [])
        if not isinstance(widget_values, list):
            widget_values = []

        widget_fields: List[str] = _widget_field_order(object_info, class_type) if object_info else []

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
            # is_required = False
            # try:
            #     is_required = int(node_id) in active_ids
            # except Exception:
            #     pass

            # spec["inputs"]["images"].append(
            #     {
            #         "key": f"image_{node_id}",
            #         "label": "Image",
            #         "modes": ["default"],
            #         "view": "view",
            #         "required": is_required,
            #         "binding": {"node_id": node_id, "field": "widget_0"},
            #     }
            # )
            # continue

            # показываем только реально активные LoadImage (после “схлопывания” switch)
            try:
                if int(node_id) not in active_ids:
                    continue
            except Exception:
                # если id не парсится — лучше показать, чем потерять
                pass

            spec["inputs"]["images"].append(
                {
                    "key": f"image_{node_id}",
                    "label": "Image",
                    "modes": ["default"],
                    "view": "view",
                    "binding": {"node_id": node_id, "field": "widget_0"},
                }
            )
            continue

        # MASK (явный LoadMask)
        if class_type in MASK_NODE_TYPES:
            # если нет ни одной image-ноды — depends_on будет None, но схема требует str
            # поэтому делаем "best effort": если нет image — привяжем к самой маске (хотя UX так себе)
            depends_on = mask_depends_on or f"image_{node_id}"

            spec["inputs"]["mask"] = {
                "key": f"mask_{node_id}",
                "label": "Mask",
                "depends_on": depends_on,
                "modes": ["default"],
                "view": "view",
                "binding": {"node_id": node_id, "field": "widget_0"},
            }
            continue

        # PARAMS
        start_idx = 1 if (class_type in TEXT_NODE_TYPES and len(widget_values) > 0) else 0
        j = 0

        for idx in range(start_idx, len(widget_values)):
            value = widget_values[idx]

            field_name: Optional[str] = None
            schema_entry = None

            if object_info and widget_fields and j < len(widget_fields):
                candidate = widget_fields[j]
                candidate_schema = _schema_entry(object_info or {}, class_type, candidate)
                if _matches_schema(candidate_schema, value):
                    field_name = candidate
                    schema_entry = candidate_schema
                    j += 1

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

    # MASK fallback: если LoadMask нет, но используется MASK-выход у LoadImage (и он активен)
    if spec["inputs"]["mask"] is None:
        for node in nodes:
            if _is_muted_ui_node(node):
                continue
            ct = _get_class_type(node)
            if ct not in IMAGE_NODE_TYPES:
                continue

            nid = str(node.get("id"))
            try:
                if int(nid) not in active_ids:
                    continue
            except Exception:
                continue

            outs = node.get("outputs") or []
            if not isinstance(outs, list):
                continue

            has_used_mask = False
            for o in outs:
                if isinstance(o, dict) and (o.get("type") == "MASK") and o.get("links"):
                    has_used_mask = True
                    break

            if has_used_mask:
                depends_on = mask_depends_on or f"image_{nid}"
                spec["inputs"]["mask"] = {
                    "key": f"mask_{nid}",
                    "label": "Mask",
                    "depends_on": depends_on,
                    "modes": ["default"],
                    "view": "view",
                    "binding": {"node_id": nid, "field": "widget_0"},
                }
                break

    # OUTPUTS
    for node in nodes:
        if _is_muted_ui_node(node):
            continue
        node_id = str(node.get("id"))
        class_type = _get_class_type(node)
        if class_type in OUTPUT_NODE_TYPES:
            spec["outputs"].append({"key": "image", "type": "image", "binding": {"node_id": node_id, "field": "images"}})

    return spec
