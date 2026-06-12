"""Contract tests for pure physics model."""
from engine.physics_model import Aabb, MoveRequest, compute_sensor_events, sweep_axis_separate


def mock_query_tiles(walls: list[Aabb]):
    def query(aabb: Aabb) -> list[Aabb]:
        hits = []
        for w in walls:
            if aabb.intersection(w):
                hits.append(w)
        return hits
    return query

def test_aabb_properties():
    b = Aabb(10, 20, 10, 10)
    assert b.left == 5
    assert b.right == 15
    assert b.top == 25
    assert b.bottom == 15

def test_move_no_collision():
    # Start at 0,0 size 10x10. Move 5, 5. Target 5, 5.
    walls = []

    req = MoveRequest(
        entity_id="p1",
        from_pos=(0, 0),
        delta=(5, 5),
        aabb=Aabb(0, 0, 10, 10)
    )

    res = sweep_axis_separate(req, mock_query_tiles(walls))

    assert res.final_pos == (5, 5)
    assert not res.hit_x
    assert not res.hit_y

def test_collide_x_stop():
    # Wall at x=20 (left edge = 15).
    # Player at 0 (right edge = 5).
    # Move +20 -> would be at 20 (right edge 25).
    # Should stop at wall left edge (15).
    # Player right edge = 15 => Player center = 10.

    wall = Aabb(20, 0, 10, 100) # x=20, w=10 -> left=15, right=25

    req = MoveRequest(
        entity_id="p1",
        from_pos=(0, 0),
        delta=(20, 0),
        aabb=Aabb(0, 0, 10, 10)
    )

    res = sweep_axis_separate(req, mock_query_tiles([wall]))

    assert res.hit_x
    assert res.final_pos == (10.0, 0.0)

def test_slide_x_blocked_y_moves():
    # Wall at x=20 (left=15).
    # Move (20, 10).
    # X should limit to 10. Y should complete to 10.

    wall = Aabb(20, 0, 10, 100)

    req = MoveRequest(
        entity_id="p1",
        from_pos=(0, 0),
        delta=(20, 10),
        aabb=Aabb(0, 0, 10, 10)
    )

    res = sweep_axis_separate(req, mock_query_tiles([wall]))

    assert res.hit_x
    assert not res.hit_y
    assert res.final_pos == (10.0, 10.0)

def test_sensor_events_determinism():
    prev = ["a", "b"]
    next_ = ["b", "c"]

    entered, exited = compute_sensor_events(prev, next_)

    assert entered == ["c"]
    assert exited == ["a"]

def test_sensor_events_sorting():
    prev = []
    next_ = ["z", "a", "m"]

    entered, _ = compute_sensor_events(prev, next_)
    assert entered == ["a", "m", "z"]
