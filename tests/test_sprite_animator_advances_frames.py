from engine.sprite_animator import AnimationDef, SpriteAnimator


def test_sprite_animator_advances_frames_and_loops():
    anim = SpriteAnimator({"idle": AnimationDef(frames=[0, 1, 2], fps=10.0, loop=True)}, initial="idle")
    assert anim.current_frame_index() == 0

    anim.update(0.05)
    assert anim.current_frame_index() == 0
    anim.update(0.05)
    assert anim.current_frame_index() == 1

    anim.update(0.10)
    assert anim.current_frame_index() == 2

    anim.update(0.10)
    assert anim.current_frame_index() == 0


def test_sprite_animator_non_looping_stops_at_last_frame_and_resets_on_change():
    anim = SpriteAnimator(
        {
            "once": AnimationDef(frames=[5, 6], fps=10.0, loop=False),
            "idle": AnimationDef(frames=[0], fps=1.0, loop=True),
        },
        initial="once",
    )
    assert anim.active_animation_name() == "once"
    assert anim.current_frame_index() == 5

    anim.update(0.10)
    assert anim.current_frame_index() == 6
    anim.update(0.10)
    assert anim.current_frame_index() == 6

    anim.set_animation("idle")
    assert anim.active_animation_name() == "idle"
    assert anim.current_frame_index() == 0

