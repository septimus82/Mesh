"""Download one pinned file for CI and keep it only if its SHA-256 is the expected one (Windows Mesa, #422).

The Windows jobs' Mesa archive comes from a GitHub release download that sometimes answers 503 / 504 for one request
while the next succeeds (E2's post-merge CI 42569498883: acceptance got a 504 at 05:50:35, in the same minute
Extended's two Windows gpu shards downloaded the same file). So a transient failure is retried a bounded number of
times, with growing waits, and anything else fails at once:

- retried: HTTP 408 / 425 / 429 / 500 / 502 / 503 / 504, a network error or timeout, a download shorter than its
  Content-Length;
- not retried: any other HTTP status (404 means the pinned asset is gone), a final URL that isn't https, and a SHA-256
  that differs from the expected one (a complete download over TLS with another hash is a different file, not a
  hiccup);
- every attempt asks the same URL; the version and the source are the caller's and never change;
- the download goes to ``<out>.part`` and becomes ``<out>`` only after its hash matched, so a partial, corrupted or
  wrongly hashed file is never left where the caller looks (a stale ``<out>`` is removed first).

Each attempt, failure and wait is printed; a final failure also prints a GitHub ``::error::`` line and exits 1.

    python tooling/ci_fetch_verified.py <https url> <sha256> <out file>
"""

from __future__ import annotations

import hashlib
import http.client
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

DELAYS = (10, 20, 40, 60)  # seconds between attempts: 5 attempts, at most 130 s of waiting (jobs allow 30+ minutes)
TIMEOUT = 60  # seconds without data before one attempt fails
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
CHUNK = 1 << 20


class Transient(Exception):
    """A failure the next attempt may not have."""


class Permanent(Exception):
    """A failure no retry can fix."""


def _attempt(url: str, sha256: str, part: Path, opener: Callable[..., Any]) -> int:
    """One download into ``part``; returns its size once the hash matched."""
    digest = hashlib.sha256()
    size = 0
    try:
        with opener(url, timeout=TIMEOUT) as response, part.open("wb") as file:
            final = response.geturl()
            if not final.startswith("https://"):
                raise Permanent(f"redirected to a non-https URL: {final}")
            expected = response.headers.get("Content-Length")
            while chunk := response.read(CHUNK):
                digest.update(chunk)
                file.write(chunk)
                size += len(chunk)
    except urllib.error.HTTPError as exc:
        raise (Transient if exc.code in RETRY_STATUS else Permanent)(f"HTTP {exc.code} {exc.reason}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:  # (URLError, timeouts and resets too)
        raise Transient(f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}") from None
    if expected is not None and expected.isdigit() and size != int(expected):
        raise Transient(f"incomplete download: {size} of {expected} bytes")
    actual = digest.hexdigest()
    if actual != sha256:
        raise Permanent(f"SHA-256 {actual}, expected {sha256} ({size} bytes)")
    return size


def fetch(url: str, sha256: str, out: Path, *, opener: Callable[..., Any] = urllib.request.urlopen,
          sleep: Callable[[float], None] = time.sleep, delays: tuple[float, ...] = DELAYS,
          log: Callable[[str], None] = print) -> bool:
    """Download ``url`` to ``out``, verified against ``sha256``; True once ``out`` holds exactly that file."""
    sha256 = sha256.lower()
    if not url.startswith("https://") or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        log(f"::error::refusing to fetch: needs an https URL and a 64-hex SHA-256 (got {url!r}, {sha256!r})")
        return False
    part = out.with_name(out.name + ".part")
    out.unlink(missing_ok=True)
    attempts = len(delays) + 1
    for n in range(1, attempts + 1):
        log(f"attempt {n}/{attempts}: GET {url}")
        try:
            size = _attempt(url, sha256, part, opener)
        except (Transient, Permanent) as exc:
            part.unlink(missing_ok=True)
            if isinstance(exc, Permanent):
                log(f"::error::{out.name}: attempt {n}/{attempts} failed permanently: {exc}; not retrying")
                return False
            if n == attempts:
                log(f"::error::{out.name}: all {attempts} attempts failed; last: {exc}")
                return False
            log(f"attempt {n}/{attempts} failed: {exc}; retrying in {delays[n - 1]:g} s")
            sleep(delays[n - 1])
            continue
        os.replace(part, out)
        log(f"ok: {out.name}, {size} bytes, SHA-256 {sha256} verified, attempt {n}/{attempts}")
        return True
    return False  # (unreachable: the last attempt returns)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(0 if fetch(sys.argv[1], sys.argv[2], Path(sys.argv[3])) else 1)
