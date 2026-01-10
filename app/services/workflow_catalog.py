from typing import Dict, List
from app.models.workflow import Workflow


COMPLEXITY_SIMPLE = "SIMPLE"
COMPLEXITY_MEDIUM = "MEDIUM"
COMPLEXITY_ADVANCED = "ADVANCED"


def prepare_workflow_catalog_item(
        *,
        workflow: Workflow,
        spec: Dict
) -> Dict:
    """
    Prepares workflow data for catalog card rendering.
    """

    meta = spec.get('meta', {})
    inputs = spec.get('inputs', {})
    modes = spec.get('modes', [])

    badges: List[str] = []

    # ---- INPUT BADGES ----
    if inputs.get('text'):
        badges.append('TEXT')
    
    if inputs.get('images'):
        badges.append('IMAGE')
    
    if workflow.requires_mask:
        badges.append('MASK')
    
    if inputs.get('params'):
        badges.append('PARAMS')
    
    # ---- MODES ----
    mode_labels = []
    if len(modes) > 1:
        for m in modes:
            label = m.get('label') or m.get('id')
            if label:
                mode_labels.append(label)
    
    # ---- COMPLEXITY ----
    score = 0
    score += len(inputs.get('text', []))
    score += len(inputs.get('images', []))
    score += len(inputs.get('params', []))

    if workflow.requires_mask:
        score += 2
    
    if score <= 20:
        complexity = COMPLEXITY_SIMPLE
    elif score <= 35:
        complexity = COMPLEXITY_MEDIUM
    else:
        complexity = COMPLEXITY_ADVANCED
    
    # ---- RESULT ----
    return {
        'id': workflow.id,
        'slug': workflow.slug,
        'category': workflow.category,
        'version': workflow.version,

        'title': meta.get('title', workflow.slug),
        'description': meta.get('description', 'No description'),

        'badges': badges,
        'modes': mode_labels,
        'complexity': complexity
    }
