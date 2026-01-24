from __future__ import annotations


def generate_docs(root_dir: str, target_dir: str) -> None:
    from engine.tooling.generate_docs import generate_docs as _generate  # noqa: PLC0415

    # Runtime wrapper keeps the historic (root_dir, target_dir) signature used by the dev console.
    # The underlying generator currently only needs the output directory.
    _generate(target_dir)
