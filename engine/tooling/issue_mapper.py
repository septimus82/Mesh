from typing import Optional, TypedDict

class IssueHint(TypedDict):
    issue_id: str
    category: str
    suggested_action: str
    target: str
    confidence: float

def map_issue_to_hint(source: str, msg: str, file_path: Optional[str]) -> Optional[IssueHint]:
    if not file_path:
        return None
        
    file_path = file_path.replace("\\", "/")
    msg_lower = msg.lower()

    # Scene not found -> create_scene
    if "not found" in msg_lower and (file_path.endswith(".json") and "scenes/" in file_path):
        return {
            "issue_id": "missing_scene",
            "category": "missing_scene",
            "suggested_action": "create_scene",
            "target": file_path,
            "confidence": 1.0
        }

    # Validation error -> validate
    if source == "validate-all":
        category = "invalid_json"
        if "transition" in msg_lower:
            category = "bad_transition"
        elif "prefab" in msg_lower:
            category = "missing_prefab"
        elif "variant" in msg_lower:
            category = "invalid_variant"
            
        return {
            "issue_id": "validation_error",
            "category": category,
            "suggested_action": "validate",
            "target": file_path,
            "confidence": 0.9
        }
        
    # Check failure -> validate (if it's a scene/world)
    if source == "check" and file_path.endswith(".json"):
         return {
            "issue_id": "check_failure",
            "category": "check_failure",
            "suggested_action": "validate",
            "target": file_path,
            "confidence": 0.8
        }

    return None
