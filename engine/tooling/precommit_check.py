#!/usr/bin/env python3
"""Pre-commit check script for Mesh Engine."""

import sys
from pathlib import Path

# Ensure we can import engine modules
root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))

from engine.tooling import check  # noqa: E402

if __name__ == "__main__":
    sys.exit(check.main())
