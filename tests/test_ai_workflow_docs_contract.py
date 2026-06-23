from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def _apply_job_op_types() -> set[str]:
    tree = ast.parse(Path("engine/ai_ops.py").read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AIOps":
            for member in node.body:
                if isinstance(member, ast.FunctionDef) and member.name == "apply_job":
                    return {
                        comparator.value
                        for compare in ast.walk(member)
                        if isinstance(compare, ast.Compare)
                        and isinstance(compare.left, ast.Name)
                        and compare.left.id == "op_type"
                        for comparator in compare.comparators
                        if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str)
                    }

    raise AssertionError("AIOps.apply_job not found")


def test_ai_workflow_documents_every_apply_job_operation() -> None:
    doc = Path("docs/ai_workflow.md").read_text(encoding="utf-8")
    missing = sorted(op_type for op_type in _apply_job_op_types() if f"`{op_type}`" not in doc)

    assert not missing
