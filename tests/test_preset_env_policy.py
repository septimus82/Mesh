import pytest

from engine.tooling.preset_policy import validate_preset_env


def test_validate_preset_env_accepts_none():
    assert validate_preset_env(None) == []


def test_validate_preset_env_rejects_non_dict():
    issues = validate_preset_env(["NOPE"])
    assert len(issues) == 1
    assert issues[0]["id"] == "preset_env_invalid"
    assert issues[0]["step_index"] is None


def test_validate_preset_env_valid():
    issues = validate_preset_env({"FOO": "BAR", "MESH_MODE": "RELEASE"})
    assert issues == []


def test_validate_preset_env_invalid_key_and_value_reported_separately():
    env = {"bad": "ok", "GOOD": "no/slash"}
    issues = validate_preset_env(env)
    keys = [i["detail"]["key"] for i in issues]
    assert "bad" in keys
    assert "GOOD" in keys
    assert any(i["message"].startswith("Env key must match") for i in issues if i["detail"]["key"] == "bad")
    assert any("path separators" in i["message"] for i in issues if i["detail"]["key"] == "GOOD")


def test_validate_preset_env_forbids_newlines_nul_and_parent_dir():
    env = {"A": "line1\nline2", "B": "nul\x00x", "C": "../x"}
    issues = validate_preset_env(env)
    by_key = {}
    for i in issues:
        by_key.setdefault(i["detail"]["key"], []).append(i["message"])
    assert any("newline" in m for m in by_key["A"])
    assert any("NUL" in m for m in by_key["B"])
    assert any("..'" in m or "contain '..'" in m for m in by_key["C"])


def test_validate_preset_env_value_max_len():
    env = {"LONG": "x" * 129}
    issues = validate_preset_env(env)
    assert any("<= 128" in i["message"] for i in issues)


def test_validate_preset_env_deterministic_ordering():
    env = {"Z": "no/slash", "A": "no/slash"}
    issues = validate_preset_env(env)
    assert [i["detail"]["key"] for i in issues] == ["A", "Z"]

