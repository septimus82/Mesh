"""F13-B (#422): CI's release bundle reuses the verify-all its verify step just ran, only with proof.

CI's verify job runs an enforced ``mesh verify-all --artifacts artifacts --ci-bundle --release-notes-artifact
--reuse-evidence``, then ``mesh release bundle``, whose release check ran a whole second verify-all (about 3 minutes
on Windows) on the same checkout. With ``--reuse-evidence`` verify-all writes ``verify_all_evidence.json`` last:

- its exit code and every step's result (a step skipped after a failure is not a pass);
- what it covered (pytest passthrough arguments, ``--skip-web-smoke``) and its CI-only options;
- the git commit and whether the tree was clean, before and after; the tool version, Python, platform and
  ``MESH_*`` environment it started with;
- the files it produced and their SHA-256: only files new or rewritten during the run. Whatever was already in the
  folder and left untouched (an older report, an archive, anything else) is listed apart and never copied.

Which produced files are verification outputs isn't left to "it changed during the run": ``RELEASE_REPORTS`` names
what a fresh release check's verify-all leaves in ``release/`` (all required), the player package's files are the ones
its own ``player_pkg/manifest.json`` lists (and the bytecode Python wrote for those of them that are ``.py`` files, when
the gate ran the package), and verify-demo's pytest folders match ``SCRATCH``. A produced file that is
none of these (nor a known non-release output, ``NOT_COPIED``) refuses the reuse, as does a missing required report.

``mesh release bundle --reuse-verify-all <folder>`` reuses that run only if every check in ``check`` holds now; the
copies are checked against the recorded hashes again. A copy that fails, or is left partial, is undone and verify-all
runs; a reuse that can't be undone fails the release check rather than leave stray files in ``release/``. Otherwise
it says why, records it, and runs verify-all itself as it always did. ``verify_all_reuse.json`` in the bundle's
``release/`` says which happened and on what evidence. Without the option nothing changes.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from engine.persistence_io import write_json_atomic

EVIDENCE = "verify_all_evidence.json"
RECORD = "verify_all_reuse.json"
SCHEMA = 2  # (2: "files" are only the files the run produced; 1 listed every file in its folder, so it is refused)
# Not part of what the release check's own verify-all leaves in release/, so not copied into the bundle:
# - written only for CI's options (--ci-bundle: index, report, overlay perf; --release-notes-artifact: the notes);
# - written to the repository's artifacts/ whatever --artifacts says (tooling/pytest_fast.py, tooling/pytest_full.py,
#   the swallow scan): CI's --artifacts is that folder, a release check's is release/ (CI run 41215383144's bundle had
#   them, its earlier bundles didn't).
NOT_COPIED = frozenset({"index.json", "verify_report.json", "overlay_perf.json", "release_notes.json", "release_notes.md",
                        "pytest_fast.log", "pytest_full.log", "swallow_scan.json"})
# What a fresh release check's verify-all leaves in release/, every one required: the same in every F13-A bundle on Linux
# and Windows (CI runs 41208533048, 41209640427, 41209645464; release check's own asset audit, export, debug bundle and
# report aside). A new verify-all report must be added here, or reuse is refused (and verify-all runs) until it is.
RELEASE_REPORTS = frozenset({
    "brush_audit.json", "content_audit_report.json", "content_audit_report.txt", "doctor_assets.json",
    "encounter_audit_compact.json", "encounter_audit_summary.json", "encounter_coverage_matrix.json",
    "encounter_headroom.json", "exception_budget.json", "exception_policy_scan.json", "macro_audit.json",
    "perf_compare.json", "perf_run.json", "replays_summary.json", "room_audit.json", "runtime_diagnostics_snapshot.json",
    "runtime_smoke.json", "scenes_index.json", "shadow_backend.json", "stamp_audit.json", "swallowed_exceptions.json",
    "verify_all_summary.json", "verify_step_budget_check.json", "verify_step_durations.json",
    "verify_step_speed_advisory.json", "verify_summary.json", "verify_summary.txt", "web_smoke.json", "worlds_index.json",
    "web_build/_web_build_stage.apk", "web_build/_web_build_stage.tar.gz", "web_build/favicon.png", "web_build/index.html",
    # the player-package gate's own records; the package's files are the ones its manifest lists
    "player_pkg/manifest.json", "player_pkg/package_check.json", "player_pkg/runtime_diagnostics_snapshot.json",
    "player_pkg/runtime_smoke.json",
})
PACKAGE = "player_pkg/"
# Python's cache of a module, <dir>/__pycache__/<name>.<tag>.pyc for <dir>/<name>.py: the player-package gate's smoke run
# writes it for the package's modules (58 such files in every F13-A bundle, each beside its listed .py).
_BYTECODE = re.compile(r"((?:[^/]+/)*)__pycache__/([^/.]+)\.[^/]+\.pyc")
SCRATCH = re.compile(r"verify_demo_pytest/pid\d+-run\d+/(?:basetemp|cache)/.+")  # (verify-demo's own pytest folders)
_BUDGET_ENV = "MESH_VERIFY_BUDGET_ENFORCE"  # (CI enforces the step budgets in its verify step only: stricter, so allowed)


def state(repo_root: Path) -> dict[str, Any]:
    """The checkout and runtime a verify-all's result depends on, as they are now."""
    from engine.provenance import get_provenance

    with contextlib.chdir(repo_root):  # (provenance asks git in the current folder)
        prov = get_provenance(deterministic=True)
    return {"git_commit": prov.git_commit, "git_dirty": prov.git_dirty, "tool_version": prov.tool_version,
            "python": prov.python_version, "platform": prov.platform,
            "env": {k: v for k, v in sorted(os.environ.items()) if k.startswith("MESH_")}}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk(folder: Path) -> list[tuple[str, Path]]:
    """Every regular file under ``folder`` but the evidence (links not followed or listed, as the bundle's file scan)."""
    found: list[tuple[str, Path]] = []
    for root, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(root, d)))
        for name in sorted(names):
            path = Path(root) / name
            rel = path.relative_to(folder).as_posix()
            if rel != EVIDENCE and not path.is_symlink() and path.is_file():
                found.append((rel, path))
    return found


