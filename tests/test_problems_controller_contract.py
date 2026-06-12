from engine.editor.editor_problems_controller import ProblemsController
from engine.editor.scene_lint_model import SceneLintIssue


class TestProblemsControllerContract:
    def test_initial_state(self) -> None:
        ctrl = ProblemsController()
        assert ctrl.issues == []
        assert ctrl.query == ""
        assert ctrl.selected_index == 0

    def test_set_issues_deterministic_sort(self) -> None:
        ctrl = ProblemsController()
        # Create issues in random order
        i1 = SceneLintIssue("id1", "WARN", "B message", "e1", "s1", "warning", "safe", None, False)
        i2 = SceneLintIssue("id2", "ERR", "A message", "e2", "s1", "error", "risky", None, False)
        i3 = SceneLintIssue("id3", "INFO", "C message", "e3", "s1", "info", "safe", None, False)

        ctrl.set_issues([i1, i3, i2])

        # Expect: Error, Warning, Info
        assert len(ctrl.issues) == 3
        assert ctrl.issues[0].severity == "error"
        assert ctrl.issues[1].severity == "warning"
        assert ctrl.issues[2].severity == "info"

    def test_sorting_tie_breakers(self) -> None:
        ctrl = ProblemsController()
        # Same severity
        # Path (scene_id) asc
        i1 = SceneLintIssue("id1", "K", "M", "e1", "sc_B", "error", "safe", None, False)
        i2 = SceneLintIssue("id2", "K", "M", "e1", "sc_A", "error", "safe", None, False)

        ctrl.set_issues([i1, i2])
        assert ctrl.issues[0].scene_id == "sc_A"
        assert ctrl.issues[1].scene_id == "sc_B"

        # Same path, same line (heuristic 0), code (kind) asc
        i3 = SceneLintIssue("id3", "B_KIND", "M", "e1", "sc_A", "error", "safe", None, False)
        i4 = SceneLintIssue("id4", "A_KIND", "M", "e1", "sc_A", "error", "safe", None, False)

        ctrl.set_issues([i3, i4])
        assert ctrl.issues[0].kind == "A_KIND"
        assert ctrl.issues[1].kind == "B_KIND"

    def test_set_query_filtering(self) -> None:
        ctrl = ProblemsController()
        i1 = SceneLintIssue("id1", "K", "FindMe", "e1", "s1", "error", "safe", None, False)
        i2 = SceneLintIssue("id2", "K", "Hidden", "e1", "s1", "error", "safe", None, False)
        ctrl.set_issues([i1, i2])

        ctrl.set_query("findme")
        filtered = ctrl.get_filtered_issues()
        assert len(filtered) == 1
        assert filtered[0].message == "FindMe"

        # Reset selection on query change
        ctrl.selected_index = 1
        ctrl.set_query("Hidden")
        assert ctrl.selected_index == 0
        assert len(ctrl.get_filtered_issues()) == 1

    def test_move_selection(self) -> None:
        ctrl = ProblemsController()
        i1 = SceneLintIssue("id1", "K", "1", "e1", "s1", "error", "safe", None, False)
        i2 = SceneLintIssue("id2", "K", "2", "e1", "s1", "error", "safe", None, False)
        i3 = SceneLintIssue("id3", "K", "3", "e1", "s1", "error", "safe", None, False)
        ctrl.set_issues([i1, i2, i3])

        ctrl.move_selection(1)
        assert ctrl.selected_index == 1
        ctrl.move_selection(1)
        assert ctrl.selected_index == 2
        ctrl.move_selection(1) # Clamp
        assert ctrl.selected_index == 2
        ctrl.move_selection(-5) # Clamp
        assert ctrl.selected_index == 0

    def test_provider_payload_autopan(self) -> None:
        ctrl = ProblemsController()
        # Create many issues
        issues = [SceneLintIssue(f"id{k}", "K", f"Msg{k}", "e", "s", "error", "safe", None, False) for k in range(20)]
        ctrl.set_issues(issues)

        row_h = 10
        view_h = 50 # 5 rows visible

        # Select last item
        last_idx = 19
        ctrl.set_selected_index(last_idx)

        payload = ctrl.get_provider_payload(view_h, row_h, overscan=0)

        # Scroll should have adjusted to show last item
        # Visible rows are [scroll_y // row_h : ...]
        # Max scroll index = 20 - 5 = 15. So items 15,16,17,18,19 are visible.
        # scroll_y should be 15 * 10 = 150

        assert payload["selected_index"] == 19
        assert payload["scroll_y"] == 150
        assert payload["start_index"] == 15
        assert len(payload["rows"]) == 5
        assert payload["rows"][-1].issue_id == "id19"
