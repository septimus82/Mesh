from engine.behaviours.utils import (
    BEHAVIOUR_META_EXPLICIT,
    ZONE_TARGET_HITBOX,
    ZONE_TARGET_TRIGGER,
    build_behaviour_config_map,
    describe_zone_behaviour,
    ensure_behaviour_config_root,
    format_behaviour_config_summary,
    infer_zone_target_from_behaviour,
    is_hitbox_behaviour,
    is_trigger_behaviour,
    normalize_behaviour_entry,
    parse_flag_list,
    prepare_behaviour_configs,
    strip_behaviour_metadata,
)


class MockBehaviour:
    def __init__(self, type_name):
        self.mesh_behaviour_type = type_name

class MockClassBehaviour:
    pass

def test_is_trigger_behaviour():
    assert is_trigger_behaviour(MockBehaviour("trigger_zone"))
    assert is_trigger_behaviour(MockBehaviour("triggerzone"))
    assert not is_trigger_behaviour(MockBehaviour("Other"))

    b = MockClassBehaviour()
    b.__class__.__name__ = "TriggerZoneBehaviour"
    assert is_trigger_behaviour(b)

def test_is_hitbox_behaviour():
    assert is_hitbox_behaviour(MockBehaviour("Hitbox"))
    assert is_hitbox_behaviour(MockBehaviour("hitbox"))
    assert not is_hitbox_behaviour(MockBehaviour("Other"))

    b = MockClassBehaviour()
    b.__class__.__name__ = "Hitbox"
    assert is_hitbox_behaviour(b)

def test_infer_zone_target_from_behaviour():
    assert infer_zone_target_from_behaviour(None) == ZONE_TARGET_TRIGGER
    assert infer_zone_target_from_behaviour(MockBehaviour("Hitbox")) == ZONE_TARGET_HITBOX
    assert infer_zone_target_from_behaviour(MockBehaviour("TriggerZoneBehaviour")) == ZONE_TARGET_TRIGGER

def test_describe_zone_behaviour():
    assert describe_zone_behaviour(None) == "Zone"
    assert describe_zone_behaviour(MockBehaviour("MyBehaviour")) == "My"
    assert describe_zone_behaviour(MockBehaviour("some_thing")) == "some thing"

    b = MockClassBehaviour()
    b.__class__.__name__ = "TestBehaviour"
    assert describe_zone_behaviour(b) == "Test"

def test_parse_flag_list():
    assert parse_flag_list("a, b, c") == ["a", "b", "c"]
    assert parse_flag_list("a,,b") == ["a", "b"]
    assert parse_flag_list("") == []
    assert parse_flag_list(None) == []

def test_normalize_behaviour_entry_str():
    assert normalize_behaviour_entry("test_behaviour") == {"type": "test_behaviour", "params": {}}
    assert normalize_behaviour_entry("  test_behaviour  ") == {"type": "test_behaviour", "params": {}}
    assert normalize_behaviour_entry("") is None

def test_normalize_behaviour_entry_dict():
    entry = {"type": "test", "param1": "value1"}
    normalized = normalize_behaviour_entry(entry)
    assert normalized == {"type": "test", "params": {"param1": "value1"}}

    entry_with_params = {"type": "test", "params": {"p1": "v1"}, "p2": "v2"}
    normalized = normalize_behaviour_entry(entry_with_params)
    assert normalized["type"] == "test"
    assert normalized["params"]["p1"] == "v1"
    assert normalized["params"]["p2"] == "v2"

    # Test explicit meta key exclusion
    entry_meta = {"type": "test", BEHAVIOUR_META_EXPLICIT: True, "p1": "v1"}
    normalized = normalize_behaviour_entry(entry_meta)
    assert "p1" in normalized["params"]
    assert BEHAVIOUR_META_EXPLICIT not in normalized["params"]

def test_prepare_behaviour_configs():
    behaviours = ["b1", {"type": "b2", "p": 1}, ""]
    prepared = prepare_behaviour_configs(behaviours)
    assert len(prepared) == 2
    assert prepared[0]["type"] == "b1"
    assert prepared[1]["type"] == "b2"

def test_strip_behaviour_metadata():
    config = {"a": 1, BEHAVIOUR_META_EXPLICIT: True}
    stripped = strip_behaviour_metadata(config)
    assert "a" in stripped
    assert BEHAVIOUR_META_EXPLICIT not in stripped
    # Original should not be modified if it was a copy, but here we test the return value

    config_clean = {"a": 1}
    assert strip_behaviour_metadata(config_clean) == config_clean

def test_ensure_behaviour_config_root():
    entity_data = {}
    root = ensure_behaviour_config_root(entity_data)
    assert root == {}
    assert entity_data["behaviour_config"] is root

    entity_data = {"behaviour_config": {"b1": {"p": 1}}}
    root = ensure_behaviour_config_root(entity_data)
    assert root == {"b1": {"p": 1}}

    # Test cleanup of invalid keys
    entity_data = {"behaviour_config": {123: "invalid", "b1": "invalid_value"}}
    root = ensure_behaviour_config_root(entity_data)
    assert 123 not in root
    assert root["b1"] == {} # Should be reset to dict if value was not dict

def test_format_behaviour_config_summary():
    config = {"a": 1, "b": "test"}
    summary = format_behaviour_config_summary(config)
    assert "a=1" in summary
    assert "b='test'" in summary
    assert summary.startswith("(") and summary.endswith(")")

def test_build_behaviour_config_map():
    entity_data = {"behaviour_config": {"b1": {"existing": 1}}}
    behaviours = [{"type": "b1", "params": {"new": 2}}, {"type": "b2", "params": {"p": 3}}]

    # Mock get_behaviour_info to return None or empty for simplicity as we can't easily mock the registry here without more setup
    # But the function uses it. We rely on it returning None for unknown behaviours which is handled.

    config_map = build_behaviour_config_map(entity_data, behaviours)

    assert "b1" in config_map
    assert config_map["b1"]["existing"] == 1
    assert config_map["b1"]["new"] == 2

    assert "b2" in config_map
    assert config_map["b2"]["p"] == 3
