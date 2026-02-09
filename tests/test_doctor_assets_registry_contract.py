"""
Contract tests for the doctor assets registry.
"""
from engine.tooling_runtime import doctor_assets_registry as registry


def test_registry_is_deterministic_and_resolves() -> None:
    specs = registry.DEFAULT_DOCTOR_CHECKS
    assert isinstance(specs, tuple)
    ids = [spec.id for spec in specs]
    assert len(ids) == len(set(ids))
    ordered = tuple(sorted(specs, key=lambda s: (s.order, s.id)))
    assert specs == ordered

    resolved = registry.build_doctor_checks()
    assert isinstance(resolved, tuple)
    for spec, pred, runner in resolved:
        assert spec.id in ids
        assert callable(pred)
        assert callable(runner)
        assert pred.__name__ != "<lambda>"
        assert runner.__name__ != "<lambda>"
        assert isinstance(spec.enabled_predicate_name, str)
        assert isinstance(spec.run_check_name, str)
