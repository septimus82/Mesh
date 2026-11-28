"""#755 (programme finding 3): a quest's ``reward.gold`` / ``reward.xp`` pay the player, once.

The validator accepted ``"reward": {"gold": 100, "xp": 30}``. Then ``normalize_reward`` kept only ``set_flags`` and
``inc_counters``, so the quest completed and paid nothing. The gold path behind it credited ``game_state.values["gold"]``,
which nothing reads, while vendors spend the ``gold`` counter. Now gold goes to that counter (``window.inc_counter``,
where the gold perk bonus applies once) and XP goes to the player's progression (``add_xp``). Validation rejects
negative amounts and unknown reward fields, which would pay nothing.

The game test makes a project with ``mesh new`` and places its objects with ``mesh author apply``. The quest is written
with the MCP ``add_quest_definition`` op, and the game is played through its own ``main.py`` in a hidden window
(tests/test_project_scaffolding_data.py, tests/test_dialogue_once_persists.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.quest_runtime.normalize import normalize_quest
from engine.quest_runtime.validation import validate_quest_definition, validate_quest_file

REPO = Path(__file__).resolve().parents[1]
STAGE = [{"id": "post", "title": "Read the notice", "complete_on": {"type": "bounty_done"}}]


def _quest(reward: Any) -> dict[str, Any]:
    return {"id": "bounty", "title": "Bounty", "stages": STAGE, "reward": reward}


def _reward_errors(reward: Any) -> list[str]:
    return [e.code for e in validate_quest_definition(_quest(reward)) if e.code.startswith("reward")]


# ------------------------------------------------------------------------------------------ loading (fast)

@pytest.mark.fast
def test_gold_and_xp_survive_loading() -> None:
    quest = normalize_quest(_quest({"gold": 100, "xp": 30, "set_flags": {"paid": True}, "inc_counters": {"tokens": 2}}))
    assert quest is not None
    assert quest["reward"] == {"set_flags": {"paid": True}, "inc_counters": {"tokens": 2.0}, "gold": 100, "xp": 30}


@pytest.mark.fast
@pytest.mark.parametrize("reward, normalized", [
    ({"inc_counters": {"gold": 50}}, {"set_flags": {}, "inc_counters": {"gold": 50.0}}),
    ({"set_flags": {"done": True}}, {"set_flags": {"done": True}, "inc_counters": {}}),
    ({"set_flags": {"done": True}, "inc_counters": {}}, {"set_flags": {"done": True}, "inc_counters": {}}),
    ({}, {"set_flags": {}, "inc_counters": {}}),
    (None, {"set_flags": {}, "inc_counters": {}}),
])
def test_existing_reward_shapes_load_as_before(reward: Any, normalized: dict[str, Any]) -> None:
    """The shapes shipped content, the golden-slice scaffold and docs use: valid, and loaded exactly as before."""
    raw = _quest(reward) if reward is not None else {"id": "bounty", "title": "Bounty", "stages": STAGE}
    assert [e for e in validate_quest_definition(raw) if e.code.startswith("reward")] == []
    quest = normalize_quest(raw)
    assert quest is not None and quest["reward"] == normalized


@pytest.mark.fast
@pytest.mark.parametrize("rel", ["assets/data/quests.json", "packs/core_regions/assets/data/quests.json"])
def test_shipped_quest_rewards_are_valid(rel: str) -> None:
    data = json.loads((REPO / rel).read_text(encoding="utf-8"))
    errors = [e for e in validate_quest_file(Path(rel), data) if e.code.startswith("reward")]
    assert errors == []


@pytest.mark.fast
def test_the_wip_packs_item_reward_is_now_reported() -> None:
    """``add_items`` was never a reward field: it paid nothing without a word. Validation now names it."""
    rel = "packs/wip_experiments/assets/data/quests.json"
    data = json.loads((REPO / rel).read_text(encoding="utf-8"))
    errors = [e for e in validate_quest_file(Path(rel), data) if e.code.startswith("reward")]
    assert [(e.code, e.json_path.rsplit(".", 1)[-1]) for e in errors] == [("reward.unknown_field", "add_items")]
    assert "add_items" in errors[0].message and "gold" in errors[0].hint


@pytest.mark.fast
@pytest.mark.parametrize("reward, code", [
    ({"gold": -5}, "reward.gold.negative"),
    ({"xp": -1}, "reward.xp.negative"),
    ({"gold": "100"}, "reward.gold.type"),
    ({"xp": True}, "reward.xp.type"),
    ({"gold": None}, "reward.gold.type"),
    ({"gold": float("inf")}, "reward.gold.not_finite"),
    ({"xp": float("nan")}, "reward.xp.not_finite"),
    ({"coins": 10}, "reward.unknown_field"),
    ({"add_items": {"coin": 50}}, "reward.unknown_field"),
    ([{"gold": 5}], "reward.type"),
])
def test_invalid_rewards_are_rejected_with_a_message(reward: Any, code: str) -> None:
    errors = [e for e in validate_quest_definition(_quest(reward)) if e.code.startswith("reward")]
    assert [e.code for e in errors] == [code]
    assert "bounty" in errors[0].message and errors[0].hint


@pytest.mark.fast
def test_an_invalid_amount_is_not_paid_and_is_reported_at_load(capsys: pytest.CaptureFixture[str]) -> None:
    quest = normalize_quest(_quest({"gold": -5, "xp": "lots", "coins": 3, "inc_counters": {"gold": 1}}))
    assert quest is not None and quest["reward"] == {"set_flags": {}, "inc_counters": {"gold": 1.0}}
    out = capsys.readouterr().out
    assert "reward.gold -5" in out and "reward.xp 'lots'" in out and "['coins']" in out
    # json.loads accepts Infinity / NaN: never a counter of inf
    quest = normalize_quest(_quest(json.loads('{"gold": Infinity, "xp": NaN}')))
    assert quest is not None and quest["reward"] == {"set_flags": {}, "inc_counters": {}}
    out = capsys.readouterr().out
    assert "reward.gold inf" in out and "reward.xp nan" in out


# ------------------------------------------------------------------------------------- paying (fast)

def _manager(perks: dict[str, dict[str, float]]) -> tuple[Any, Any]:
    """A QuestManager over a real GameStateController, whose window's inc_counter is the game window's."""
    from engine.config import EngineConfig
    from engine.game_state_controller import GameStateController
    from engine.perks import Perk
    from engine.quests import QuestManager

    window = MagicMock()
    window.engine_config = EngineConfig(xp_base=1000, xp_per_level=1000)
    gs = GameStateController(window)
    gs.perk_manager = MagicMock()
    gs.perk_manager.get_perk.side_effect = lambda pid: Perk(pid, pid, "", perks[pid]) if pid in perks else None
    gs.state.perks.extend(perks)
    window.game_state_controller = gs
    window.game_state = gs.state
    window.inc_counter = gs.inc_counter  # (engine/game_parts/state_facade.py)
    manager = QuestManager(window, data_path="assets/data/quests.json")
    quest = normalize_quest(_quest({"gold": 100, "xp": 100}))
    manager._definitions = {"bounty": quest}
    manager._rebuild_stage_lookup()
    return manager, gs


@pytest.mark.fast
def test_perk_bonuses_apply_exactly_once_and_the_reward_pays_once() -> None:
    manager, gs = _manager({"gold_boost": {"gold_bonus_pct": 0.5}, "xp_boost": {"xp_bonus_pct": 0.5}})
    assert manager.complete_quest("bounty")
    assert manager.complete_quest("bounty")  # (a retry: the console's "quest complete", QuestProgress "finish")
    assert gs.get_counter("gold") == 150.0  # 100 + 50%, not 225 (bonus twice) nor 300 (paid twice)
    assert gs.get_xp() == 150
    assert "gold" not in gs.state.values


@pytest.mark.fast
def test_a_window_whose_inc_counter_returns_nothing_still_gets_xp_and_the_completion() -> None:
    """Test doubles (and any host) may return None from inc_counter: the payout mustn't depend on its value."""
    manager, gs = _manager({})
    manager.window.inc_counter = MagicMock(return_value=None)
    assert manager.complete_quest("bounty")
    manager.window.inc_counter.assert_called_once_with("gold", 100.0)
    assert gs.get_xp() == 100
    assert any(c.args[:1] == ("quest_completed",) for c in manager.window.emit_signal.call_args_list)