def _identity(path: Path) -> list[Any]:
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, _sha256(path)]


def snapshot(folder: Path) -> dict[str, list[Any]]:
    """What ``folder`` holds before a verify-all runs (each file's size, modification time and hash): files still the
    same afterwards weren't produced by it."""
    return {rel: _identity(path) for rel, path in _walk(folder)} if folder.is_dir() else {}


def write_evidence(artifacts_dir: Path, *, repo_root: Path, before: dict[str, Any], files_before: dict[str, list[Any]],
                   exit_code: int, payload: dict[str, Any], args: Any) -> None:
    """Record, last, what this verify-all did and on what (it never decides anything: ``check`` does). Its files are
    the ones it produced: new, or rewritten, since ``files_before`` (``snapshot`` before the run)."""
    produced: dict[str, str] = {}
    untouched: list[str] = []
    for rel, path in _walk(artifacts_dir):
        identity = _identity(path)
        if files_before.get(rel) == identity:
            untouched.append(rel)
        else:
            produced[rel] = identity[2]
    steps = payload.get("steps") if isinstance(payload, dict) else None
    evidence = {
        "schema": SCHEMA,
        "exit_code": int(exit_code),
        "ok": bool(payload.get("ok")) if isinstance(payload, dict) else False,
        "steps": [{"name": s.get("name"), "code": s.get("code"), "error": s.get("error")}
                  for s in (steps or []) if isinstance(s, dict)],
        "selection": {"pytest_args": [str(a) for a in (getattr(args, "pytest_args", None) or [])],
                      "skip_web_smoke": bool(getattr(args, "skip_web_smoke", False))},
        "options": {"ci_bundle": bool(getattr(args, "ci_bundle", False)),
                    "release_notes_artifact": bool(getattr(args, "release_notes_artifact", False))},
        "before": before,
        "after": state(repo_root),
        "files": produced,
        "untouched": untouched,
    }
    write_json_atomic(artifacts_dir / EVIDENCE, evidence, indent=2, sort_keys=True, trailing_newline=True)


