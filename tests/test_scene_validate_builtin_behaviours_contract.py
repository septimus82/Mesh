from engine.ai_ops import AIOps
from engine.scene_loader import SceneLoader


def _builtin_registration_errors(errors: list[str]) -> list[str]:
    return [
        error
        for error in errors
        if "behaviour 'PlayerController' is not registered" in error
        or "behaviour 'CameraFollow' is not registered" in error
    ]


def test_scene_loader_validate_file_warms_builtin_behaviours() -> None:
    report = SceneLoader().validate_scene_file("scenes/outside.json")

    assert _builtin_registration_errors(report.errors) == []


def test_ai_ops_run_validation_warms_builtin_behaviours() -> None:
    result = AIOps(base_dir=".").run_validation("scenes/outside.json")

    errors = []
    if result.data is not None:
        errors = list(result.data.get("errors", []))
    assert _builtin_registration_errors(errors) == []
