"""Compatibility facade for verify-demo.

The implementation lives in `engine.tooling_runtime.verify_demo`.
This module re-exports the public surface used by `mesh_cli.py`.
"""

from engine.tooling_runtime.verify_demo import (  # noqa: F401
    build_verify_demo_pytest_cmd,
    iter_missing_paths,
    run_verify_demo,
    validate_pytest_passthrough_args,
)

# Keep a patchable subprocess binding for existing tests/callers that
# monkeypatch `engine.tooling.verify_demo.subprocess.run`.
from engine.tooling_runtime.verify_demo import subprocess as subprocess  # noqa: F401,E402
