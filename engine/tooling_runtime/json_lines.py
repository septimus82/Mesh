from __future__ import annotations

import json
from typing import Any

from engine.validators.schema_validation import render_validation_error_line as render_validation_error_line


def dumps_one_line(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

