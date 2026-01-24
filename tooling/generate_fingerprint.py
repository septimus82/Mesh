from engine.content_lock import build_lock, compute_strict_fingerprint

lock = build_lock("worlds/main_world.json")
fp = compute_strict_fingerprint(lock)
print(fp)
