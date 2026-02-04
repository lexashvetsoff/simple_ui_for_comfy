import random
from typing import List


_SEED_MODES = {"randomize", "fixed", "increment", "decrement"}


def get_ui_widget_names(node: dict) -> List[str]:
    """
    Возвращает имена виджетов в ТОЧНОМ UI-порядке (под widgets_values).
    1) Основной источник: node["inputs"] list, только item с widget и без link
    2) Fallback: properties.ue_properties.widget_ue_connectable keys
    """
    names: List[str] = []

    node_inputs = node.get('inputs')
    if isinstance(node_inputs, list):
        for item in node_inputs:
            if not isinstance(item, dict):
                continue
            if item.get('link') is not None:
                continue
            w = item.get('widget')
            if not isinstance(w, dict):
                continue # <-- критично: это НЕ виджет
            name = item.get('name') or w.get('name')
            if isinstance(name, str) and name:
                names.append(name)
    
    if names:
        return names
    
    props = node.get('properties') or {}
    ue = props.get('ue_properties') or {}
    w = ue.get('widget_ue_connectable') or {}
    if isinstance(w, dict):
        return [k for k in w.keys() if isinstance(k, str) and k]

    return []


def _patch_widget_fields_for_seed_in_spec(spec: dict):
    params = spec['inputs']['params']
    new_params = []

    i = 0
    while i < len(params):
        current = params[i]

        # Пропускаем mode для seed
        if isinstance(current.get('default'), str) and current.get('default') in _SEED_MODES:
            i += 1
            continue

        # Проверяем, является ли текущее поле seed
        if current.get('name') == 'seed' and current.get('type') == 'int':
            # Проверяем, есть ли следующее поле и является ли оно "randomize", "fixed", "increment", "decrement"
            if i + 1 < len(params):
                next_field = params[i + 1]
                mode_seed = next_field.get('default')
                if (mode_seed in _SEED_MODES and
                    current.get('binding', {}).get('node_id') == next_field.get('binding', {}).get('node_id')):
                    # Обрабатываем mode для seed
                    seed_int = int(current.get('default', 0))
                    if mode_seed == "randomize":
                        current['default'] = random.randint(0, 2**63 - 1)
                    elif mode_seed == "increment":
                        current['default'] = seed_int + 1
                    elif mode_seed == "decrement":
                        current['default'] = max(0, seed_int - 1)
                    # fixed -> keep

        new_params.append(current)
        i += 1
    
    # Обновляем номера для всех полей с одинаковым node_id
    node_id_groups = {}
    # Группируем по node_id
    for param in new_params:
        node_id = param.get('binding', {}).get('node_id')
        if node_id:
            if node_id not in node_id_groups:
                node_id_groups[node_id] = []
            node_id_groups[node_id].append(param)
    
    # Выравниваем номера внутри каждой группы
    for node_id, group in node_id_groups.items():
        # Сортируем по текущему key (если он есть)
        group.sort(key=lambda x: x.get('key', ''))
        
        # Обновляем ключи и поля widget
        for index, param in enumerate(group):
            # Обновляем ключ
            param['key'] = f"param_{node_id}_{index}"
            
            # Обновляем binding.field если оно начинается с "widget_"
            if 'binding' in param and 'field' in param['binding']:
                if param['binding']['field'].startswith('widget_'):
                    param['binding']['field'] = f"widget_{index}"
    
    # Заменяем параметры в исходных данных
    spec['inputs']['params'] = new_params
    return spec
