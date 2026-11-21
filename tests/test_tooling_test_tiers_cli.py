from tooling import test_tiers


def test_test_tiers_defines_expected_tiers():
    assert set(test_tiers.TIERS.keys()) == {"tier0", "tier1", "tier2", "extended", "gpu", "acceptance"}
    # GL tests are found by capability (the `gl` marker), never by file name (#422 H6).
    assert test_tiers.TIERS["gpu"].pytest_mark == "gl" and not test_tiers.TIERS["gpu"].paths
    assert dict(test_tiers.TIERS["gpu"].env) == {"MESH_GL_SMOKE": "1", "MESH_REQUIRE_GL": "1"}
    assert test_tiers.TIERS["extended"].pytest_mark == "(slow or e2e) and not gl"
    assert test_tiers.TIERS["acceptance"].pytest_mark == "gl" and test_tiers.TIERS["acceptance"].paths
    assert test_tiers.TIERS["tier0"].pytest_mark == "fast"
