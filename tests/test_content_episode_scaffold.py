from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import mesh_cli
from mesh_cli.content_scaffold import build_episode_scaffold_plan
from tests.subprocess_tools import run_checked


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _init_content_root(root: Path) -> None:
    _write_json(
        root / "assets/data/events.json",
        {
            "events": [
                {
                    "name": "existing_event",
                    "description": "baseline",
                    "payload": {},
                }
            ]
        },
    )
    _write_json(
        root / "assets/data/quests.json",
        {
            "quests": [
                {
                    "id": "existing_quest",
                    "title": "Existing Quest",
                    "description": "baseline",
                    "stages": [],
                }
            ]
        },
    )
    _write_json(
        root / "cutscenes.json",
        {
            "cutscenes": [
                {
                    "id": "existing_cutscene",
                    "steps": [],
                }
            ]
        },
    )
    _write_json(
        root / "assets/prefabs.json",
        [
            {
                "id": "player",
                "entity": {
                    "sprite": "assets/placeholder.png",
                    "behaviours": [],
                    "behaviour_config": {},
                },
            }
        ],
    )


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_episode_scaffold_is_deterministic(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    _init_content_root(root_a)
    _init_content_root(root_b)

    args = [
        "content",
        "episode",
        "new",
        "--id",
        "ep02",
        "--title",
        "Signal in the Dust",
        "--seed",
        "123",
    ]
    assert mesh_cli.main([*args, "--out-dir", str(root_a)]) == 0
    assert mesh_cli.main([*args, "--out-dir", str(root_b)]) == 0

    plan_a = build_episode_scaffold_plan(
        episode_id="ep02",
        title="Signal in the Dust",
        out_dir=root_a,
        seed=123,
    )
    plan_b = build_episode_scaffold_plan(
        episode_id="ep02",
        title="Signal in the Dust",
        out_dir=root_b,
        seed=123,
    )

    rel_paths = [
        plan_a.events_rel_path,
        plan_a.quests_rel_path,
        plan_a.cutscenes_rel_path,
        plan_a.dialogues_rel_path,
        plan_a.prefabs_rel_path,
        plan_a.scene_rel_path,
        plan_a.doc_rel_path,
        plan_a.test_rel_path,
    ]
    for rel_path in rel_paths:
        a_bytes = (root_a / rel_path).read_bytes()
        b_bytes = (root_b / rel_path).read_bytes()
        assert a_bytes == b_bytes, f"non-deterministic output in {rel_path.as_posix()}"

    assert plan_a.scene_rel_path == plan_b.scene_rel_path


def test_episode_scaffold_refuses_duplicates(tmp_path: Path, capsys) -> None:
    _init_content_root(tmp_path)
    args = [
        "content",
        "episode",
        "new",
        "--id",
        "ep02",
        "--title",
        "Signal in the Dust",
        "--out-dir",
        str(tmp_path),
    ]
    assert mesh_cli.main(args) == 0
    assert mesh_cli.main(args) == 2
    out = capsys.readouterr().out
    assert "refusing to overwrite existing file" in out or "already defines" in out


def test_episode_scaffold_writes_expected_registry_stubs(tmp_path: Path) -> None:
    _init_content_root(tmp_path)
    assert (
        mesh_cli.main(
            [
                "content",
                "episode",
                "new",
                "--id",
                "ep02",
                "--title",
                "Signal in the Dust",
                "--out-dir",
                str(tmp_path),
            ]
        )
        == 0
    )

    plan = build_episode_scaffold_plan(
        episode_id="ep02",
        title="Signal in the Dust",
        out_dir=tmp_path,
        seed=123,
    )

    events = _read_json(tmp_path / plan.events_rel_path)
    event_names = {str(entry.get("name", "")) for entry in events["events"]}  # type: ignore[index]
    for name in plan.event_names:
        assert name in event_names

    quests = _read_json(tmp_path / plan.quests_rel_path)
    quest_ids = {str(entry.get("id", "")) for entry in quests["quests"]}  # type: ignore[index]
    assert plan.quest_id in quest_ids

    cutscenes = _read_json(tmp_path / plan.cutscenes_rel_path)
    cutscene_ids = {str(entry.get("id", "")) for entry in cutscenes["cutscenes"]}  # type: ignore[index]
    assert plan.cutscene_intro_id in cutscene_ids
    assert plan.cutscene_outro_id in cutscene_ids

    dialogues = _read_json(tmp_path / plan.dialogues_rel_path)
    dialogue_ids = {str(entry.get("id", "")) for entry in dialogues["dialogues"]}  # type: ignore[index]
    assert plan.dialogue_id in dialogue_ids

    prefabs = _read_json(tmp_path / plan.prefabs_rel_path)
    prefab_ids = {str(entry.get("id", "")) for entry in prefabs}  # type: ignore[arg-type]
    for prefab_id in plan.prefab_ids:
        assert prefab_id in prefab_ids


def test_episode_scaffold_scene_references_valid_prefabs_and_behaviours(tmp_path: Path) -> None:
    _init_content_root(tmp_path)
    assert (
        mesh_cli.main(
            [
                "content",
                "episode",
                "new",
                "--id",
                "ep02",
                "--title",
                "Signal in the Dust",
                "--out-dir",
                str(tmp_path),
            ]
        )
        == 0
    )

    plan = build_episode_scaffold_plan(
        episode_id="ep02",
        title="Signal in the Dust",
        out_dir=tmp_path,
        seed=123,
    )

    scene = _read_json(tmp_path / plan.scene_rel_path)
    prefabs = _read_json(tmp_path / plan.prefabs_rel_path)
    prefab_map = {str(entry.get("id", "")): entry for entry in prefabs}  # type: ignore[arg-type]

    entities = list(scene.get("entities", []))  # type: ignore[union-attr]
    for entity in entities:
        prefab_id = str(entity.get("prefab_id", "")).strip()
        if prefab_id:
            assert prefab_id in prefab_map

    allowed_behaviours = {"DialogueRunner", "TriggerVolume", "Interactable", "ActionListRunner"}
    for prefab_id in plan.prefab_ids:
        prefab = prefab_map[prefab_id]
        behaviours = set(prefab["entity"]["behaviours"])  # type: ignore[index]
        assert behaviours
        assert behaviours.issubset(allowed_behaviours)


def test_episode_scaffold_generated_test_runs(tmp_path: Path) -> None:
    _init_content_root(tmp_path)
    assert (
        mesh_cli.main(
            [
                "content",
                "episode",
                "new",
                "--id",
                "ep02",
                "--title",
                "Signal in the Dust",
                "--out-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    plan = build_episode_scaffold_plan(
        episode_id="ep02",
        title="Signal in the Dust",
        out_dir=tmp_path,
        seed=123,
    )

    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root) if not existing else f"{repo_root}{os.pathsep}{existing}"

    result = run_checked(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            plan.test_rel_path.as_posix(),
        ],
        cwd=str(tmp_path),
        env=env,
        timeout_s=120,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_episode_scaffold_dry_run_is_read_only(tmp_path: Path) -> None:
    _init_content_root(tmp_path)
    before = {
        "events": (tmp_path / "assets/data/events.json").read_bytes(),
        "quests": (tmp_path / "assets/data/quests.json").read_bytes(),
        "cutscenes": (tmp_path / "cutscenes.json").read_bytes(),
        "prefabs": (tmp_path / "assets/prefabs.json").read_bytes(),
    }

    assert (
        mesh_cli.main(
            [
                "content",
                "episode",
                "new",
                "--id",
                "ep02",
                "--title",
                "Signal in the Dust",
                "--out-dir",
                str(tmp_path),
                "--dry-run",
            ]
        )
        == 0
    )

    assert not (tmp_path / "assets/data/dialogues.json").exists()
    plan = build_episode_scaffold_plan(
        episode_id="ep02",
        title="Signal in the Dust",
        out_dir=tmp_path,
        seed=123,
    )
    assert not (tmp_path / plan.scene_rel_path).exists()
    assert not (tmp_path / plan.doc_rel_path).exists()
    assert not (tmp_path / plan.test_rel_path).exists()

    assert (tmp_path / "assets/data/events.json").read_bytes() == before["events"]
    assert (tmp_path / "assets/data/quests.json").read_bytes() == before["quests"]
    assert (tmp_path / "cutscenes.json").read_bytes() == before["cutscenes"]
    assert (tmp_path / "assets/prefabs.json").read_bytes() == before["prefabs"]
