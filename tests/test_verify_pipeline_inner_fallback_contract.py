import logging
from pathlib import Path

import pytest

import mesh_cli.verify_steps.pipeline as verify_pipeline


pytestmark = [pytest.mark.fast]


def test_read_json_dict_artifact_logs_stable_parse_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "package_check.json"
    target.write_text("{bad json\n", encoding="utf-8")

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    payload = verify_pipeline._read_json_dict_artifact(
        target,
        tag="VSTP-049",
        purpose="player-package-gate package_check",
    )

    assert payload is None
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-049]" in stderr
    assert "player-package-gate package_check parse fallback" in stderr
    assert "package_check.json" in stderr


def test_coerce_int_field_logs_stable_baseline_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_path = tmp_path / "exception_policy_baseline.json"
    payload = {"ble001_count_total": "bad"}

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    value = verify_pipeline._coerce_int_field(
        payload,
        "ble001_count_total",
        default=0,
        tag="VSTP-048",
        path=baseline_path,
        purpose="exception-policy-scan baseline coercion fallback",
    )

    assert value is None
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-048]" in stderr
    assert "field=ble001_count_total" in stderr
    assert "exception_policy_baseline.json" in stderr


def test_coerce_int_logs_stable_origin_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    world_path = tmp_path / "world.json"

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    value = verify_pipeline._coerce_int(
        "bad",
        "origin_x",
        tag="VSTP-018",
        path=world_path,
        purpose="stamp-audit origin coercion fallback case=0",
    )

    assert value is None
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-018]" in stderr
    assert "stamp-audit origin coercion fallback case=0" in stderr
    assert "field=origin_x" in stderr
    assert "world.json" in stderr


def test_read_json_dict_artifact_logs_stable_root_shape_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "room_scene.json"
    target.write_text("[1, 2, 3]\n", encoding="utf-8")

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    payload = verify_pipeline._read_json_dict_artifact(
        target,
        tag="VSTP-030",
        purpose="room-audit from_scene",
    )

    assert payload is None
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-030]" in stderr
    assert "room-audit from_scene root fallback" in stderr
    assert "room_scene.json" in stderr


def test_read_json_dict_artifact_logs_stamp_scene_parse_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "stamp_scene.json"
    target.write_text("{bad json\n", encoding="utf-8")

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    payload = verify_pipeline._read_json_dict_artifact(
        target,
        tag="VSTP-019",
        purpose="stamp-audit scene",
    )

    assert payload is None
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-019]" in stderr
    assert "stamp-audit scene parse fallback" in stderr
    assert "stamp_scene.json" in stderr


def test_read_json_dict_artifact_logs_macro_scene_root_shape_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "macro_scene.json"
    target.write_text("[{\"entities\": []}]\n", encoding="utf-8")

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    payload = verify_pipeline._read_json_dict_artifact(
        target,
        tag="VSTP-050",
        purpose="macro-audit scene",
    )

    assert payload is None
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-050]" in stderr
    assert "macro-audit scene root fallback" in stderr
    assert "macro_scene.json" in stderr


def test_coerce_xy_pair_logs_stable_macro_position_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scene_path = tmp_path / "macro_scene.json"

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    value = verify_pipeline._coerce_xy_pair(
        {"x": "bad", "y": 12},
        default=(0.0, 0.0),
        tag="VSTP-027",
        path=scene_path,
        purpose="macro-audit player position coercion fallback entity=player",
    )

    assert value == (0.0, 0.0)
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-027]" in stderr
    assert "macro-audit player position coercion fallback entity=player" in stderr
    assert "field=x" in stderr
    assert "macro_scene.json" in stderr


def test_coerce_xy_pair_logs_stable_spawn_position_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scene_path = tmp_path / "room_scene.json"

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    value = verify_pipeline._coerce_xy_pair(
        {"x": 4, "y": object()},
        default=(0.0, 0.0),
        tag="VSTP-029",
        path=scene_path,
        purpose="room-audit spawn position coercion fallback spawn_id=entry",
    )

    assert value == (0.0, 0.0)
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-029]" in stderr
    assert "room-audit spawn position coercion fallback spawn_id=entry" in stderr
    assert "field=y" in stderr
    assert "room_scene.json" in stderr


def test_coerce_float_logs_stable_macro_preview_tag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    macro_path = tmp_path / "objective_zone.macro.json"

    logging.getLogger("mesh_cli.verify_steps.pipeline").setLevel(logging.DEBUG)
    value = verify_pipeline._coerce_float(
        "bad",
        "radius",
        tag="VSTP-026",
        path=macro_path,
        purpose="macro-audit preview arg coercion fallback macro_id=macro.objective_zone scene_path=scenes/test.json",
    )

    assert value is None
    stderr = capsys.readouterr().err
    assert "SWALLOW[VSTP-026]" in stderr
    assert "macro-audit preview arg coercion fallback macro_id=macro.objective_zone scene_path=scenes/test.json" in stderr
    assert "field=radius" in stderr
    assert "objective_zone.macro.json" in stderr


def test_cleanup_stale_pytest_fast_budget_artifacts_removes_only_budget_artifacts(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_artifacts = repo_root / "artifacts"
    repo_artifacts.mkdir()
    custom_artifacts = tmp_path / "custom_artifacts"
    custom_artifacts.mkdir()

    repo_budget = repo_artifacts / "verify_step_budget_check.json"
    repo_diag_json = repo_artifacts / "pytest_fast_budget_diagnostic.json"
    repo_diag_txt = repo_artifacts / "pytest_fast_budget_diagnostic.txt"
    repo_keep = repo_artifacts / "verify_step_durations.json"
    custom_budget = custom_artifacts / "verify_step_budget_check.json"

    for path in (repo_budget, repo_diag_json, repo_diag_txt, repo_keep, custom_budget):
        path.write_text("{}", encoding="utf-8")

    verify_pipeline._cleanup_stale_pytest_fast_budget_artifacts(
        repo_root,
        artifacts_dir=custom_artifacts,
    )

    assert not repo_budget.exists()
    assert not repo_diag_json.exists()
    assert not repo_diag_txt.exists()
    assert repo_keep.exists()
    assert not custom_budget.exists()
