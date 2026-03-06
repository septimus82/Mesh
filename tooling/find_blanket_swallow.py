from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

_CANONICAL_OUT = Path("artifacts/swallow_scan.json")


def _is_exception_name(expr: ast.expr | None) -> bool:
    return isinstance(expr, ast.Name) and expr.id == "Exception"


def _is_exception_tuple(expr: ast.expr | None) -> bool:
    if not isinstance(expr, ast.Tuple):
        return False
    return any(_is_exception_name(item) for item in expr.elts)


def _is_blanket_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return _is_exception_name(handler.type) or _is_exception_tuple(handler.type)


def _is_pass_only(handler: ast.ExceptHandler) -> bool:
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)


def _pattern_for_handler(handler: ast.ExceptHandler) -> str | None:
    if not _is_blanket_exception(handler):
        return None
    if not _is_pass_only(handler):
        return None
    if handler.type is None:
        return "except: pass"
    if _is_exception_name(handler.type):
        return "except Exception: pass"
    return "except Exception: pass"


def _scan_file(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(text, filename=path.as_posix())
    except SyntaxError:
        return None
    line_numbers: list[int] = []
    patterns: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        pattern = _pattern_for_handler(node)
        if pattern is None:
            continue
        line_numbers.append(int(node.lineno))
        patterns.add(pattern)
    if not line_numbers:
        return None
    line_numbers.sort()
    return {
        "file": path.as_posix(),
        "count": len(line_numbers),
        "line_numbers": line_numbers,
        "patterns_found": sorted(patterns),
    }


def _iter_python_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*.py") if p.is_file())
    return sorted(files, key=lambda p: p.as_posix())


def _build_report(roots: list[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in _iter_python_files(roots):
        row = _scan_file(path)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: item["file"])
    top_offenders = sorted(rows, key=lambda item: (-int(item["count"]), item["file"]))
    return {
        "schema_version": 1,
        "roots": [root.as_posix() for root in roots],
        "total_files_with_matches": len(rows),
        "total_matches": int(sum(int(row["count"]) for row in rows)),
        "results": rows,
        "top_offenders": top_offenders,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find blanket swallow pass patterns.")
    parser.add_argument(
        "--out",
        default=None,
        help="Optional additional output JSON path",
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        default=["engine", "mesh_cli"],
        help="Roots to scan (default: engine mesh_cli)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top offenders to include (default: 10)",
    )
    args = parser.parse_args(argv)

    roots = [Path(root) for root in args.roots]
    payload = _build_report(roots)
    top_n = max(0, int(args.top_n))
    payload["top_n"] = top_n
    payload["top_offenders"] = payload["top_offenders"][:top_n]

    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _CANONICAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    _CANONICAL_OUT.write_text(
        encoded,
        encoding="utf-8",
    )

    if args.out is not None:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            encoded,
            encoding="utf-8",
        )
    return 1 if int(payload["total_matches"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
