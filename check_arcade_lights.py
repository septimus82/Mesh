
try:
    from arcade.experimental.lights import Light, LightLayer, Wall
    print("Arcade 2.x experimental lights found")
    print(f"Wall: {Wall}")
except ImportError:
    print("Arcade 2.x experimental lights NOT found")

try:
    from arcade.future.light import Light, LightLayer
    print("Arcade 3.x future lights found")
    # Check if Wall exists there
    try:
        from arcade.future.light import Wall
        print(f"Wall: {Wall}")
    except ImportError:
        print("Wall not found in arcade.future.light")
except ImportError:
    print("Arcade 3.x future lights NOT found")
