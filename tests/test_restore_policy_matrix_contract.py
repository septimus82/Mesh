from __future__ import annotations

import json
from pathlib import Path

import mesh_cli

from engine.persistence_io import SAVE_FORMAT_VERSION
from engine.save_manager import SaveManager
from engine import savegame
from engine.save_runtime import io as save_io
from engine.save_runtime import payloads as save_payloads
from engine.save_runtime.restore_policy import REPLAY_POLICY, SLOT_POLICY, SNAPSHOT_POLICY
from engine.save_runtime.save_diagnostics import SaveDiagnosticsAggregator
from engine.save_runtime.state_codec import decode_state
from mesh_cli import replays as replays_module


class _CodecMismatchBehaviour:
    TYPE_ID = "codec_behaviour"
    STATE_VERSION = 1

    def __init__(self) -> None:
        self._last_restore_diagnostics = ()

    def restore_state(self, payload, *, strict: bool = True, source: str = "codec") -> None:
        state, diagnostics = decode_state(
            payload,
            expected_type_id=self.TYPE_ID,
            supported_versions={self.STATE_VERSION},
            strict=bool(strict),
            source=source,
        )
        self._last_restore_diagnostics = tuple(diagnostics)
        if state is None and strict:
            raise ValueError("codec mismatch")


class _ExplodingBehaviour:
    def restore_state(self, payload, *, strict: bool = True, source: str = "boom") -> None:  # noqa: ARG002
        raise RuntimeError("restore exploded")


class _Sprite:
    def __init__(self, mesh_name: str, behaviours: list[object]) -> None:
        self.mesh_name = mesh_name
        self.center_x = 0.0
        self.center_y = 0.0
        self.mesh_entity_data = {}
        self.mesh_tag = None
        self.mesh_tags = []
        self.mesh_animator = None
        self.mesh_behaviours_runtime = list(behaviours)


class _UIController:
    def reset_transient_state(self) -> None:
        return None


class _State:
    def __init__(self) -> None:
        self.flags: dict[str, bool] = {}
        self.counters: dict[str, int] = {"gold": 0}


class _GameStateController:
    def __init__(self) -> None:
        self.state = _State()
        self.quests = None

    def import_state(self, payload) -> None:  # noqa: ANN001
        return None

    def replace_state(self, payload) -> None:  # noqa: ANN001
        return None


class _Window:
    def __init__(self, sprites: list[object]) -> None:
        self.scene_controller = type("SceneController", (), {"all_sprites": sprites, "current_scene_path": "scenes/test.json"})()
        self.game_state_controller = _GameStateController()
        self.ui_controller = _UIController()
        self.player_hud = type("Hud", (), {"clear_toasts": lambda self: None, "enqueue_toast": lambda self, text: None})()
        self.requested_scene = None

    def request_scene_change(self, scene_path: str) -> None:
        self.requested_scene = scene_path

    def set_next_spawn_point(self, spawn_id: str) -> None:
        self.next_spawn_id = spawn_id


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _slot_payload(*, behaviour_name: str, behaviour_state: dict) -> dict:
    return {
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": 2,
        "flags": {},
        "gold": 0,
        "game_state": {"flags": {}, "counters": {"gold": 0}},
        "saved_entities": {
            "schema_version": 1,
            "entities": [
                {
                    "entity_id": "entity_1",
                    "x": 0.0,
                    "y": 0.0,
                    "behaviour_state": {behaviour_name: behaviour_state},
                }
            ],
        },
        "saved_quests": {"schema_version": 1, "quests": {}},
    }


def _digest_triplet_from_artifacts(case: replays_module.ReplaySuiteCase, out_dir: Path) -> tuple[str, str, str]:
    actual = replays_module._collect_case_actual(case=case, case_out_dir=out_dir)
    return (
        str(actual["expected_event_digest"]),
        str(actual["expected_world_digest"]),
        str(actual["expected_final_state_digest"]),
    )


def test_restore_policy_constants_matrix() -> None:
    assert SLOT_POLICY.strict_schema is True
    assert SLOT_POLICY.strict_restore is True
    assert SLOT_POLICY.write_sidecars_on_failure is True
    assert SLOT_POLICY.surface_in_debug_bundle is True

    assert SNAPSHOT_POLICY.strict_schema is True
    assert SNAPSHOT_POLICY.strict_restore is False
    assert SNAPSHOT_POLICY.write_sidecars_on_failure is True
    assert SNAPSHOT_POLICY.surface_in_debug_bundle is True

    assert REPLAY_POLICY.strict_schema is True
    assert REPLAY_POLICY.strict_restore is False
    assert REPLAY_POLICY.write_sidecars_on_failure is False
    assert REPLAY_POLICY.surface_in_debug_bundle is False


def test_slot_policy_schema_error_fails_with_deterministic_message_and_sidecars(tmp_path: Path) -> None:
    slot_path = tmp_path / "saves" / "slot_bad.json"
    _write_json(
        slot_path,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": 2,
            "gold": 1,
            "flags": [],
            "saved_entities": "bad-type",
            "saved_quests": [],
        },
    )

    ok, payload_or_error = save_io.load_slot_payload(slot_path, policy=SLOT_POLICY)
    assert ok is False
    message = str(payload_or_error)
    assert message.startswith("[Mesh][Save] ERROR:")
    assert "code=save.load.schema_validation_error" in message
    assert "pointer=$/saved_entities" in message
    assert (slot_path.parent / "slot_bad.json.diagnostics.json").exists()
    assert (slot_path.parent / "slot_bad.json.diagnostics.txt").exists()