def check(source: Path, repo_root: Path) -> tuple[dict[str, Any] | None, str]:
    """``(evidence, "")`` when the verify-all recorded in ``source`` can stand for one run now, else ``(None, why)``."""
    from mesh_cli.verify_steps import STEP_ORDER

    try:
        evidence = json.loads((source / EVIDENCE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"no {EVIDENCE} in {source.as_posix()}"
    except (OSError, ValueError) as exc:
        return None, f"{EVIDENCE} can't be read ({exc})"
    if not isinstance(evidence, dict) or evidence.get("schema") != SCHEMA:
        return None, f"{EVIDENCE} has an unknown format"
    if evidence.get("exit_code") != 0 or evidence.get("ok") is not True:
        return None, f"that verify-all didn't pass (exit {evidence.get('exit_code')}, ok {evidence.get('ok')})"
    steps = [s for s in _part(evidence, "steps", list) if isinstance(s, dict)]
    if [s.get("name") for s in steps] != list(STEP_ORDER) or len(steps) != len(_part(evidence, "steps", list)):
        return None, "that verify-all's steps aren't the complete list"
    unrun = [str(s["name"]) for s in steps if s.get("code") != 0 or str(s.get("error") or "").startswith("skipped")]
    if unrun:
        return None, f"steps that didn't pass or didn't run: {', '.join(unrun)}"
    selection = _part(evidence, "selection", dict)
    if selection.get("pytest_args") != [] or selection.get("skip_web_smoke") is not False:
        return None, "that verify-all ran a narrowed selection (pytest arguments or --skip-web-smoke)"
    before, after = _part(evidence, "before", dict), _part(evidence, "after", dict)
    now = state(repo_root)
    if not now["git_commit"] or before.get("git_commit") != now["git_commit"] or after.get("git_commit") != now["git_commit"]:
        return None, f"it ran on commit {before.get('git_commit')}, this is {now['git_commit']}"
    if before.get("git_dirty") is not False or after.get("git_dirty") is not False or now["git_dirty"] is not False:
        return None, "the tree wasn't clean (before, after or now)"
    for key in ("tool_version", "python", "platform"):
        if before.get(key) != now[key]:
            return None, f"{key} differs ({before.get(key)} then, {now[key]} now)"
    then_env = dict(before.get("env") or {})
    now_env = dict(now["env"])
    if then_env.pop(_BUDGET_ENV, None) not in ("1", now_env.get(_BUDGET_ENV)):
        return None, f"{_BUDGET_ENV} was weaker then than now"
    now_env.pop(_BUDGET_ENV, None)
    if then_env != now_env:
        changed = sorted(k for k in set(then_env) | set(now_env) if then_env.get(k) != now_env.get(k))
        return None, f"MESH_* environment differs: {', '.join(changed)}"
    files = evidence.get("files")
    if not isinstance(files, dict) or "verify_all_summary.json" not in files:
        return None, "the evidence lists no verify_all_summary.json"
    for rel, digest in files.items():
        parts = Path(rel).parts
        if Path(rel).is_absolute() or ".." in parts or not parts:
            return None, f"the evidence lists a path outside its folder: {rel}"
        path = source / rel
        if not path.is_file() or path.is_symlink() or _sha256(path) != digest:
            return None, f"{rel} is missing or changed since that verify-all"
    package, why = _package_files(source, files)
    if why:
        return None, why
    unexpected = sorted(rel for rel in files
                        if rel not in RELEASE_REPORTS and rel not in package and rel not in NOT_COPIED
                        and not SCRATCH.fullmatch(rel) and not _package_bytecode(rel, package))
    if unexpected:
        for rel in unexpected[:50]:  # (all of them in the log, not only the reason's first five)
            print(f"[Mesh][Release] not a verification output: {rel}", file=sys.stderr)
        return None, (f"files that aren't verification outputs appeared during it ({len(unexpected)}): "
                      f"{', '.join(unexpected[:5])}")
    missing = sorted((RELEASE_REPORTS | package) - set(files))
    if missing:
        return None, f"reports a release check needs weren't produced by it: {', '.join(missing[:5])}"
    summary = json.loads((source / "verify_all_summary.json").read_text(encoding="utf-8"))
    summary_steps = summary.get("steps") if isinstance(summary, dict) else None
    if (not isinstance(summary, dict) or summary.get("ok") is not True or not isinstance(summary_steps, list)
            or [s.get("name") for s in summary_steps] != list(STEP_ORDER)
            or any(s.get("code") != 0 for s in summary_steps)):
        return None, "its verify_all_summary.json doesn't record the same passing run"
    return evidence, ""


def reuse(source: Path, release_dir: Path, *, repo_root: Path, deterministic: bool) -> dict[str, Any] | None:
    """The release check's verify-all outputs (``_run_verify_all``'s), from the run recorded in ``source`` if ``check``
    accepts it; else None, after recording why (the caller then runs verify-all itself)."""
    from mesh_cli.release_check_pipeline import _write_deterministic_verify_all_summary

    label = _label(source, repo_root)
    evidence, why = check(source, repo_root)
    copied: list[Path] = []
    made: list[Path] = []
    if evidence is not None:
        for rel, digest in sorted(evidence["files"].items()):
            if rel in NOT_COPIED:
                continue
            dest = release_dir / rel
            try:
                missing = [d for d in (dest.parent, *dest.parent.parents) if d.is_relative_to(release_dir)
                           and d != release_dir and not d.exists()]
                dest.parent.mkdir(parents=True, exist_ok=True)
                made.extend(missing)
                copied.append(dest)  # (before copying: a partial file is undone too)
                shutil.copyfile(source / rel, dest)
                intact = _sha256(dest) == digest  # (copied as recorded, or not at all)
            except OSError as exc:
                why = f"{rel} couldn't be copied ({exc})"
                break
            if not intact:
                why = f"{rel} changed while it was being copied"
                break
    if why or evidence is None:
        left = _undo(copied, made)
        reason = why if not left else f"{why}; and the attempt couldn't be undone ({'; '.join(left)})"
        write_json_atomic(release_dir / RECORD, {"reused": False, "source": label, "reason": reason},
                          indent=2, sort_keys=True, trailing_newline=True)
        if left:  # (fail rather than package a release/ with stray copies in it)
            raise OSError(f"verify-all reuse couldn't be undone in {release_dir.as_posix()}: {'; '.join(left)}")
        print(f"[Mesh][Release] verify-all not reused ({why}): running it here", file=sys.stderr)
        return None
    summary = json.loads((release_dir / "verify_all_summary.json").read_text(encoding="utf-8"))
    if deterministic:
        summary = _write_deterministic_verify_all_summary(release_dir, summary)
    commit = evidence["before"]["git_commit"]
    write_json_atomic(release_dir / RECORD, {
        "reused": True, "source": label, "commit": commit, "evidence_sha256": _sha256(source / EVIDENCE),
        "files_copied": len(copied), "not_copied": sorted(rel for rel in evidence["files"] if rel in NOT_COPIED),
        "untouched_not_copied": len(evidence.get("untouched") or []),
        "checked": ["exit code 0 and ok", "every step ran and passed", "full selection", "same commit before, after, now",
                    "clean tree before, after, now", "same tool version, Python and platform",
                    "only files the run produced (new or rewritten during it)",
                    "each one a verification output (named report, package manifest and its bytecode, verify-demo scratch)",
                    "every required report produced",
                    "same MESH_* environment (budget enforcement at least as strict)", "every file's SHA-256",
                    "summary agrees", "copies match the recorded hashes"],
    }, indent=2, sort_keys=True, trailing_newline=True)
    print(f"[Mesh][Release] verify-all reused from {label}: it passed on this clean commit ({commit[:12]}), "
          f"{len(copied)} reports copied and checked", file=sys.stderr)
    return {"verify_all_ok": summary.get("ok") is True, "verify_all_summary": (release_dir / "verify_all_summary.json").as_posix(),
            "verify_all_reused_from": label}


def _package_files(source: Path, files: dict[str, str]) -> tuple[frozenset[str], str]:
    """The player package's files as its own (hash-checked) manifest lists them, or the reason they can't be known."""
    manifest = f"{PACKAGE}manifest.json"
    if manifest not in files:
        return frozenset(), ""  # (then reported as a missing required report)
    try:
        listed = json.loads((source / manifest).read_text(encoding="utf-8")).get("included_files")
    except (OSError, ValueError, AttributeError) as exc:
        return frozenset(), f"{manifest} can't be read ({exc})"
    if not isinstance(listed, list) or not all(isinstance(rel, str) for rel in listed):
        return frozenset(), f"{manifest} lists no included_files"
    if any(Path(rel).is_absolute() or ".." in Path(rel).parts for rel in listed):
        return frozenset(), f"{manifest} lists a path outside the package"
    return frozenset(f"{PACKAGE}{rel}" for rel in listed), ""


def _package_bytecode(rel: str, package: frozenset[str]) -> bool:
    """Whether ``rel`` is Python's bytecode for a ``.py`` file the package's manifest lists."""
    match = _BYTECODE.fullmatch(rel[len(PACKAGE):]) if rel.startswith(PACKAGE) else None
    if match is None:
        return False
    return f"{PACKAGE}{match[1]}{match[2]}.py" in package


def _undo(copied: list[Path], made: list[Path]) -> list[str]:
    """Remove an abandoned reuse's copies (partial ones too) and the folders made for them; what couldn't be removed."""
    left: list[str] = []
    for path in copied:
        try:
            _remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            left.append(f"{path.name}: {exc}")
    for folder in sorted(set(made), key=lambda d: len(d.parts), reverse=True):
        try:
            folder.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            left.append(f"{folder.name}/: {exc}")
    return left


def _remove(path: Path) -> None:
    path.unlink()


def _part(evidence: dict[str, Any], key: str, kind: type) -> Any:
    """``evidence[key]`` if it is a ``kind``, else an empty one (a malformed record then fails the check that reads it)."""
    value = evidence.get(key)
    return value if isinstance(value, kind) else kind()


def _label(source: Path, repo_root: Path) -> str:
    """``source`` as the record names it: relative to the repository when inside it (no machine paths in a bundle)."""
    try:
        return source.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return source.name
