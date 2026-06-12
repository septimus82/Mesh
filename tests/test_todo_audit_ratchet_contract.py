from __future__ import annotations

from pathlib import Path

from tooling.todo_audit import scan_repo, summarize

BASELINE_TOTAL = 35


def test_todo_audit_total_does_not_increase() -> None:
    root = Path(__file__).resolve().parents[1]
    hits = scan_repo(root)
    counts = summarize(hits)
    total = int(counts.get("TOTAL", 0))
    if total > BASELINE_TOTAL:
        new_hits = hits[:20]
        details = "\n".join(f"{h.path}:{h.line} [{h.tag}] {h.text}" for h in new_hits)
        raise AssertionError(
            f"Tech-debt markers increased: {total} > {BASELINE_TOTAL}\n"
            f"Sample hits:\n{details}"
        )
