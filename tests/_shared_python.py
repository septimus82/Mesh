"""Run ``python -c`` snippets for import-boundary tests in one long-lived interpreter, not a fresh one each.

A fresh interpreter costs about a second here (``engine.editor`` imports arcade). The answers stay those of a fresh
interpreter:

- ``watch`` names the modules a snippet reports on. If any is already loaded when the snippet arrives, the shared
  interpreter can't tell what *this* import loads, so that snippet runs in a fresh interpreter instead.
- ``without_arcade=True`` uses an interpreter where arcade was made unimportable before anything was imported, so every
  module it ever loaded was loaded without arcade.
"""

from __future__ import annotations

import atexit
import json
import subprocess
import sys
from collections.abc import Sequence

_NO_ARCADE = "import sys; sys.modules['arcade'] = None\n"

_WORKER = """
import contextlib, io, json, sys, traceback
for line in sys.stdin:
    request = json.loads(line)
    if any(name in sys.modules for name in request["watch"]):
        reply = {"clean": False}
    else:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                exec(request["code"], {"__name__": "__shared_python__"})
            reply = {"clean": True, "stdout": out.getvalue()}
        except BaseException:
            reply = {"clean": True, "error": traceback.format_exc()}
    sys.__stdout__.write(json.dumps(reply) + "\\n")
    sys.__stdout__.flush()
"""

_workers: dict[bool, subprocess.Popen[str]] = {}


def _worker(without_arcade: bool) -> subprocess.Popen[str]:
    worker = _workers.get(without_arcade)
    if worker is None or worker.poll() is not None:
        source = (_NO_ARCADE if without_arcade else "") + _WORKER
        worker = subprocess.Popen([sys.executable, "-c", source], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, encoding="utf-8")
        _workers[without_arcade] = worker
    return worker


def run_python(code: str, *, watch: Sequence[str] = (), without_arcade: bool = False) -> str:
    """What ``python -c code`` prints (with arcade unimportable when ``without_arcade``); fails like ``check=True``."""
    worker = _worker(without_arcade)
    assert worker.stdin is not None and worker.stdout is not None
    worker.stdin.write(json.dumps({"code": code, "watch": list(watch)}) + "\n")
    worker.stdin.flush()
    reply = json.loads(worker.stdout.readline())
    if not reply["clean"]:
        source = (_NO_ARCADE if without_arcade else "") + code
        return subprocess.run([sys.executable, "-c", source], capture_output=True, check=True, text=True).stdout
    assert "error" not in reply, reply.get("error")
    return reply["stdout"]


@atexit.register
def _stop_workers() -> None:
    for worker in _workers.values():
        if worker.stdin is not None:
            worker.stdin.close()
        worker.wait(timeout=10)
