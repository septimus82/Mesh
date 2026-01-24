import unittest
import time
from engine.prefabs import PrefabManager

class TestPrefabResolutionPerfGuard(unittest.TestCase):
    def setUp(self):
        self.manager = PrefabManager()
        self.manager._loaded = True
        
        # Create a chain of 10 prefabs
        prefabs = {}
        for i in range(10):
            prefabs[f"P{i}"] = {
                "id": f"P{i}",
                "base": f"P{i+1}" if i < 9 else None,
                "entity": {f"attr_{i}": i, "common": "value"}
            }
        self.manager._prefabs = prefabs

    def test_resolution_performance(self):
        # Resolve the head of the chain 1000 times
        # This tests caching effectiveness
        
        start_time = time.perf_counter()
        
        for _ in range(1000):
            # Resolve P0 (depth 10)
            # First time: computes and caches
            # Subsequent times: hits cache
            resolved = self.manager.get_prefab("P0")
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved["entity"]["attr_0"], 0)
            self.assertEqual(resolved["entity"]["attr_9"], 9)
            
            # Also test resolve() with entity override
            entity = {"prefab_id": "P0", "x": 100}
            final = self.manager.resolve(entity)
            self.assertEqual(final["x"], 100)

        end_time = time.perf_counter()
        duration = end_time - start_time
        
        # Threshold: 0.5 seconds is very generous for 1000 iterations.
        # Without caching, 1000 * 10 merges might take a bit, but still fast.
        # With caching, it should be instant.
        print(f"\n[Perf] 1000 resolutions took {duration:.4f}s")
        self.assertLess(duration, 0.5, "Prefab resolution is too slow!")

if __name__ == "__main__":
    unittest.main()
