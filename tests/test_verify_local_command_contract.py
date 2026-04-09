from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def test_verify_local_parser_contract() -> None:
    from mesh_cli.main import create_parser

    parser = create_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"  # noqa: SLF001
    )
    choices = set(subparsers_action.choices.keys())
    assert "verify-local" in choices
    help_text = subparsers_action.choices["verify-local"].format_help()
    assert "--artifacts" in help_text


def test_verify_local_outputs_deterministic_subset_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mesh_cli
    import mesh_cli.legacy_impl as legacy_impl
    import tooling.find_blanket_swallow as find_blanket_swallow
    import tooling.mypy_island as mypy_island
    import tooling.scan_exception_policies as scan_exception_policies
    from engine import repo_root as repo_root_mod

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='mesh'\n", encoding="utf-8")
    (repo / "worlds").mkdir()
    (repo / "worlds" / "main_world.json").write_text("{}", encoding="utf-8")
    (repo / "artifacts").mkdir()

    monkeypatch.chdir(repo)
    monkeypatch.setattr(repo_root_mod, "get_repo_root", lambda start=None, strict=True: repo.resolve())
    monkeypatch.setattr(legacy_impl, "load_config", lambda: type("Cfg", (), {"world_file": "worlds/main_world.json"})())
    monkeypatch.setattr(legacy_impl.validate_all, "main", lambda argv: 0)
    monkeypatch.setattr(mypy_island, "main", lambda argv: 0)

    def _fake_swallow_scan(argv: list[str]) -> int:
        _ = argv
        (repo / "artifacts" / "swallow_scan.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "total_matches": 0,
                    "total_files_with_matches": 0,
                    "results": [],
                    "top_n": 10,
                    "top_offenders": [],
                    "roots": ["engine", "mesh_cli"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(find_blanket_swallow, "main", _fake_swallow_scan)
    monkeypatch.setattr(
        scan_exception_policies,
        "scan",
        lambda roots, repo_root=None: {
            "schema_version": 1,
            "ble001_count_total": 0,
            "ble001_missing_reason_count": 0,
            "except_pass_count_total": 0,
            "broad_catch_count_total": 0,
            "silent_broad_catch_count_total": 0,
            "top_offenders": {},
            "silent_broad_catches": [],
        },
    )

    code = mesh_cli.main(["verify-local", "--artifacts", "artifacts"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ok"] is True
    assert [row["name"] for row in payload["steps"]] == [
        "verify-strict",
        "mypy-island",
        "swallow-scan-gate",
        "exception-policy-scan",
        "pytest-fast",
    ]
    assert payload["steps"][-1]["error"] == "skipped: running under pytest"
    assert payload["artifacts"]["written"]["swallow_scan"] == "artifacts/swallow_scan.json"
    assert payload["artifacts"]["written"]["exception_policy_scan"] == "artifacts/exception_policy_scan.json"


def test_verify_local_swallow_scan_bad_artifact_keeps_deterministic_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mesh_cli
    import mesh_cli.legacy_impl as legacy_impl
    import tooling.find_blanket_swallow as find_blanket_swallow
    import tooling.mypy_island as mypy_island
    import tooling.scan_exception_policies as scan_exception_policies
    from engine import repo_root as repo_root_mod

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='mesh'\n", encoding="utf-8")
    (repo / "worlds").mkdir()
    (repo / "worlds" / "main_world.json").write_text("{}", encoding="utf-8")
    (repo / "artifacts").mkdir()

    monkeypatch.chdir(repo)
    monkeypatch.setattr(repo_root_mod, "get_repo_root", lambda start=None, strict=True: repo.resolve())
    monkeypatch.setattr(legacy_impl, "load_config", lambda: type("Cfg", (), {"world_file": "worlds/main_world.json"})())
    monkeypatch.setattr(legacy_impl.validate_all, "main", lambda argv: 0)
    monkeypatch.setattr(mypy_island, "main", lambda argv: 0)

    def _fake_swallow_scan(argv: list[str]) -> int:
        _ = argv
        (repo / "artifacts" / "swallow_scan.json").write_text("{bad json\n", encoding="utf-8")
        return 1

    monkeypatch.setattr(find_blanket_swallow, "main", _fake_swallow_scan)
    monkeypatch.setattr(
        scan_exception_policies,
        "scan",
        lambda roots, repo_root=None: {
            "schema_version": 1,
            "ble001_count_total": 0,
            "ble001_missing_reason_count": 0,
            "except_pass_count_total": 0,
            "broad_catch_count_total": 0,
            "silent_broad_catch_count_total": 0,
            "top_offenders": {},
            "silent_broad_catches": [],
        },
    )

    code = mesh_cli.main(["verify-local", "--artifacts", "artifacts"])
    payload = json.loads(capsys.readouterr().out)
    by_name = {step["name"]: step for step in payload["steps"]}

    assert code == 1
    assert by_name["swallow-scan-gate"]["ok"] is False
    assert by_name["swallow-scan-gate"]["error"] == "pass-only blanket swallows found"
    assert payload["artifacts"]["written"]["swallow_scan"] == "artifacts/swallow_scan.json"
