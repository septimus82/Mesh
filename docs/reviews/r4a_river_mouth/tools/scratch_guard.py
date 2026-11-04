r"""The evidence scripts' output guard (#463 review): every path they write must resolve inside the session's
scratchpad, as a Windows path. A POSIX-looking path such as "/c/Users/..." resolves to "D:\c\Users\..." on Windows,
and this refuses it before anything is written."""
from pathlib import Path

SCRATCH = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad")


def inside_scratch(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(SCRATCH.resolve()):
        raise SystemExit(f"refusing to write outside the scratchpad: {path} -> {resolved}")
    return resolved


if __name__ == "__main__":
    assert inside_scratch(SCRATCH / "river4" / "x") == (SCRATCH / "river4" / "x").resolve()
    for bad in (Path("/c/Users/slebb/AppData/Local/Temp/claude/x"), Path(r"D:\Games\Mesh\x"), SCRATCH / ".." / "x"):
        try:
            inside_scratch(bad)
        except SystemExit:
            continue
        raise AssertionError(f"not refused: {bad}")
    print("guard ok")
