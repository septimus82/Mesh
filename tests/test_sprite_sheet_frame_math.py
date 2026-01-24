from engine.sprite_sheet_math import SpriteSheetSliceSpec, frame_index_to_box, iter_sprite_sheet_frame_boxes


def test_sprite_sheet_frame_index_to_rect_bottom_left_order():
    spec = SpriteSheetSliceSpec(
        sheet_width=64,
        sheet_height=32,
        frame_width=16,
        frame_height=16,
        margin=0,
        spacing=0,
        columns=None,
        rows=None,
    )
    boxes = iter_sprite_sheet_frame_boxes(spec)
    assert len(boxes) == 8
    assert frame_index_to_box(spec, 0) == (0, 16, 16, 32)  # bottom-left
    assert frame_index_to_box(spec, 3) == (48, 16, 64, 32)  # bottom-right
    assert frame_index_to_box(spec, 4) == (0, 0, 16, 16)  # top-left
