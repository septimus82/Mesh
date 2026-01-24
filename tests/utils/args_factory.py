from typing import Any
from tests.utils.parser_defaults import get_default_args
import argparse

def update_namespace(ns: argparse.Namespace, **kwargs) -> argparse.Namespace:
    """Update a namespace with kwargs, ensuring keys exist."""
    for k, v in kwargs.items():
        if not hasattr(ns, k):
            raise AttributeError(f"Namespace has no attribute '{k}'")
        setattr(ns, k, v)
    return ns

def make_release_args(**overrides) -> argparse.Namespace:
    # release-check requires world_path
    defaults = get_default_args(["release-check"], ["dummy_world.json"])
    return update_namespace(defaults, **overrides)

def make_build_demo_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["build-demo"])
    return update_namespace(defaults, **overrides)

def make_check_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["check"])
    return update_namespace(defaults, **overrides)

def make_audit_args(**overrides) -> argparse.Namespace:
    # audit-content requires world_path
    defaults = get_default_args(["audit-content"], ["dummy_world.json"]) 
    return update_namespace(defaults, **overrides)

def make_plan_test_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["plan", "test"], ["dummy_plan.json"])
    return update_namespace(defaults, **overrides)

def make_apply_plan_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["apply-plan"], ["dummy_plan.json"])
    return update_namespace(defaults, **overrides)

def make_audit_trend_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["audit-trend"], ["dummy_locks"])
    return update_namespace(defaults, **overrides)

def make_doctor_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["doctor"])
    return update_namespace(defaults, **overrides)

def make_init_pack_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["init-content-pack"], ["dummy_pack"])
    return update_namespace(defaults, **overrides)

def make_recipes_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["recipes"])
    return update_namespace(defaults, **overrides)

def make_run_preset_args(**overrides) -> argparse.Namespace:
    defaults = get_default_args(["run-preset"], ["dummy_preset"])
    return update_namespace(defaults, **overrides)
