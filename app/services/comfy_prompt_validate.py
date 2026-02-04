from __future__ import annotations

import os
from typing import Any, Dict, Tuple


def _schema_inputs_for_class(object_info: Dict[str, Any], class_type: str) -> Dict[str, Any]:
    info = object_info.get(class_type) or {}
    inputs = info.get("input") or {}
    required = inputs.get("required") or {}
    optional = inputs.get("optional") or {}
    merged: Dict[str, Any] = {}
    merged.update(required)
    merged.update(optional)
    return merged


def _meta_default(schema_entry: Any) -> Any:
    """
    Для INT/FLOAT/BOOLEAN/STRING и для COMBO meta может содержать default.
    schema_entry обычно вида: ["INT", {"default": 20, ...}]
    или: [["a","b"], {"default": "a"}]
    """
    if not isinstance(schema_entry, (list, tuple)) or len(schema_entry) < 2:
        return None
    meta = schema_entry[1]
    if isinstance(meta, dict) and "default" in meta:
        return meta["default"]
    return None


def _is_link(v: Any) -> bool:
    # linked input вида ["123", 0]
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int)


def _coerce_value_to_type(schema_entry: Any, value: Any) -> Any:
    """
    schema_entry может быть:
      ["INT", {default..}]
      [["a","b","c"], {default..}]  # COMBO
      ["FLOAT", ...]
      ["BOOLEAN", ...]
      ...
    """
    if not isinstance(schema_entry, (list, tuple)) or not schema_entry:
        return value

    type_or_choices = schema_entry[0]

    # COMBO — типизацию не делаем, тут другая логика
    if isinstance(type_or_choices, list):
        return value

    t = str(type_or_choices).upper()

    # Если форма прислала "", ставим default (если есть)
    if value == "" or value is None:
        d = _meta_default(schema_entry)
        return d if d is not None else value

    if t == "INT":
        return int(value)

    if t == "FLOAT":
        return float(value)

    if t == "BOOLEAN":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            return v in ("1", "true", "yes", "y", "on")
        return bool(value)

    # STRING и прочее
    return value


def _combo_fix_value(allowed: list, value: Any) -> Any:
    """
    Пытаемся "починить" значение для COMBO:
      1) точное совпадение
      2) совпадение по basename (для путей типа "Kontext\\file.safetensors")
      3) fallback None
    """
    if value in allowed:
        return value

    if isinstance(value, str) and value:
        # нормализуем слэши и берём basename
        base = os.path.basename(value.replace("\\", "/"))
        if base in allowed:
            return base

        # иногда allowed содержит путь, а value — basename
        # (редко, но полезно)
        for a in allowed:
            if isinstance(a, str) and os.path.basename(a.replace("\\", "/")) == base:
                return a

    return None


def validate_and_fix_prompt(prompt: Dict[str, Any], object_info: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    """
    Проходит по всем node.inputs и:
      - приводит типы (int/float/bool)
      - для COMBO:
          - если значение не в списке, пытается сматчить по basename
          - иначе ставит default
      - для INT/FLOAT/BOOLEAN:
          - если пришло ""/None, ставит default (если есть)
    Возвращает (prompt, warnings)
    """
    warnings: list[str] = []

    graph = prompt.get("prompt") or {}
    if not isinstance(graph, dict):
        return prompt, ["prompt['prompt'] is not a dict"]

    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue

        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue

        schema_inputs = _schema_inputs_for_class(object_info, str(class_type))

        for k, v in list(inputs.items()):
            schema_entry = schema_inputs.get(k)
            if schema_entry is None:
                continue

            # linked input — не трогаем
            if _is_link(v):
                continue

            # COMBO
            if isinstance(schema_entry, (list, tuple)) and schema_entry and isinstance(schema_entry[0], list):
                allowed = schema_entry[0]

                # пустое значение -> default
                if v == "" or v is None:
                    d = _meta_default(schema_entry)
                    if d is not None:
                        inputs[k] = d
                        warnings.append(f"node {node_id}.{k}: empty -> default '{d}'")
                    continue

                fixed = _combo_fix_value(allowed, v)
                if fixed is not None:
                    if fixed != v:
                        warnings.append(f"node {node_id}.{k}: '{v}' -> '{fixed}' (combo match)")
                    inputs[k] = fixed
                else:
                    d = _meta_default(schema_entry)
                    if d is not None:
                        inputs[k] = d
                        warnings.append(f"node {node_id}.{k}: '{v}' not in list -> default '{d}'")
                    # если default нет — оставляем как есть, пусть Comfy ругнётся явно
                continue

            # типы
            try:
                coerced = _coerce_value_to_type(schema_entry, v)
                if coerced != v:
                    warnings.append(f"node {node_id}.{k}: '{v}' -> '{coerced}' (coerce)")
                inputs[k] = coerced
            except Exception as e:
                warnings.append(f"node {node_id}.{k}: failed to coerce '{v}' ({e})")

        node["inputs"] = inputs

    return prompt, warnings
