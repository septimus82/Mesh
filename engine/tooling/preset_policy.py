import os
import re
from typing import Any


def validate_preset_python_step(args: list[str]) -> None:
    if not args:
        raise ValueError("Python step args cannot be empty")

    # 1. Check start allowlist
    is_pytest = len(args) >= 2 and args[0] == "-m" and args[1] == "pytest"
    is_mesh_cli = len(args) >= 1 and args[0] == "mesh_cli.py"

    if not (is_pytest or is_mesh_cli):
        raise ValueError("Python step must start with ['-m', 'pytest', ...] or ['mesh_cli.py', ...]")

    # 2. Check disallowed flags
    if "-c" in args:
        raise ValueError("Python step cannot use '-c'")

    # 3. Check path safety
    for arg in args:
        if ".." in arg:
            raise ValueError(f"Arg '{arg}' contains disallowed '..'")
        if os.path.isabs(arg):
            raise ValueError(f"Arg '{arg}' is an absolute path")
        if "\\" in arg:
            raise ValueError(f"Arg '{arg}' contains disallowed backslash")

    # 4. Check recursion (no run-preset)
    if is_mesh_cli and "run-preset" in args:
        raise ValueError("Preset steps may not invoke run-preset (no recursion).")

    # 5. Check pytest flags
    if is_pytest:
        banned_flags = {
            "--lf", "--last-failed",
            "--ff", "--failed-first",
            "--co", "--collect-only",
            "--disable-warnings",
            "--tb=no", "--tb=none"
        }

        for arg in args:
            if arg in banned_flags:
                raise ValueError(f"Pytest step cannot use '{arg}'")
            if arg.startswith("-k"):
                raise ValueError("Pytest step cannot use '-k'")

            # Check targets (positional args that are not flags)
            if not arg.startswith("-"):
                # Skip the initial "-m" and "pytest"
                if arg in ["-m", "pytest"]:
                    continue

                # Must be in tests/
                if not arg.startswith("tests/"):
                    raise ValueError(f"Pytest target '{arg}' must be in 'tests/'")


def get_preset_policy_snapshot() -> dict:
    """Return a deterministic snapshot of the current preset policy."""
    return {
        "version": 1,
        "env": {
            "key_regex": "^[A-Z][A-Z0-9_]{0,63}$",
            "max_key_len": 64,
            "max_value_len": 128,
            "banned_substrings": [".."],
            "banned_chars": ["\\n", "\\r", "\\0", "/", "\\"],
        },
        "python": {
            "allowed_starts": [["-m", "pytest"], ["mesh_cli.py"]],
            "disallowed_flags": ["-c"],
            "disallow_run_preset": True,
            "disallow_backslashes": True,
            "disallow_absolute_paths": True,
            "disallow_parent_dir": True
        },
        "pytest": {
            "disallowed_flags": [
                "--lf", "--last-failed",
                "--ff", "--failed-first",
                "--co", "--collect-only",
                "--disable-warnings",
                "--tb=no", "--tb=none",
                "-k"
            ],
            "allowed_targets_root": "tests/"
        }
    }


def validate_preset_env(env: Any) -> list[dict]:
    """Validate preset env block and return structured issue dicts."""
    issues: list[dict] = []

    if env is None:
        return issues

    if not isinstance(env, dict):
        return [
            {
                "id": "preset_env_invalid",
                "step_index": None,
                "message": "Preset env must be a dict[str, str]",
                "detail": {"type": type(env).__name__},
            }
        ]

    key_re = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

    def _add(*, key: Any, value: Any, message: str) -> None:
        issues.append(
            {
                "id": "preset_env_invalid",
                "step_index": None,
                "message": message,
                "detail": {"key": str(key), "value": str(value)},
            }
        )

    for key, value in env.items():
        if not isinstance(key, str):
            _add(key=key, value=value, message="Env key must be a string")
            continue

        if not key_re.fullmatch(key):
            _add(key=key, value=value, message="Env key must match ^[A-Z][A-Z0-9_]{0,63}$")

        if not isinstance(value, str):
            _add(key=key, value=value, message="Env value must be a string")
            continue

        if len(value) > 128:
            _add(key=key, value=value, message="Env value must be <= 128 chars")

        if "\n" in value or "\r" in value or "\x00" in value:
            _add(key=key, value=value, message="Env value may not contain newline, carriage return, or NUL")

        if "/" in value or "\\" in value:
            _add(key=key, value=value, message="Env value may not contain path separators")

        if ".." in value:
            _add(key=key, value=value, message="Env value may not contain '..'")

    issues.sort(key=lambda i: (str(i.get("detail", {}).get("key", "")), str(i.get("message", ""))))
    return issues
