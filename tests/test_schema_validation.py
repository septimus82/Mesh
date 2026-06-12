import json
from pathlib import Path

import mesh_cli
from engine.paths import get_content_roots, set_content_roots
from engine.validators.schema_validation import (
    ValidationError,
    render_validation_error_line,
    sort_validation_errors,
    validate_scene,
    validate_world,
)


def test_scene_validation_deterministic_order_and_format() -> None:
    scene_path = Path("bad_scene.json")
    data = {
        "entities": [
            {
                "x": "nope",
                "y": None,
            }
        ]
    }

    errors = validate_scene(scene_path, data, workspace_root=Path("."))
    lines = [render_validation_error_line(err) for err in errors]

    assert lines == [
        json.dumps(
            {
                "code": "entity.position.required",
                "path": "entities[0].x",
                "message": "Scene bad_scene.json: entities[0].x must be a number",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        json.dumps(
            {
                "code": "entity.position.required",
                "path": "entities[0].y",
                "message": "Scene bad_scene.json: entities[0].y must be a number",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    ]


def test_world_validation_missing_start_scene_exact_error(tmp_path) -> None:
    # Make the test hermetic by creating a scene file and pointing the content roots at tmp_path.
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir(parents=True)
    (scenes_dir / "door_field.json").write_text(
        json.dumps({"name": "Door Field", "entities": []}),
        encoding="utf-8",
    )

    old_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        world_path = Path("world.json")
        data = {
            "id": "w",
            "start_scene": "missing",
            "scenes": {
                "door_field": {"path": "scenes/door_field.json"},
            },
            "links": [],
        }

        errors = validate_world(world_path, data, validate_scene_files=False)
    finally:
        set_content_roots(old_roots)

    assert errors == [
        ValidationError(
            code="world.start_scene.unknown",
            path="start_scene",
            message="World world.json: start_scene 'missing' not found in scenes",
        )
    ]


def test_validate_all_command_emits_one_line_json_errors(tmp_path, capsys) -> None:
    broken_scene = tmp_path / "broken_scene.json"
    broken_scene.write_text(
        "{\n  \"entities\": [ { \"x\": \"no\", \"y\": null } ]\n}\n",
        encoding="utf-8",
    )

    rc = mesh_cli.main(["validate-all", "--path", str(broken_scene)])
    assert rc == 1

    out = capsys.readouterr().out
    lines = [line.strip() for line in out.splitlines() if line.strip()]

    # Expect at least one structured error line.
    parsed = []
    for line in lines:
        if not line.startswith("{"):
            continue
        obj = json.loads(line)
        if isinstance(obj, dict) and {"code", "path", "message"}.issubset(obj.keys()):
            parsed.append(obj)

    assert parsed, f"Expected JSON error lines, got:\n{out}"

    # Deterministic sort order should have x before y for schema errors.
    schema = [p for p in parsed if p.get("code") == "entity.position.required"]
    paths = [p.get("path") for p in schema]
    assert "entities[0].x" in paths
    assert "entities[0].y" in paths
    assert paths.index("entities[0].x") < paths.index("entities[0].y")


def test_sort_validation_errors_is_deterministic() -> None:
    errs = [
        ValidationError(code="b", path="z", message="1"),
        ValidationError(code="a", path="z", message="2"),
        ValidationError(code="a", path="a", message="3"),
    ]
    sorted_errs = sort_validation_errors(errs)
    assert [e.path for e in sorted_errs] == ["a", "z", "z"]
    assert [e.code for e in sorted_errs] == ["a", "a", "b"]
