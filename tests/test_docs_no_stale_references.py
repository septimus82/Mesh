from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"

TOKENS = (
    "ai-apply",
    "requirements.txt",
    "pip install -r requirements.txt",
)


@dataclass(frozen=True)
class _Hit:
    path: str
    line: int
    token: str
    text: str


def test_docs_no_stale_references() -> None:
    hits: list[_Hit] = []

    for path in sorted(DOCS_ROOT.rglob("*.md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, start=1):
            for token in TOKENS:
                if token in line:
                    hits.append(_Hit(path=rel, line=idx, token=token, text=line))

    hits.sort(key=lambda h: (h.path, h.line, h.token))
    if hits:
        rendered = "\n".join(f"{h.path}:{h.line} {h.token}: {h.text}" for h in hits)
        raise AssertionError(f"Stale docs references detected:\n{rendered}")