# ---------------------------------------------------- the authoring write path and content audit (integration)

@pytest.mark.integration  # (mesh new in a temporary folder)
def test_the_mcp_quest_ops_refuse_a_reward_the_game_would_drop(tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """add_quest_definition / update_quest_definition / edit_quest wrote any reward and said ok: the only sign was a
    line at game load. A reward with an unknown field, or a negative or non-finite amount, is refused and nothing is
    written."""
    from engine.mcp_server import tools
    from engine.paths import reset_path_caches
    from tests.test_project_scaffolding_data import _new

    root = _new(tmp_path, "starter")
    monkeypatch.delenv("MESH_REPO_ROOT", raising=False)
    reset_path_caches()
    quests = root / "assets/data/quests.json"

    def op(kind: str, quest: dict[str, Any]) -> dict[str, Any]:
        return tools.apply_ops([{"type": kind, "quest_id": "bounty", "quest": quest}], root=str(root), validate=False)

    for reward, code in (({"items": {"coin": 5}}, "reward.unknown_field"), ({"gold": -5}, "reward.gold.negative")):
        result = op("add_quest_definition", {"title": "Bounty", "stages": STAGE, "reward": reward})
        assert not result["ok"] and code in result["results"][0]["message"], result
        assert "not written" in result["results"][0]["message"]
        assert not quests.exists(), "nothing written"

    assert op("add_quest_definition", {"title": "Bounty", "stages": STAGE, "reward": {"gold": 10}})["ok"]
    before = quests.read_bytes()
    for reward in ({"items": {"coin": 5}}, {"gold": -5}, {"xp": float("inf")}):
        result = op("update_quest_definition", {"reward": reward})
        assert not result["ok"], result
        assert quests.read_bytes() == before, "the file is unchanged"
    for reward, code in (({"items": {"coin": 5}}, "reward.unknown_field"), ({"gold": -5}, "reward.gold.negative")):
        result = tools.apply_ops([{"type": "edit_quest", "quest_id": "bounty", "patch": {"reward": reward}}],
                                 root=str(root), validate=False)
        assert not result["ok"] and code in result["results"][0]["message"], result
        assert quests.read_bytes() == before, "edit_quest wrote nothing"


@pytest.mark.integration  # (a content tree in a temporary folder)
def test_the_content_audit_warns_about_a_reward_the_game_would_drop(tmp_path: Path) -> None:
    from mesh_cli.content_integrity import run_content_audit
    from tests.test_content_integrity_audit import _build_valid_content_fixture, _make_minimums, _write_json

    _build_valid_content_fixture(tmp_path)
    path = tmp_path / "assets/data/quests.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["quests"][0]["reward"] = {"gold": -5, "items": {"coin": 1}}
    _write_json(path, data)
    report = run_content_audit(tmp_path, minimum_counts=_make_minimums())
    assert report.ok, "warnings: shipped content doesn't fail"
    found = {(w.code, w.pointer) for w in report.warnings if w.code.startswith("content.quests.reward")}
    assert found == {("content.quests.reward.gold.negative", "$/quests/0/reward/gold"),
                     ("content.quests.reward.unknown_field", "$/quests/0/reward/items")}


# ------------------------------------------------------------------------ the game (integration, real window)

PICTURE = "assets/sprites/starter_sign.png"
POTION_PRICE = 30
BOUNTY = {"title": "Bounty", "auto_start": True, "stages": STAGE,
          "reward": {"gold": 100, "xp": 60, "set_flags": {"bounty_paid": True}}}


def _author(root: Path) -> None:
    """A notice board (E emits ``bounty_done``) and a merchant (E opens the shop) beside the player, then the quest."""
    from engine.mcp_server import tools
    from tests.test_project_scaffolding_data import START, _mesh

    start = json.loads((root / START).read_text(encoding="utf-8"))
    player = next(e for e in start["entities"] if e.get("prefab_id") == "player" or e.get("tag") == "player")
    px, py = float(player["x"]), float(player["y"])
    objects = [
        ("Notice", (320, -32), [("Interactable", {"interact_event": "bounty_done"})]),
        ("Merchant", (576, -32), [("Vendor", {"stock": [{"item_id": "healing_potion", "price": POTION_PRICE,
                                                         "quantity": 3}]}),
                                  ("Interactable", {"interact_event": "open_shop"})]),
    ]
    changes: list[dict[str, Any]] = []
    for name, (dx, dy), setup in objects:
        ref = f"@{len(changes)}"
        changes += [{"op": "place_blank", "room": "start", "name": name, "x": px + dx, "y": py + dy},
                    {"op": "set_picture", "room": "start", "entity_id": ref, "sprite": PICTURE}]
        for behaviour, params in setup:
            changes.append({"op": "add_behaviour", "room": "start", "entity_id": ref, "behaviour": behaviour})
            changes += [{"op": "set_behaviour_param", "room": "start", "entity_id": ref, "behaviour": behaviour,
                         "param": key, "value": value} for key, value in params.items()]
    plan = root.parent / "changes.json"
    plan.write_text(json.dumps(changes), encoding="utf-8")
    code, out = _mesh("author", "apply", str(plan), "--project", str(root))
    assert code == 0 and json.loads(out)["ok"], out
    result = tools.apply_ops([{"type": "add_quest_definition", "quest_id": "bounty", "quest": BOUNTY}],
                             root=str(root), validate=False)
    assert result["ok"], result


@pytest.mark.integration  # (mesh new in a temporary folder; hidden game windows)
@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
def test_a_quest_reward_pays_spendable_gold_and_xp_once_across_reentry_and_save_load(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_dialogue_once_persists import _Player, _sessions
    from tests.test_project_scaffolding_data import _new

    root = _new(tmp_path, "adventure")
    _author(root)
    seen: dict[str, Any] = {}

    def progress(play: _Player) -> tuple[Any, ...]:
        gs, qm = play.game.gs, play.game.window.quest_manager
        return (play.gold(), gs.get_level(), gs.get_xp(), play.game.count(), qm.is_quest_completed("bounty"),
                gs.get_flag("bounty_paid"))

    def first(play: _Player) -> None:
        game = play.game
        cfg = game.window.engine_config
        seen["level up at"] = int(cfg.xp_base)
        seen["active"] = game.window.quest_manager.is_quest_active("bounty")
        game.use("Notice")  # the interact key on the notice: its event completes the quest's only stage
        seen["paid"] = progress(play)
        game.use("Notice")  # the completing event again
        game.window.quest_manager.complete_quest("bounty")  # a retry through the quest API
        play.leave_and_return()
        seen["again"] = progress(play)
        game.use("Merchant")
        seen["shop open"] = bool(game.window.ui_controller.shop_panel.visible)
        game.press(optional_arcade.arcade.key.ENTER)  # buy the first item with the quest's gold
        game.window.ui_controller.shop_panel.close()
        game.step(2)
        seen["bought"] = progress(play)
        play.save("after")

    def second(play: _Player) -> None:
        play.load("after")
        seen["loaded"] = progress(play)
        play.game.use("Notice")
        play.game.window.quest_manager.complete_quest("bounty")
        play.leave_and_return()
        play.load("after")
        seen["reloaded"] = progress(play)

    _sessions(root, monkeypatch, first, second)
    level_up_at = seen["level up at"]
    assert level_up_at <= 60, "the test expects 60 XP to reach level 2 (xp_base)"
    paid = (100.0, 2, 60 - level_up_at, 0, True, True)
    assert seen["active"]
    assert seen["paid"] == paid, "100 gold on the vendors' counter, 60 XP through the progression"
    assert seen["again"] == paid, "not paid again: repeated event, retry, room re-entry"
    assert seen["shop open"]
    spent = (100.0 - POTION_PRICE, 2, 60 - level_up_at, 1, True, True)
    assert seen["bought"] == spent, "the merchant took the quest's gold"
    assert seen["loaded"] == spent, "a fresh window loads the same gold, XP and quest"
    assert seen["reloaded"] == spent, "and the reward can't be claimed again after loading"
