from typing import Dict, Any, Tuple, Optional

SKIP_CLASS_TYPES = {
    "Note",
    "MarkdownNote",
    "Label (rgthree)",
    "Fast Groups Muter (rgthree)",
    "Image Comparer (rgthree)",
}

SWITCH_CLASS_TYPES = {
    "Any Switch (rgthree)",
}

# Узлы, которые лучше ВЫРЕЗАТЬ при API-запуске (или разворачивать как bypass)
# SageAttention как раз сюда: он может падать даже "в bypass".
BYPASS_SAFE_CLASS_TYPES = {
    "PathchSageAttentionKJ",  # comfyui-kjnodes (Patch SageAttention)
}


def sanitize_prompt_for_comfy(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    0) фикс формата extra_pnginfo (dict -> [dict]) для некоторых custom nodes
    1) убираем ноды, которых нет/не нужны (Note/rgthree ui)
    2) разворачиваем Any Switch (rgthree) -> прямой источник (по умолчанию any_01)
    3) вырезаем/разворачиваем bypass-ноды (и проблемные оптимизации вроде SageAttention)
    4) FIX Florence2: если lora пустая -> УДАЛЯЕМ ключ lora полностью
    """

    # ------------------------------------------------------------
    # 0) extra_pnginfo: dict -> [dict]
    # ------------------------------------------------------------
    extra = payload.get("extra_pnginfo")
    if isinstance(extra, dict):
        # lora-manager и некоторые хуки ожидают список
        payload["extra_pnginfo"] = [extra]

    prompt = payload.get("prompt")
    if not isinstance(prompt, dict):
        return payload

    def resolve_ref(node_id: str, slot: int) -> Optional[Tuple[str, int]]:
        n = prompt.get(node_id)
        if not isinstance(n, dict):
            return None

        ct = n.get("class_type")
        if ct in SKIP_CLASS_TYPES:
            return None

        ins = n.get("inputs") or {}
        if not isinstance(ins, dict):
            ins = {}

        # ------------------------------------------------------------
        # Разворачиваем switch: берём первую подключенную ветку
        # ------------------------------------------------------------
        if ct in SWITCH_CLASS_TYPES:
            for k in sorted(ins.keys()):
                v = ins.get(k)
                if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int):
                    deeper = resolve_ref(v[0], v[1])
                    return deeper or (v[0], v[1])
            return None

        # ------------------------------------------------------------
        # Проблемные/оптимизационные узлы: разворачиваем как bypass
        # (берём первый подключенный вход и возвращаем его)
        # ------------------------------------------------------------
        if ct in BYPASS_SAFE_CLASS_TYPES:
            for k, v in ins.items():
                if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int):
                    deeper = resolve_ref(v[0], v[1])
                    return deeper or (v[0], v[1])
            return None

        return (node_id, slot)

    # ------------------------------------------------------------
    # 1) Переписываем ссылки на switch/skip/bypass-ноды
    # ------------------------------------------------------------
    for nid, node in list(prompt.items()):
        if not isinstance(node, dict):
            continue
        ins = node.get("inputs")
        if not isinstance(ins, dict):
            continue

        for in_name, v in list(ins.items()):
            if isinstance(v, list) and len(v) == 2:
                src_id, src_slot = v[0], v[1]
                if not isinstance(src_id, str) or not isinstance(src_slot, int):
                    continue
                resolved = resolve_ref(src_id, src_slot)
                if resolved is not None:
                    ins[in_name] = [resolved[0], resolved[1]]

    # ------------------------------------------------------------
    # 2) Удаляем skip/switch/bypass-ноды из prompt вообще
    # ------------------------------------------------------------
    for nid, node in list(prompt.items()):
        ct = (node or {}).get("class_type")
        if ct in SKIP_CLASS_TYPES or ct in SWITCH_CLASS_TYPES or ct in BYPASS_SAFE_CLASS_TYPES:
            prompt.pop(nid, None)

    # ------------------------------------------------------------
    # 3) FIX Florence2: если lora == "" / None / False -> удалить ключ целиком
    # ------------------------------------------------------------
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "DownloadAndLoadFlorence2Model":
            continue

        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue

        if "lora" in inputs:
            v = inputs.get("lora")
            if v is None or v is False or (isinstance(v, str) and not v.strip()):
                inputs.pop("lora", None)

    return payload
