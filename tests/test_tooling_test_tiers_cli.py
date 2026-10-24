from tooling import test_tiers


def test_test_tiers_defines_expected_tiers():
    assert set(test_tiers.TIERS.keys()) == {"tier0", "tier1", "tier2", "gpu"}
    assert test_tiers.TIERS["gpu"].paths and dict(test_tiers.TIERS["gpu"].env) == {"MESH_GL_SMOKE": "1"}
    assert test_tiers.TIERS["tier0"].pytest_mark == "fast"
