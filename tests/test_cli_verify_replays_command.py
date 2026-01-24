from __future__ import annotations

import json

import mesh_cli


def test_cli_verify_replays_exits_nonzero_when_any_script_fails(tmp_path, capsys):
    folder = tmp_path / "replays"
    folder.mkdir()

    # Pass: last_zone_id matches.
    (folder / "01_pass.json").write_text(
        json.dumps(
            {
                "steps": [{"emit": "entered_zone", "zone_id": "ZoneOK"}],
                "expect": {"last_zone_id": "ZoneOK"},
            }
        ),
        encoding="utf-8",
    )

    # Fail: last_zone_id mismatch.
    (folder / "02_fail.json").write_text(
        json.dumps(
            {
                "steps": [{"emit": "entered_zone", "zone_id": "ZoneOK"}],
                "expect": {"last_zone_id": "ZoneNOPE"},
            }
        ),
        encoding="utf-8",
    )

    rc = mesh_cli.main(["verify-replays", "--folder", str(folder)])
    assert rc == 1

    out = capsys.readouterr().out
    payload = json.loads(out)

    assert payload["total"] == 2
    assert payload["passed"] == 1
    assert payload["failed"] == 1
    assert [r["script"] for r in payload["results"]] == ["01_pass.json", "02_fail.json"]
    assert payload["results"][0]["ok"] is True
    assert payload["results"][0]["error"] == ""
    assert payload["results"][1]["ok"] is False
    assert payload["results"][1]["error"] != ""
