from tooling import test_tiers


def test_test_tiers_defines_expected_tiers():
    assert set(test_tiers.TIERS.keys()) == {"tier0", "tier1", "tier2"}
    assert test_tiers.TIERS["tier0"].pytest_mark == "fast"
