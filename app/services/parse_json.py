import json
from fastapi import HTTPException


def parse_json_field(value: str, field_name: str) -> dict:
    if value is None:
        raise HTTPException(status_code=400, detail=f'{field_name} is requared')
    
    s = value.strip()
    if not s:
        raise HTTPException(status_code=400, detail=f'{field_name} is emty')
    
    # если ошибочно попала JSON-строка вида "\"{...}\""
    # то json.loads вернёт str, и нужно распарсить ещё раз
    try:
        obj = json.loads(s)
        if isinstance(obj, str):
            obj = json.loads(obj)
        if not isinstance(obj, dict):
            raise ValueError('Not a Json object')
        return obj
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Invalid {field_name}: {e}')
