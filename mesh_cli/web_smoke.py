from __future__ import annotations

import importlib.util
from pathlib import Path
import re
from typing import Any
import tomllib

from engine.diagnostics import clear_diagnostics
from engine.diagnostics import error as diag_error
from engine.diagnostics import get_diagnostics_payload
from engine.diagnostics import warn as diag_warn
from engine.persistence_io import write_json_atomic


DEFAULT_WEB_BUILD_DIR = "build/web"
_LAYOUT_CANDIDATE_SUFFIXES: tuple[str, ...] = ("", "build", "dist", "web", "html")
_WEB_REF_RE = re.compile(r"""["']([^"']+\.(?:js|wasm|data|zip|pack)(?:\?[^"']*)?)["']""", re.IGNORECASE)
_DATA_SUFFIXES: tuple[str, ...] = (".data", ".zip", ".pack")


def resolve_web_build_dir(repo_root: Path | None = None) -> Path:
    root = (repo_root or Path.cwd()).resolve()
    config_path = root / "pygbag.toml"
    if not config_path.exists():
        return root / DEFAULT_WEB_BUILD_DIR
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return root / DEFAULT_WEB_BUILD_DIR
    pygbag = parsed.get("pygbag")
    if isinstance(pygbag, dict):
        output = pygbag.get("output")
        if isinstance(output, str) and output.strip():
            return root / output.strip()
    return root / DEFAULT_WEB_BUILD_DIR


def _collect_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def _candidate_roots(build_dir: Path) -> list[Path]:
    rows: list[Path] = []
    seen: set[str] = set()
    for suffix in _LAYOUT_CANDIDATE_SUFFIXES:
        candidate = (build_dir / suffix) if suffix else build_dir
        key = candidate.as_posix()
        if key in seen:
            continue
        seen.add(key)
        rows.append(candidate)
    return rows


def _extract_index_refs(index_text: str) -> dict[str, list[str]]:
    buckets: dict[str, set[str]] = {
        ".js": set(),
        ".wasm": set(),
        ".data": set(),
        ".zip": set(),
        ".pack": set(),
    }
    for raw in _WEB_REF_RE.findall(index_text):
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        is_external = "://" in candidate or candidate.startswith("//")
        candidate = candidate.split("?", 1)[0].split("#", 1)[0]
        if not is_external:
            candidate = candidate.replace("\\", "/").lstrip("/")
            if candidate.startswith("./"):
                candidate = candidate[2:]
        suffix = Path(candidate).suffix.lower()
        if suffix in buckets:
            buckets[suffix].add(candidate)
    return {key: sorted(values) for key, values in sorted(buckets.items())}


def _existing_refs(root: Path, refs: list[str], *, allow_external: bool = False) -> list[str]:
    present: list[str] = []
    for ref in refs:
        if allow_external and ("://" in ref or ref.startswith("//")):
            present.append(ref)
            continue
        if (root / ref).is_file():
            present.append(ref)
    return sorted(present)


def inspect_web_build_outputs(build_dir: Path) -> dict[str, Any]:
    files = _collect_files(build_dir)
    return {
        "file_count": int(len(files)),
        "files_sample": files[:25],
    }


