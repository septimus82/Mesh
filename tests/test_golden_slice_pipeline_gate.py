from pathlib import Path

from engine.config import load_config
from engine.tooling.pipeline_runner import run_pipeline_result


def _verify_preset(preset_name, world_path):
    cfg = load_config()
    preset = cfg.presets.get(preset_name)

    steps = preset
    if isinstance(preset, dict):
        steps = preset.get("steps")

    assert isinstance(steps, list)
    assert steps and steps[0].get("cmd") == "pipeline"
    args = steps[0].get("args") or []
    assert "plans/golden_slice_noop.json" in args
    assert world_path in args
    assert "--dry-run" in args

    result = run_pipeline_result(
        plan_path="plans/golden_slice_noop.json",
        path=world_path,
        dry_run=True,
        strict=True,
        check_refs=True,
    )
    if result.exit_code != 0:
        import contextlib
        import io

        import mesh_cli

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            doctor_rc = mesh_cli.main(["doctor", "--world", world_path, "--quiet"])
        last_path = Path(".mesh/reports/doctor_last_failure.json")
        assert doctor_rc != 0
        assert last_path.exists()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = mesh_cli.main(["explain", "--last"])
        assert rc != 0

        # Print explain output (normalized) so CI logs show actionable guidance.
        print(buf.getvalue().replace("\\", "/"), end="")

    assert result.exit_code == 0


def test_golden_slice_pipeline_gate():
    _verify_preset("golden_slice", "worlds/main_world.json")


def test_golden_slice_variant_b_pipeline_gate():
    _verify_preset("golden_slice_variant_b", "worlds/golden_slice_variant_b.json")


def test_golden_slice_variant_c_pipeline_gate():
    _verify_preset("golden_slice_variant_c", "worlds/golden_slice_variant_c.json")


def test_golden_slice_variant_d_pipeline_gate():
    _verify_preset("golden_slice_variant_d", "worlds/golden_slice_variant_d.json")


def test_golden_slice_variant_e_pipeline_gate():
    _verify_preset("golden_slice_variant_e", "worlds/golden_slice_variant_e.json")


def test_golden_slice_variant_f_pipeline_gate():
    _verify_preset("golden_slice_variant_f", "worlds/golden_slice_variant_f.json")


def test_golden_slice_variant_g_pipeline_gate():
    _verify_preset("golden_slice_variant_g", "worlds/golden_slice_variant_g.json")
