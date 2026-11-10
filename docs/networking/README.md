# Experimental local cooperative room

Two independent Mesh game windows connect to one authoritative room on the same machine. The sample owns its clock, combat and character state. It uses a static Mesh scene and the engine's pure combat model. Existing projects continue to launch through the normal single-player entry point. The [architecture investigation](architecture_investigation.md) records the decision before implementation. [N6](n6_scene_integration.md) hosts a Studio-authored scene the same way: shared movement with the scene's collision, a lever and gate, and cooperative combat.

## Run with Python 3.11 or later

Install Mesh in a virtual environment with `python -m pip install -e ".[dev]"` from the repository, or install the experimental wheel. Open three terminals using the same environment.

| Terminal | Command |
|---|---|
| Server | `python -m mesh_net.server --port 46870` |
| First window | `python -m mesh_net.demo --port 46870` |
| Second window | `python -m mesh_net.demo --port 46870` |

Each window loads its own disposable blank project with the packaged arena sign. Teal is the local player, gold is a peer and red is the stationary enemy. Use arrows or WASD to move. Press Space once in each window near the enemy, then E in either window to collect its green drop. The title shows the enemy's HP and your loot count. F2 disconnects, R resumes, N starts a fresh character after a disconnect, and Escape closes the window. Stop the server with Ctrl+C. Restart it to reset the encounter. A client that closes its process loses its resume credential.

## Protocol version 1

IPv4 loopback TCP carries one UTF-8 JSON object per LF-terminated frame, up to 8,192 bytes including LF. Both peers check field names, types, version and value ranges. Duplicate JSON keys are rejected. Coordinates, IDs, ticks and sequences are integers. Entity IDs are unique within the lifetime of a server process. Every join gets a new session and entity.

| Direction | Fields in addition to `v: 1` and `type` | Effect |
|---|---|---|
| Client → server, `join` | `resume` is null or a previously issued 64-hex bearer credential | Claims a fresh character or a retained offline character. Successful resume rotates the credential. |
| Server → client, `welcome` | `entity`, `session` (32 hex), `resume`, `state` | Establishes socket ownership and includes a complete current snapshot. |
| Client → server, `input` | `entity`, increasing `seq`, `dx`, `dy`, optional `action` | At most one cardinal direction. The optional action is `attack` or `take`. The server rejects forged ownership, ignores old sequences and latches at most one pending action per character. |
| Server → clients, `state` | `tick`, `players` as ordered triples [entity, x, y], `enemy_hp`, `pickup`, `holder` | A full snapshot. Omission despawns a player. `pickup` denotes a drop on the ground. `holder` identifies its online owner, or is null. The offline character retains the resource until expiry. |

The simulation advances integer steps at a target of 20 Hz, moving four pixels per tick within a 480 × 270 room. Input expires after five steps. Stalls may slow game time. The server checks a 36-pixel attack/collection radius and an eight-tick attack cooldown. One hit deals one damage. The enemy has two HP. Actors resolve in increasing entity ID order, including a race for the one pickup. The latest full snapshot corrects each client's view. The client buffers eight states and interpolates remote players two ticks behind. It displays its own latest authoritative position. Outgoing input runs at 20 Hz independently of snapshot reception, so a delayed downlink does not block release or attack while upstream remains writable. Remote positions hold at their last known values on starvation. Prediction remains deferred pending a play-feel budget.

The listener accepts up to eight concurrent connections including incomplete handshakes. Live and offline character slots together are capped at sixteen. Incomplete frames time out after five seconds. More than eight inputs from a socket in one server tick ends that session. A peer with more than 16 KiB in the asyncio write backlog is disconnected on broadcast. OS socket buffers are additional. A disconnect removes the avatar and retains position, cooldown and loot for 600 simulation ticks (nominally 30 seconds). Server shutdown clears all credentials and progress.

## Reproduce the checks

```sh
python -m pytest -q tests/test_mesh_net.py tests/test_mesh_net_downlink.py tests/test_mesh_net_encounter.py tests/test_mesh_net_playback.py
python -m mesh_net.study --loopback
python -m mesh_net.study --lag-ms 0 --jitter-ms 0 --loss 0
python -m mesh_net.study --lag-ms 75 --jitter-ms 110 --loss 0.1 --seed 42
```

