# N5.1 rendered responsiveness check

This check compares two display policies on the same N5.1 implementation. The
server still determines all positions. Both runs use independent 20 Hz outbound
input, the same 20 Hz authority and two real Mesh `GameWindow` processes over
loopback TCP. The only changed setting is whether the owner is shown through
the original two-tick playback buffer or at its most recent authoritative
snapshot. Remote actors retain two-tick interpolation in both runs.

## Method and environment

Windows, Python 3.11, Arcade's hidden OpenGL windows, 480 × 270, two local
processes and one local server. `frame_probe.py` dispatches key events through
the real window, reads the rendered framebuffer row before swap, and timestamps
the first changed pixel and the final stable pixel using `perf_counter`.
Random seed 3941 offsets 16 alternating left/right trials from the server
tick. Each direction is held for 380 ms, followed by a 360 ms rest. The probe
also sends eight rapid reversals, kills the enemy with two attacks, and moves
the server-owned player by 64 pixels to observe correction. Both processes
exited normally in each reported run. No trials were excluded. The script is
in this directory; from the checkout run:

```powershell
$env:PYTHONPATH=(Get-Location).Path
$env:MESH_NET_LOCAL_INTERPOLATION='1'
python docs/networking/frame_probe.py
Remove-Item Env:MESH_NET_LOCAL_INTERPOLATION
python docs/networking/frame_probe.py
```

The environment variable is read by the probe, not the game. Results below are
one complete run per policy. The previous independent N5 measurement on the
unfixed candidate found 171 ms median first movement, 203 ms sample p95 and
152 ms median stopping with two-tick local interpolation. That baseline also
had snapshot-gated input, so it is context rather than a controlled comparison.

| Rendered observation | Two-tick local buffer | Latest authoritative local |
| --- | ---: | ---: |
| First local movement, 16 trials: median / sample p95 | 132.62 / 174.03 ms | 99.59 / 129.16 ms |
| Local settling after release: median / sample p95 | 124.90 / 168.81 ms | 31.29 / 79.81 ms |
| Local pixels traveled after release: median / sample p95 | 10.25 / 12.75 px | 4.00 / 8.00 px |
| First remote movement: median / sample p95 | 136.05 / 174.85 ms | 141.77 / 174.33 ms |
| Remote settling after release: median / sample p95 | 125.46 / 169.30 ms | 128.11 / 170.77 ms |
| Remote frame interval: median / sample p95 | 19.83 / 24.55 ms | 19.63 / 24.36 ms |
| Authority correction visible at owner | 133.20 ms | 19.62 ms |
| Authority correction visible at peer | 131.77 ms | 137.23 ms |
| Fatal attack key to rendered pickup, owner | 134.66 ms | 118.25 ms |
| Visible rapid direction reversals, out of eight intents | 7 | 7 |
| Between-window movement onset skew: median / sample p95 | 1.70 / 7.17 ms | 43.66 / 61.02 ms |

The latest local snapshot cuts median first movement by 33 ms and median
stopping delay by 94 ms in this pair of runs. The onset skew is intentional:
the owner leads the peer's interpolated view. Both windows still converge to
the same authority. The correction measurement shows the local view follows a
fresh server correction promptly; it does not test a divergent predicted
position because this implementation has no client prediction. The remote
frame interval reflects the window loop, not independent proof of smooth
motion under WAN jitter.

These numbers are descriptive, not CI thresholds. Dispatch-to-framebuffer
latency excludes physical keyboard, display scanout and internet transit.
The two runs are sequential, so scheduler and OpenGL variance remain. A real
network play-feel check is still required before promising action-game
responsiveness. Because the local snapshot change substantially improved
stopping and preserves simple authority, N5.1 does not add prediction or
reconciliation. Prediction can be reconsidered against a measured play-feel
budget on a representative network.
