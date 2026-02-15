from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RestorePolicy:
    strict_schema: bool
    strict_restore: bool
    write_sidecars_on_failure: bool
    surface_in_debug_bundle: bool


SLOT_POLICY = RestorePolicy(
    strict_schema=True,
    strict_restore=True,
    write_sidecars_on_failure=True,
    surface_in_debug_bundle=True,
)

SNAPSHOT_POLICY = RestorePolicy(
    strict_schema=True,
    strict_restore=False,
    write_sidecars_on_failure=True,
    surface_in_debug_bundle=True,
)

REPLAY_POLICY = RestorePolicy(
    strict_schema=True,
    strict_restore=False,
    write_sidecars_on_failure=False,
    surface_in_debug_bundle=False,
)

