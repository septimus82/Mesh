from __future__ import annotations

from engine.ui import compute_objective_tracker_lines


def _get_flag_from(flags: dict[str, bool]):
    def _get_flag(name: str, default: bool = False) -> bool:
        return bool(flags.get(name, default))

    return _get_flag


def test_objective_tracker_lines_empty_when_no_objectives() -> None:
    lines = compute_objective_tracker_lines(_get_flag_from({}))
    assert lines == []


def test_objective_tracker_lines_enter_cellar_when_started() -> None:
    lines = compute_objective_tracker_lines(
        _get_flag_from(
            {
                "demo.objective_started": True,
                "demo.reached_cellar": False,
            }
        )
    )
    assert lines == ["Objective: Enter the cellar"]


def test_objective_tracker_lines_prefers_find_cellar_when_interior_reached() -> None:
    lines = compute_objective_tracker_lines(
        _get_flag_from(
            {
                "demo.objective_started": True,
                "demo.reached_interior": True,
                "demo.reached_cellar": False,
            }
        )
    )
    assert lines == ["Objective: Find the cellar"]


def test_objective_tracker_lines_optional_second() -> None:
    lines = compute_objective_tracker_lines(
        _get_flag_from(
            {
                "demo.objective_started": True,
                "demo.reached_cellar": False,
                "demo.objective_upper_started": True,
                "demo.reached_upper_hall": False,
            }
        )
    )
    assert lines == ["Objective: Enter the cellar", "Optional: Visit the upper hall"]


def test_objective_tracker_lines_optional_pull_lever_after_reaching_upper_hall() -> None:
    lines = compute_objective_tracker_lines(
        _get_flag_from(
            {
                "demo.objective_upper_started": True,
                "demo.reached_upper_hall": True,
                "demo.upper_hall_lever_pulled": False,
            }
        )
    )
    assert lines == ["Optional: Pull the lever"]


def test_objective_tracker_lines_optional_enter_vault_after_pulling_lever() -> None:
    lines = compute_objective_tracker_lines(
        _get_flag_from(
            {
                "demo.objective_upper_started": True,
                "demo.reached_upper_hall": True,
                "demo.upper_hall_lever_pulled": True,
                "demo.reached_upper_hall_vault": False,
            }
        )
    )
    assert lines == ["Optional: Enter the vault"]


def test_objective_tracker_lines_hide_when_demo_complete_visible() -> None:
    lines = compute_objective_tracker_lines(
        _get_flag_from(
            {
                "demo.objective_started": True,
                "demo.reached_cellar": False,
            }
        ),
        demo_complete_visible=True,
    )
    assert lines == []


def test_objective_tracker_lines_hide_when_cellar_reached() -> None:
    lines = compute_objective_tracker_lines(
        _get_flag_from(
            {
                "demo.objective_started": True,
                "demo.reached_cellar": True,
                "demo.objective_upper_started": True,
                "demo.reached_upper_hall": False,
            }
        )
    )
    assert lines == []
