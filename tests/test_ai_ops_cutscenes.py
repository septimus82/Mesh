from pathlib import Path

from engine.ai_ops import AIOps


def make_cutscene_file(tmp_path: Path) -> Path:
    payload = {
        "cutscenes": [
            {"id": "intro", "steps": [{"type": "wait", "duration": 1.0}]},
        ]
    }
    path = tmp_path / "cutscenes.json"
    path.write_text('{"cutscenes": [{"id":"intro","steps":[{"type":"wait","duration":1}]}]}', encoding="utf-8")
    return path


def test_add_update_delete_cutscene(tmp_path: Path):
    path = make_cutscene_file(tmp_path)
    ops = AIOps(base_dir=tmp_path)

    res = ops.add_or_update_cutscene("intro", [{"type": "wait", "duration": 2.0}], cutscenes_path=str(path))
    assert res.ok

    res = ops.add_or_update_cutscene("outro", [{"type": "emit_event", "event": "done"}], cutscenes_path=str(path))
    assert res.ok

    res = ops.delete_cutscene("intro", cutscenes_path=str(path))
    assert res.ok


def test_insert_update_delete_step(tmp_path: Path):
    path = make_cutscene_file(tmp_path)
    ops = AIOps(base_dir=tmp_path)

    res = ops.insert_cutscene_step(
        "intro",
        {"type": "emit_event", "event": "boom"},
        index=0,
        cutscenes_path=str(path),
    )
    assert res.ok
    res = ops.update_cutscene_step(
        "intro",
        0,
        {"duration": 0.5},
        cutscenes_path=str(path),
    )
    assert res.ok
    res = ops.delete_cutscene_step("intro", 0, cutscenes_path=str(path))
    assert res.ok
