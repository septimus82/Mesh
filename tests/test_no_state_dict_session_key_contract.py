from __future__ import annotations

from pathlib import Path
import re


def test_no_state_dict_session_keys_in_tests() -> None:
    allowlist = {
        Path("tests/_session_stub.py"),
        Path("tests/test_editor_session_query_contract.py"),
    }
    key_pattern = re.compile(r"[\"']session[\"']\s*:")
    index_pattern = re.compile(r"\[\s*[\"']session[\"']\s*\]")
    hits: list[str] = []
    for path in Path("tests").rglob("*.py"):
        if path in allowlist:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if key_pattern.search(text) or index_pattern.search(text):
            hits.append(str(path))
    assert not hits, f"session key/index usage found in tests: {hits}"
