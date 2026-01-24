from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from engine.tooling_runtime.event_validator import EventValidatorCore


class EventValidator(EventValidatorCore):
    pass


def main(argv: List[str] | None = None) -> int:
    validator = EventValidator(Path("."))
    return validator.run()


if __name__ == "__main__":
    sys.exit(main())

