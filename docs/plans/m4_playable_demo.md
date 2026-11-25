# M4 playable demo: two clients, one server, injected latency

How to play M4's online co-op combat on one PC, with real windows, at 0, 50, 100 and 200 ms round trip, and switch
the input queue and lag compensation. The rendered evidence of the same world is in
`docs/reviews/m4_rendered_evidence/`, and the checkpoint summary is in `docs/plans/m4_checkpoint.md`.

**The world** (`tooling/m4_demo_world.py`, built from files already in the repository):

- **The crossing (HD-2D), where you arrive.** Open ground, two platforms 2 m up with a staircase each, and a railed
  bridge deck between them over an underpass. Three bandits walk on the server (30 HP each, so they last):
  - one on the open ground, just east of where you arrive;
  - one up and down the west stairs;
  - one along the bridge deck.
- **The ruins (2D)**, the expedition's Layer 1, through a walk-in door on the open ground to the west. It has a lever,
  a gate and a standing bandit. Its door back is on its west edge.

## Launch

Open a PowerShell window for each process below and paste one line into each, in this order. Every line starts from
the checkout, so it works in a fresh window. Use the checkout this branch is merged into (here `D:\Games\Mesh`;
change the path if yours differs).

**1. The server (one window).** It prints `Mesh room listening on 127.0.0.1:46870`. This line starts it with the
defaults, drain and lag compensation on:

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py server --queue drain --rewind on
```

**2a. No added latency: two clients straight to the server (two windows, one line each).**

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py client --port 46870
```

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py client --port 46870
```

**2b. With latency: start one delay proxy (one window), then both clients through it on port 46871.** Pick one proxy
line. Each adds OD1's ±10 ms jitter and 1% loss, and every loss stalls like a TCP retransmission (RTT + 200 ms).

```powershell
cd D:\Games\Mesh; py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 0 --jitter-ms 10 --loss 0.01 --seed 7
```

```powershell
cd D:\Games\Mesh; py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 50 --jitter-ms 10 --loss 0.01 --seed 7
```

```powershell
cd D:\Games\Mesh; py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 100 --jitter-ms 10 --loss 0.01 --seed 7
```

```powershell
cd D:\Games\Mesh; py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 200 --jitter-ms 10 --loss 0.01 --seed 7
```

For a pure delay with no jitter or loss, drop `--jitter-ms 10 --loss 0.01`. Then, in two more windows, one line each:

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py client --port 46871
```

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py client --port 46871
```

To change the latency, stop the proxy (Ctrl+C) and start another line; the clients reconnect with **R**.

**3. Switching the input queue and lag compensation.** Both are the server's: stop it (Ctrl+C) and start it again
with other values. Restarting also brings the bandits back to full HP. Clients then press **N** (a new session) or
restart.

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py server --queue drain --rewind on
```

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py server --queue deep --rewind on
```

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py server --queue small --rewind on
```

```powershell
cd D:\Games\Mesh; $env:PYTHONPATH='D:\Games\Mesh'; py -3.13 tooling/m4_demo_world.py server --queue drain --rewind off
```

- `--queue`:
  - `drain` is the provisional default: keeps a burst and drops a step every 4 ticks of a lasting backlog;
  - `deep` keeps every step: no corrections, but it lags while you keep walking;
  - `small` keeps 2 and walks on: least lag, most corrections.
- `--rewind on|off` turns lag compensation on or off: attacks judged where your window showed the enemies, at most
  300 ms back.
- The server prints the settings it runs with: `Mesh input queue depth … hold … drain …` and
  `Mesh lag compensation on|off`.

## Controls

The window with keyboard focus is the one you play; click the other window to switch players. A window that loses
focus lets go of its held keys.

| Key | Action |
|---|---|
| Arrows or WASD | move |
| Space | attack (a white crescent shows at once where the hitbox is) |
| E | use (the ruins' lever) or take (a dropped item) |
| Walk into a door | transfer to the other room (the crossing's door is on the open ground to the west of where you arrive) |
| P, I, Y / N, L | party: create, invite the nearest player, accept / decline, leave (not needed in this world) |
| F2 | disconnect; **R** resume, **N** new session |
| Esc | quit the window |

## What to look for

- **Your swing and a confirmed hit are different things.**
  - The **white crescent with a blue rim** is your own swing. It shows the moment you press Space, over the hitbox
    the server will make, in the direction you face, for 0.2 s. It promises nothing.
  - The **red burst with a yellow core** on a bandit is a **hit the server confirmed**. It comes about a round trip
    later.
  - A crescent with no burst is a miss.
  - The other player's swings show as crescents too, when their state reaches you.
- **Movement prediction.** Your own avatar moves on the frame you press, at every latency.
  - A small snap (one step, 7.5 px) is a **correction**: the server dropped or changed a step.
  - Compare the presets at 100 and 200 ms while walking in circles:
    - drain makes one-step corrections after loss stalls;
    - deep makes none, but the other window sees you late while you keep walking;
    - small makes larger ones (up to 37.5 px).
- **The stairs** (west platform, and the bandit climbing it).
  - Walk up and down at 100 and 200 ms with drain: occasionally a correction snaps you between the stairs and the
    ground beside them. The plan measured about one a minute of stair walking at 100 ms and two to three at 200 ms.
  - Strike at the climbing bandit from the ground beside the stairs. It can be hit only while it is within 1.5 m of
    your level.
- **The bridge deck.**
  - Walk onto it and strike the bandit walking there: hits land.
  - Then stand on the ground underneath while it walks over you: it is 2 m up and can never be hit from below.
- **Moving enemies.**
  - Online they walk slower than authored: 52 px/s for 70 authored, from the 20 Hz server's waypoint pauses.
  - Their pictures show two ticks behind, and under loss they freeze, then catch up.
  - With `--rewind on`, a swing that looked like a hit is mostly judged a hit. Switch to `--rewind off` at 100 ms and
    compare: more swings that looked right miss.
  - Walking into a moving bandit makes small corrections, more under loss.
- **200 ms.**
  - Hits confirm about 270 ms after the press.
  - Lag compensation's 300 ms cap is reached, so moving targets are judged up to 300 ms back, not the full delay.
  - Swings made while walking can come back as misses when their claim is older than 600 ms ("stale").
- **Room transfers.** Walk west through the door, and back: the next room shows about 130–150 ms after the server
  moves you, and nothing you pressed in the old room runs in the new one.

## Stop

- Close each client window, or press Esc in it.
- Press Ctrl+C in the proxy's and the server's PowerShell windows.
- Each process keeps its files in its own temporary folder, which is removed when it ends. Nothing is written to the
  repository or your projects.

## Notes

- **Sound.** The clients play the attack and hit sounds at your normal volume: these are your own windows.
- **Party.** The ruins are an ordinary shared room here, so no party is needed. The expedition's party flow is
  still in `python -m mesh_net.server --expedition` with `python -m mesh_net.world_client`.
- **Commands checked.** Every command above was checked against its `--help` (`tooling/m4_demo_world.py server`,
  `client` and `files`, `tooling/net_delay_proxy.py`) and runs headless in the evidence harness. The windows were
  never opened on a visible desktop by the author: you are the first to play them visibly.
