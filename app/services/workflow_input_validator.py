from typing import Any
from fastapi import HTTPException
from app.schemas.workflow_spec_v1 import WorkflowSpec


def validate_user_input(spec: WorkflowSpec, payload: dict[str, Any]):
    errors = []

    for field in spec.inputs:
        value = payload.get(field.key)

        # required
        if field.required and value is None:
            errors.append(f'{field.key} is required')
            continue

        if value is None:
            continue

        # type check
        if field.type == 'int' and not isinstance(value, int):
            errors.append(f'{field.key} must be int')
        
        if field.type == 'float' and not isinstance(value, (int, float)):
            errors.append(f'{field.key} must be float')
        
        if field.type == 'bool' and not isinstance(value, bool):
            errors.append(f'{field.key} must be bool')
        
        if field.type in {'text'} and not isinstance(value, str):
            errors.append(f'{field.key} must be string')
        
        # validation rules
        rules = field.validation or {}

        if isinstance(value, str):
            if "min_length" in rules and len(value) < rules["min_length"]:
                errors.append(f"{field.key} too short")

            if "max_length" in rules and len(value) > rules["max_length"]:
                errors.append(f"{field.key} too long")
        
        if isinstance(value, int):
            if "min" in rules and value < rules["min"]:
                errors.append(f"{field.key} < min")

            if "max" in rules and value > rules["max"]:
                errors.append(f"{field.key} > max")
        
        if field.depends_on:
            dep = field.depends_on["field"]
            if dep not in payload:
                errors.append(f"{field.key} depends on {dep}")
    
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": errors}
        )
