"""Moved to ``engine.tooling.export_bundle``: it ships with Mesh (``mesh export``, ``mesh assets``), so a pip-installed Mesh has it
(issue #357). This name stays so repository scripts and ``python -m tooling.export_bundle`` keep working."""

import sys

from engine.tooling import export_bundle as _module

if __name__ == "__main__":
    raise SystemExit(_module.main())
sys.modules[__name__] = _module
