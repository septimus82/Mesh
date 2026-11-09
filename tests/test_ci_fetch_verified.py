"""Windows CI's Mesa download (#422, #481): a cached archive is used only with the pinned SHA-256, transient download
failures are retried a bounded number of times, anything else fails at once, and only a file with the pinned SHA-256
is ever left at the output path. The setup action caches that file under one exact key."""

from __future__ import annotations

import hashlib
import io
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from tooling.ci_fetch_verified import DELAYS, fetch

pytestmark = [pytest.mark.fast]

URL = "https://github.com/pal1000/mesa-dist-win/releases/download/26.0.3/mesa3d-26.0.3-release-msvc.7z"
BODY = b"mesa archive bytes " * 1000
SHA = hashlib.sha256(BODY).hexdigest()
ACTION = Path(__file__).resolve().parents[1] / ".github" / "actions" / "mesh-ci-setup" / "action.yml"
PINNED = "de1ec45c906164de2c046288a8969e83cf2d51d031dc8dfd1f9371bb31cd6755"


class _Response(io.BytesIO):
    def __init__(self, body: bytes, *, length: int | None = None, final: str = URL) -> None:
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body) if length is None else length)}
        self._final = final

    def geturl(self) -> str:
        return self._final


def _http(code: int, reason: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(URL, code, reason, Message(), None)


class _Server:
    """Answers each request with the next scripted outcome (a response or an exception), recording the URLs asked."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> _Response:
        self.urls.append(url)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, _Response)
        return outcome


def _fetch(tmp_path: Path, server: _Server, sha: str = SHA) -> tuple[bool, Path, list[float], list[str]]:
    out = tmp_path / "mesa.7z"
    slept: list[float] = []
    logged: list[str] = []
    ok = fetch(URL, sha, out, opener=server, sleep=slept.append, log=logged.append)
    assert not (tmp_path / "mesa.7z.part").exists()  # never left behind, whatever happened
    return ok, out, slept, logged


def test_a_first_good_download_is_kept_without_waiting(tmp_path: Path) -> None:
    ok, out, slept, logged = _fetch(tmp_path, _Server(_Response(BODY)))
    assert ok and out.read_bytes() == BODY and slept == []
    assert logged[-1] == f"ok: mesa.7z, {len(BODY)} bytes, SHA-256 {SHA} verified, attempt 1/5"


def test_transient_failures_are_retried_with_growing_waits_from_the_same_url(tmp_path: Path) -> None:
    server = _Server(_http(503, "Service Unavailable"), _http(504, "Gateway Time-out"),
                     TimeoutError("timed out"), _Response(BODY[:100], length=len(BODY)),  # cut short
                     _Response(BODY))
    ok, out, slept, logged = _fetch(tmp_path, server)
    assert ok and out.read_bytes() == BODY
    assert slept == list(DELAYS) and server.urls == [URL] * 5
    assert "attempt 1/5 failed: HTTP 503 Service Unavailable; retrying in 10 s" in logged
    assert "attempt 2/5 failed: HTTP 504 Gateway Time-out; retrying in 20 s" in logged
    assert any(line.startswith("attempt 3/5 failed: TimeoutError") for line in logged)
    assert f"attempt 4/5 failed: incomplete download: 100 of {len(BODY)} bytes; retrying in 60 s" in logged
    assert logged[-1].endswith("verified, attempt 5/5")


def test_retries_are_bounded_and_the_last_failure_is_reported(tmp_path: Path) -> None:
    server = _Server(*[_http(504, "Gateway Time-out")] * 6)
    ok, out, slept, logged = _fetch(tmp_path, server)
    assert not ok and not out.exists()
    assert len(server.urls) == 5 and slept == list(DELAYS) and server.outcomes  # the 6th answer is never asked for
    assert logged[-1] == "::error::mesa.7z: all 5 attempts failed; last: HTTP 504 Gateway Time-out"


def test_a_wrong_checksum_fails_at_once_and_nothing_is_kept(tmp_path: Path) -> None:
    server = _Server(_Response(b"another file"), _Response(BODY))
    ok, out, slept, logged = _fetch(tmp_path, server)
    assert not ok and not out.exists() and slept == [] and len(server.urls) == 1
    assert logged[-1].startswith("::error::mesa.7z: attempt 1/5 failed permanently: SHA-256 ")
    assert logged[-1].endswith(f", expected {SHA} (12 bytes); not retrying")


def test_a_cached_archive_with_the_pinned_hash_is_used_without_a_download(tmp_path: Path) -> None:
    (tmp_path / "mesa.7z").write_bytes(BODY)
    server = _Server()  # (any request would fail the test)
    ok, out, slept, logged = _fetch(tmp_path, server)
    assert ok and out.read_bytes() == BODY and server.urls == [] and slept == []
    assert logged == [f"cached: mesa.7z, {len(BODY)} bytes, SHA-256 {SHA} verified; no download"]


def test_a_cache_miss_downloads_into_the_cache_folder_even_before_it_exists(tmp_path: Path) -> None:
    out = tmp_path / "mesa-cache" / "mesa.7z"  # (actions/cache/restore made nothing on a miss)
    slept: list[float] = []
    logged: list[str] = []
    assert fetch(URL, SHA, out, opener=_Server(_Response(BODY)), sleep=slept.append, log=logged.append)
    assert out.read_bytes() == BODY and slept == [] and logged[-1].endswith("verified, attempt 1/5")
    assert sorted(p.name for p in out.parent.iterdir()) == ["mesa.7z"]  # what the save step saves: no .part


def test_a_corrupt_cached_archive_is_reported_deleted_and_replaced_by_a_verified_download(tmp_path: Path) -> None:
    corrupt = BODY[:-1] + b"X"
    (tmp_path / "mesa.7z").write_bytes(corrupt)
    server = _Server(_Response(BODY))
    ok, out, _slept, logged = _fetch(tmp_path, server)
    assert ok and out.read_bytes() == BODY and server.urls == [URL]
    bad = hashlib.sha256(corrupt).hexdigest()
    assert logged[0] == (f"::warning::mesa.7z: rejected the file already there (cache): SHA-256 {bad}, expected {SHA}; "
                         "deleted, downloading instead")


@pytest.mark.parametrize("failure", [_http(404, "Not Found"), _http(504, "Gateway Time-out")])
def test_a_corrupt_cached_archive_is_never_left_even_when_the_download_fails(tmp_path: Path, failure: object) -> None:
    (tmp_path / "mesa.7z").write_bytes(b"corrupt")
    ok, out, _slept, logged = _fetch(tmp_path, _Server(*[failure] * 5))
    assert not ok and not out.exists() and logged[0].startswith("::warning::mesa.7z: rejected")
    assert logged[-1].startswith("::error::mesa.7z: ")


class _Killed(_Response):
    """Part of the file arrives, then the process is stopped (a cancelled job): no cleanup code runs."""

    def read(self, size: int | None = -1) -> bytes:
        if self.tell():
            raise KeyboardInterrupt
        return super().read(100)


def test_a_download_stopped_midway_never_leaves_a_file_at_the_output_path(tmp_path: Path) -> None:
    out = tmp_path / "mesa.7z"
    with pytest.raises(KeyboardInterrupt):
        fetch(URL, SHA, out, opener=_Server(_Killed(BODY)), sleep=lambda _s: None, log=lambda _m: None)
    assert not out.exists() and (tmp_path / "mesa.7z.part").stat().st_size == 100  # only the .part has the bytes


@pytest.mark.parametrize("outcome, why", [
    (_http(404, "Not Found"), "HTTP 404 Not Found"),
    (_Response(BODY, final="http://example.com/mesa.7z"), "redirected to a non-https URL: http://example.com/mesa.7z"),
])
def test_permanent_failures_are_not_retried(tmp_path: Path, outcome: object, why: str) -> None:
    ok, out, slept, logged = _fetch(tmp_path, _Server(outcome, _Response(BODY)))
    assert not ok and not out.exists() and slept == []
    assert logged[-1] == f"::error::mesa.7z: attempt 1/5 failed permanently: {why}; not retrying"


@pytest.mark.parametrize("url, sha", [(URL.replace("https", "http"), SHA), (URL, "abc"), (URL, SHA + "0")])
def test_it_refuses_without_an_https_url_and_a_full_sha256(tmp_path: Path, url: str, sha: str) -> None:
    server = _Server()
    slept: list[float] = []
    logged: list[str] = []
    assert not fetch(url, sha, tmp_path / "mesa.7z", opener=server, sleep=slept.append, log=logged.append)
    assert slept == []
    assert server.urls == [] and logged[0].startswith("::error::refusing to fetch")


def _step(setup: str, name: str) -> str:
    return setup[setup.index(f"- name: {name}"):].split("\n    - name:", 1)[0]


KEY = "key: mesa-${{ runner.os }}-${{ steps.mesa.outputs.version }}-${{ steps.mesa.outputs.sha256 }}"
CACHED = "path: ${{ runner.temp }}/mesa-cache/${{ steps.mesa.outputs.name }}"


def test_the_windows_setup_pins_mesa_once_and_caches_only_the_verified_archive_under_one_exact_key() -> None:
    setup = ACTION.read_text(encoding="utf-8")
    pin = _step(setup, "Mesa pin (Windows)")
    restore = _step(setup, "Restore the verified Mesa archive (Windows)")
    install = _step(setup, "Install Mesa OpenGL (Windows)")
    save = _step(setup, "Save the verified Mesa archive (Windows)")
    # One pin, which the URL, the hash checks and the cache key all read.
    assert 'MESA_VERSION: "26.0.3"' in pin and f'MESA_SHA256: "{PINNED}"' in pin
    assert setup.count('MESA_VERSION: "') == 1 and setup.count('MESA_SHA256: "') == 1
    assert '"version=$env:MESA_VERSION"' in pin and '"sha256=$env:MESA_SHA256"' in pin
    assert "MESA_VERSION: ${{ steps.mesa.outputs.version }}" in install
    assert "MESA_SHA256: ${{ steps.mesa.outputs.sha256 }}" in install
    # The exact archive file (not the DLLs), one exact key, no restore-keys that could pick another version.
    assert "uses: actions/cache/restore@v4" in restore and KEY in restore and CACHED in restore
    assert "uses: actions/cache/save@v4" in save and KEY in save and CACHED in save
    assert "restore-keys:" not in setup
    # Saved only after the install step passed (its checks throw, and a failed step skips the rest), never over a hit.
    assert "if: runner.os == 'Windows' && steps.mesa-cache.outputs.cache-hit != 'true'" in save
    assert setup.index(pin) < setup.index(restore) < setup.index(install) < setup.index(save)


@pytest.mark.parametrize("version, sha", [("26.0.4", PINNED), ("26.0.3", "0" * 64)])
def test_the_cache_key_changes_with_the_pinned_version_or_checksum(version: str, sha: str) -> None:
    def key(os_name: str, v: str, s: str) -> str:
        return (KEY.removeprefix("key: ").replace("${{ runner.os }}", os_name)
                .replace("${{ steps.mesa.outputs.version }}", v).replace("${{ steps.mesa.outputs.sha256 }}", s))

    assert key("Windows", "26.0.3", PINNED) == f"mesa-Windows-26.0.3-{PINNED}"
    assert key("Windows", version, sha) != key("Windows", "26.0.3", PINNED)


def test_the_windows_setup_gets_mesa_through_it_unbuffered_and_still_checks_the_hash() -> None:
    install = _step(ACTION.read_text(encoding="utf-8"), "Install Mesa OpenGL (Windows)")
    assert "Invoke-WebRequest" not in install
    assert '$archive = Join-Path $env:RUNNER_TEMP "mesa-cache/$name"' in install  # where the cache restores it
    fetch_line = next(line for line in install.splitlines() if "ci_fetch_verified.py" in line)
    assert fetch_line.lstrip().startswith('python -u "$env:GITHUB_WORKSPACE/tooling/ci_fetch_verified.py" ')
    assert ('"https://github.com/pal1000/mesa-dist-win/releases/download/$env:MESA_VERSION/$name" '
            "$env:MESA_SHA256 $archive") in fetch_line
    # It stops the step if no verified file was had, and the step's own hash check still runs before 7z extracts.
    after = install[install.index(fetch_line) + len(fetch_line):]
    assert after.lstrip().startswith('if ($LASTEXITCODE -ne 0) { throw "could not get a verified $name" }')
    assert after.index("Get-FileHash") < after.index("$actual -ne $env:MESA_SHA256") < after.index("7z x")
