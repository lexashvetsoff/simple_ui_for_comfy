from typing import Any, Dict, List, Tuple


# Чуть “человеческих” названий групп для типовых нод
FRIENDLY_NODE_GROUPS: dict[str, str] = {
    "CLIPTextEncode": "Prompt",
    "CLIPTextEncodeSDXL": "Prompt",
    "TextEncode": "Prompt",

    "RandomNoise": "Seed / Noise",
    "KSamplerSelect": "Sampler",
    "BasicScheduler": "Scheduler",
    "EmptyLatentImage": "Latent size",

    "LoadImage": "Image input",
    "LoadImageFromPath": "Image input",

    "PreviewImage": "Output",
    "SaveImage": "Output",
}


def _safe_get(d: dict, path: List[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _node_title(node: dict, class_type: str) -> str:
    # Comfy UI workflow node может иметь title (как в твоём примере)
    title = node.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()

    # Иногда можно вытащить “Node name for S&R”
    s_and_r = _safe_get(node, ["properties", "Node name for S&R"])
    if isinstance(s_and_r, str) and s_and_r.strip():
        return s_and_r.strip()

    # Fallback: по маппингу или class_type
    return FRIENDLY_NODE_GROUPS.get(class_type, class_type or "Node")


# def prepare_spec_groups(
#     *,
#     spec: Dict[str, Any],
#     workflow_json: Dict[str, Any] | None = None,
# ) -> List[Dict[str, Any]]:
#     """
#     Готовит удобную структуру для шаблона:
#     groups = [
#       {
#         "id": "node_6",
#         "node_id": "6",
#         "label": "Позитивный промпт",
#         "order": 6,
#         "text": [...],
#         "params_view": [...],
#         "params_hidden": [...],
#         "params_no_view": [...],
#         "images": [...],
#       },
#       ...
#     ]
#     """
#     nodes_by_id: dict[str, dict] = {}
#     if workflow_json and isinstance(workflow_json.get("nodes"), list):
#         for n in workflow_json["nodes"]:
#             nid = n.get("id")
#             if nid is None:
#                 continue
#             nodes_by_id[str(nid)] = n

#     def group_key(item: dict) -> Tuple[int, str]:
#         binding = item.get("binding") or {}
#         node_id = str(binding.get("node_id") or "")
#         node = nodes_by_id.get(node_id, {})
#         order = node.get("order")
#         if not isinstance(order, int):
#             order = 0

#         class_type = str(node.get("class_type") or node.get("type") or "")
#         label = _node_title(node, class_type) if node_id else "Other"

#         return (order, label)

#     # собираем плоский список всех UI-инпутов
#     flat_items: List[Dict[str, Any]] = []
#     inputs = (spec.get("inputs") or {})
#     for t in inputs.get("text") or []:
#         flat_items.append({**t, "_kind": "text"})
#     for p in inputs.get("params") or []:
#         flat_items.append({**p, "_kind": "param"})
#     for img in inputs.get("images") or []:
#         flat_items.append({**img, "_kind": "image"})

#     # группируем
#     buckets: dict[Tuple[int, str], List[dict]] = {}
#     for item in flat_items:
#         k = group_key(item)
#         buckets.setdefault(k, []).append(item)

#     groups: List[Dict[str, Any]] = []

#     for (order, label), items in buckets.items():
#         # определяем node_id из первого элемента (в пределах группы одинаковый)
#         node_id = ""
#         for it in items:
#             b = it.get("binding") or {}
#             if b.get("node_id") is not None:
#                 node_id = str(b["node_id"])
#                 break

#         text_items = [i for i in items if i.get("_kind") == "text"]
#         param_items = [i for i in items if i.get("_kind") == "param"]
#         image_items = [i for i in items if i.get("_kind") == "image"]

#         # параметров может быть много — разделим по view
#         params_view: List[dict] = []
#         params_hidden: List[dict] = []
#         params_no_view: List[dict] = []

#         for p in param_items:
#             v = p.get("view")
#             if v == "no_view":
#                 params_no_view.append(p)
#             elif v == "hidden":
#                 params_hidden.append(p)
#             else:
#                 params_view.append(p)
        
#         # проверка: есть ли что реально показывать
#         has_visible_content = (
#             bool(text_items)
#             or bool(params_view)
#             or bool(params_hidden)
#             or bool(image_items)
#         )
#         if not has_visible_content:
#             # группа состоит ТОЛЬКО из no_view → пропускаем
#             continue

#         groups.append(
#             {
#                 "id": f"node_{node_id or label}",
#                 "node_id": node_id,
#                 "label": label,
#                 "order": order,
#                 "text": text_items,
#                 "params_view": params_view,
#                 "params_hidden": params_hidden,
#                 "params_no_view": params_no_view,
#                 "images": image_items,
#             }
#         )

#     # сортировка групп: сначала order, потом label
#     groups.sort(key=lambda g: (g["order"], g["label"]))

#     return groups


def prepare_spec_groups(
    *,
    spec: Dict[str, Any],
    workflow_json: Dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Возвращает 2 списка:
      - visible_groups: группы, где есть view/text/image
      - hidden_only_groups: группы, где НЕТ view/text/image, но есть hidden
    Группы только с no_view не возвращаем.
    """
    nodes_by_id: dict[str, dict] = {}
    if workflow_json and isinstance(workflow_json.get("nodes"), list):
        for n in workflow_json["nodes"]:
            nid = n.get("id")
            if nid is None:
                continue
            nodes_by_id[str(nid)] = n

    def group_key(item: dict) -> Tuple[int, str]:
        binding = item.get("binding") or {}
        node_id = str(binding.get("node_id") or "")
        node = nodes_by_id.get(node_id, {})
        order = node.get("order")
        if not isinstance(order, int):
            order = 0

        class_type = str(node.get("class_type") or node.get("type") or "")
        label = _node_title(node, class_type) if node_id else "Other"
        return (order, label)

    # плоский список инпутов
    flat_items: List[Dict[str, Any]] = []
    inputs = (spec.get("inputs") or {})
    for t in inputs.get("text") or []:
        flat_items.append({**t, "_kind": "text"})
    for p in inputs.get("params") or []:
        flat_items.append({**p, "_kind": "param"})
    for img in inputs.get("images") or []:
        flat_items.append({**img, "_kind": "image"})

    # buckets
    buckets: dict[Tuple[int, str], List[dict]] = {}
    for item in flat_items:
        k = group_key(item)
        buckets.setdefault(k, []).append(item)

    visible_groups: List[Dict[str, Any]] = []
    hidden_only_groups: List[Dict[str, Any]] = []

    for (order, label), items in buckets.items():
        # node_id
        node_id = ""
        for it in items:
            b = it.get("binding") or {}
            if b.get("node_id") is not None:
                node_id = str(b["node_id"])
                break

        text_items = [i for i in items if i.get("_kind") == "text"]
        param_items = [i for i in items if i.get("_kind") == "param"]
        image_items = [i for i in items if i.get("_kind") == "image"]

        params_view: List[dict] = []
        params_hidden: List[dict] = []
        params_no_view: List[dict] = []

        for p in param_items:
            v = p.get("view")
            if v == "no_view":
                params_no_view.append(p)
            elif v == "hidden":
                params_hidden.append(p)
            else:
                params_view.append(p)

        # 1) группы только из no_view → пропускаем полностью
        if not text_items and not image_items and not params_view and not params_hidden:
            continue

        group = {
            "id": f"node_{node_id or label}",
            "node_id": node_id,
            "label": label,
            "order": order,
            "text": text_items,
            "params_view": params_view,
            "params_hidden": params_hidden,
            "params_no_view": params_no_view,
            "images": image_items,
        }

        # 2) если есть хоть что-то "видимое" (text/image/view params) → в visible_groups
        has_visible = bool(text_items) or bool(image_items) or bool(params_view)

        # 3) если видимого нет, но есть hidden → в hidden_only_groups
        if has_visible:
            visible_groups.append(group)
        elif params_hidden:
            hidden_only_groups.append(group)
        # иначе (например нет hidden тоже) уже отфильтровано выше

    visible_groups.sort(key=lambda g: (g["order"], g["label"]))
    hidden_only_groups.sort(key=lambda g: (g["order"], g["label"]))

    return visible_groups, hidden_only_groups
