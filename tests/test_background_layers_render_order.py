from engine.background_layers import BackgroundLayer, sort_background_layers


def test_background_layers_sorted_by_z_then_id():
    layers = [
        BackgroundLayer(id="B", path="b.png", z=-100, parallax=1.0, repeat_x=False, repeat_y=False),
        BackgroundLayer(id="A", path="a.png", z=-100, parallax=1.0, repeat_x=False, repeat_y=False),
        BackgroundLayer(id="Z", path="z.png", z=-200, parallax=1.0, repeat_x=False, repeat_y=False),
    ]
    ordered = sort_background_layers(layers)
    assert [(layer.z, layer.id) for layer in ordered] == [(-200, "Z"), (-100, "A"), (-100, "B")]
