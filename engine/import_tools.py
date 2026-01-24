from __future__ import annotations

import sys


def repair_package_submodule_attr(pkg_name: str, submod_name: str) -> None:
    """Repair stale package attribute pointers after sys.modules manipulation.

    Ensures that if both the package and submodule are already loaded,
    `getattr(pkg, submod_name)` points at the same object as
    `sys.modules[f"{pkg}.{sub}"]`.

    Safety properties:
    - Does not import anything unless it is already present in sys.modules.
    - If either the package or submodule are not loaded, it is a no-op.
    - Optionally repairs parent package attributes when pkg_name is dotted.
    """

    if not isinstance(pkg_name, str) or not pkg_name.strip():
        return
    if not isinstance(submod_name, str) or not submod_name.strip():
        return

    pkg_name = pkg_name.strip()
    submod_name = submod_name.strip()

    full = f"{pkg_name}.{submod_name}"
    submod = sys.modules.get(full)
    if submod is None:
        return

    # Repair parents first so dotted packages have consistent attribute chains.
    if "." in pkg_name:
        parts = pkg_name.split(".")
        for i in range(1, len(parts)):
            parent_name = ".".join(parts[:i])
            child_name = parts[i]
            parent_mod = sys.modules.get(parent_name)
            child_mod = sys.modules.get(".".join(parts[: i + 1]))
            if parent_mod is None or child_mod is None:
                return
            try:
                setattr(parent_mod, child_name, child_mod)
            except Exception:
                return

    pkg_mod = sys.modules.get(pkg_name)
    if pkg_mod is None:
        return

    try:
        setattr(pkg_mod, submod_name, submod)
    except Exception:
        return
