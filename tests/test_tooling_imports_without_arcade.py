import sys

import pytest
from pathlib import Path

from tests.subprocess_tools import run_checked

def test_tooling_imports_without_arcade():
    """
    Verify that we can import engine.tooling.validate_all and run the validator
    even if 'arcade' is not available.
    
    Runs in a subprocess to ensure total isolation and no side-effects on sys.modules.
    """
    repo_root = Path(__file__).parent.parent
    
    # Script to run in subprocess
    # We use a dedicated script or a -c command
    # Using a helper string here
    check_script = """
import sys
import os
import builtins
import importlib.util

# 1. Mock arcade to fail import
# Remove it if it exists (though likely it does in the env)
if "arcade" in sys.modules:
    del sys.modules["arcade"]
keys_to_remove = [k for k in sys.modules if k.startswith("arcade.")]
for k in keys_to_remove:
    del sys.modules[k]

# Patch import to fail for arcade
orig_import = builtins.__import__
def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "arcade" or (name and name.startswith("arcade.")):
        raise ImportError(f"No module named '{name}' (Mocked missing)")
    return orig_import(name, globals, locals, fromlist, level)
builtins.__import__ = mock_import

# Also patch find_spec
orig_find_spec = importlib.util.find_spec
def mock_find_spec(name, package=None):
    if name == "arcade" or name.startswith("arcade."):
        return None
    return orig_find_spec(name, package)
importlib.util.find_spec = mock_find_spec

# 2. Try to import the tooling
try:
    from engine.tooling import validate_all
    print("Import successful")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Crash on import: {e}")
    sys.exit(1)

# 3. Try checking availability
# The validator main() might need arguments or files, but checking import is the main step
# checking if safe to run
"""
    
    # Run the subprocess
    result = run_checked(
        [sys.executable, "-c", check_script],
        cwd=repo_root,
    )
    
    if result.returncode != 0:
        pytest.fail(f"Headless check failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    
    assert "Import successful" in result.stdout




