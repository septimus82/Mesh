
import engine.optional_arcade as optional_arcade
try:
    from optional_arcade.arcade.future.light import LightLayer
    window = optional_arcade.arcade.Window(100, 100)
    layer = LightLayer(100, 100)
    points = [(0, 0), (10, 0), (10, 10), (0, 10)]
    try:
        layer.add(points)
        print("layer.add(points) SUCCESS")
    except Exception as e:
        print(f"layer.add(points) FAILED: {e}")
except ImportError:
    print("LightLayer not found")
