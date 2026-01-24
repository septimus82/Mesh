from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Iterable, Mapping


def build_pytest_env(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def build_pytest_args(extra_args: Iterable[str]) -> list[str]:
    return ["-o", "addopts="] + list(extra_args)


def format_xdist(enabled: bool, workers: str | int | None = None) -> str:
    if not enabled:
        return "False"
    if workers is None:
        return "True (workers=auto)"
    return f"True (workers={workers})"


def write_runner_log(path: Path, info: Mapping[str, object], command: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("[pytest-runner]\n")
    for key in sorted(info):
        lines.append(f"{key}: {info[key]}\n")
    lines.append(f"command: {shlex.join(list(command))}\n")
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("".join(lines))
