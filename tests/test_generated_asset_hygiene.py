"""Generated art must never bring account data or credentials into a commit (Milestone 17).

PixelLab's raw job records hold the account id inside storage URLs, and its API takes a bearer token. Raw records
are ignored (any ``raw/`` folder); what is tracked is only sanitized provenance. These checks read what
git tracks, so they hold in CI and on any checkout.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEXT = {".json", ".jsonl", ".md", ".txt", ".py", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".csv", ".log", ".html",
        ".htm", ".js", ".xml", ".svg"}
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# What leaks is an account id inside a storage path, not the host's name (reviews describe the URL form). Assembled
# from parts so this file doesn't match itself.
FORBIDDEN = {
    "PixelLab storage URL with an id": re.compile(re.escape("backblaze." + "pixellab.ai") + r"[^\s\"']*" + UUID),
    "PixelLab storage bucket path with an id": re.compile(re.escape("pixellab-" + "characters/") + UUID),
    "bearer token literal": re.compile("Bear" + r"er [A-Za-z0-9._\-]{20,}"),
    "signed URL with an id in its path": re.compile(r"https?://[^\s\"']*/" + UUID + r"/[^\s\"']*\?t="),
}


# SHA-256 of the owner's PixelLab API token and account id, lower case without hyphens (both are UUIDs, so their
# digests can't be reversed): CI has neither value, so a bare token or account id, with or without hyphens, is
# recognised by its digest.
PRIVATE_DIGESTS = {
    "82393a40101eaf6ce5274def5e581c4437d30c718cb23246911a2ee9fc09b03a",  # the API token
    "417dd669e8b5291385a87778f4db800c5efec3e9b2eda3d67a183c9d5fb7e998",  # the account id
}
ID_ANYWHERE = re.compile(UUID + r"|(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", re.IGNORECASE)


def _private(text: str) -> bool:
    return any(hashlib.sha256(m.lower().replace("-", "").encode()).hexdigest() in PRIVATE_DIGESTS
               for m in ID_ANYWHERE.findall(text))


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


@pytest.mark.fast
def test_raw_generator_records_are_ignored() -> None:
    _tracked()
    for path in ("tooling/hd2d_assets/pilot_m17/raw/characters/calls.jsonl",
                 "tooling/hd2d_assets/any_pilot/raw/textures/job/record.json", "raw/record.json",
                 "assets/somewhere/raw/job.json"):
        assert _git("check-ignore", "-q", path).returncode == 0, f"{path} would not be ignored"


@pytest.mark.fast
def test_no_raw_generator_records_are_tracked() -> None:
    raw = [p for p in _tracked() if "raw" in p.split("/")[:-1]]
    assert raw == []


@pytest.mark.integration  # reads every tracked text file (seconds): CI's full pytest run, not the fast tier
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


@pytest.mark.fast
def test_the_private_digests_recognise_a_bare_value() -> None:
    assert not _private("job 12345678-9abc-def0-1234-56789abcdef0 finished")
    digest = hashlib.sha256(b"123456789abcdef0123456789abcdef0").hexdigest()
    PRIVATE_DIGESTS.add(digest)
    try:
        assert _private("job 12345678-9ABC-def0-1234-56789abcdef0 finished")  # any case
        assert _private('{"key": "123456789abcdef0123456789abcdef0"}')  # without hyphens
        assert not _private("sha 0123456789abcdef0123456789abcdef0123")  # part of a longer hex string
    finally:
        PRIVATE_DIGESTS.discard(digest)


@pytest.mark.fast
def test_the_patterns_catch_what_they_are_for() -> None:
    account = "12345678-9abc-def0-1234-56789abcdef0"
    url = f"https://backblaze.pixellab.ai/file/pixellab-characters/{account}/c/south.png?t=1"
    assert all(pattern.search(url) for name, pattern in FORBIDDEN.items() if name != "bearer token literal")
    described = "backblaze.pixellab.ai/file/pixellab-characters/<account>/<character>/...?t=..."
    assert not any(pattern.search(described) for pattern in FORBIDDEN.values())
    assert FORBIDDEN["bearer token literal"].search("Authorization: Bear" + "er abcdefghij0123456789xyz")
    assert not FORBIDDEN["bearer token literal"].search('{"Authorization": "Bearer " + token}')
