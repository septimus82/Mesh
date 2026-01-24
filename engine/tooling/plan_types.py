from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Action:
    type: str
    args: Dict[str, Any]
    description: str

@dataclass
class Plan:
    wizard: str
    version: int
    inputs: Dict[str, Any]
    actions: List[Action]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Plan':
        actions = [Action(**a) for a in data.get("actions", [])]
        return cls(
            wizard=data.get("wizard", "unknown"),
            version=data.get("version", 1),
            inputs=data.get("inputs", {}),
            actions=actions
        )
