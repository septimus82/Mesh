from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.command_palette as command_palette_module
import engine.editor_controller as editor_controller_module
import engine.prefabs as prefabs_module
from engine.editor.prefab_editor_model import save_prefabs, validate_prefab_entries

pytestmark = [pytest.mark.fast]


class _PrefabManagerSpy:
    def __init__(self) -> None:
        self.load_calls: list[bool] = []

    def load(self, *, force: bool = False) -> None:
        self.load_calls.append(bool(force))


def _prefab(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "torch_wisp",
        "display_name": "Torch Wisp",
        "entity": {
            "sprite": "assets/placeholder.png",
            "encounter_cost": 2,
            "behaviours": ["EnemyAI"],
        },
        "tags": ["enemy", "fire"],
        "metadata": {"author": "core"},
    }
    payload.update(overrides)
    return payload


def _install_cache_spies(monkeypatch: pytest.MonkeyPatch) -> tuple[_PrefabManagerSpy, list[bool]]:
    manager = _PrefabManagerSpy()
    cache_clear_calls: list[bool] = []

    def fake_list_prefab_ids_from_assets() -> tuple[str, ...]:
        return ("stale_prefab",)

    def fake_cache_clear() -> None:
        cache_clear_calls.append(True)

    fake_list_prefab_ids_from_assets.cache_clear = fake_cache_clear  # type: ignore[attr-defined]

    monkeypatch.setattr(prefabs_module, "get_prefab_manager", lambda: manager)
    monkeypatch.setattr(command_palette_module, "_list_prefab_ids_from_assets", fake_list_prefab_ids_from_assets)
    monkeypatch.setattr(editor_controller_module, "PREFAB_PALETTE", [{"id": "stale_prefab"}])
    return manager, cache_clear_calls


def test_save_prefabs_round_trips_entries_sorted_by_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_cache_spies(monkeypatch)
    target = tmp_path / "assets" / "prefabs.json"
    entries = [
        _prefab(id="z_last", display_name="Z Last"),
        _prefab(id="a_first", display_name="A First"),
    ]

    save_prefabs(entries, target)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in loaded] == ["a_first", "z_last"]
    assert loaded[0]["display_name"] == "A First"
    assert loaded[1]["entity"]["sprite"] == "assets/placeholder.png"
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_save_prefabs_invalid_entry_raises_and_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_cache_spies(monkeypatch)
    target = tmp_path / "assets" / "prefabs.json"

    with pytest.raises(ValueError, match="'id' must be a non-empty string"):
        save_prefabs([_prefab(id="")], target)

    assert not target.exists()


def test_save_prefabs_invalid_entry_leaves_existing_file_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cache_spies(monkeypatch)
    target = tmp_path / "assets" / "prefabs.json"
    target.parent.mkdir(parents=True)
    original = '[{"id": "existing", "entity": {}}]\n'
    target.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="'tags' must be an array"):
        save_prefabs([_prefab(tags="enemy")], target)

    assert target.read_text(encoding="utf-8") == original


def test_save_prefabs_rejects_duplicate_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_cache_spies(monkeypatch)
    target = tmp_path / "assets" / "prefabs.json"

    with pytest.raises(ValueError, match="duplicate prefab id 'same_id'"):
        save_prefabs(
            [
                _prefab(id="same_id", display_name="First"),
                _prefab(id="same_id", display_name="Second"),
            ],
            target,
        )

    assert not target.exists()


def test_save_prefabs_invalid_shape_raises_and_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_cache_spies(monkeypatch)
    target = tmp_path / "assets" / "prefabs.json"

    with pytest.raises(ValueError, match="must be an object"):
        save_prefabs([{"id": "bad_entity", "entity": "not a dict"}], target)

    assert not target.exists()


def test_save_prefabs_calls_invalidate_prefab_editor_caches_for_module_level_prefab_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, cache_clear_calls = _install_cache_spies(monkeypatch)
    target = tmp_path / "assets" / "prefabs.json"

    save_prefabs([_prefab()], target)

    assert manager.load_calls == [True]
    assert cache_clear_calls == [True]
    assert editor_controller_module.PREFAB_PALETTE is None


def test_validate_prefab_entries_normalizes_validation_errors_to_strings(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "prefabs.json"

    errors = validate_prefab_entries([_prefab(id="")], target)

    assert errors
    assert all(isinstance(error, str) for error in errors)
    assert any("'id' must be a non-empty string" in error for error in errors)
