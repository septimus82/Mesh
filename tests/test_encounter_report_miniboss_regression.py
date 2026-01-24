import unittest
from types import SimpleNamespace


class _StubPrefabManager:
    def __init__(self, prefabs):
        self._prefabs = dict(prefabs)

    def get_prefab(self, prefab_id):
        return self._prefabs.get(prefab_id)


class TestEncounterReportMiniBossRegression(unittest.TestCase):
    def test_mini_boss_counted_separately_not_elite_or_boss(self):
        from engine.encounter_report import _extract_stats

        boss_prefab = {"encounter_cost": 1, "tags": ["enemy", "boss", "mini_boss"], "is_boss": True, "is_mini_boss": True}
        mini_boss_prefab = {"encounter_cost": 1, "tags": ["enemy", "mini_boss"]}
        elite_prefab = {"encounter_cost": 1, "tags": ["enemy", "elite"]}
        normal_prefab = {"encounter_cost": 1, "tags": ["enemy"]}

        pm = _StubPrefabManager(
            {
                "boss_a": boss_prefab,
                "mini_a": mini_boss_prefab,
                "elite_a": elite_prefab,
                "normal_a": normal_prefab,
            }
        )

        controller = SimpleNamespace(
            window=SimpleNamespace(engine_config=SimpleNamespace(encounter_budget_profiles={"normal": 1.0}))
        )

        scene_data = {
            "settings": {"encounter_budget": 999},
            "entities": [
                {"prefab_id": "boss_a", "encounter_group": "g"},
                {"prefab_id": "mini_a", "encounter_group": "g"},
                {"prefab_id": "elite_a", "encounter_group": "g"},
                {"prefab_id": "normal_a", "encounter_group": "g"},
            ],
        }

        # Ensure the report uses our prefab manager.
        import engine.encounter_report as encounter_report

        original_pm = encounter_report.get_prefab_manager
        try:
            encounter_report.get_prefab_manager = lambda: pm  # noqa: E731
            report = _extract_stats(scene_data, "scenes/x.json", "normal", controller)
        finally:
            encounter_report.get_prefab_manager = original_pm

        self.assertEqual(report.spawn_count, 4)
        self.assertEqual(report.elite_count, 1)
        self.assertEqual(report.mini_boss_count, 1)

        self.assertEqual(len(report.groups), 1)
        group = report.groups[0]
        self.assertEqual(group.spawn_count, 4)
        self.assertEqual(group.elite_count, 1)
        self.assertEqual(group.mini_boss_count, 1)

