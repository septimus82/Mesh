from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from json import JSONDecodeError

from engine.config import EngineConfig, load_config
from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from engine.quests import QuestManager
from engine.tooling.state_dump import dump_state


@dataclass(slots=True)
class ReplayWindow:
    """Lightweight stub window that supports quest/event + game state machinery."""

    engine_config: EngineConfig
    scene_controller: Any
    game_state_controller: GameStateController = field(init=False)
    quest_manager: QuestManager = field(init=False)

    def __post_init__(self) -> None:
        self.game_state_controller = GameStateController(self)  # type: ignore[arg-type]

        repo_root = Path(__file__).resolve().parents[2]
        quests_path = repo_root / "assets" / "data" / "quests.json"
        self.quest_manager = QuestManager(self, data_path=str(quests_path))

    # GameWindow-like helpers used by QuestManager rewards.
    @property
    def game_state(self):
        return self.game_state_controller.state

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)

    def set_var(self, name: str, value: Any) -> None:
        self.game_state_controller.set_var(name, value)

    def get_var(self, name: str, default: Any = None) -> Any:
        return self.game_state_controller.get_var(name, default)

    def console_log(self, message: str) -> None:
        # Keep tests deterministic: no extra printing.
        return None

    def emit_signal(self, event_type: str, **payload: Any) -> None:  # noqa: ARG002
        # Replay scripts don't need the full event queue.
        return None


def _default_window_factory(script: dict[str, Any]) -> ReplayWindow:
    preset = str(script.get("preset") or "").strip() or None
    world_file = str(script.get("world_file") or "").strip() or None
    scene_path = str(script.get("scene_path") or "").strip() or None

    cfg = load_config()

    if preset:
        os.environ["MESH_ACTIVE_PRESET"] = preset
        preset_cfg = (cfg.presets or {}).get(preset)
        if isinstance(preset_cfg, dict):
            wf = preset_cfg.get("world_file")
            if wf and not world_file:
                world_file = str(wf)
            ss = preset_cfg.get("start_scene")
            if ss and not scene_path:
                scene_path = str(ss)

    engine_cfg = EngineConfig()
    engine_cfg.world_file = world_file or cfg.world_file

    if not scene_path:
        scene_path = cfg.start_scene

    scene_controller = type("Scene", (), {"current_scene_path": scene_path})()
    return ReplayWindow(engine_config=engine_cfg, scene_controller=scene_controller)


def _emit_event(window: Any, event_type: str, payload: dict[str, Any]) -> None:
    # Update game state controller (records last_zone_id, etc.).
    gsc = getattr(window, "game_state_controller", None)
    if gsc is not None and hasattr(gsc, "handle_event"):
        gsc.handle_event({"type": event_type, "payload": dict(payload)})

    # Update runtime quest manager (applies rewards).
    qm = getattr(window, "quest_manager", None)
    if qm is not None and hasattr(qm, "handle_event"):
        qm.handle_event(MeshEvent(type=event_type, payload=dict(payload)))


def _repr_expect_value(value: Any) -> str:
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(f"'{item}'")
            else:
                parts.append(repr(item))
        return "[" + ", ".join(parts) + "]"
    return repr(value)


def _validate_expect_state(expect_state: Any) -> dict[str, Any]:
    if expect_state is None:
        return {}
    if not isinstance(expect_state, dict):
        raise ValueError("expect_state must be an object")

    normalized: dict[str, Any] = {}
    for raw_key, expected in expect_state.items():
        key = str(raw_key)
        if isinstance(expected, dict):
            raise ValueError(f"expect_state value for '{key}' must not be an object")

        if isinstance(expected, list):
            if not all(isinstance(x, str) for x in expected):
                raise ValueError(f"expect_state '{key}' must be a list of strings")
            normalized[key] = list(expected)
            continue

        if isinstance(expected, (str, int, bool)):
            normalized[key] = expected
            continue

        raise ValueError(f"expect_state '{key}' has unsupported value type")

    return normalized