def test_slot_policy_restore_fail_is_hard_fail_with_sidecars(tmp_path: Path, capsys) -> None:
    window = _Window([_Sprite("entity_1", [_CodecMismatchBehaviour(), _ExplodingBehaviour()])])
    manager = SaveManager(window, save_dir=str(tmp_path / "saves"))
    slot_path = manager.get_save_path("slot1")
    _write_json(
        slot_path,
        _slot_payload(
            behaviour_name="_CodecMismatchBehaviour",
            behaviour_state={"type": "wrong_type", "state_version": 1, "state": {}},
        ),
    )

    ok = manager.load_game("slot1")
    assert ok is False
    err = capsys.readouterr().err
    assert "[Mesh][Save] ERROR:" in err
    assert "code=" in err
    assert "pointer=" in err
    assert (slot_path.parent / "slot1.json.diagnostics.json").exists()
    assert (slot_path.parent / "slot1.json.diagnostics.txt").exists()


def test_snapshot_policy_best_effort_restore_returns_true_and_writes_diagnostics_sidecar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    world_path = Path("worlds/bad_world.json")
    world_path.parent.mkdir(parents=True, exist_ok=True)
    world_path.write_text("{", encoding="utf-8")

    snapshot_path = Path("saves/quick.json")
    _write_json(
        snapshot_path,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": 2,
            "version": 1,
            "world_file": "worlds/bad_world.json",
            "world_id": "test_world",
            "scene_id": "scenes/test.json",
            "gold": 0,
            "flags": [],
        },
    )

    window = _Window([])
    ok = savegame.load_quick_snapshot(window, path=snapshot_path)
    assert ok is True
    sidecar_json = snapshot_path.parent / "quick.json.diagnostics.json"
    sidecar_txt = snapshot_path.parent / "quick.json.diagnostics.txt"
    assert sidecar_json.exists()
    assert sidecar_txt.exists()
    payload = json.loads(sidecar_json.read_text(encoding="utf-8"))
    codes = [item.get("code") for item in payload.get("diagnostics", []) if isinstance(item, dict)]
    assert "save.snapshot.world_load_failed" in codes


def test_snapshot_policy_schema_error_is_non_crashing_and_fails_cleanly(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "quick_invalid.json"
    _write_json(
        snapshot_path,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": 2,
            "version": 1,
            "world_file": "worlds/ok.json",
            "world_id": "test_world",
            "scene_id": "scenes/test.json",
            "gold": "oops",
            "flags": [],
        },
    )
    window = _Window([])
    ok = savegame.load_quick_snapshot(window, path=snapshot_path)
    assert ok is False
    assert (snapshot_path.parent / "quick_invalid.json.diagnostics.json").exists()
    assert (snapshot_path.parent / "quick_invalid.json.diagnostics.txt").exists()


def test_snapshot_policy_non_strict_restore_keeps_ok_and_surfaces_runner_diagnostics(tmp_path: Path) -> None:
    window = _Window([_Sprite("entity_1", [_CodecMismatchBehaviour(), _ExplodingBehaviour()])])
    payload = _slot_payload(
        behaviour_name="_CodecMismatchBehaviour",
        behaviour_state={"type": "wrong_type", "state_version": 1, "state": {}},
    )
    payload["saved_entities"]["entities"][0]["behaviour_state"]["_ExplodingBehaviour"] = {"any": "value"}

    diagnostics = SaveDiagnosticsAggregator()
    ok = save_payloads.apply_loaded_payload(
        window,
        payload,
        mode="slot",
        policy=SNAPSHOT_POLICY,
        diagnostics=diagnostics,
        source="tests/snapshot_policy_non_strict",
    )
    assert ok is True
    counts = diagnostics.counts()
    assert int(counts.get("warnings", 0)) > 0

    sidecar_base = tmp_path / "snapshot_policy_case.json"
    json_sidecar, txt_sidecar = save_io.write_diagnostics_sidecars(sidecar_base, diagnostics)
    assert json_sidecar.exists()
    assert txt_sidecar.exists()
    sidecar_payload = json.loads(json_sidecar.read_text(encoding="utf-8"))
    codes = [item.get("code") for item in sidecar_payload.get("diagnostics", []) if isinstance(item, dict)]
    assert "SAVE_STATE_TYPE_MISMATCH" in codes
    assert "save.restore.behaviour_state_failed" in codes


def test_replay_policy_keeps_replay_resilient_and_digests_unchanged(tmp_path: Path) -> None:
    out_dir = tmp_path / "ep02_run"
    rc = mesh_cli.main(
        [
            "episode",
            "replay-check",
            "--scene",
            "episode_02_ep02.json",
            "--script",
            "replays/ep02.json",
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc == 0
    diagnostics_json = out_dir / "save_restore_diagnostics.json"
    diagnostics_txt = out_dir / "save_restore_diagnostics.txt"
    assert diagnostics_json.exists()
    assert diagnostics_txt.exists()

    case = replays_module.ReplaySuiteCase(
        case_id="ep02",
        mode="episode",
        scene_rel="episode_02_ep02.json",
        script_rel="replays/ep02.json",
        golden_rel="replays/golden/ep02_golden.json",
        scene_path=Path("episode_02_ep02.json"),
        script_path=Path("replays/ep02.json"),
        golden_path=tmp_path / "unused_golden.json",
        budgets=None,
    )
    before = _digest_triplet_from_artifacts(case, out_dir)
    payload = json.loads(diagnostics_json.read_text(encoding="utf-8"))
    payload["host"] = "ci-runner"
    payload["timing_debug"] = {"jitter_ms": 999.0}
    diagnostics_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    diagnostics_txt.write_text("diagnostics metadata only\n", encoding="utf-8")
    after = _digest_triplet_from_artifacts(case, out_dir)
    assert before == after
