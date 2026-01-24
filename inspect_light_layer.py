
try:
    from arcade.future.light import LightLayer
    print("LightLayer found")
    print(dir(LightLayer))
except ImportError:
    print("LightLayer not found")