def _load_expect_state_file(*, expect_state_file: str, script_path: Path | None) -> dict[str, Any]:
    raw = str(expect_state_file or "").strip()
    if not raw:
        return {}

    path = Path(raw)
    if not path.is_absolute():
        if script_path is None:
            raise ValueError("expect_state_file is relative but script path is unknown")
        path = (script_path.parent / path).resolve()

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        raise ValueError(f"expect_state_file not found: {path}")
    except JSONDecodeError:
        raise ValueError(f"expect_state_file invalid JSON: {path}")

    if not isinstance(payload, dict):
        raise ValueError(f"expect_state_file must be a JSON object: {path}")

    # Validate allowed types (dict values rejected, etc.).
    return _validate_expect_state(payload)


def _check_expect_state(final_state: dict[str, Any], expect_state: dict[str, Any]) -> None:
    for key in sorted(expect_state.keys()):
        expected = expect_state[key]
        actual = final_state.get(key, None)

        if isinstance(expected, list):
            if not isinstance(actual, list) or actual != expected:
                raise ValueError(
                    "expect_state mismatch: "
                    f"{key} expected {_repr_expect_value(expected)} got {_repr_expect_value(actual)}"
                )
            continue

        if actual != expected:
            raise ValueError(
                "expect_state mismatch: "
                f"{key} expected {_repr_expect_value(expected)} got {_repr_expect_value(actual)}"
            )


def run_replay_script(
    script: dict[str, Any],
    *,
    window_factory: Callable[[dict[str, Any]], Any] | None = None,
    script_path: Path | None = None,
) -> dict[str, Any]:
    """Run a deterministic replay script and return the final state dump."""

    _window, final_dump = run_replay_script_with_window(
        script,
        window_factory=window_factory,
        script_path=script_path,
    )
    return final_dump


def run_replay_script_with_window(
    script: dict[str, Any],
    *,
    window_factory: Callable[[dict[str, Any]], Any] | None = None,
    script_path: Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Run a deterministic replay script and return (window, final state dump)."""

    if not isinstance(script, dict):
        raise ValueError("Replay script root must be an object")

    steps = script.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Replay script must contain a 'steps' list")

    window_factory = window_factory or _default_window_factory
    window = window_factory(script)

    flags_sample_limit = script.get("flags_sample_limit", 10)
    try:
        flags_sample_limit = int(flags_sample_limit)
    except (TypeError, ValueError):
        flags_sample_limit = 10

    last_dump: dict[str, Any] | None = None

    for step in steps:
        if not isinstance(step, dict):
            continue

        if step.get("dump_state") is True:
            last_dump = dump_state(window, flags_sample_limit=flags_sample_limit)
            continue

        emit_kind = step.get("emit")
        if emit_kind == "entered_zone":
            zone_id = str(step.get("zone_id") or step.get("zone") or "").strip()
            if zone_id:
                _emit_event(window, "entered_zone", {"zone": zone_id})
            continue

        if emit_kind == "event":
            name = str(step.get("name") or "").strip()
            if not name:
                continue
            payload = step.get("payload")
            payload_dict = dict(payload) if isinstance(payload, dict) else {}
            _emit_event(window, name, payload_dict)
            continue

    final = last_dump or dump_state(window, flags_sample_limit=flags_sample_limit)

    if "expect_state" in script and "expect_state_file" in script and script.get("expect_state") is not None and script.get("expect_state_file") is not None:
        raise ValueError("expect_state and expect_state_file are mutually exclusive")

    expect_state = _validate_expect_state(script.get("expect_state"))
    if not expect_state and script.get("expect_state_file") is not None:
        expect_state = _load_expect_state_file(
            expect_state_file=str(script.get("expect_state_file") or ""),
            script_path=script_path,
        )

    if expect_state:
        _check_expect_state(final, expect_state)

    return window, final


def load_replay_script(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Replay script must be a JSON object")
    return payload
