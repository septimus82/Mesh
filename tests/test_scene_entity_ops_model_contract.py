from engine.scene_entity_ops_model import (
    EntityOp,
    FieldPatch,
    MutateOp,
    build_drain_plan,
    normalize_ops,
    stable_entity_order,
)


def test_stable_entity_order_primary_first() -> None:
    ids = ["b", "a", "c"]
    assert stable_entity_order(ids, "a") == ["a", "b", "c"]


def test_normalize_ops_deterministic() -> None:
    ops = [
        EntityOp("mutate", MutateOp("b", (FieldPatch(("x",), "set", 1),)), seq=2),
        EntityOp("spawn", object(), seq=1),
        EntityOp("despawn", object(), seq=0),
    ]
    ordered = normalize_ops(ops)
    assert [op.kind for op in ordered] == ["despawn", "spawn", "mutate"]
    plan = build_drain_plan(ops)
    assert [op.kind for op in plan.ordered_ops] == ["despawn", "spawn", "mutate"]
