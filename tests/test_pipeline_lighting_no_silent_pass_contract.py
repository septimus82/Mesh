import ast
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TARGETS = (
    _REPO_ROOT / "mesh_cli" / "verify_steps" / "pipeline.py",
    _REPO_ROOT / "engine" / "lighting" / "__init__.py",
    _REPO_ROOT / "engine" / "ui_overlays" / "hud.py",
)
_APPROVED_LOG_HELPERS = {"_log_swallow", "_log_once_debug", "_log_once_error"}
_BASELINE_SILENT_PASSES = {
    "mesh_cli/verify_steps/pipeline.py": (),
    "engine/lighting/__init__.py": (370, 375, 380),
    "engine/ui_overlays/hud.py": (),
}
_BASELINE_EXCEPTION_ENVELOPES = {
    "mesh_cli/verify_steps/pipeline.py": (
        350, 390, 410, 435, 479, 505, 544, 584, 712, 763,
        791, 854, 933, 1070, 1128, 1172, 1365, 1570, 1803, 2069,
        2102, 2134, 2168, 2191, 2217, 2253, 2310, 2375, 2429, 2465,
    ),
    "engine/lighting/__init__.py": (
        416, 424, 433, 441, 450, 469, 478, 488, 813, 953,
        982, 1019,
    ),
    "engine/ui_overlays/hud.py": (68, 169),
}


def _iter_calls(node: ast.AST) -> list[ast.Call]:
    return [child for child in ast.walk(node) if isinstance(child, ast.Call)]


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _has_approved_log_call(handler: ast.ExceptHandler) -> bool:
    for stmt in handler.body:
        for call in _iter_calls(stmt):
            if _call_name(call) in _APPROVED_LOG_HELPERS:
                return True
    return False


def _matches_forbidden_silent_type(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in {"Exception", "TypeError", "ValueError"}
    if isinstance(handler.type, ast.Tuple):
        names = {elt.id for elt in handler.type.elts if isinstance(elt, ast.Name)}
        return bool(names & {"Exception", "TypeError", "ValueError"})
    return False


def _is_forbidden_silent_handler(handler: ast.ExceptHandler) -> bool:
    if not any(isinstance(stmt, ast.Pass) for stmt in handler.body):
        return False
    if not _matches_forbidden_silent_type(handler):
        return False
    return not _has_approved_log_call(handler)


def _is_exception_envelope(handler: ast.ExceptHandler) -> bool:
    return isinstance(handler.type, ast.Name) and handler.type.id == "Exception"


def _has_envelope_marker(lines: list[str], lineno: int) -> bool:
    for candidate in (lineno - 1, lineno - 2):
        if 0 <= candidate < len(lines) and "EXC_ENVELOPE: runtime-dependent" in lines[candidate]:
            return True
    return False


def test_pipeline_lighting_and_hud_have_no_except_pass_blocks() -> None:
    failures: list[str] = []

    for path in _TARGETS:
        rel = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        baseline = set(_BASELINE_SILENT_PASSES.get(rel, ()))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.lineno in baseline:
                continue
            if _is_forbidden_silent_handler(node):
                failures.append(f"{rel}:{node.lineno}: except-pass block is forbidden")

    assert not failures, "Silent except-pass contract violations:\n" + "\n".join(sorted(failures))


def test_pipeline_lighting_and_hud_new_exception_envelopes_require_marker() -> None:
    failures: list[str] = []

    for path in _TARGETS:
        rel = path.relative_to(_REPO_ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        tree = ast.parse("\n".join(lines) + "\n", filename=rel)
        baseline = set(_BASELINE_EXCEPTION_ENVELOPES.get(rel, ()))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not _is_exception_envelope(node):
                continue
            if node.lineno in baseline:
                continue
            if _has_envelope_marker(lines, node.lineno):
                continue
            failures.append(
                f"{rel}:{node.lineno}: new except Exception requires '# EXC_ENVELOPE: runtime-dependent'"
            )

    assert not failures, "Broad exception envelope ratchet violations:\n" + "\n".join(sorted(failures))
