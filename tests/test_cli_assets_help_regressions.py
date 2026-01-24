import subprocess
import sys
import pytest

def run_help(command):
    """Run a command with --help and return the output."""
    cmd = [sys.executable, "-m", "mesh_cli"] + command + ["--help"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def test_index_help():
    output = run_help(["index"])
    assert "Rebuild project index" in output

def test_doctor_assets_help():
    output = run_help(["doctor-assets"])
    assert "Inventory content/assets deterministically" in output
    assert "--fix" in output
    assert "--strict" in output

def test_schema_fix_ids_help():
    output = run_help(["schema-fix-ids"])
    assert "Deterministically add missing entity ids" in output
    assert "--dry-run" in output
    assert "--paths" in output

def test_polish_help():
    output = run_help(["polish"])
    assert "Polish content" in output
    assert "--compact-scenes" in output
    assert "--export-graph" in output

def test_migrate_help():
    output = run_help(["migrate"])
    assert "Migrate content to latest version" in output
    assert "--write" in output

def test_sprite_help():
    output = run_help(["sprite"])
    assert "Sprite authoring utilities" in output
    assert "import-sheet" in output

def test_sprite_import_sheet_help():
    output = run_help(["sprite", "import-sheet"])
    assert "Import a spritesheet" in output
    assert "--prefab-id" in output
    assert "--frame-w" in output
    assert "--anim" in output