def run_web_smoke(
    *,
    build_dir: str | None = None,
    artifact_path: str | None = None,
) -> int:
    clear_diagnostics()

    build_dir_raw = str(build_dir or "").strip()
    target_dir = Path(build_dir_raw).resolve() if build_dir_raw else resolve_web_build_dir()
    outputs_present = {
        "index_html": False,
        "js_bundle": False,
        "wasm_bundle": False,
        "data_bundle": False,
    }
    file_count = 0
    files_sample: list[str] = []
    selected_root: str | None = None

    if not target_dir.exists():
        diag_error(
            "WEB_BUILD_DIR_MISSING",
            f"web build directory not found: {target_dir.as_posix()}",
            "mesh_cli.web_smoke",
            location=target_dir.as_posix(),
            hint="Run `python -m mesh_cli build-web --out artifacts/web_build` first.",
        )
        if importlib.util.find_spec("pygbag") is None:
            diag_error(
                "WEB_BUILD_TOOLING_FAILED",
                "web build tooling unavailable: pygbag module not installed",
                "mesh_cli.web_smoke",
                location=target_dir.as_posix(),
                hint="Install pygbag in this Python environment before running build-web.",
            )
        ok = False
    else:
        target_summary = inspect_web_build_outputs(target_dir)
        file_count = int(target_summary.get("file_count", 0))
        files_sample = [str(item) for item in target_summary.get("files_sample", []) if isinstance(item, str)]
        if file_count == 0:
            diag_error(
                "WEB_BUILD_EMPTY",
                "web build directory is empty",
                "mesh_cli.web_smoke",
                location=target_dir.as_posix(),
                hint="Re-run build-web and confirm output permissions.",
            )
            if importlib.util.find_spec("pygbag") is None:
                diag_error(
                    "WEB_BUILD_TOOLING_FAILED",
                    "web build tooling unavailable: pygbag module not installed",
                    "mesh_cli.web_smoke",
                    location=target_dir.as_posix(),
                    hint="Install pygbag in this Python environment before running build-web.",
                )
            ok = False
        else:
            candidate_roots = _candidate_roots(target_dir)
            selected: Path | None = None
            for candidate in candidate_roots:
                if (candidate / "index.html").is_file():
                    selected = candidate
                    break

            if selected is None:
                diag_error(
                    "WEB_INDEX_MISSING",
                    "missing required web output: index.html",
                    "mesh_cli.web_smoke",
                    location=target_dir.as_posix(),
                    hint="Expected index.html in build root or known nested layout.",
                )
                diag_error(
                    "WEB_OUTPUT_LAYOUT_UNKNOWN",
                    "web output layout did not match known patterns",
                    "mesh_cli.web_smoke",
                    location=target_dir.as_posix(),
                    hint="Expected one of: /, /build, /dist, /web, /html.",
                )
                if importlib.util.find_spec("pygbag") is None:
                    diag_error(
                        "WEB_BUILD_TOOLING_FAILED",
                        "web build tooling unavailable: pygbag module not installed",
                        "mesh_cli.web_smoke",
                        location=target_dir.as_posix(),
                        hint="Install pygbag in this Python environment before running build-web.",
                    )
                ok = False
            else:
                selected_root = selected.as_posix()
                outputs_present["index_html"] = True
                if selected != target_dir:
                    diag_warn(
                        "WEB_BUILD_NESTED_DIR_DETECTED",
                        f"web build detected in nested layout: {selected.relative_to(target_dir).as_posix()}",
                        "mesh_cli.web_smoke",
                        location=selected.as_posix(),
                        hint="Nested layout is accepted, but keep CI paths deterministic.",
                    )

                selected_files = _collect_files(selected)
                selected_files_set = set(selected_files)
                index_text = (selected / "index.html").read_text(encoding="utf-8")
                refs = _extract_index_refs(index_text)

                js_refs = refs.get(".js", [])
                wasm_refs = refs.get(".wasm", [])
                data_refs = sorted(
                    [*refs.get(".data", []), *refs.get(".zip", []), *refs.get(".pack", [])]
                )
                js_refs_existing = _existing_refs(selected, js_refs, allow_external=True)
                wasm_refs_existing = _existing_refs(selected, wasm_refs)
                data_refs_existing = _existing_refs(selected, data_refs)

                outputs_present["js_bundle"] = bool(js_refs_existing)
                outputs_present["wasm_bundle"] = bool(
                    any(name.endswith(".wasm") for name in selected_files_set) or wasm_refs_existing
                )
                outputs_present["data_bundle"] = bool(data_refs_existing)

                if not outputs_present["js_bundle"]:
                    diag_error(
                        "WEB_JS_BUNDLE_MISSING",
                        "index.html does not reference an existing .js bundle",
                        "mesh_cli.web_smoke",
                        location=(selected / "index.html").as_posix(),
                        hint="Ensure script src paths in index.html resolve to built JS files.",
                    )

                if wasm_refs and not wasm_refs_existing:
                    diag_error(
                        "WEB_WASM_MISSING",
                        "index.html references .wasm assets that are missing",
                        "mesh_cli.web_smoke",
                        location=(selected / "index.html").as_posix(),
                        hint="Rebuild web output and verify wasm files are emitted.",
                    )

                if data_refs and not data_refs_existing:
                    diag_error(
                        "WEB_DATA_MISSING",
                        "index.html references data assets that are missing",
                        "mesh_cli.web_smoke",
                        location=(selected / "index.html").as_posix(),
                        hint="Rebuild web output and verify data bundles are emitted.",
                    )

                ok = bool(outputs_present["index_html"] and outputs_present["js_bundle"])
                if wasm_refs and not wasm_refs_existing:
                    ok = False
                if data_refs and not data_refs_existing:
                    ok = False

    payload = {
        "schema_version": 1,
        "ok": bool(ok),
        "build_dir": target_dir.as_posix(),
        "selected_root": selected_root,
        "outputs_present": outputs_present,
        "file_count": int(file_count),
        "files_sample": files_sample,
        "diagnostics": get_diagnostics_payload(),
    }
    artifact = str(artifact_path or "").strip()
    if artifact:
        write_json_atomic(
            Path(artifact),
            payload,
            indent=2,
            sort_keys=True,
            trailing_newline=True,
        )
    return 0 if ok else 1


__all__ = [
    "DEFAULT_WEB_BUILD_DIR",
    "inspect_web_build_outputs",
    "resolve_web_build_dir",
    "run_web_smoke",
]
