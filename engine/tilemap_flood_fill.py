from __future__ import annotations

class FloodFillMaxTilesExceeded(Exception):
    def __init__(self, *, max_tiles: int, attempted: int, partial_indices: list[int]) -> None:
        super().__init__(f"max_tiles_exceeded: max_tiles={max_tiles} attempted={attempted}")
        self.max_tiles = int(max_tiles)
        self.attempted = int(attempted)
        self.partial_indices = list(partial_indices)


def _neighbors4(x: int, y: int) -> list[tuple[int, int]]:
    # Deterministic neighbor ordering for BFS.
    # R, L, D, U
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _neighbors8(x: int, y: int) -> list[tuple[int, int]]:
    # Deterministic neighbor ordering for BFS.
    # 4-neighbor first, then diagonals: DR, DL, UR, UL
    return [
        (x + 1, y),
        (x - 1, y),
        (x, y + 1),
        (x, y - 1),
        (x + 1, y + 1),
        (x - 1, y + 1),
        (x + 1, y - 1),
        (x - 1, y - 1),
    ]


def flood_fill_indices(
    tiles: list[int],
    w: int,
    h: int,
    x: int,
    y: int,
    target_tile: int,
    *,
    diag: bool = False,
    max_tiles: int = 5000,
) -> list[int]:
    if w <= 0 or h <= 0:
        raise ValueError("dims must be > 0")
    if len(tiles) != int(w) * int(h):
        raise ValueError(f"tiles length mismatch: expected {int(w) * int(h)}, got {len(tiles)}")
    if max_tiles <= 0:
        raise ValueError("max_tiles must be > 0")
    if x < 0 or y < 0 or x >= int(w) or y >= int(h):
        raise IndexError(f"start out of bounds: ({x},{y}) in {w}x{h}")

    start_idx = int(y) * int(w) + int(x)
    if int(tiles[start_idx]) != int(target_tile):
        return []

    neighbor_fn = _neighbors8 if diag else _neighbors4

    visited: set[int] = {start_idx}
    queue: list[tuple[int, int]] = [(int(x), int(y))]
    head = 0

    indices: list[int] = []
    while head < len(queue):
        cx, cy = queue[head]
        head += 1
        idx = int(cy) * int(w) + int(cx)
        if int(tiles[idx]) != int(target_tile):
            continue
        indices.append(idx)
        if len(indices) > int(max_tiles):
            raise FloodFillMaxTilesExceeded(
                max_tiles=int(max_tiles),
                attempted=len(indices),
                partial_indices=list(indices[: int(max_tiles)]),
            )
        for nx, ny in neighbor_fn(cx, cy):
            if nx < 0 or ny < 0 or nx >= int(w) or ny >= int(h):
                continue
            nidx = int(ny) * int(w) + int(nx)
            if nidx in visited:
                continue
            visited.add(nidx)
            queue.append((nx, ny))

    return indices


def apply_flood_fill(tiles: list[int], indices: list[int], new_tile: int) -> list[int]:
    desired = int(new_tile)
    if not indices:
        return list(tiles)
    out = list(tiles)
    for idx in indices:
        out[int(idx)] = desired
    return out
