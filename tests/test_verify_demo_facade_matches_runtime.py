import engine.tooling.verify_demo as facade
import engine.tooling_runtime.verify_demo as runtime


def test_verify_demo_facade_reexports_runtime_objects_by_identity() -> None:
    assert hasattr(facade, "subprocess")
    assert hasattr(runtime, "subprocess")

    assert facade.build_verify_demo_pytest_cmd is runtime.build_verify_demo_pytest_cmd
    assert facade.validate_pytest_passthrough_args is runtime.validate_pytest_passthrough_args
    assert facade.run_verify_demo is runtime.run_verify_demo
    assert facade.iter_missing_paths is runtime.iter_missing_paths
    assert facade.subprocess is runtime.subprocess

    # Ensure monkeypatching engine.tooling.verify_demo.subprocess.run targets the real subprocess binding.
    assert facade.subprocess.run is runtime.subprocess.run
