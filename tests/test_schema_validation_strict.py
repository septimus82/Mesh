import json
from pathlib import Path

import mesh_cli

from engine.paths import get_content_roots, set_content_roots
from engine.validators.schema_validation import (
    ValidationError,
    render_validation_error_line,
    validate_scene,
    validate_world,
)


def test_strict_entity_id_required() -> None:
    errors = validate_scene(
        Path("s.json"),
        {"entities": [{"x": 1, "y": 2}]},
        strict=True,
    )
    codes = [e.code for e in errors]
    assert "entity.id.required" in codes


def test_strict_entity_ids_unique() -> None:
    errors = validate_scene(
        Path("s.json"),
        {"entities": [{"id": "a", "x": 1, "y": 2}, {"id": "a", "x": 3, "y": 4}]},
        strict=True,
    )
    codes = [e.code for e in errors]
    assert "entity.id.duplicate" in codes


def test_strict_trigger_zone_zone_id_required() -> None:
    data = {
        "entities": [
            {
                "id": "e1",
                "x": 1,
                "y": 2,
                "behaviours": ["TriggerZone"],
                "behaviour_config": {
                    "TriggerZone": {
                        "trigger_radius": 10,
                        "trigger_target": "some_target",
                    }
                },
            }
        ]
    }
    errors = validate_scene(Path("s.json"), data, strict=True)
    codes = [e.code for e in errors]
    assert "trigger_zone.zone_id.required" in codes


def test_strict_world_start_scene_required(tmp_path) -> None:
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir(parents=True)
    (scenes_dir / "a.json").write_text(json.dumps({"name": "A", "entities": []}), encoding="utf-8")

    old_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        errors = validate_world(
            Path("w.json"),
            {"scenes": {"a": {"path": "scenes/a.json"}}, "links": []},
            validate_scene_files=False,
            strict=True,
        )
    finally:
        set_content_roots(old_roots)

    assert "world.start_scene.required" in [e.code for e in errors]


def test_strict_scene_transition_target_must_exist_cli_level(tmp_path, capsys) -> None:
    # Build a tiny workspace with one scene that transitions to a missing file.
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir(parents=True)

    (scenes_dir / "a.json").write_text(
        json.dumps(
            {
                "name": "A",
                "entities": [
                    {
                        "id": "e1",
                        "x": 1,
                        "y": 2,
                        "behaviour_config": {"SceneTransition": {"target_scene": "scenes/missing.json"}},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    world_path = tmp_path / "world.json"
    world_path.write_text(
        json.dumps(
            {
                "start_scene": "a",
                "scenes": {"a": {"path": "scenes/a.json"}},
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    old_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        rc = mesh_cli.main(["validate-all", "--path", str(world_path), "--schema-strict"])
    finally:
        set_content_roots(old_roots)

    assert rc == 1

    out = capsys.readouterr().out
    # Find at least one strict-only SceneTransition missing-target error.
    lines = [line.strip() for line in out.splitlines() if line.strip().startswith("{")]
    payloads = [json.loads(line) for line in lines]
    codes = [p.get("code") for p in payloads if isinstance(p, dict)]
    assert "scene_transition.target_scene.missing" in codes

    # Example line should be one-line JSON.
    sample = next(p for p in payloads if p.get("code") == "scene_transition.target_scene.missing")
    rendered = render_validation_error_line(
        ValidationError(code=str(sample["code"]), path=str(sample["path"]), message=str(sample["message"]))
    )
    assert "\n" not in rendered
