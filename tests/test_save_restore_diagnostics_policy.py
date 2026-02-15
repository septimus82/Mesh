from __future__ import annotations

import json
import re
from pathlib import Path

import mesh_cli

from engine.diagnostics import Diagnostic, DiagnosticLevel
from engine.save_runtime.io import write_diagnostics_sidecars
from engine.save_runtime.save_diagnostics import SaveDiagnosticsAggregator
from mesh_cli import replays as replays_module


ROOT = Path(__file__).resolve().parents[1]
SAVE_RUNTIME_DIR = ROOT / "engine" / "save_runtime"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest_triplet_from_artifacts(case: replays_module.ReplaySuiteCase, out_dir: Path) -> tuple[str, str, str]:
    actual = replays_module._collect_case_actual(case=case, case_out_dir=out_dir)
    return (
        str(actual["expected_event_digest"]),
        str(actual["expected_world_digest"]),
        str(actual["expected_final_state_digest"]),
    )


def test_policy_forbids_silent_exception_pass_in_save_runtime() -> None:
    offenders: list[str] = []
    for path in sorted(SAVE_RUNTIME_DIR.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        for index, line in enumerate(lines, start=1):
            if line.strip() == "except Exception: pass":
                offenders.append(f"{rel}:{index}")
    assert not offenders, (
        "save/runtime policy violation: silent swallow found. "
        f"Unexpected 'except Exception: pass' sites: {sorted(offenders)}"
    )


def test_policy_forbids_bare_logging_getlogger_in_save_diagnostics_module() -> None:
    path = ROOT / "engine" / "save_runtime" / "save_diagnostics.py"
    source = path.read_text(encoding="utf-8-sig")
    assert "logging.getLogger" not in source, (
        "save_diagnostics policy violation: use deterministic Diagnostic aggregation only; "
        "do not call logging.getLogger directly in save_diagnostics.py"
    )


def test_save_diagnostics_sort_and_text_cap_are_deterministic() -> None:
    diag_a = Diagnostic(
        level=DiagnosticLevel.ERROR,
        code="save.code.b",
        message="b",
        context={"pointer": "/b", "source": "tmp/b"},
        hint="hint-b",
    )
    diag_b = Diagnostic(
        level=DiagnosticLevel.WARN,
        code="save.code.a",
        message="a",
        context={"pointer": "/a", "source": "tmp/a"},
        hint=None,
    )

    agg_1 = SaveDiagnosticsAggregator()
    agg_1.add((diag_a, diag_b))
    agg_2 = SaveDiagnosticsAggregator()
    agg_2.add((diag_b, diag_a))

    assert [d.to_dict() for d in agg_1.finalize_sorted()] == [d.to_dict() for d in agg_2.finalize_sorted()]

    capped_1 = agg_1.to_text(max_lines=1)
    capped_2 = agg_2.to_text(max_lines=1)
    assert capped_1 == capped_2
    assert "... (" in capped_1


def test_sidecar_filenames_are_stable_and_relative_to_target(tmp_path: Path) -> None:
    slot_path = tmp_path / "saves" / "slot_01.json"
    slot_path.parent.mkdir(parents=True, exist_ok=True)

    aggregator = SaveDiagnosticsAggregator()
    aggregator.add(
        (
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.load.schema_validation_error",
                message="bad field",
                context={"source": "tests/slot_01.json", "pointer": "/saved_entities"},
                hint="Fix payload",
            ),
        )
    )

    json_path, txt_path = write_diagnostics_sidecars(slot_path, aggregator)
    assert json_path.name == "slot_01.json.diagnostics.json"
    assert txt_path.name == "slot_01.json.diagnostics.txt"
    assert json_path.parent == slot_path.parent
    assert txt_path.parent == slot_path.parent

    payload = _read_json(json_path)
    payload_text = json.dumps(payload, sort_keys=True)
    assert not re.search(r"[A-Za-z]:\\\\", payload_text)
    assert '"source": "/"' not in payload_text


def test_replay_digests_unchanged_when_only_diagnostics_artifacts_change(tmp_path: Path) -> None:
    out_dir = tmp_path / "ep01_run"
    rc = mesh_cli.main(
        [
            "episode",
            "replay-check",
            "--scene",
            "episode_01_intro.json",
            "--script",
            "replays/ep01.json",
            "--out-dir",
            str(out_dir),
            "--seed",
            "123",
            "--quiet",
        ]
    )
    assert rc == 0

    case = replays_module.ReplaySuiteCase(
        case_id="ep01",
        mode="episode",
        scene_rel="episode_01_intro.json",
        script_rel="replays/ep01.json",
        golden_rel="replays/golden/ep01_golden.json",
        scene_path=ROOT / "episode_01_intro.json",
        script_path=ROOT / "replays" / "ep01.json",
        golden_path=tmp_path / "unused_golden.json",
        budgets=None,
    )
    before = _digest_triplet_from_artifacts(case, out_dir)

    diagnostics_json = out_dir / "save_restore_diagnostics.json"
    diagnostics_txt = out_dir / "save_restore_diagnostics.txt"
    payload = _read_json(diagnostics_json)
    payload["host"] = "ci-runner-1"
    payload["environment"] = "test"
    payload["timing_debug"] = {"jitter": 123}
    diagnostics_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    diagnostics_txt.write_text("changed diagnostics text only\n", encoding="utf-8")

    after = _digest_triplet_from_artifacts(case, out_dir)
    assert before == after, (
        "artifact=save_restore_diagnostics.{json,txt} changed but digest triplet changed: "
        f"before={before} after={after}"
    )
