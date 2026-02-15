from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.tooling import replay_script


@dataclass(frozen=True, slots=True)
class ReplayExpectation:
    flags_has: tuple[str, ...] = ()
    flags_lacks: tuple[str, ...] = ()
    gold_at_least: int | None = None
    last_zone_id: str | None = None


def _coerce_flag_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    flags: list[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            flags.append(s)
    return tuple(flags)


def _parse_expect(expect: Any) -> tuple[ReplayExpectation | None, list[str]]:
    if expect is None:
        return None, []
    if not isinstance(expect, dict):
        return None, ["expect must be an object"]

    errors: list[str] = []

    if "flags_has" in expect and expect.get("flags_has") is not None and not isinstance(expect.get("flags_has"), list):
        errors.append("expect.flags_has must be a list")
    if "flags_lacks" in expect and expect.get("flags_lacks") is not None and not isinstance(expect.get("flags_lacks"), list):
        errors.append("expect.flags_lacks must be a list")

    flags_has = _coerce_flag_list(expect.get("flags_has"))
    flags_lacks = _coerce_flag_list(expect.get("flags_lacks"))

    gold_at_least: int | None = None
    gold_raw = expect.get("gold_at_least")
    if "gold_at_least" in expect and gold_raw is not None:
        try:
            gold_at_least = int(gold_raw)
        except (TypeError, ValueError):
            errors.append("expect.gold_at_least must be an int")

    last_zone_id: str | None = None
    if "last_zone_id" in expect and expect.get("last_zone_id") is not None:
        last_zone_id = str(expect.get("last_zone_id")).strip() or None

    return (
        ReplayExpectation(
            flags_has=flags_has,
            flags_lacks=flags_lacks,
            gold_at_least=gold_at_least,
            last_zone_id=last_zone_id,
        ),
        errors,
    )


def _check_expectations(final_state: dict[str, Any], expect: ReplayExpectation) -> list[str]:
    errors: list[str] = []

    flags_count = final_state.get("flags_count", 0)
    flags_sample = final_state.get("flags_sample", [])
    if not isinstance(flags_sample, list):
        flags_sample = []

    flags_true = [str(x) for x in flags_sample if str(x).strip()]
    flags_set = set(flags_true)

    # Best-effort guard: if the dump's sample is truncated, expectations may be unreliable.
    try:
        flags_count_int = int(flags_count)
    except (TypeError, ValueError):
        flags_count_int = 0

    if flags_count_int > len(flags_true):
        errors.append(
            "flags_sample_limit too low to evaluate expectations (flags_sample is truncated)"
        )
        return errors

    missing = sorted(set(expect.flags_has) - flags_set)
    for flag in missing:
        errors.append(f"Missing expected flag: {flag}")

    present = sorted(set(expect.flags_lacks) & flags_set)
    for flag in present:
        errors.append(f"Unexpected flag present: {flag}")

    if expect.gold_at_least is not None:
        gold = final_state.get("gold", 0)
        try:
            gold_int = int(gold)
        except (TypeError, ValueError):
            gold_int = 0
        if gold_int < expect.gold_at_least:
            errors.append(f"Gold {gold_int} is less than expected minimum {expect.gold_at_least}")

    if expect.last_zone_id is not None:
        last_zone = final_state.get("last_zone_id", None)
        last_zone_str = str(last_zone).strip() if last_zone is not None else None
        if last_zone_str != expect.last_zone_id:
            errors.append(
                f"last_zone_id '{last_zone_str}' does not match expected '{expect.last_zone_id}'"
            )

    return errors


def _collect_true_flags(window: Any) -> set[str]:
    gsc = getattr(window, "game_state_controller", None)
    state = getattr(gsc, "state", None) if gsc is not None else None
    flags = getattr(state, "flags", None) if state is not None else None
    if not isinstance(flags, dict):
        return set()
    return {str(k) for k, v in flags.items() if bool(v) and str(k).strip()}


def _check_expectations_against_window(
    *,
    window: Any,
    final_state: dict[str, Any],
    expect: ReplayExpectation,
) -> list[str]:
    errors: list[str] = []

    flags_true = _collect_true_flags(window)
    missing = sorted(set(expect.flags_has) - flags_true)
    for flag in missing:
        errors.append(f"Missing expected flag: {flag}")

    present = sorted(set(expect.flags_lacks) & flags_true)
    for flag in present:
        errors.append(f"Unexpected flag present: {flag}")

    if expect.gold_at_least is not None:
        gold = final_state.get("gold", 0)
        try:
            gold_int = int(gold)
        except (TypeError, ValueError):
            gold_int = 0
        if gold_int < expect.gold_at_least:
            errors.append(f"Gold {gold_int} is less than expected minimum {expect.gold_at_least}")

    if expect.last_zone_id is not None:
        last_zone = final_state.get("last_zone_id", None)
        last_zone_str = str(last_zone).strip() if last_zone is not None else None
        if last_zone_str != expect.last_zone_id:
            errors.append(
                f"last_zone_id '{last_zone_str}' does not match expected '{expect.last_zone_id}'"
            )

    return errors


def _single_line_error(message: str) -> str:
    msg = str(message).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    # Collapse multiple spaces to keep output stable and readable.
    while "  " in msg:
        msg = msg.replace("  ", " ")
    return msg


def _is_replay_script_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name
    if not name.endswith(".json"):
        return False
    if name.endswith(".hash.json"):
        return False
    if name == "suite.json":
        return False
    if name.endswith("_golden.json"):
        return False
    return True


def _first_expectation_error(
    *,
    window: Any,
    state: dict[str, Any],
    expect: ReplayExpectation,
) -> str:
    flags_true = _collect_true_flags(window)

    missing = sorted(set(expect.flags_has) - flags_true)
    if missing:
        return f"missing flag: {missing[0]}"

    present = sorted(set(expect.flags_lacks) & flags_true)
    if present:
        return f"unexpected flag: {present[0]}"

    if expect.gold_at_least is not None:
        gold = state.get("gold", 0)
        try:
            gold_int = int(gold)
        except (TypeError, ValueError):
            gold_int = 0
        if gold_int < expect.gold_at_least:
            return f"gold too low: expected >= {expect.gold_at_least}, got {gold_int}"

    if expect.last_zone_id is not None:
        last_zone = state.get("last_zone_id", None)
        last_zone_str = str(last_zone).strip() if last_zone is not None else "None"
        if last_zone_str != expect.last_zone_id:
            return f"last_zone_id mismatch: expected {expect.last_zone_id}, got {last_zone_str}"

    return ""


def run_replay_suite(folder: str, *, window_factory=None) -> dict[str, Any]:
    """Run all `*.json` replay scripts in `folder` deterministically.

        Returns a summary dict:
            - total, passed, failed
            - results: list[{script, ok, error, state}]

    Ordering is stable: sorted by filename.
    """

    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        raise ValueError(f"Replay suite folder not found: {folder}")

    scripts = sorted([p for p in folder_path.glob("*.json") if _is_replay_script_file(p)], key=lambda p: p.name)

    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    for path in scripts:
        script_name = path.name
        ok = True
        error = ""
        state: dict[str, Any] = {}

        try:
            script = replay_script.load_replay_script(path)
            # Campaign chain scripts live beside replay scripts for the newer
            # suite runner and should be ignored by this legacy verifier.
            if isinstance(script, dict) and "steps" not in script:
                if "campaign_id" in script and "scenes" in script:
                    continue
            expect_obj = script.get("expect") if isinstance(script, dict) else None
            expect, parse_errors = _parse_expect(expect_obj)
            if parse_errors:
                ok = False
                error = _single_line_error(parse_errors[0])

            window, final_state = replay_script.run_replay_script_with_window(
                script,
                window_factory=window_factory,
                script_path=path,
            )
            state = dict(final_state) if isinstance(final_state, dict) else {}

            if ok and expect is not None:
                exp_error = _first_expectation_error(window=window, state=state, expect=expect)
                if exp_error:
                    ok = False
                    error = _single_line_error(exp_error)

        except Exception as exc:  # noqa: BLE001
            ok = False
            if isinstance(exc, ValueError):
                error = _single_line_error(str(exc))
            else:
                error = _single_line_error(f"{type(exc).__name__}: {exc}")

        if ok:
            passed += 1
        else:
            failed += 1

        results.append(
            {
                "script": script_name,
                "ok": bool(ok),
                "error": str(error),
                "state": state,
            }
        )

    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
