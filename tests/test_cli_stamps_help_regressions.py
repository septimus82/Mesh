import subprocess
import sys
import pytest

def run_help(command):
    """Run a command with --help and return the output."""
    cmd = [sys.executable, "-m", "mesh_cli"] + command + ["--help"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def test_stamp_help():
    output = run_help(["stamp"])
    assert "Stamp discovery and validation" in output
    assert "list" in output
    assert "validate-all" in output
    assert "preview" in output

def test_stamp_list_help():
    output = run_help(["stamp", "list"])
    assert "List available stamps under packs/*/stamps" in output
    assert "--pack" in output
    assert "--format" in output

def test_stamp_validate_help():
    output = run_help(["stamp", "validate-all"])
    assert "Validate all stamps (quality gate)" in output
    assert "--pack" in output

def test_stamp_preview_help():
    output = run_help(["stamp", "preview"])
    assert "Render an ASCII preview of a stamp layer" in output
    assert "stamp_path" in output
    assert "--layer" in output
    assert "--tile" in output
    assert "--format" in output

def test_brush_help():
    output = run_help(["brush"])
    assert "Brush discovery and validation" in output
    assert "list" in output
    assert "validate-all" in output
    assert "preview" in output

def test_brush_list_help():
    output = run_help(["brush", "list"])
    assert "List available brushes under packs/*/brushes" in output
    assert "--pack" in output
    assert "--format" in output

def test_brush_validate_help():
    output = run_help(["brush", "validate-all"])
    assert "Validate all brushes (quality gate)" in output
    assert "--pack" in output

def test_brush_preview_help():
    output = run_help(["brush", "preview"])
    assert "Render an ASCII preview of a brush" in output
    assert "brush_path" in output
    assert "--layer" in output
    assert "--tile" in output
    assert "--format" in output

def test_capture_help():
    output = run_help(["capture"])
    assert "Captured asset discovery and validation" in output
    assert "list" in output
    assert "validate-all" in output

def test_capture_list_help():
    output = run_help(["capture", "list"])
    assert "List captured stamps/brushes under packs/*" in output
    assert "--pack" in output
    assert "--format" in output

def test_capture_validate_help():
    output = run_help(["capture", "validate-all"])
    assert "Validate all captured stamps/brushes (quality gate)" in output
    assert "--pack" in output
