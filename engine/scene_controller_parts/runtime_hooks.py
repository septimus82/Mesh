# mypy: ignore-errors
from __future__ import annotations


def update(self, delta_time: float) -> None:
    self.updater.handle_update(delta_time, self)

def bind_runtime_hooks_methods(cls) -> None:
    cls.update = update
