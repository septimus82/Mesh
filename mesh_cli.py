"""Compatibility shim for local dev workflows.

The CLI implementation now lives in the `mesh_cli/` package.
`python -m mesh_cli ...` uses `mesh_cli.__main__`.
`python mesh_cli.py ...` continues to work via this shim.
"""

from __future__ import annotations

from mesh_cli.main import main

raise SystemExit(main())

