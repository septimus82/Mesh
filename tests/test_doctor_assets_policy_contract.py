"""
Policy tests for doctor_assets orchestration.
"""
from __future__ import annotations

import ast
import inspect

from engine.tooling_runtime import asset_doctor


def test_doctor_assets_is_thin() -> None:
    source = inspect.getsource(asset_doctor.doctor_assets)
    assert len(source.splitlines()) <= 120

    tree = ast.parse(source)
    func = next((n for n in tree.body if isinstance(n, ast.FunctionDef)), None)
    assert func is not None
    nested_defs = [n for n in ast.walk(func) if isinstance(n, (ast.FunctionDef, ast.Lambda))]
    # Includes the function itself; ensure no nested defs/lambdas.
    assert len(nested_defs) == 1
