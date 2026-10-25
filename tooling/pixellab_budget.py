"""One shared PixelLab generation budget for every agent of a generation stage (Milestone 17).

    py -3.13 tooling/pixellab_budget.py init LEDGER --approved 30 --agents textures,character
    py -3.13 tooling/pixellab_budget.py status LEDGER

Before each PixelLab request an agent calls ``reserve`` with the endpoint; the cost comes from ``COSTS``, and the
request is refused (``BudgetError``) when the endpoint's cost isn't established, the agent isn't a generation agent
of the ledger (QA agents are never listed: they are read-only), or the reservation would take the stage past its
approved budget. After the response it calls ``settle`` with the generations the API reported (its ``usage``), or
``release`` when nothing was charged. Results are stored only after ``sanitize``: no URLs or storage paths (they hold
the account id), no account or user fields, no long blobs, no credentials. The ledger is a JSON file every agent
shares; a lock file serialises them. It is a discipline for cooperating agents, not a security boundary: an agent
names itself, so the owner gives each generation agent its name and never gives a QA agent one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# Generations per request, with where the figure comes from. An endpoint not listed has no established cost: establish
# it (PixelLab's documentation, or one approved probe whose ``usage`` is recorded here) before using it.
COSTS: dict[str, tuple[float, str]] = {
    "create-tiles-pro": (15, "M17 Stage 1: usage of 1 call (64 px, 16 variations)"),
    "create-image-pixflux": (1, "M17 Stage 1: usage of 8 calls"),
    "create-image-bitforge": (1, "M17 Stage 1: usage of 2 calls"),
    "inpaint-v3": (10, "M17 Stage 1: usage of 1 call (undocumented beforehand)"),
    "create-character-with-4-directions": (1, "M17 Stage 1: usage of 2 calls"),
    "characters/animations": (1, "M17 Stage 1: template walk, about 1 per direction (cost the directions as units)"),
}
SECRET_KEYS = {"authorization", "api_key", "apikey", "token", "access_token", "secret", "password", "cookie"}
PRIVATE_KEY_PARTS = ("account", "user", "owner", "email")  # keys naming who made a request
URL = re.compile(r"[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
STORAGE_PATH = re.compile(r"\S*/" + UUID + r"\S*", re.IGNORECASE)  # a path with an id in it, with or without a scheme


class BudgetError(RuntimeError):
    """A request the stage's budget does not allow."""


def _private(key: Any) -> bool:
    key = str(key).lower()
    return key in SECRET_KEYS or any(part in key for part in PRIVATE_KEY_PARTS)


def sanitize(value: Any, secret: str | None = None) -> Any:
    """``value`` (a response, a request) safe to keep in provenance: URLs, storage paths, account and user fields,
    blobs and credentials removed. ``secret`` defaults to the PixelLab token in the environment."""
    if secret is None:
        secret = os.environ.get("PIXELLAB_API_TOKEN", "")
    if isinstance(value, dict):
        return {k: sanitize(v, secret) for k, v in value.items() if not _private(k)}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, secret) for v in value]
    if isinstance(value, str):
        if secret and secret in value:
            value = value.replace(secret, "<redacted>")
        if len(value) > 256:
            return f"<{len(value)} characters removed>"
        return STORAGE_PATH.sub("<path removed>", URL.sub("<url removed>", value))
    return value


@contextmanager
def _locked(path: Path, wait_s: float = 30.0) -> Iterator[dict[str, Any]]:
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise BudgetError(f"the ledger is locked ({lock}); remove the lock only if no agent is running")
            time.sleep(0.05)
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
        yield ledger
        path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    finally:
        os.close(fd)
        lock.unlink()


def committed(ledger: dict[str, Any]) -> float:
    """Generations spent or held: what settled entries used plus what open reservations hold."""
    return sum(e["used"] if e["state"] == "settled" else e["reserved"] if e["state"] == "reserved" else 0
               for e in ledger["entries"])


def init(path: Path, approved: float, agents: list[str]) -> None:
    if path.exists():
        raise BudgetError(f"{path} exists; a stage's ledger is never reset")
    path.write_text(json.dumps({"approved": approved, "agents": agents, "entries": []}, indent=2) + "\n",
                    encoding="utf-8")


def reserve(path: Path, agent: str, endpoint: str, purpose: str, units: int = 1) -> str:
    """Hold the cost of one request before it is sent; returns the reservation's id."""
    if endpoint not in COSTS:
        raise BudgetError(f"{endpoint}: no established cost; establish it before any request")
    if isinstance(units, bool) or not isinstance(units, int) or units < 1:
        raise BudgetError(f"units must be a whole number of requests, at least 1 (got {units!r})")
    cost = COSTS[endpoint][0] * units
    with _locked(path) as ledger:
        if agent not in ledger["agents"]:
            raise BudgetError(f"{agent} is not a generation agent of this ledger (QA agents are read-only)")
        left = ledger["approved"] - committed(ledger)
        if cost > left:
            raise BudgetError(f"{endpoint} needs {cost} generations; {left} of {ledger['approved']} remain")
        rid = uuid.uuid4().hex[:12]
        ledger["entries"].append({"id": rid, "agent": agent, "endpoint": endpoint, "purpose": purpose,
                                  "reserved": cost, "used": None, "state": "reserved", "at": time.time()})
    return rid


def _entry(ledger: dict[str, Any], rid: str) -> dict[str, Any]:
    entry: dict[str, Any] | None = next((e for e in ledger["entries"] if e["id"] == rid), None)
    if entry is None or entry["state"] != "reserved":
        raise BudgetError(f"{rid}: no open reservation")
    return entry


def settle(path: Path, rid: str, used: float, result: Any = None, secret: str | None = None) -> None:
    """Record what the request actually used (the API's ``usage``) and its sanitized result."""
    if isinstance(used, bool) or not isinstance(used, (int, float)) or not used >= 0:
        raise BudgetError(f"used must be a number of generations, at least 0 (got {used!r})")
    with _locked(path) as ledger:
        entry = _entry(ledger, rid)
        entry.update(state="settled", used=used, overrun=used > entry["reserved"], result=sanitize(result, secret))


def release(path: Path, rid: str, reason: str) -> None:
    """The request failed or was never sent, and nothing was charged."""
    with _locked(path) as ledger:
        _entry(ledger, rid).update(state="released", used=0, reason=sanitize(reason))


def status(path: Path) -> dict[str, Any]:
    ledger = json.loads(path.read_text(encoding="utf-8"))
    used: dict[str, float] = {}
    for e in ledger["entries"]:
        if e["state"] == "settled":
            used[e["agent"]] = used.get(e["agent"], 0) + e["used"]
    return {"approved": ledger["approved"], "committed": committed(ledger), "used_by_agent": used,
            "open": [e["id"] for e in ledger["entries"] if e["state"] == "reserved"],
            "overruns": [e["id"] for e in ledger["entries"] if e.get("overrun")]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("init")
    start.add_argument("ledger", type=Path)
    start.add_argument("--approved", type=float, required=True)
    start.add_argument("--agents", required=True, help="comma-separated generation agents (never QA)")
    sub.add_parser("status").add_argument("ledger", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        init(args.ledger, args.approved, [a for a in args.agents.split(",") if a])
    print(json.dumps(status(args.ledger), indent=1))


if __name__ == "__main__":
    main()
