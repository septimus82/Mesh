from __future__ import annotations

from pathlib import Path

from engine.tooling_runtime.pack_manifest import PackDependencySpec, PackManifest, resolve_pack_order


def _manifest(pack_id: str, deps: list[PackDependencySpec] | None = None, version: str = "1.0.0") -> PackManifest:
    return PackManifest(
        id=pack_id,
        version=version,
        title=None,
        description=None,
        engine_compat=None,
        dependencies=deps or [],
        root=Path(pack_id),
        path=f"{pack_id}/pack.json",
        implicit=False,
    )


def test_pack_dependency_resolution_order() -> None:
    base = _manifest("base")
    alpha = _manifest("alpha", deps=[PackDependencySpec(id="base")])
    beta = _manifest("beta", deps=[PackDependencySpec(id="alpha")])
    order, errors = resolve_pack_order([beta, alpha, base])
    assert not errors
    assert [m.id for m in order] == ["base", "alpha", "beta"]


def test_pack_dependency_resolution_missing_and_cycle() -> None:
    alpha = _manifest("alpha", deps=[PackDependencySpec(id="missing")])
    order, errors = resolve_pack_order([alpha])
    assert errors
    assert any("missing dependency" in err for err in errors)
    assert order == [alpha]

    a = _manifest("a", deps=[PackDependencySpec(id="b")])
    b = _manifest("b", deps=[PackDependencySpec(id="a")])
    order2, errors2 = resolve_pack_order([a, b])
    assert errors2
    assert any("cycle" in err for err in errors2)
    assert {m.id for m in order2} == {"a", "b"}
