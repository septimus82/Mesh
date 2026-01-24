from __future__ import annotations

import math

from engine.tooling.replay_hash import hash_payload, normalize_floats


def test_replay_hash_canonicalization() -> None:
    payload_a = {
        "b": 1.23456789,
        "a": -0.0,
        "nested": [1.0000004, {"x": -0.0}],
    }
    payload_b = {
        "nested": [1.00000049, {"x": 0.0}],
        "a": 0.0,
        "b": 1.23456785,
    }

    hash_a = hash_payload(payload_a, decimals=6)
    hash_b = hash_payload(payload_b, decimals=6)
    assert hash_a == hash_b

    normalized = normalize_floats({"value": -0.0}, 6)
    assert math.copysign(1.0, normalized["value"]) == 1.0
