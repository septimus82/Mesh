import subprocess
import sys
import pytest

def run_help(command):
    """Run a command with --help and return the output."""
    cmd = [sys.executable, "-m", "mesh_cli"] + command + ["--help"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def test_apply_plan_help():
    output = run_help(["apply-plan"])
    assert "Apply a content plan" in output
    assert "plan_path" in output
    assert "--from-triage" in output
    assert "--no-lint" in output
    assert "--dry-run" in output
    assert "--run-tests" in output
    assert "--ai-safe" in output

def test_undo_last_plan_help():
    output = run_help(["undo-last-plan"])
    assert "Undo last applied plan" in output

def test_ai_generate_plan_help():
    output = run_help(["ai-generate-plan"])
    assert "Generate plan from prompt" in output
    assert "prompt" in output
    assert "--out" in output
    assert "--allow-todos" in output

def test_ai_export_context_help():
    output = run_help(["ai-export-context"])
    assert "Export scene context for AI" in output
    assert "scene_paths" in output
    assert "--out" in output

def test_ai_bundle_help():
    output = run_help(["ai-bundle"])
    assert "Create AI bundle" in output
    assert "--scenes" in output
    assert "--goal" in output
    assert "--out" in output

def test_ai_history_help():
    output = run_help(["ai-history"])
    assert "Show AI plan history" in output
    assert "--scene" in output
    assert "--plan" in output
    assert "--limit" in output
    assert "--json" in output

def test_ai_audit_help():
    output = run_help(["ai-audit"])
    assert "Audit scenes and quests for AI completeness" in output
    assert "--json" in output
