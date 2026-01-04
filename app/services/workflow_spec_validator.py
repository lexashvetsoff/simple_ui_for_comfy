from fastapi import HTTPException
from app.schemas.workflow_spec_v2 import WorkflowSpecV2


def validate_workflow_spec(spec: dict) -> WorkflowSpecV2:
    try:
        parsed = WorkflowSpecV2(**spec)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Invalid workflow spec: {e}')
    
    # validate modes
    mode_ids = {m.id for m in parsed.modes}

    for img in parsed.inputs.images:
        if img.modes:
            for m in img.modes:
                if m not in mode_ids:
                    raise HTTPException(status_code=400, detail=f"Unknown mode '{m}' in image input '{img.key}'")
    
    if parsed.inputs.mask:
        if parsed.inputs.mask.depends_on not in [
            i.key for i in parsed.inputs.images
        ]:
            raise HTTPException(status_code=400, detail='Mask depends_on unknown image input')
    
    return parsed
