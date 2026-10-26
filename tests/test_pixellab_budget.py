"""The shared PixelLab budget refuses what it must, and keeps only sanitized records (Milestone 17)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tooling import pixellab_budget as budget

pytestmark = pytest.mark.fast


def _ledger(tmp_path: Path, approved: float = 20) -> Path:
    path = tmp_path / "ledger.json"
    budget.init(path, approved, {"textures": 15, "character": 5})
    return path


def test_reservations_share_one_budget_and_refuse_overspend(tmp_path: Path) -> None:
    path = _ledger(tmp_path)
    a = budget.reserve(path, "textures", "create-tiles-pro", "plaster")  # 15
    with pytest.raises(budget.BudgetError, match="5 of 20 remain"):
        budget.reserve(path, "character", "inpaint-v3", "moss")  # 10: the other agent sees the same budget
    budget.reserve(path, "character", "create-image-pixflux", "door", units=5)  # exactly fills it
    with pytest.raises(budget.BudgetError):
        budget.reserve(path, "character", "create-image-pixflux", "one more")
    budget.release(path, a, "timed out before sending")
    assert budget.status(path)["committed"] == 5


def test_unknown_costs_qa_agents_and_reset_are_refused(tmp_path: Path) -> None:
    path = _ledger(tmp_path)
    with pytest.raises(budget.BudgetError, match="no established cost"):
        budget.reserve(path, "textures", "generate-image-v2", "anything")
    with pytest.raises(budget.BudgetError, match="read-only"):
        budget.reserve(path, "art-qa", "create-image-pixflux", "a look")
    with pytest.raises(budget.BudgetError, match="never reset"):
        budget.init(path, 999, {"textures": 1})


def test_each_agent_spends_only_its_own_cap_and_delegating_adds_none(tmp_path: Path) -> None:
    path = _ledger(tmp_path)
    budget.reserve(path, "character", "create-image-pixflux", "walk", units=4)  # 4 of the character's 5
    with pytest.raises(budget.BudgetError, match="character has 1 of its 5 left"):
        budget.reserve(path, "character", "create-image-pixflux", "a subtask the character agent handed on", units=2)
    with pytest.raises(budget.BudgetError, match="read-only"):  # a subtask can't take a name of its own
        budget.reserve(path, "character-helper", "create-image-pixflux", "a new name for more budget")
    budget.reserve(path, "textures", "create-tiles-pro", "plaster")  # the other agent's cap is untouched
    assert budget.status(path)["committed"] == 19


@pytest.mark.parametrize("caps", [{}, {"textures": 0}, {"textures": 15, "character": 6}])
def test_a_ledger_needs_positive_caps_within_the_approved_budget(tmp_path: Path, caps: dict[str, float]) -> None:
    with pytest.raises(budget.BudgetError, match="caps"):
        budget.init(tmp_path / "ledger.json", 20, caps)
    assert not (tmp_path / "ledger.json").exists()


@pytest.mark.parametrize("units", [0, -3, 1.5, True])
def test_reservations_take_whole_positive_units(tmp_path: Path, units: Any) -> None:
    path = _ledger(tmp_path)
    with pytest.raises(budget.BudgetError, match="units"):
        budget.reserve(path, "textures", "create-tiles-pro", "a negative count must not free budget", units=units)
    assert budget.status(path)["committed"] == 0


@pytest.mark.parametrize("used", [-1, float("nan"), "2"])
def test_settle_takes_a_real_non_negative_usage(tmp_path: Path, used: Any) -> None:
    path = _ledger(tmp_path)
    rid = budget.reserve(path, "textures", "create-image-pixflux", "door")
    with pytest.raises(budget.BudgetError, match="used"):
        budget.settle(path, rid, used)


def test_sanitize_drops_account_fields_and_storage_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    account = "12345678-9abc-def0-1234-56789abcdef0"
    monkeypatch.setenv("PIXELLAB_API_TOKEN", "env-token-value-0123456789")
    raw = {"account_id": account, "userId": account, "owner": {"email": "a@b.c"},
           "files": ("pixellab-characters/" + account + "/c/south.png", "plain"),
           "header": "x-api-key env-token-value-0123456789", "job": "j1"}
    clean = budget.sanitize(raw)
    text = repr(clean)
    assert account not in text and "env-token" not in text and "a@b.c" not in text
    assert clean == {"files": ["<path removed>", "plain"], "header": "x-api-key <redacted>", "job": "j1"}


def test_settle_records_usage_overruns_and_sanitized_results(tmp_path: Path) -> None:
    path = _ledger(tmp_path)
    rid = budget.reserve(path, "textures", "create-image-pixflux", "window")
    secret = "s3cr3t-token-value-0123456789"
    budget.settle(path, rid, 2, {"usage": 2, "authorization": f"Bearer {secret}",
                                 "image": "x" * 5000, "note": f"see https://store.example/u/acct-1/w.png {secret}"},
                  secret=secret)
    text = path.read_text(encoding="utf-8")
    assert secret not in text and "acct-1" not in text and "x" * 300 not in text
    entry = json.loads(text)["entries"][0]
    assert entry["result"] == {"usage": 2, "image": "<5000 characters removed>",
                               "note": "see <url removed> <redacted>"}
    assert budget.status(path) == {"approved": 20, "caps": {"textures": 15, "character": 5}, "committed": 2,
                                   "used_by_agent": {"textures": 2}, "open": [], "overruns": [rid]}
    with pytest.raises(budget.BudgetError, match="no open reservation"):
        budget.settle(path, rid, 1)