For the two-window check, set `MESH_GL_SMOKE=1` (`$env:MESH_GL_SMOKE='1'` in PowerShell), then run `python -m pytest -q tests/test_mesh_net_gpu.py` with a working display and OpenGL context. Linux software GL can use `MESH_GL_SMOKE=1 xvfb-run -a python -m pytest -q tests/test_mesh_net_gpu.py`. This test starts two hidden GameWindow processes with actual sockets, dispatches window key events, checks the loaded sign and samples both framebuffers for avatar colors. It checks movement, both attacks, death, exclusive loot, despawn and restored ownership on resume. The stdin test driver is checkout tooling and is excluded from the wheel.

The [N5.1 rendered responsiveness check](n5_1_responsiveness.md) records the controlled local-display comparison, remote observations, correction behaviour and measurement limits. The check is descriptive and does not set a timing gate.

## Recorded evidence

Implementation commit `9b31cb8d98088c7d4528dc86fb07418d61807145`, Windows, CPython 3.11.17, Arcade 3.3.3. Ten focused tests including the two-window proof passed in 11.19 s. The broader 33-test local run included Mesh's save/load isolation, scene lifecycle, combat and headless verification. Two existing wheel/installed-product checks passed using a disposable Python installation outside the checkout. The installed wheel also ran the two-socket study in isolated Python from a temporary directory. The PR records the final documentation-inclusive commit.

| Measurement | Result |
|---|---|
| Actual loopback, 40 alternating intent changes at seeded offsets from a tick, time from send to the observer reading its first matching position | Median 46.34 ms, sample p95 63.12 ms, maximum 77.85 ms. At the final tick the two-player snapshot was 112 bytes. Client and server shared an asyncio loop for this benchmark. Window rendering and interpolation were excluded. |
| Same loopback study from the installed wheel, separate run | Median 46.03 ms, sample p95 76.18 ms, maximum 76.93 ms. |
| Virtual delivery, zero lag/jitter/loss, 120 simulation ticks, one player | Mean display error 4.02 px, maximum 8 px, final 0 px. The buffer introduces visible lag even on ideal delivery. |
| Virtual delivery, 75 ms one-way base delay, uniform ±110 ms jitter clamped at zero, 10% per-message omission, seed 42 | 24 input/snapshot messages dropped in total, 28 outdated snapshots discarded. Mean display error 6.54 px, maximum 22.4 px, final 0 px after the player stopped. |

The virtual study samples horizontal display error against the authority every 5 ms over six seconds of simulated time. Both profiles generated 1,982 JSON snapshot bytes per simulated second for one recipient, before omissions and transport overhead. Application-level omission/reordering exercises stale-input and interpolation logic. TCP retransmission delays, WAN loss, production scale and physical input-to-display latency still need separate measurements. These observations are descriptive and carry no CI timing thresholds.

## Integration and rollback

The production change outside `mesh_net/` is the setuptools inclusion of the package and its sample JSON. The existing wheel test also asserts those files travel together. The window driver runs under the existing optional-Arcade import policy. A separate subprocess test checks that the authority loads without graphics or Studio. The adapter reuses GameWindow, scene loading, the scaffold and sign asset. The server imports only Mesh's pure damage model and its constants. No entry point in the engine, CLI or Studio imports this experiment. The adapter owns a single process for one room and deliberately omits ordinary game behaviours and the local player controller.

Review in three pieces if useful: transport/session and simulation tests, display/interpolation and real-window proof, then the encounter, packaging and documentation. Before integration, repeat the window proof on Linux and Windows at the proposed merge tree, review the authority and reconnection rules, and check the ordinary CI and installed-product gates. A revert of the experimental changes removes the capability. There are no user data migrations, scene format changes or settings to roll back.

## Boundaries and next decisions

- Any local process can join or occupy slots. Credentials travel in plaintext and only live in memory. A lost welcome during token rotation can strand that character until expiry. Reconnect cannot recover from server restart. A public host requires authentication, encrypted transport, credential recovery and connection-abuse controls.
- The enemy and drop have one lifetime per room. Expiring the last owner's character discards the resource. Durable awards need a stable character ID and an atomic inventory/room transaction.
- The static sign is scenery. Arbitrary authored behaviours, scene transitions, map collision, inventory UI, quests, HD-2D and save slots still have no multiplayer contract. The client draws replicated actors over the loaded scene. Extending this adapter to arbitrary games requires decisions about each rule's authority and about mapping world coordinates through a moving camera.
- For parties and expeditions, add explicit room membership and one server-owned room instance per group before shared hubs. Introduce durable character identity and resumable room transfers before multi-process routing. Measure tick deadlines, queued bytes and interest filtering under load before choosing another transport or adding MMO services.
