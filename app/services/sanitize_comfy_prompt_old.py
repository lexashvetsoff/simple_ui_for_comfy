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

def sanitize_prompt_for_comfy(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    1) убираем ноды, которых нет/не нужны (Note/rgthree ui)
    2) разворачиваем Any Switch (rgthree) -> прямой источник (по умолчанию any_01)
    """
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

        # Разворачиваем switch: берём первую подключенную ветку
        if ct in SWITCH_CLASS_TYPES:
            ins = n.get("inputs") or {}
            if not isinstance(ins, dict):
                return None

            # приоритет any_01, any_02, ...
            for k in sorted(ins.keys()):
                v = ins.get(k)
                if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int):
                    # рекурсивно раскрываем, если там тоже switch
                    deeper = resolve_ref(v[0], v[1])
                    return deeper or (v[0], v[1])
            return None

        return (node_id, slot)

    # 1) Переписываем ссылки на switch/skip-ноды
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
                # if resolved is None:
                #     # если вход стал “пустым” — убираем его
                #     ins.pop(in_name, None)
                # else:
                #     ins[in_name] = [resolved[0], resolved[1]]
                if resolved is not None:
                    ins[in_name] = [resolved[0], resolved[1]]

    # 2) Удаляем skip и switch-ноды из prompt вообще
    for nid, node in list(prompt.items()):
        ct = (node or {}).get("class_type")
        if ct in SKIP_CLASS_TYPES or ct in SWITCH_CLASS_TYPES:
            prompt.pop(nid, None)

    return payload
