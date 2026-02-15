"""Episode replay-check command for deterministic playtest artifacts."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

from engine.diagnostics import Diagnostic, DiagnosticLevel
from engine.cutscene_runtime.runner import CutsceneRunner
from engine.gameplay_event_bus import GameplayEvent, GameplayEventBus
from engine.game_state_controller import GameState
from engine.logging_tools import suppress_stdout
from engine.persistence_io import (
    dumps_json_deterministic,
    write_json_atomic,
    write_text_atomic,
)
from engine.provenance import get_provenance, provenance_to_dict
from engine.quest_runtime.runner import QuestRunner
from engine.save_runtime.save_diagnostics import SaveDiagnosticsAggregator
from engine.save_runtime.digest import compute_world_digest
from engine.save_runtime.normalize import normalize_save_payload
from engine.save_runtime.restore_policy import REPLAY_POLICY, RestorePolicy
from engine.state_runtime import flags as state_flags
from .replay_digest_projection import (
    project_event_for_digest as _project_event_for_digest,
    project_final_state_for_digest as _project_final_state_for_digest,
    project_world_digests_for_digest as _project_world_digests_for_digest,
)


SCHEMA_VERSION = 1
DEFAULT_SEED = 123
PREFIX_PATTERN = re.compile(r"^([a-z]+[0-9]+)_")

DEFAULT_PREFABS_PATH = Path("assets/prefabs.json")
DEFAULT_QUESTS_PATH = Path("assets/data/quests.json")
DEFAULT_DIALOGUES_PATH = Path("assets/data/dialogues.json")
DEFAULT_CUTSCENES_PATH = Path("cutscenes.json")


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    repo_root: Path
    scene_path: Path
    scene_rel: str
    script_path: Path
    script_rel: str
    out_dir: Path
    out_dir_rel: str
    seed: int
    episode_prefix: str
    quest_id: str | None
    intro_cutscene_id: str | None
    outro_cutscene_id: str | None
    prefabs_path: Path = DEFAULT_PREFABS_PATH
    quests_path: Path = DEFAULT_QUESTS_PATH
    dialogues_path: Path = DEFAULT_DIALOGUES_PATH
    cutscenes_path: Path = DEFAULT_CUTSCENES_PATH


@dataclass(slots=True)
class ReplayContext:
    spec: RuntimeSpec
    window: MagicMock
    entities: dict[str, Any]
    behaviours: dict[str, dict[str, Any]]
    action_runners: list[Any]
    trigger_volumes: dict[str, Any]
    interactables: dict[str, Any]
    dialogue_runners: dict[str, Any]
    quest_runner: QuestRunner
    cutscene_runners: dict[str, CutsceneRunner]
    event_log: list[dict[str, Any]] = field(default_factory=list)
    player_entity_id: str = ""


@dataclass(frozen=True, slots=True)
class ParsedAction:
    tick: int
    index: int
    data: dict[str, Any]


@dataclass(slots=True)
class ReplayRunResult:
    ok: bool
    error: str | None
    events: list[dict[str, Any]]
    digests: list[dict[str, Any]]
    snapshots: list[dict[str, Any]]
    final_state_bundle: dict[str, Any]
    save_actions: int
    restore_actions: int
    tick_ms_list: list[float]
    total_ms: float
    tick_ms_p50: float
    tick_ms_p95: float
    tick_ms_max: float
    save_restore_diagnostics: dict[str, Any]


def register(subparsers: argparse._SubParsersAction) -> None:
    episode_parser = subparsers.add_parser(
        "episode",
        help="Episode tooling commands",
        description="Deterministic episode replay checks",
    )
    episode_subparsers = episode_parser.add_subparsers(dest="episode_command", help="Episode subcommand")

    replay_parser = episode_subparsers.add_parser(
        "replay-check",
        help="Run deterministic replay-check for an episode scene",
        description=(
            "Loads an episode scene, executes scripted actions on a deterministic dt schedule, "
            "captures events/digests/state snapshots, and verifies run-to-run determinism."
        ),
    )
    replay_parser.add_argument("--scene", required=True, help="Episode scene file path")
    replay_parser.add_argument("--script", required=True, help="Replay script JSON path")
    replay_parser.add_argument("--out-dir", required=True, help="Output artifacts directory")
    replay_parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Deterministic seed (default: {DEFAULT_SEED})")
    replay_parser.add_argument("--json", action="store_true", dest="episode_json", help="Print report JSON to stdout")
    replay_parser.add_argument("--quiet", action="store_true", help="Suppress non-essential stdout")


def handle(args: argparse.Namespace) -> int:
    subcommand = getattr(args, "episode_command", None)
    if subcommand == "replay-check":
        return _handle_replay_check(args)
    print("[Mesh][Episode] Error: missing episode subcommand")
    return 2


def _handle_replay_check(args: argparse.Namespace) -> int:
    quiet = bool(getattr(args, "quiet", False))
    json_stdout = bool(getattr(args, "episode_json", False))
    seed = int(getattr(args, "seed", DEFAULT_SEED))

    try:
        repo_root = _get_repo_root()
        scene_path = _resolve_scene_path(str(getattr(args, "scene", "") or "").strip(), repo_root)
        script_path = _resolve_script_path(str(getattr(args, "script", "") or "").strip(), repo_root)
        out_dir = _resolve_output_dir(str(getattr(args, "out_dir", "") or "").strip(), repo_root)
        out_dir.mkdir(parents=True, exist_ok=True)
        script_payload = _load_json_file(script_path)
        if not isinstance(script_payload, dict):
            raise ValueError(f"Replay script must be a JSON object: {_rel_path(script_path, repo_root)}")

        scene_payload = _load_json_file(scene_path)
        if not isinstance(scene_payload, dict):
            raise ValueError(f"Scene file must be a JSON object: {_rel_path(scene_path, repo_root)}")

        prefabs_payload = _load_json_file(repo_root / DEFAULT_PREFABS_PATH)
        if not isinstance(prefabs_payload, list):
            raise ValueError(f"{DEFAULT_PREFABS_PATH.as_posix()} must be a JSON array")
        prefabs_map = _prefab_map(prefabs_payload)

        cutscenes_payload = _load_json_file(repo_root / DEFAULT_CUTSCENES_PATH)
        if not isinstance(cutscenes_payload, dict):
            raise ValueError(f"{DEFAULT_CUTSCENES_PATH.as_posix()} must be a JSON object")

        quests_payload = _load_json_file(repo_root / DEFAULT_QUESTS_PATH)
        if not isinstance(quests_payload, dict):
            raise ValueError(f"{DEFAULT_QUESTS_PATH.as_posix()} must be a JSON object")

        episode_prefix = _derive_episode_prefix(
            scene_payload=scene_payload,
            prefabs_map=prefabs_map,
            replay_payload=script_payload,
        )
        intro_cutscene_id, outro_cutscene_id = _detect_cutscene_ids(episode_prefix, cutscenes_payload)
        quest_id = _detect_quest_id(episode_prefix, quests_payload)

        spec = RuntimeSpec(
            repo_root=repo_root,
            scene_path=scene_path,
            scene_rel=_rel_path(scene_path, repo_root),
            script_path=script_path,
            script_rel=_rel_path(script_path, repo_root),
            out_dir=out_dir,
            out_dir_rel=_rel_path(out_dir, repo_root),
            seed=seed,
            episode_prefix=episode_prefix,
            quest_id=quest_id,
            intro_cutscene_id=intro_cutscene_id,
            outro_cutscene_id=outro_cutscene_id,
        )

        with suppress_stdout():
            run_1 = _run_replay_once(spec, script_payload)
            run_2 = _run_replay_once(spec, script_payload) if run_1.ok else ReplayRunResult(
                ok=False,
                error="skipped: run_1 failed",
                events=[],
                digests=[],
                snapshots=[],
                final_state_bundle={},
                save_actions=0,
                restore_actions=0,
                tick_ms_list=[],
                total_ms=0.0,
                tick_ms_p50=0.0,
                tick_ms_p95=0.0,
                tick_ms_max=0.0,
                save_restore_diagnostics={"counts": {"total": 0, "errors": 0, "warnings": 0, "infos": 0}, "diagnostics": []},
            )

        determinism = {
            "digests_match": run_1.ok and run_2.ok and run_1.digests == run_2.digests,
            "events_match": run_1.ok and run_2.ok and run_1.events == run_2.events,
            "final_state_match": run_1.ok and run_2.ok and run_1.final_state_bundle == run_2.final_state_bundle,
        }
        ok = run_1.ok and run_2.ok and all(bool(v) for v in determinism.values())
        digest_triplet = {
            "expected_event_digest": "",
            "expected_world_digest": "",
            "expected_final_state_digest": "",
        }
        if run_1.ok:
            run_1_final_state_payload = {
                "schema_version": 1,
                "final_state": run_1.final_state_bundle,
                "snapshots": run_1.snapshots,
            }
            digest_triplet = _compute_replay_artifact_digest_triplet(
                events=run_1.events,
                world_digests=run_1.digests,
                final_state_payload=run_1_final_state_payload,
            )

        report = {
            "schema_version": SCHEMA_VERSION,
            "ok": ok,
            "seed": seed,
            "scene": spec.scene_rel,
            "script": spec.script_rel,
            "out_dir": spec.out_dir_rel,
            "episode": {
                "prefix": spec.episode_prefix,
                "quest_id": spec.quest_id,
                "intro_cutscene_id": spec.intro_cutscene_id,
                "outro_cutscene_id": spec.outro_cutscene_id,
            },
            "determinism": determinism,
            "run_1": _summarize_run(run_1),
            "run_2": _summarize_run(run_2),
            "expected_event_digest": digest_triplet["expected_event_digest"],
            "expected_world_digest": digest_triplet["expected_world_digest"],
            "expected_final_state_digest": digest_triplet["expected_final_state_digest"],
            "artifacts": {
                "report_json": "replay_report.json",
                "report_txt": "replay_report.txt",
                "events_ndjson": "events.ndjson",
                "digests_json": "digests.json",
                "final_state_bundle_json": "final_state_bundle.json",
                "timings_json": "timings.json",
                "save_restore_diagnostics_json": "save_restore_diagnostics.json",
                "save_restore_diagnostics_txt": "save_restore_diagnostics.txt",
            },
            "provenance": provenance_to_dict(get_provenance(deterministic=True)),
        }
        _write_replay_artifacts(out_dir=out_dir, report=report, run=run_1)

        if json_stdout:
            sys.stdout.write(dumps_json_deterministic(report))
            sys.stdout.write("\n")
        elif not quiet:
            print(_format_replay_report_text(report), end="")

        return 0 if ok else 1
    except ValueError as exc:
        print(f"[Mesh][Episode] ERROR: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][Episode] ERROR: {type(exc).__name__}: {exc}")
        return 1


def _get_repo_root() -> Path:
    try:
        from engine.repo_root import get_repo_root

        return get_repo_root(start=Path.cwd(), strict=True)
    except Exception:
        return Path.cwd().resolve()


def _resolve_scene_path(raw: str, repo_root: Path) -> Path:
    if not raw:
        raise ValueError("--scene is required")
    candidate = Path(raw)
    if not candidate.is_absolute():
        direct = repo_root / candidate
        scene_dir = repo_root / "scenes" / candidate
        if direct.exists():
            candidate = direct
        elif scene_dir.exists():
            candidate = scene_dir
        else:
            raise ValueError(f"scene not found: {raw}")
    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"scene not found: {raw}")
    return candidate.resolve()


def _resolve_script_path(raw: str, repo_root: Path) -> Path:
    if not raw:
        raise ValueError("--script is required")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    if not candidate.exists() or not candidate.is_file():
        raise ValueError(f"script not found: {raw}")
    return candidate


def _resolve_output_dir(raw: str, repo_root: Path) -> Path:
    if not raw:
        raise ValueError("--out-dir is required")
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _rel_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.name


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at {path.as_posix()}: {exc}") from exc


def _prefab_map(prefabs: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in prefabs:
        if not isinstance(entry, dict):
            continue
        prefab_id = str(entry.get("id", "")).strip()
        if prefab_id:
            out[prefab_id] = entry
    return out


def _dialogue_map(dialogues_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    entries = dialogues_payload.get("dialogues", [])
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        dialogue_id = str(entry.get("id", "")).strip()
        if dialogue_id:
            out[dialogue_id] = entry
    return out


def _derive_episode_prefix(
    *,
    scene_payload: dict[str, Any],
    prefabs_map: dict[str, dict[str, Any]],
    replay_payload: dict[str, Any],
) -> str:
    counts: Counter[str] = Counter()

    for action in replay_payload.get("actions", []):
        if not isinstance(action, dict):
            continue
        if str(action.get("type", "")).strip() != "emit":
            continue
        event_name = str(action.get("event", action.get("event_type", ""))).strip()
        prefix = _event_prefix(event_name)
        if prefix:
            counts[prefix] += 1

    entities = scene_payload.get("entities", [])
    if isinstance(entities, list):
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            merged_cfg = _merged_behaviour_configs(entity, prefabs_map)
            for behaviour_name, cfg in merged_cfg.items():
                if not isinstance(cfg, dict):
                    continue
                if behaviour_name == "TriggerVolume":
                    for key in ("on_enter_event", "on_exit_event"):
                        prefix = _event_prefix(str(cfg.get(key, "")).strip())
                        if prefix:
                            counts[prefix] += 1
                elif behaviour_name == "Interactable":
                    prefix = _event_prefix(str(cfg.get("interact_event", "")).strip())
                    if prefix:
                        counts[prefix] += 1
                elif behaviour_name == "ActionListRunner":
                    listen_events = cfg.get("listen_events", [])
                    if isinstance(listen_events, list):
                        for event_name in listen_events:
                            prefix = _event_prefix(str(event_name).strip())
                            if prefix:
                                counts[prefix] += 1
                    actions = cfg.get("actions", [])
                    if isinstance(actions, list):
                        for action in actions:
                            if not isinstance(action, dict):
                                continue
                            if str(action.get("type", "")).strip() != "emit_event":
                                continue
                            event_name = str(action.get("event_type", "")).strip()
                            prefix = _event_prefix(event_name)
                            if prefix:
                                counts[prefix] += 1

    if not counts:
        raise ValueError(
            "could not infer episode prefix; ensure scene or replay emits events like 'ep02_entered'"
        )

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked[0][0]


def _event_prefix(event_name: str) -> str | None:
    match = PREFIX_PATTERN.match(event_name)
    if match is None:
        return None
    return match.group(1)


def _detect_cutscene_ids(prefix: str, cutscenes_payload: dict[str, Any]) -> tuple[str | None, str | None]:
    cutscenes = cutscenes_payload.get("cutscenes", [])
    if not isinstance(cutscenes, list):
        return (None, None)
    ids = {
        str(entry.get("id", "")).strip()
        for entry in cutscenes
        if isinstance(entry, dict)
    }
    intro = f"{prefix}_intro"
    outro = f"{prefix}_outro"
    return (intro if intro in ids else None, outro if outro in ids else None)


def _detect_quest_id(prefix: str, quests_payload: dict[str, Any]) -> str | None:
    quests = quests_payload.get("quests", [])
    if not isinstance(quests, list):
        return None

    ranked: list[tuple[int, str]] = []
    for entry in quests:
        if not isinstance(entry, dict):
            continue
        quest_id = str(entry.get("id", "")).strip()
        if not quest_id:
            continue
        score = 0
        if prefix in quest_id:
            score += 1
        stages = entry.get("stages", [])
        if isinstance(stages, list):
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                for key in ("complete_on", "start_on"):
                    event_name = str(stage.get(key, "")).strip()
                    if event_name.startswith(f"{prefix}_"):
                        score += 3
                emitted = stage.get("emit_events_on_complete", [])
                if isinstance(emitted, list):
                    for emitted_event in emitted:
                        event_name = str(emitted_event).strip()
                        if event_name.startswith(f"{prefix}_"):
                            score += 1
        if score > 0:
            ranked.append((score, quest_id))

    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]


def _merged_behaviour_configs(entity: dict[str, Any], prefabs_map: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    prefab_id = str(entity.get("prefab_id", "")).strip()
    prefab = prefabs_map.get(prefab_id, {})
    prefab_entity = prefab.get("entity", {}) if isinstance(prefab, dict) else {}
    base_cfg = prefab_entity.get("behaviour_config", {}) if isinstance(prefab_entity, dict) else {}
    override_cfg = entity.get("behaviour_config", {})
    if not isinstance(base_cfg, dict):
        base_cfg = {}
    if not isinstance(override_cfg, dict):
        override_cfg = {}
    merged: dict[str, dict[str, Any]] = {}
    behaviour_names: list[str] = []
    raw_behaviours = prefab_entity.get("behaviours", []) if isinstance(prefab_entity, dict) else []
    if isinstance(raw_behaviours, list):
        behaviour_names.extend(str(name) for name in raw_behaviours)
    behaviour_names.extend(str(name) for name in override_cfg.keys())
    for behaviour_name in sorted(set(name for name in behaviour_names if name)):
        cfg: dict[str, Any] = {}
        base_value = base_cfg.get(behaviour_name, {})
        if isinstance(base_value, dict):
            cfg.update(base_value)
        override_value = override_cfg.get(behaviour_name, {})
        if isinstance(override_value, dict):
            cfg.update(override_value)
        merged[behaviour_name] = cfg
    return merged


def _build_window() -> MagicMock:
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    game_state_ctrl = MagicMock()
    game_state_ctrl.state = GameState()
    window.game_state_controller = game_state_ctrl
    window.get_flag = lambda name, default=False: state_flags.get_flag(game_state_ctrl.state, name, default)
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    return window


def _build_cutscene_runner(window: MagicMock, script: dict[str, Any]) -> CutsceneRunner:
    class _Flags:
        def __init__(self, state: Any) -> None:
            self._state = state

        def get_flag(self, name: str, default: bool = False) -> bool:
            return state_flags.get_flag(self._state, name, default)

        def set_flag(self, name: str, value: bool) -> None:
            state_flags.set_flag(self._state, name, bool(value))

    flags = _Flags(window.game_state_controller.state)
    runner = CutsceneRunner(
        event_bus=window.gameplay_event_bus,
        flag_provider=flags,
        flag_setter=flags,
    )
    errors = runner.load_script_from_data(dict(script))
    if errors:
        raise ValueError(f"Cutscene load errors for {script.get('id', '<unknown>')}: {errors}")
    return runner


def _load_cutscene_script(cutscene_id: str, cutscenes_payload: dict[str, Any]) -> dict[str, Any] | None:
    entries = cutscenes_payload.get("cutscenes", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id", "")).strip() != cutscene_id:
            continue
        commands = entry.get("commands")
        if isinstance(commands, list):
            return {
                "schema_version": int(entry.get("schema_version", 1)),
                "id": cutscene_id,
                "commands": list(commands),
            }
        steps = entry.get("steps", [])
        converted: list[dict[str, Any]] = []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                step_type = str(step.get("type", "")).strip()
                if not step_type:
                    continue
                if step_type == "emit_event":
                    command: dict[str, Any] = {
                        "type": "emit_event",
                        "event_type": str(step.get("event", "")),
                    }
                    payload = {k: v for k, v in step.items() if k not in {"type", "event"}}
                    if payload:
                        command["payload"] = payload
                    converted.append(command)
                else:
                    converted.append(dict(step))
        return {
            "schema_version": int(entry.get("schema_version", 1)),
            "id": cutscene_id,
            "commands": converted,
        }
    return None


def _build_context(spec: RuntimeSpec, *, start_quest: bool) -> ReplayContext:
    from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
    from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour
    from engine.behaviours.interactable import InteractableBehaviour
    from engine.behaviours.timer import TimerBehaviour
    from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

    behaviour_builders = {
        "ActionListRunner": ActionListRunnerBehaviour,
        "DialogueRunner": DialogueRunnerBehaviour,
        "Interactable": InteractableBehaviour,
        "TriggerVolume": TriggerVolumeBehaviour,
        "Timer": TimerBehaviour,
    }

    scene_payload = _load_json_file(spec.scene_path)
    if not isinstance(scene_payload, dict):
        raise ValueError(f"scene payload must be an object: {spec.scene_rel}")
    prefabs_payload = _load_json_file(spec.repo_root / spec.prefabs_path)
    if not isinstance(prefabs_payload, list):
        raise ValueError(f"{spec.prefabs_path.as_posix()} must be a JSON array")
    prefabs_map = _prefab_map(prefabs_payload)
    dialogues_payload = _load_json_file(spec.repo_root / spec.dialogues_path)
    if not isinstance(dialogues_payload, dict):
        raise ValueError(f"{spec.dialogues_path.as_posix()} must be a JSON object")
    dialogues_map = _dialogue_map(dialogues_payload)

    window = _build_window()

    entities: dict[str, Any] = {}
    behaviours: dict[str, dict[str, Any]] = {}
    action_runners: list[Any] = []
    trigger_volumes: dict[str, Any] = {}
    interactables: dict[str, Any] = {}
    dialogue_runners: dict[str, Any] = {}
    player_entity_id = ""

    raw_entities = scene_payload.get("entities", [])
    if not isinstance(raw_entities, list):
        raise ValueError(f"scene entities must be a list: {spec.scene_rel}")

    for raw in raw_entities:
        if not isinstance(raw, dict):
            continue
        entity_id = str(raw.get("id", "")).strip()
        if not entity_id:
            continue
        prefab_id = str(raw.get("prefab_id", "")).strip()
        prefab = prefabs_map.get(prefab_id, {})
        prefab_entity = prefab.get("entity", {}) if isinstance(prefab, dict) else {}

        base_behaviours = prefab_entity.get("behaviours", []) if isinstance(prefab_entity, dict) else []
        if not isinstance(base_behaviours, list):
            base_behaviours = []
        base_cfg = prefab_entity.get("behaviour_config", {}) if isinstance(prefab_entity, dict) else {}
        override_cfg = raw.get("behaviour_config", {})
        if not isinstance(base_cfg, dict):
            base_cfg = {}
        if not isinstance(override_cfg, dict):
            override_cfg = {}

        entity = MagicMock()
        entity.mesh_id = entity_id
        entity.mesh_name = str(raw.get("name", entity_id))
        tags = prefab.get("tags", []) if isinstance(prefab, dict) else []
        entity.mesh_tags = list(tags) if isinstance(tags, list) else []
        entity.center_x = float(raw.get("x", 0.0))
        entity.center_y = float(raw.get("y", 0.0))
        entity.behaviours = []
        entity.mesh_entity_data = {
            **(prefab_entity if isinstance(prefab_entity, dict) else {}),
            "require_flags": list(prefab.get("require_flags", [])) if isinstance(prefab.get("require_flags"), list) else [],
            "forbid_flags": list(prefab.get("forbid_flags", [])) if isinstance(prefab.get("forbid_flags"), list) else [],
        }

        per_entity: dict[str, Any] = {}
        for behaviour_name in base_behaviours:
            name = str(behaviour_name)
            builder = behaviour_builders.get(name)
            if builder is None:
                continue
            cfg = dict(base_cfg.get(name, {})) if isinstance(base_cfg.get(name, {}), dict) else {}
            override_value = override_cfg.get(name, {})
            if isinstance(override_value, dict):
                cfg.update(override_value)
            if name == "DialogueRunner":
                dialogue_id = str(cfg.get("dialogue_id", "")).strip()
                existing_script = cfg.get("script")
                has_script = isinstance(existing_script, dict) and bool(existing_script)
                if dialogue_id and not has_script:
                    dialogue_entry = dialogues_map.get(dialogue_id, {})
                    if isinstance(dialogue_entry, dict):
                        script = dialogue_entry.get("script")
                        if isinstance(script, dict):
                            cfg["script"] = script
                        start_node = dialogue_entry.get("start_node")
                        if isinstance(start_node, str) and start_node:
                            cfg["start_node"] = start_node
            instance = builder(entity, window, **cfg)
            entity.behaviours.append(instance)
            per_entity[name] = instance
            if name == "ActionListRunner":
                action_runners.append(instance)
            elif name == "TriggerVolume":
                trigger_volumes[entity_id] = instance
            elif name == "Interactable":
                interactables[entity_id] = instance
            elif name == "DialogueRunner":
                dialogue_runners[entity_id] = instance

        entities[entity_id] = entity
        behaviours[entity_id] = per_entity
        if not player_entity_id and ("player" in entity.mesh_tags or "player" in entity_id.lower()):
            player_entity_id = entity_id

    if not player_entity_id:
        for candidate in sorted(entities.keys()):
            if "player" in candidate.lower():
                player_entity_id = candidate
                break
    if not player_entity_id:
        raise ValueError(f"no player entity found in scene: {spec.scene_rel}")

    window.scene_controller.all_sprites = [entities[key] for key in sorted(entities.keys())]

    quests = QuestRunner()
    quests.load_definitions(spec.repo_root / spec.quests_path)
    if start_quest and spec.quest_id:
        started = quests.start_quest(spec.quest_id)
        if not started:
            raise ValueError(f"failed to start quest '{spec.quest_id}'")

    cutscenes_payload = _load_json_file(spec.repo_root / spec.cutscenes_path)
    if not isinstance(cutscenes_payload, dict):
        raise ValueError(f"{spec.cutscenes_path.as_posix()} must be a JSON object")
    cutscene_runners: dict[str, CutsceneRunner] = {}
    for cutscene_id in (spec.intro_cutscene_id, spec.outro_cutscene_id):
        if not cutscene_id:
            continue
        script = _load_cutscene_script(cutscene_id, cutscenes_payload)
        if script is None:
            continue
        cutscene_runners[cutscene_id] = _build_cutscene_runner(window, script)

    return ReplayContext(
        spec=spec,
        window=window,
        entities=entities,
        behaviours=behaviours,
        action_runners=action_runners,
        trigger_volumes=trigger_volumes,
        interactables=interactables,
        dialogue_runners=dialogue_runners,
        quest_runner=quests,
        cutscene_runners=cutscene_runners,
        event_log=[],
        player_entity_id=player_entity_id,
    )


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical_value(value[k]) for k in sorted(value.keys())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_event(event: GameplayEvent) -> dict[str, Any]:
    return {
        "event_type": str(event.event_type),
        "payload": _canonical_value(dict(event.payload or {})),
        "sequence": int(event.sequence),
    }


def _sha256_payload(payload: Any) -> str:
    canonical = dumps_json_deterministic(payload, trailing_newline=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _replay_diagnostic(
    *,
    level: DiagnosticLevel,
    code: str,
    message: str,
    source: str,
    pointer: str,
    hint: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        level=level,
        code=code,
        message=str(message),
        context={"pointer": str(pointer), "source": str(source)},
        hint=hint,
    )


def _compute_replay_artifact_digest_triplet(
    *,
    events: list[dict[str, Any]],
    world_digests: list[dict[str, Any]],
    final_state_payload: dict[str, Any],
) -> dict[str, str]:
    events_for_digest = [_project_event_for_digest(event) for event in events]
    world_for_digest = _project_world_digests_for_digest(world_digests)
    normalized_final_state_payload, _ = normalize_save_payload(
        final_state_payload,
        source="episode_replay/final_state_payload",
    )
    final_for_digest = _project_final_state_for_digest(normalized_final_state_payload)
    return {
        "expected_event_digest": _sha256_payload(events_for_digest),
        "expected_world_digest": _sha256_payload(world_for_digest),
        "expected_final_state_digest": _sha256_payload(final_for_digest),
    }


def _unwrap_state_wrapper(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"type", "state_version", "state"} and isinstance(value.get("state"), dict):
            return _unwrap_state_wrapper(value["state"])
        return {
            str(key): _unwrap_state_wrapper(value[key])
            for key in sorted(value.keys(), key=lambda item: str(item))
        }
    if isinstance(value, list):
        return [_unwrap_state_wrapper(item) for item in value]
    return value


def _restore_saveable_state(
    target: Any,
    payload: dict[str, Any],
    *,
    strict: bool,
    source: str,
    diagnostics: SaveDiagnosticsAggregator | None = None,
) -> None:
    restore = getattr(target, "restore_state", None)
    if not callable(restore):
        return

    try:
        signature = inspect.signature(restore)
        has_strict = "strict" in signature.parameters
        has_source = "source" in signature.parameters
    except (TypeError, ValueError):
        has_strict = False
        has_source = False

    try:
        if has_strict:
            kwargs: dict[str, Any] = {"strict": bool(strict)}
            if has_source:
                kwargs["source"] = str(source)
            restore(payload, **kwargs)
        else:
            restore(payload)
    except Exception as exc:  # noqa: BLE001
        if diagnostics is not None:
            diagnostics.add_exception(
                "episode.restore_state.failed",
                exc,
                source=str(source),
                pointer="$",
                hint="Replay restore failed for a saveable runner/behaviour.",
            )
        if strict:
            raise
        return

    if diagnostics is not None:
        restore_diags = getattr(target, "_last_restore_diagnostics", ())
        if isinstance(restore_diags, (tuple, list)):
            diagnostics.add(item for item in restore_diags if hasattr(item, "code"))


def _start_dialogue_from_cutscene_event(ctx: ReplayContext, payload: dict[str, Any]) -> None:
    target_id = str(payload.get("target", "")).strip()
    if not target_id:
        return
    dialogue_id = str(payload.get("dialogue_id", "")).strip()
    node_id_raw = payload.get("node_id")
    node_id = node_id_raw if isinstance(node_id_raw, str) and node_id_raw else None
    try:
        target = _resolve_entity(ctx, target_id)
    except ValueError:
        return
    for behaviour in getattr(target, "behaviours", []):
        if type(behaviour).__name__ != "DialogueRunnerBehaviour":
            continue
        if dialogue_id and getattr(behaviour, "dialogue_id", "") != dialogue_id:
            continue
        behaviour.start(node_id)
        return


def _drain_and_route(ctx: ReplayContext) -> list[GameplayEvent]:
    events = cast(list[GameplayEvent], ctx.window.gameplay_event_bus.drain())
    if not events:
        return []

    for event in events:
        ctx.event_log.append(_canonical_event(event))

        for runner in ctx.action_runners:
            if event.event_type in runner.listen_events:
                runner.handle_event(event.event_type, event.payload)

        if event.event_type.endswith("_intro_start"):
            prefix = event.event_type[: -len("_intro_start")]
            runner = ctx.cutscene_runners.get(f"{prefix}_intro")
            if runner is not None and not runner.is_running:
                runner.start()
        elif event.event_type.endswith("_outro_start"):
            prefix = event.event_type[: -len("_outro_start")]
            runner = ctx.cutscene_runners.get(f"{prefix}_outro")
            if runner is not None and not runner.is_running:
                runner.start()
        elif event.event_type == "cutscene_start_dialogue":
            _start_dialogue_from_cutscene_event(ctx, event.payload)

    for runner in ctx.action_runners:
        runner.update(0.0)

    emitted = ctx.quest_runner.process_events(events)
    for event in emitted:
        ctx.window.gameplay_event_bus.emit(event.event_type, **(event.payload or {}))
    return events


def _drain_until_empty(ctx: ReplayContext, max_passes: int = 64) -> list[GameplayEvent]:
    collected: list[GameplayEvent] = []
    for _ in range(max_passes):
        batch = _drain_and_route(ctx)
        if not batch:
            break
        collected.extend(batch)
    return collected


def _advance_cutscene_time(runner: CutsceneRunner, dt: float) -> None:
    was_waiting = runner._state.wait_remaining > 0  # noqa: SLF001
    if not was_waiting and runner.is_running:
        runner.tick(0.0)
        if runner._state.wait_remaining > 0:  # noqa: SLF001
            runner.tick(dt)
            return
        if runner.is_running:
            runner.tick(dt)
            return
    runner.tick(dt)


def _advance(ctx: ReplayContext, dt: float) -> None:
    for cutscene_id in sorted(ctx.cutscene_runners.keys()):
        runner = ctx.cutscene_runners[cutscene_id]
        if runner.is_running:
            _advance_cutscene_time(runner, dt)
    for runner in ctx.action_runners:
        runner.update(dt)
    for entity_id in sorted(ctx.interactables.keys()):
        ctx.interactables[entity_id].update(dt)
    _drain_until_empty(ctx)


def _resolve_entity(ctx: ReplayContext, identifier: str) -> Any:
    token = str(identifier or "").strip()
    if not token:
        raise ValueError("entity identifier is required")
    entities = ctx.entities
    if token in entities:
        return entities[token]

    lower = token.lower()
    exact_matches = [
        entity
        for entity in entities.values()
        if str(getattr(entity, "mesh_id", "")).lower() == lower
        or str(getattr(entity, "mesh_name", "")).lower() == lower
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        ids = sorted(str(getattr(entity, "mesh_id", "")) for entity in exact_matches)
        raise ValueError(f"entity '{token}' is ambiguous among: {ids}")

    suffix_matches = [
        entity
        for entity in entities.values()
        if str(getattr(entity, "mesh_id", "")).lower().endswith(lower)
        or str(getattr(entity, "mesh_name", "")).lower().endswith(lower)
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    if len(suffix_matches) > 1:
        ids = sorted(str(getattr(entity, "mesh_id", "")) for entity in suffix_matches)
        raise ValueError(f"entity suffix '{token}' is ambiguous among: {ids}")

    sample = sorted(entities.keys())[:8]
    raise ValueError(f"entity '{token}' not found (available: {sample})")


def _select_dialogue_runner(ctx: ReplayContext, action: dict[str, Any]) -> Any:
    entity_token = str(action.get("entity", "")).strip()
    if entity_token:
        entity = _resolve_entity(ctx, entity_token)
        runner = ctx.dialogue_runners.get(str(getattr(entity, "mesh_id", "")))
        if runner is None:
            raise ValueError(f"entity '{entity_token}' has no DialogueRunner")
        return runner

    active = [
        (entity_id, runner)
        for entity_id, runner in sorted(ctx.dialogue_runners.items())
        if bool(getattr(runner, "is_running", False))
    ]
    if len(active) == 1:
        return active[0][1]
    if len(active) > 1:
        return active[0][1]
    all_ids = sorted(ctx.dialogue_runners.keys())
    raise ValueError(f"no active dialogue runner (available: {all_ids})")


def _snapshot_context(ctx: ReplayContext) -> dict[str, Any]:
    behaviour_states: dict[str, dict[str, Any]] = {}
    for entity_id in sorted(ctx.behaviours.keys()):
        per_entity = ctx.behaviours[entity_id]
        for behaviour_name in sorted(per_entity.keys()):
            behaviour = per_entity[behaviour_name]
            if hasattr(behaviour, "saveable_state"):
                behaviour_states[f"{entity_id}:{behaviour_name}"] = behaviour.saveable_state()

    cutscene_states = {
        cutscene_id: runner.saveable_state()
        for cutscene_id, runner in sorted(ctx.cutscene_runners.items())
    }

    return {
        "flags": ctx.window.game_state_controller.state.snapshot(),
        "bus": ctx.window.gameplay_event_bus.saveable_state(),
        "behaviours": behaviour_states,
        "cutscenes": cutscene_states,
        "quests": ctx.quest_runner.saveable_state(),
        "events": list(ctx.event_log),
        "player_entity_id": ctx.player_entity_id,
    }


def _restore_context(
    snapshot: dict[str, Any],
    spec: RuntimeSpec,
    *,
    diagnostics: SaveDiagnosticsAggregator | None = None,
    policy: RestorePolicy = REPLAY_POLICY,
) -> ReplayContext:
    ctx = _build_context(spec, start_quest=False)
    try:
        ctx.window.game_state_controller.state.restore(snapshot["flags"])
    except Exception as exc:  # noqa: BLE001
        if diagnostics is not None:
            diagnostics.add_exception(
                "episode.restore.flags_failed",
                exc,
                source="episode_snapshot/flags",
                pointer="/flags",
                hint="Replay snapshot flags restore failed.",
            )
        raise
    try:
        ctx.window.gameplay_event_bus.restore_state(snapshot["bus"])
    except Exception as exc:  # noqa: BLE001
        if diagnostics is not None:
            diagnostics.add_exception(
                "episode.restore.bus_failed",
                exc,
                source="episode_snapshot/bus",
                pointer="/bus",
                hint="Replay snapshot event bus restore failed.",
            )
        raise
    for entity_id in sorted(ctx.behaviours.keys()):
        per_entity = ctx.behaviours[entity_id]
        for behaviour_name in sorted(per_entity.keys()):
            key = f"{entity_id}:{behaviour_name}"
            if key in snapshot["behaviours"] and hasattr(per_entity[behaviour_name], "restore_state"):
                _restore_saveable_state(
                    per_entity[behaviour_name],
                    snapshot["behaviours"][key],
                    strict=policy.strict_restore,
                    source=f"episode_snapshot/{key}",
                    diagnostics=diagnostics,
                )
    for cutscene_id in sorted(ctx.cutscene_runners.keys()):
        if cutscene_id in snapshot["cutscenes"]:
            _restore_saveable_state(
                ctx.cutscene_runners[cutscene_id],
                snapshot["cutscenes"][cutscene_id],
                strict=policy.strict_restore,
                source=f"episode_snapshot/cutscene/{cutscene_id}",
                diagnostics=diagnostics,
            )
    _restore_saveable_state(
        ctx.quest_runner,
        snapshot["quests"],
        strict=policy.strict_restore,
        source="episode_snapshot/quests",
        diagnostics=diagnostics,
    )
    ctx.event_log = list(snapshot["events"])
    ctx.player_entity_id = str(snapshot.get("player_entity_id", ctx.player_entity_id) or ctx.player_entity_id)
    return ctx


def _compute_digest(ctx: ReplayContext, frame: int) -> str:
    entities_payload: list[dict[str, Any]] = []
    for entity_id in sorted(ctx.entities.keys()):
        entity = ctx.entities[entity_id]
        behaviour_state: dict[str, Any] = {}
        for behaviour_name in sorted(ctx.behaviours.get(entity_id, {}).keys()):
            behaviour = ctx.behaviours[entity_id][behaviour_name]
            if hasattr(behaviour, "saveable_state"):
                behaviour_state[behaviour_name] = _unwrap_state_wrapper(behaviour.saveable_state())
        entities_payload.append(
            {
                "entity_id": entity_id,
                "x": float(getattr(entity, "center_x", 0.0)),
                "y": float(getattr(entity, "center_y", 0.0)),
                "behaviour_state": behaviour_state,
            }
        )

    entities_payload.append(
        {
            "entity_id": f"{ctx.spec.episode_prefix}_runtime_state",
            "x": 0.0,
            "y": 0.0,
            "behaviour_state": {
                "flags": dict(sorted(ctx.window.game_state_controller.state.flags.items())),
                "quest_state": ctx.quest_runner.get_state(),
                "cutscenes": {
                    cutscene_id: _unwrap_state_wrapper(runner.saveable_state())
                    for cutscene_id, runner in sorted(ctx.cutscene_runners.items())
                },
                "event_bus": ctx.window.gameplay_event_bus.saveable_state(),
            },
        }
    )
    return compute_world_digest(entities=entities_payload, quests=[], frame=frame)


def _build_state_snapshot(ctx: ReplayContext, *, frame: int, label: str, tick: int, dt: float) -> dict[str, Any]:
    dialogue_states = {
        entity_id: _unwrap_state_wrapper(runner.saveable_state())
        for entity_id, runner in sorted(ctx.dialogue_runners.items())
    }
    cutscene_states = {
        cutscene_id: _unwrap_state_wrapper(runner.saveable_state())
        for cutscene_id, runner in sorted(ctx.cutscene_runners.items())
    }
    return {
        "frame": frame,
        "label": label,
        "tick": tick,
        "dt": float(dt),
        "flags": dict(sorted(ctx.window.game_state_controller.state.flags.items())),
        "quest_state": ctx.quest_runner.get_state(),
        "cutscenes": cutscene_states,
        "dialogues": dialogue_states,
    }


def _build_final_state_bundle(ctx: ReplayContext, *, seed: int, scene_rel: str, script_rel: str) -> dict[str, Any]:
    entities_payload: list[dict[str, Any]] = []
    for entity_id in sorted(ctx.entities.keys()):
        entity = ctx.entities[entity_id]
        behaviour_state: dict[str, Any] = {}
        for behaviour_name in sorted(ctx.behaviours.get(entity_id, {}).keys()):
            behaviour = ctx.behaviours[entity_id][behaviour_name]
            if hasattr(behaviour, "saveable_state"):
                behaviour_state[behaviour_name] = _unwrap_state_wrapper(behaviour.saveable_state())
        entities_payload.append(
            {
                "entity_id": entity_id,
                "name": str(getattr(entity, "mesh_name", "")),
                "x": float(getattr(entity, "center_x", 0.0)),
                "y": float(getattr(entity, "center_y", 0.0)),
                "behaviour_state": behaviour_state,
            }
        )
    return {
        "schema_version": 1,
        "seed": seed,
        "scene": scene_rel,
        "script": script_rel,
        "episode_prefix": ctx.spec.episode_prefix,
        "quest_id": ctx.spec.quest_id,
        "flags": dict(sorted(ctx.window.game_state_controller.state.flags.items())),
        "quest_state": ctx.quest_runner.get_state(),
        "cutscene_state": {
            cutscene_id: _unwrap_state_wrapper(runner.saveable_state())
            for cutscene_id, runner in sorted(ctx.cutscene_runners.items())
        },
        "dialogue_state": {
            entity_id: _unwrap_state_wrapper(runner.saveable_state())
            for entity_id, runner in sorted(ctx.dialogue_runners.items())
        },
        "event_bus_state": ctx.window.gameplay_event_bus.saveable_state(),
        "entities": entities_payload,
        "event_log_count": len(ctx.event_log),
    }


def _parse_replay_script(payload: dict[str, Any]) -> tuple[list[float], list[ParsedAction], int, int]:
    dt_schedule_raw = payload.get("dt_schedule")
    if not isinstance(dt_schedule_raw, list) or not dt_schedule_raw:
        raise ValueError("replay script must contain a non-empty 'dt_schedule' array")
    dt_schedule: list[float] = []
    for index, value in enumerate(dt_schedule_raw):
        try:
            dt = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"dt_schedule[{index}] must be numeric") from exc
        if dt < 0:
            raise ValueError(f"dt_schedule[{index}] must be >= 0")
        dt_schedule.append(dt)

    actions_raw = payload.get("actions", [])
    if not isinstance(actions_raw, list):
        raise ValueError("replay script 'actions' must be an array")
    actions: list[ParsedAction] = []
    save_actions = 0
    restore_actions = 0
    for index, raw in enumerate(actions_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"actions[{index}] must be an object")
        tick_raw = raw.get("t")
        if not isinstance(tick_raw, int):
            raise ValueError(f"actions[{index}].t must be an integer tick index")
        if tick_raw < 0:
            raise ValueError(f"actions[{index}].t must be >= 0")
        if tick_raw >= len(dt_schedule):
            raise ValueError(
                f"actions[{index}].t={tick_raw} out of range for dt_schedule size {len(dt_schedule)}"
            )
        kind = str(raw.get("type", "")).strip()
        if not kind:
            raise ValueError(f"actions[{index}].type is required")
        if kind == "save":
            save_actions += 1
        elif kind == "restore":
            restore_actions += 1
        actions.append(ParsedAction(tick=tick_raw, index=index, data=dict(raw)))
    actions.sort(key=lambda action: (action.tick, action.index))
    return dt_schedule, actions, save_actions, restore_actions


def _run_replay_once(spec: RuntimeSpec, replay_payload: dict[str, Any]) -> ReplayRunResult:
    try:
        dt_schedule, actions, save_actions, restore_actions = _parse_replay_script(replay_payload)
        ctx = _build_context(spec, start_quest=spec.quest_id is not None)
        _drain_until_empty(ctx)
        save_restore_diags = SaveDiagnosticsAggregator()

        snapshots: list[dict[str, Any]] = []
        digests: list[dict[str, Any]] = []
        tick_ms_list: list[float] = []
        save_slots: dict[str, dict[str, Any]] = {}
        frame = 0

        def _record(label: str, *, tick: int, dt: float) -> None:
            nonlocal frame
            digest = _compute_digest(ctx, frame)
            digests.append({"frame": frame, "label": label, "tick": tick, "digest": digest})
            snap = _build_state_snapshot(ctx, frame=frame, label=label, tick=tick, dt=dt)
            snapshots.append(snap)
            frame += 1

        _record("initial", tick=-1, dt=0.0)

        actions_by_tick: dict[int, list[ParsedAction]] = defaultdict(list)
        for action in actions:
            actions_by_tick[action.tick].append(action)

        for tick_index, dt in enumerate(dt_schedule):
            tick_start = time.perf_counter()
            for action in actions_by_tick.get(tick_index, []):
                ctx = _execute_action(
                    ctx=ctx,
                    action=action.data,
                    action_index=action.index,
                    tick=tick_index,
                    save_slots=save_slots,
                    save_restore_diags=save_restore_diags,
                )
                _record(
                    f"t{tick_index}:action{action.index}:{str(action.data.get('type', '')).strip()}",
                    tick=tick_index,
                    dt=0.0,
                )

            _advance(ctx, dt)
            _record(f"t{tick_index}:post_tick", tick=tick_index, dt=dt)
            tick_elapsed_ms = (time.perf_counter() - tick_start) * 1000.0
            tick_ms_list.append(_round_ms(tick_elapsed_ms))

        _drain_until_empty(ctx)
        _record("final", tick=len(dt_schedule), dt=0.0)

        final_bundle = _build_final_state_bundle(
            ctx,
            seed=spec.seed,
            scene_rel=spec.scene_rel,
            script_rel=spec.script_rel,
        )
        total_ms = _round_ms(sum(tick_ms_list))
        tick_ms_p50 = _compute_percentile_ms(tick_ms_list, 0.50)
        tick_ms_p95 = _compute_percentile_ms(tick_ms_list, 0.95)
        tick_ms_max = _round_ms(max(tick_ms_list)) if tick_ms_list else 0.0
        return ReplayRunResult(
            ok=True,
            error=None,
            events=list(ctx.event_log),
            digests=digests,
            snapshots=snapshots,
            final_state_bundle=final_bundle,
            save_actions=save_actions,
            restore_actions=restore_actions,
            tick_ms_list=tick_ms_list,
            total_ms=total_ms,
            tick_ms_p50=tick_ms_p50,
            tick_ms_p95=tick_ms_p95,
            tick_ms_max=tick_ms_max,
            save_restore_diagnostics=save_restore_diags.to_json(),
        )
    except Exception as exc:  # noqa: BLE001
        return ReplayRunResult(
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            events=[],
            digests=[],
            snapshots=[],
            final_state_bundle={},
            save_actions=0,
            restore_actions=0,
            tick_ms_list=[],
            total_ms=0.0,
            tick_ms_p50=0.0,
            tick_ms_p95=0.0,
            tick_ms_max=0.0,
            save_restore_diagnostics={"counts": {"total": 0, "errors": 0, "warnings": 0, "infos": 0}, "diagnostics": []},
        )


def _execute_action(
    *,
    ctx: ReplayContext,
    action: dict[str, Any],
    action_index: int,
    tick: int,
    save_slots: dict[str, dict[str, Any]],
    save_restore_diags: SaveDiagnosticsAggregator,
) -> ReplayContext:
    kind = str(action.get("type", "")).strip()
    if not kind:
        raise ValueError(f"actions[{action_index}] missing type at tick {tick}")

    if kind == "emit":
        event_type = str(action.get("event", action.get("event_type", ""))).strip()
        if not event_type:
            raise ValueError(f"actions[{action_index}] emit requires 'event'")
        payload = action.get("payload", {})
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError(f"actions[{action_index}] emit payload must be an object")
        ctx.window.gameplay_event_bus.emit(event_type, **payload)
        _drain_until_empty(ctx)
        return ctx

    if kind == "interact":
        entity_token = str(action.get("entity", "")).strip()
        if not entity_token:
            raise ValueError(f"actions[{action_index}] interact requires 'entity'")
        target = _resolve_entity(ctx, entity_token)
        target_id = str(getattr(target, "mesh_id", ""))
        interactable = ctx.interactables.get(target_id)
        if interactable is None:
            raise ValueError(f"actions[{action_index}] entity '{entity_token}' has no Interactable")
        player = ctx.entities.get(ctx.player_entity_id)
        if player is None:
            raise ValueError("player entity is missing from runtime context")
        player.center_x = float(getattr(target, "center_x", 0.0))
        player.center_y = float(getattr(target, "center_y", 0.0))
        interacted = bool(interactable.try_interact())
        if not interacted:
            raise ValueError(
                f"actions[{action_index}] interaction failed for '{entity_token}'"
            )
        _drain_until_empty(ctx)
        return ctx

    if kind == "dialogue_choose":
        if "choice" not in action:
            raise ValueError(f"actions[{action_index}] dialogue_choose requires 'choice'")
        choice_raw = action.get("choice")
        if not isinstance(choice_raw, int):
            raise ValueError(f"actions[{action_index}] dialogue choice must be an integer")
        runner = _select_dialogue_runner(ctx, action)
        chosen = bool(runner.choose(choice_raw))
        if not chosen:
            raise ValueError(
                f"actions[{action_index}] dialogue choice {choice_raw} was rejected"
            )
        _drain_until_empty(ctx)
        return ctx

    if kind == "save":
        slot = str(action.get("slot", "default")).strip() or "default"
        save_slots[slot] = _snapshot_context(ctx)
        save_restore_diags.add(
            (
                _replay_diagnostic(
                    code="episode.snapshot.saved",
                    source=f"actions[{action_index}]",
                    pointer="/save",
                    message=f"Saved snapshot slot '{slot}' at tick={tick}.",
                    level=DiagnosticLevel.INFO,
                ),
            )
        )
        return ctx

    if kind == "restore":
        slot = str(action.get("slot", "default")).strip() or "default"
        if slot not in save_slots:
            raise ValueError(f"actions[{action_index}] restore slot not found: '{slot}'")
        restored = _restore_context(
            save_slots[slot],
            ctx.spec,
            diagnostics=save_restore_diags,
            policy=REPLAY_POLICY,
        )
        save_restore_diags.add(
            (
                _replay_diagnostic(
                    code="episode.snapshot.restored",
                    source=f"actions[{action_index}]",
                    pointer="/restore",
                    message=f"Restored snapshot slot '{slot}' at tick={tick}.",
                    level=DiagnosticLevel.INFO,
                ),
            )
        )
        _drain_until_empty(restored)
        return restored

    if kind == "assert_flag":
        flag = str(action.get("flag", "")).strip()
        if not flag:
            raise ValueError(f"actions[{action_index}] assert_flag requires 'flag'")
        expected = bool(action.get("value", True))
        actual = state_flags.get_flag(ctx.window.game_state_controller.state, flag, False)
        if bool(actual) != expected:
            raise ValueError(
                f"actions[{action_index}] assert_flag failed for '{flag}': expected={expected} actual={bool(actual)}"
            )
        return ctx

    raise ValueError(f"actions[{action_index}] unsupported action type: '{kind}'")


def _summarize_run(run: ReplayRunResult) -> dict[str, Any]:
    save_restore_counts: dict[str, Any] = {}
    if isinstance(run.save_restore_diagnostics, dict):
        raw_counts = run.save_restore_diagnostics.get("counts", {})
        if isinstance(raw_counts, dict):
            save_restore_counts = dict(raw_counts)
    return {
        "ok": run.ok,
        "error": run.error,
        "event_count": len(run.events),
        "digest_count": len(run.digests),
        "snapshot_count": len(run.snapshots),
        "save_actions": run.save_actions,
        "restore_actions": run.restore_actions,
        "timing": {
            "total_ms": run.total_ms,
            "tick_ms_count": len(run.tick_ms_list),
            "tick_ms_list": list(run.tick_ms_list),
            "tick_ms_p50": run.tick_ms_p50,
            "tick_ms_p95": run.tick_ms_p95,
            "tick_ms_max": run.tick_ms_max,
        },
        "save_restore_diagnostics": save_restore_counts,
    }


def _write_replay_artifacts(*, out_dir: Path, report: dict[str, Any], run: ReplayRunResult) -> None:
    write_json_atomic(out_dir / "replay_report.json", report, indent=2, sort_keys=True, trailing_newline=True)
    write_text_atomic(out_dir / "replay_report.txt", _format_replay_report_text(report), encoding="utf-8")

    digests_payload = {
        "schema_version": 1,
        "digests": run.digests,
    }
    write_json_atomic(out_dir / "digests.json", digests_payload, indent=2, sort_keys=True, trailing_newline=True)

    final_state_payload = {
        "schema_version": 1,
        "final_state": run.final_state_bundle,
        "snapshots": run.snapshots,
    }
    write_json_atomic(
        out_dir / "final_state_bundle.json",
        final_state_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )

    ndjson_path = out_dir / "events.ndjson"
    lines: list[str] = []
    for event in run.events:
        line = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        lines.append(line)
    text = "\n".join(lines)
    if lines:
        text += "\n"
    write_text_atomic(ndjson_path, text, encoding="utf-8")

    timing_payload = {
        "schema_version": 1,
        "timing": {
            "total_ms": run.total_ms,
            "tick_ms_count": len(run.tick_ms_list),
            "tick_ms_list": list(run.tick_ms_list),
            "tick_ms_p50": run.tick_ms_p50,
            "tick_ms_p95": run.tick_ms_p95,
            "tick_ms_max": run.tick_ms_max,
        },
    }
    write_json_atomic(out_dir / "timings.json", timing_payload, indent=2, sort_keys=True, trailing_newline=True)

    diagnostics_payload = run.save_restore_diagnostics
    if not isinstance(diagnostics_payload, dict):
        diagnostics_payload = {"counts": {"total": 0, "errors": 0, "warnings": 0, "infos": 0}, "diagnostics": []}
    write_json_atomic(
        out_dir / "save_restore_diagnostics.json",
        diagnostics_payload,
        indent=2,
        sort_keys=True,
        trailing_newline=True,
    )
    diagnostics_text = SaveDiagnosticsAggregator()
    raw_items = diagnostics_payload.get("diagnostics", [])
    if isinstance(raw_items, list):
        diagnostics_text.add(
            Diagnostic.from_dict(item)
            for item in raw_items
            if isinstance(item, dict)
        )
    write_text_atomic(
        out_dir / "save_restore_diagnostics.txt",
        diagnostics_text.to_text(max_lines=50),
        encoding="utf-8",
    )


def _format_replay_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("Mesh Episode Replay Check")
    lines.append(f"Result: {'OK' if report.get('ok') else 'FAILED'}")
    lines.append(f"Scene: {report.get('scene')}")
    lines.append(f"Script: {report.get('script')}")
    lines.append(f"Seed: {report.get('seed')}")
    episode = report.get("episode", {})
    lines.append(f"Episode Prefix: {episode.get('prefix')}")
    lines.append(f"Quest: {episode.get('quest_id')}")
    lines.append("")
    lines.append("Determinism:")
    determinism = report.get("determinism", {})
    lines.append(f"- Digests Match: {determinism.get('digests_match')}")
    lines.append(f"- Events Match: {determinism.get('events_match')}")
    lines.append(f"- Final State Match: {determinism.get('final_state_match')}")
    lines.append("")
    lines.append("Runs:")
    for name in ("run_1", "run_2"):
        run = report.get(name, {})
        if run.get("ok"):
            timing = run.get("timing", {}) if isinstance(run.get("timing"), dict) else {}
            lines.append(
                f"- {name}: OK (events={run.get('event_count')} digests={run.get('digest_count')} snapshots={run.get('snapshot_count')} total_ms={timing.get('total_ms')} p95_ms={timing.get('tick_ms_p95')} max_ms={timing.get('tick_ms_max')})"
            )
        else:
            lines.append(f"- {name}: FAILED ({run.get('error')})")
    lines.append("")
    lines.append("Artifacts:")
    artifacts = report.get("artifacts", {})
    for key in sorted(artifacts.keys()):
        lines.append(f"- {key}: {artifacts.get(key)}")
    lines.append("")
    return "\n".join(lines)


def _round_ms(value: float, *, decimals: int = 3) -> float:
    return float(f"{float(value):.{decimals}f}")


def _compute_percentile_ms(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    clamped = min(max(float(percentile), 0.0), 1.0)
    ordered = sorted(float(v) for v in values)
    rank = max(1, int(math.ceil(clamped * len(ordered))))
    index = min(rank - 1, len(ordered) - 1)
    return _round_ms(ordered[index])
