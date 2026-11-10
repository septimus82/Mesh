# Optional local cooperative simulation

Decision at integration commit e3f5a6341b5d3139b0d8de3ecb0e7e041412dd27, before implementation.

## What owns the game today

| Path and symbol | Relevant behaviour and consequence |
|---|---|
| engine/game.py (GameWindow.__init__), engine/game_runtime/tick.py (on_update, on_draw) | The window owns input, camera, audio, controllers and GL context. Input and audio run before paused/game-over returns. Active frames then update the scene, HD-2D, particles and UI. Frame delta, menus and local pauses cannot be a shared server clock. |
| engine/input_controller.py (on_key_press), engine/behaviours/player_controller.py (PlayerController.update) | Actions read the local window input map and disabled state. Movement writes a sprite and uses the scene's collision state. Send intent from each client and validate its owner on the server. |
| engine/scene_entity_store_controller.py (find_entity), engine/scene_lifecycle_controller.py (load_scene) | Lookup accepts an index or a name. Room changes rebuild layers, spawn sprites, apply queued operations and restore room memory. An index or display name cannot identify a connected player across loads. |
| engine/behaviours/__init__.py (load_builtin_behaviours), engine/behaviours/registry.py | Registered classes bind entity and window. An imported behaviour may need sprites, UI or sound. Arbitrary authored behaviour execution belongs outside this initial server. |
| engine/game_state_controller.py (replace_state, handle_event), engine/events.py (MeshEventBus) | A game holds quest/flag state and dispatches synchronous callbacks. State replacement can resync quests and clear game-over UI. Client callbacks must never arbitrate shared rewards. |
| engine/save_manager.py (save_game, _load_game_impl), engine/game_runtime/scene_flow.py (resolve_game_start_scene, request_scene_change) | Local slots restore one game and request a deferred scene change. Project paths and world/room membership are local. Server reconnect will use its own session state and a full snapshot. |
| engine/physics_model.py (sweep_axis_separate), engine/combat_model.py (resolve_attack), engine/inventory.py (Inventory) | Geometry and damage rules have pure inputs. Runtime collision bridges these results to sprites. Reuse damage resolution for the cooperative test. A rectangular arena and one counted pickup need no scene collision database or inventory UI. |
| docs/architecture_hardening_phase38.md, engine/singletons.py | Registry, path caches and rendering state assume a process-local game. Use independent processes for the two clients. |
| tests/conftest.py, tooling/hd2d_demo.py (HiddenGame), .github/workflows/{ci,extended}.yml | Pure deterministic tests can run without GL. Actual scene loading and drawing need a display/context. Mark loopback tests integration and isolate the real-window demonstration. CI targets Python 3.11 with separate default, acceptance and GL lanes. Keep fast-tier timing gates intact. |

## Transport decision

Use length-limited newline-framed UTF-8 JSON on asyncio TCP over IPv4 loopback. Windows and Linux ship the required standard library. Ordered, reliable delivery simplifies reconnect and protocol tests. Small replaceable snapshots still suffer head-of-line delay when TCP retransmits. A stalled reader must have a bounded outbound backlog. [Python transports](https://docs.python.org/3.11/library/asyncio-protocol.html).

WebSockets add browser interoperability, framing and deployment behind HTTP proxies. TCP ordering still applies. A library and handshake add little to the native two-client demonstration. Origin, TLS, authentication and message limits would still need deployment policy. [RFC 6455](https://www.rfc-editor.org/rfc/rfc6455).

UDP permits discarding late position updates. It adds loss, duplication, reordering, MTU and congestion responsibilities. ENet provides reliable UDP channels, at the cost of native builds/bindings and separate wheel/platform validation. Revisit if measurements show TCP delivery stalls exceed a gameplay budget. [UDP guidelines](https://www.rfc-editor.org/rfc/rfc8085), [ENet](https://github.com/lsalzman/enet).

## Ownership, ordering and risk

One server loop owns a room. Connection events bind a server-issued session to a fresh entity. Resume credentials are opaque capabilities. The simulation takes bounded directional inputs, advances fixed integer steps and emits full tick-stamped states. Only the server decrements HP and awards a pickup. Within a tick, entity ID determines tie order. The client interpolates server positions. Omit prediction until input-delay measurements justify reconciliation.

| Risk | Control and residual limit |
|---|---|
| Forged state, replay or stale socket | Strict versioned message shapes, connection-owned entity, monotonically increasing input sequence. No client position or health fields. |
| CPU/memory growth and half-open peers | Cap clients, retained characters, input rate, bytes per frame, send backlog and read time. Release disconnected slots after a finite resume window. |
| Threading and non-deterministic updates | Run networking and GL on each client's main thread. Server physics owns a discrete clock. Arrival timing still decides which tick receives an intent. |
| Client/server rule divergence | Sample has explicit small rules, shares Mesh's pure damage model, renders snapshots. General behaviour mirroring requires separate design. |
| Slow network and process loss | Expire movement input, bound interpolation and show disconnected state. Resume is limited to the same server process. |
| Untrusted network | Loopback only. Bearer credentials on plaintext TCP suit a trusted local demonstration. Internet deployment needs authenticated encrypted transport and operational controls. |

## Feasibility and stages

A headless authority for a bounded cooperative room is feasible without core runtime changes. Hosting arbitrary existing Mesh projects with identical single-player behaviour would require separating window-bound input, physics, event and behaviour ownership. That wider port is outside this experiment.

1. N1: verify framing, two TCP clients, ownership, stepping, rejection and shutdown independently of Arcade.
2. N2: exercise snapshot interpolation, reconnect, stale commands and reproducible disruption with measurements.
3. N3: launch two isolated Mesh clients, load a placeholder scene, draw replicated participants and verify movement.
4. N4: after N3 passes, prove two attacks, death and a single server-awarded pickup, including resume.

Keep the sample behind separate module entry points. The only packaging changes anticipated are distribution of the optional module and its scene. Rollback removes the experimental package, tests, documentation and package declarations.
