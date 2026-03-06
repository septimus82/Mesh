from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TARGET_FILES = (
    _REPO_ROOT / "engine" / "command_palette_registry_actions_impl.py",
    _REPO_ROOT / "engine" / "lighting" / "shadow_pipeline.py",
    _REPO_ROOT / "engine" / "sprite_shadow_model.py",
    _REPO_ROOT / "engine" / "lighting" / "__init__.py",
    _REPO_ROOT / "engine" / "depth_tint_model.py",
    _REPO_ROOT / "mesh_cli" / "verify_steps" / "pipeline.py",
    _REPO_ROOT / "mesh_cli" / "verify.py",
    _REPO_ROOT / "engine" / "editor" / "asset_ops" / "editor_file_ops_controller.py",
    _REPO_ROOT / "engine" / "ui_overlays" / "providers.py",
    _REPO_ROOT / "mesh_cli" / "legacy_impl.py",
    _REPO_ROOT / "mesh_cli" / "assets.py",
    _REPO_ROOT / "engine" / "audio.py",
    _REPO_ROOT / "engine" / "physics_runtime.py",
    _REPO_ROOT / "engine" / "tooling_runtime" / "doctor_assets_registry.py",
)

_BARE_PASS_RE = re.compile(r"except\s*:\s*pass")
_EXC_PASS_RE = re.compile(r"except\s+Exception(?:\s+as\s+\w+)?\s*:\s*pass")


def _is_blanket_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return isinstance(handler.type, ast.Name) and handler.type.id == "Exception"


def _has_logging_call(node: ast.ExceptHandler) -> bool:
    for stmt in node.body:
        for child in ast.walk(stmt):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name) and func.id == "_log_swallow":
                return True
            if isinstance(func, ast.Attribute):
                if func.attr == "_log_swallow":
                    return True
                if isinstance(func.value, ast.Name) and func.value.id == "logger" and func.attr in {"debug", "exception"}:
                    return True
    return False


def test_blanket_swallow_sites_log_exceptions_contract() -> None:
    failures: list[str] = []

    for path in _TARGET_FILES:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(_REPO_ROOT).as_posix()

        if _BARE_PASS_RE.search(text):
            failures.append(f"{rel}: found forbidden `except: pass`")
        if _EXC_PASS_RE.search(text):
            failures.append(f"{rel}: found forbidden `except Exception: pass`")

        tree = ast.parse(text, filename=rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not _is_blanket_exception(node):
                continue
            if _has_logging_call(node):
                continue
            failures.append(f"{rel}:{node.lineno}: blanket catch without swallow logging")

    assert not failures, "Swallow logging contract violations:\n" + "\n".join(sorted(failures))
