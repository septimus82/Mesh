from pathlib import Path

def _format_placeholder_id_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    text = f"{float(value):g}"
    text = text.replace("-", "m").replace(".", "p")
    return text


def _sanitize_entity_id_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "x"
    out: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"_"}:
            out.append(ch)
        elif ch in {".", "-", ":", "/", "\\", " "}:
            out.append("_")
        else:
            out.append("_")
    collapsed = "".join(out)
    while "__" in collapsed:
        collapsed = collapsed.replace("__", "_")
    return collapsed.strip("_") or "x"


def _dict_diffs(expected: dict, actual: dict, *, prefix: str = "") -> list[str]:
    diffs: list[str] = []
    for key in sorted(expected.keys()):
        path = f"{prefix}{key}"
        if key not in actual:
            diffs.append(f"missing {path}")
            continue
        exp = expected[key]
        act = actual[key]
        if isinstance(exp, dict) and isinstance(act, dict):
            diffs.extend(_dict_diffs(exp, act, prefix=f"{path}."))
            continue
        if exp != act:
            diffs.append(f"mismatch {path}: expected={exp!r} actual={act!r}")
    return diffs


def _single_line_error(text: str) -> str:
    return text.replace("\n", " ").replace("\r", "")
