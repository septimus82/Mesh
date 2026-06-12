import unittest

from engine.migrations import _MIGRATORS, migrate_payload, register_migrator


class TestMigrationsFramework(unittest.TestCase):
    def setUp(self):
        # Clear migrators for test isolation (careful with global state)
        self._original_migrators = _MIGRATORS.copy()
        _MIGRATORS.clear()

    def tearDown(self):
        _MIGRATORS.clear()
        _MIGRATORS.update(self._original_migrators)

    def test_register_and_run(self):
        def v1_to_v2(data):
            data["v"] = 2
            data["new_field"] = "added"
            return data

        register_migrator("test_type", 1, 2, v1_to_v2)

        payload = {"schema_version": 1, "v": 1}
        migrated = migrate_payload("test_type", payload)

        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["v"], 2)
        self.assertEqual(migrated["new_field"], "added")

    def test_chain_migrations(self):
        register_migrator("chain", 1, 2, lambda d: {**d, "step1": True})
        register_migrator("chain", 2, 3, lambda d: {**d, "step2": True})

        payload = {"schema_version": 1}
        migrated = migrate_payload("chain", payload)

        self.assertEqual(migrated["schema_version"], 3)
        self.assertTrue(migrated.get("step1"))
        self.assertTrue(migrated.get("step2"))

    def test_no_migration_needed(self):
        register_migrator("noop", 1, 2, lambda d: d)

        payload = {"schema_version": 2}
        migrated = migrate_payload("noop", payload)

        self.assertEqual(migrated["schema_version"], 2)

if __name__ == "__main__":
    unittest.main()
