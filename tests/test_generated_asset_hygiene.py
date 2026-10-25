"""Generated art must never bring account data or credentials into a commit (Milestone 17).

PixelLab's raw job records hold the account id inside storage URLs, and its API takes a bearer token. The raw records
are ignored (``tooling/hd2d_assets/**/raw/``); what is tracked is only sanitized provenance. These checks read what
git tracks, so they hold in CI and on any checkout.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[1]
TEXT = {".json", ".jsonl", ".md", ".txt", ".py", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".csv"}
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# What leaks is an account id inside a storage path, not the host's name (reviews describe the URL form). Assembled
# from parts so this file doesn't match itself.
FORBIDDEN = {
    "PixelLab storage URL with an id": re.compile(re.escape("backblaze." + "pixellab.ai") + r"[^\s\"']*" + UUID),
    "PixelLab storage bucket path with an id": re.compile(re.escape("pixellab-" + "characters/") + UUID),
    "bearer token literal": re.compile("Bear" + r"er [A-Za-z0-9._\-]{20,}"),
    "signed URL with an id in its path": re.compile(r"https?://[^\s\"']*/" + UUID + r"/[^\s\"']*\?t="),
}


# SHA-256 of the owner's PixelLab API token and account id (both UUID-shaped, so their digests can't be reversed):
# CI has neither value, so a bare token or account id is recognised by its digest.
PRIVATE_DIGESTS = {
    "a66601fb24f37573baf0ebc0a09b70e6ca7adb1486bcc4c57501692fb0cae9a7",  # the API token
    "9f838975bf09a5de437b82781df594a8e0ecea311bc8efea0927688a69fe4263",  # the account id
}
UUID_ANYWHERE = re.compile(UUID, re.IGNORECASE)


def _private(text: str) -> bool:
    return any(hashlib.sha256(m.lower().encode()).hexdigest() in PRIVATE_DIGESTS for m in UUID_ANYWHERE.findall(text))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


def _tracked() -> list[str]:
    try:
        listing = _git("ls-files")
    except OSError:
        pytest.skip("git is not available")
    if listing.returncode != 0:
        pytest.skip("not a git checkout")
    return listing.stdout.splitlines()


def test_raw_generator_records_are_ignored() -> None:
    _tracked()
    for path in ("tooling/hd2d_assets/pilot_m17/raw/characters/calls.jsonl",
                 "tooling/hd2d_assets/any_pilot/raw/textures/job/record.json"):
        assert _git("check-ignore", "-q", path).returncode == 0, f"{path} would not be ignored"


def test_no_raw_generator_records_are_tracked() -> None:
    raw = [p for p in _tracked() if p.startswith("tooling/hd2d_assets/") and "/raw/" in p]
    assert raw == []


def test_tracked_text_holds_no_storage_urls_or_credentials() -> None:
    token = os.environ.get("PIXELLAB_API_TOKEN", "")
    found: list[str] = []
    for rel in _tracked():
        path = REPO / rel
        if path.suffix.lower() not in TEXT or not path.is_file() or path.stat().st_size > 4_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        found += [f"{rel}: {name}" for name, pattern in FORBIDDEN.items() if pattern.search(text)]
        if _private(text) or (len(token) >= 16 and token in text):
            found.append(f"{rel}: the PixelLab API token or account id")
    assert found == []


def test_the_private_digests_recognise_a_bare_value() -> None:
    assert not _private("job 12345678-9abc-def0-1234-56789abcdef0 finished")
    digest = hashlib.sha256(b"12345678-9abc-def0-1234-56789abcdef0").hexdigest()
    PRIVATE_DIGESTS.add(digest)
    try:
        assert _private("job 12345678-9ABC-def0-1234-56789abcdef0 finished")  # any case
    finally:
        PRIVATE_DIGESTS.discard(digest)


def test_the_patterns_catch_what_they_are_for() -> None:
    account = "12345678-9abc-def0-1234-56789abcdef0"
    url = f"https://backblaze.pixellab.ai/file/pixellab-characters/{account}/c/south.png?t=1"
    assert all(pattern.search(url) for name, pattern in FORBIDDEN.items() if name != "bearer token literal")
    described = "backblaze.pixellab.ai/file/pixellab-characters/<account>/<character>/...?t=..."
    assert not any(pattern.search(described) for pattern in FORBIDDEN.values())
    assert FORBIDDEN["bearer token literal"].search("Authorization: Bear" + "er abcdefghij0123456789xyz")
    assert not FORBIDDEN["bearer token literal"].search('{"Authorization": "Bearer " + token}')
