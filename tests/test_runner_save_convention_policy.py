from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNNER_SPECS: tuple[tuple[str, str], ...] = (
    ("engine/behaviours/dialogue_runner.py", "DialogueRunnerBehaviour"),
    ("engine/cutscene_runtime/runner.py", "CutsceneRunner"),
    ("engine/quest_runtime/runner.py", "QuestRunner"),
)


def _read_tree(relative_path: str) -> ast.Module:
    path = ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=relative_path)


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _has_method(class_node: ast.ClassDef, name: str) -> bool:
    return any(isinstance(node, ast.FunctionDef) and node.name == name for node in class_node.body)


def _state_version_value(class_node: ast.ClassDef) -> int | None:
    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != "STATE_VERSION":
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
            return int(node.value.value)
        return None
    return None


def _method_calls_encode_state(class_node: ast.ClassDef) -> bool:
    for node in class_node.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "saveable_state":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name) and func.id == "encode_state":
                return True
    return False


def test_runner_save_conventions_are_wrapped_and_versioned() -> None:
    violations: list[str] = []
    for relative_path, class_name in RUNNER_SPECS:
        tree = _read_tree(relative_path)
        class_node = _find_class(tree, class_name)
        if class_node is None:
            violations.append(f"{relative_path}:?:{class_name} missing class")
            continue

        state_version = _state_version_value(class_node)
        if state_version is None or state_version <= 0:
            violations.append(f"{relative_path}:{class_node.lineno}:{class_name} missing positive STATE_VERSION")

        if not _has_method(class_node, "saveable_state"):
            violations.append(f"{relative_path}:{class_node.lineno}:{class_name} missing saveable_state()")
        if not _has_method(class_node, "restore_state"):
            violations.append(f"{relative_path}:{class_node.lineno}:{class_name} missing restore_state()")
        if not _method_calls_encode_state(class_node):
            violations.append(
                f"{relative_path}:{class_node.lineno}:{class_name} saveable_state() must call encode_state(...)"
            )

    assert not violations, (
        "Runner save convention policy failed. Each canonical runner must define STATE_VERSION and "
        "wrapped saveable_state()/restore_state() using encode_state/decode_state. "
        f"Offenders: {sorted(violations)}"
    )
