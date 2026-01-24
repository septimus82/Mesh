from pathlib import Path

from engine.content_lock import build_lock, write_lock

lock_data = build_lock("worlds/main_world.json")
write_lock(Path("content.lock.json"), lock_data)
print("Created content.lock.json")
