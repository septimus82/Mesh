"""An AI plays a Mesh Studio play-test with the player's own controls, in bounded steps (D2, #422).

D1 (``engine.runtime_debug``) lets an AI look at the running game. Here, once the person allows it in Studio's AI
panel (``StudioAIHost.gameplay_control``: separate from starting and stopping play-tests, off until turned on, for
that Studio session only), it can also act in the game, through four bounded actions:

- ``move``: hold a direction (``up``, ``down``, ``left``, ``right``) for 1 to ``MOVE_FRAMES_MAX`` frames;
- ``interact``: press the interact key once, to talk to or use what's in front of the player;
- ``advance``: press it once in a conversation, to go on to the next line;
- ``choose``: pick one of the conversation's choices (its number or its words), moving the cursor with the
  up and down keys and confirming with the interact key, as a player does.

Every action is the game's own input: key presses and releases sent to the window, for the keys the game binds to
``move_up`` / ``move_down`` / ``move_left`` / ``move_right`` and ``interact``. So the game's rules apply as they do to
a player (collisions, doors, dialogue, quests), and nothing else is reachable: no other keys, no code, no state set
directly, no project files.

``PlayDriver`` runs one action at a time on Studio's main thread, a frame at a time (``tick``, from
``Studio.on_update`` before the game's own update). Starting an action and reading how it went are each a short
request over the live-session bridge (its queue, its timeout), so a slow or frozen Studio answers ``timeout`` as for
every other request. An action is refused when the person hasn't allowed it, when Studio isn't playing, when the
game is paused or has taken the controls (a cutscene), when the person is holding the same key, when another action
is running, or when it doesn't fit what's on screen (moving or interacting during a conversation, advancing past a
choice, choosing where there are none). A running action is cancelled, its keys released, when the person takes
back the permission, the play-test stops, the game pauses or Studio closes; it never outlasts its frames.

``request_action`` is the MCP side: start the action, wait for it, then read a snapshot (``runtime_debug``), so the
AI sees what its action did.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

Doc = dict[str, Any]

ACTIONS = ("move", "interact", "advance", "choose")
DIRECTIONS = {"up": "move_up", "down": "move_down", "left": "move_left", "right": "move_right"}
MOVE_FRAMES_MAX = 120  # two seconds at 60 frames a second
TAP_FRAMES = 2  # a key pressed and let go, as a quick tap
SETTLE_FRAMES = 4  # frames after the last key, for the game to show what it did
RESULTS_KEPT = 20
CHOICES_MAX = 20  # a conversation's choices listed (and so choosable)
WAIT_SECONDS = 90.0  # (the MCP side) the longest it waits for an action: a slow software renderer is slow


def _refused(reason: str, message: str, **extra: Any) -> Doc:
    return {"ok": False, "mode": "live_studio", "reason": reason, "message": message, **extra}


def dialogue_view(window: Any) -> Doc:
    """The conversation on screen, if any: who says what, its choices and which one is selected."""
    box = getattr(getattr(window, "ui_controller", None), "dialogue_box", None)
    if box is None or not callable(getattr(box, "is_active", None)):
        return {"available": False, "reason": "the game has no dialogue box"}
    if not box.is_active():
        return {"available": True, "open": False}
    from engine.runtime_debug import plain  # noqa: PLC0415

    entry = box.get_current_entry() or {}
    choices = box.get_choices() if box.has_choices() else []
    return {"available": True, "open": True, "speaker": plain(entry.get("speaker") or entry.get("name")),
            "text": plain(entry.get("text")),
            "choices": [{"index": i, "text": plain(c.get("text")), "available": not c.get("disabled")}
                        for i, c in enumerate(choices[:CHOICES_MAX])],
            "selected": box.get_choice_cursor() if choices else None}


def _player(window: Any) -> Any:
    finder = getattr(getattr(window, "scene_controller", None), "_find_player_sprite", None)
    return finder() if callable(finder) else None


def _where(window: Any) -> Doc:
    player = _player(window)
    scene = getattr(getattr(window, "scene_controller", None), "current_scene_path", None)
    at = [round(float(player.center_x), 1), round(float(player.center_y), 1)] if player is not None else None
    return {"scene": str(scene) if scene else None, "player": at}


class PlayDriver:
    """The AI's hands in a play-test: one bounded action at a time, as key presses, a frame at a time."""

    def __init__(self, studio: Any) -> None:
        self.studio = studio
        self.running: Doc | None = None  # {"id", "request", "steps", "step", "frames", "held", "before", ...}
        self.results: dict[str, Doc] = {}
        self._count = 0

    @property
    def window(self) -> Any:
        return self.studio.window

    # ------------------------------------------------------------------ starting one
    def start(self, request: Doc) -> Doc:
        """Check the request against what's on screen and start it; or say why not (nothing is pressed then)."""
        if self.studio.mode != "play":
            return _refused("not_playing", "Mesh Studio isn't play-testing, so there's no game to play. "
                                           "debug_start_playtest starts one (if the person allowed it).")
        if self.running is not None:
            return _refused("action_running", "Another action is still running; wait for it (its result says when "
                                              "it's done).", action_id=self.running["id"])
        problem = self._game_problem()
        if problem:
            return problem
        planned = self._plan(request)
        if "reason" in planned:
            return planned
        held = self._keys_down()
        clash = sorted({key for kind, key, _ in planned["steps"] if kind == "press"} & held)
        if clash:
            return _refused("person_using_controls", "The person is holding a key this action needs; nothing was "
                                                     "pressed.")
        self._count += 1
        action_id = f"a{self._count}"
        self.running = {"id": action_id, "request": planned["request"], "steps": planned["steps"], "step": 0,
                        "left": None, "held": None, "frames": 0, "before": _where(self.window),
                        "target": planned.get("target"), "started_at": round(time.time(), 3)}
        return {"ok": True, "mode": "live_studio", "action_id": action_id, "status": "running",
                "action": planned["request"]}

    def _plan(self, request: Doc) -> Doc:
        """The request as key steps (``("press", key, frames)`` / ``("wait", None, frames)`` /
        ``("check", None, 0)``), or the refusal."""
        action = request.get("action")
        if action not in ACTIONS:
            return _refused("invalid_action", f"action must be one of {', '.join(ACTIONS)}, not {action!r}.")
        dialogue = dialogue_view(self.window)
        talking = bool(dialogue.get("open"))
        choices = dialogue.get("choices") or []
        if action == "move":
            direction, frames = request.get("direction"), request.get("frames", 30)
            if direction not in DIRECTIONS:
                return _refused("invalid_action", f"direction must be one of {', '.join(DIRECTIONS)}, "
                                                  f"not {direction!r}.")
            if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= MOVE_FRAMES_MAX:
                return _refused("invalid_action", f"frames must be a whole number from 1 to {MOVE_FRAMES_MAX}, "
                                                  f"not {frames!r}.")
            if talking:
                return _refused("dialogue_open", "A conversation is on screen, so the player can't move: advance "
                                                 "or choose first.", dialogue=dialogue)
            key = self._key(DIRECTIONS[direction])
            if key is None:
                return _refused("no_key", f"The game binds no key to {DIRECTIONS[direction]}.")
            return {"request": {"action": "move", "direction": direction, "frames": frames},
                    "steps": [("press", key, frames), ("wait", None, SETTLE_FRAMES)]}
        interact = self._key("interact")
        if interact is None:
            return _refused("no_key", "The game binds no key to interact.")
        tap = [("press", interact, TAP_FRAMES), ("wait", None, SETTLE_FRAMES)]
        if action == "interact":
            if talking:
                return _refused("dialogue_open", "A conversation is on screen: advance or choose instead.",
                                dialogue=dialogue)
            return {"request": {"action": "interact"}, "steps": tap}
        if action == "advance":
            if not talking:
                return _refused("no_dialogue", "There's no conversation on screen to advance.")
            if choices:
                return _refused("choice_needed", "This line waits for a choice: choose one.", dialogue=dialogue)
            return {"request": {"action": "advance"}, "steps": tap}
        # choose
        if not talking or not choices:
            return _refused("no_choices", "There's no choice on screen to make.", dialogue=dialogue)
        wanted = request.get("choice")
        target = next((c for c in choices if c["index"] == wanted or (isinstance(wanted, str) and c["text"] == wanted)),
                      None) if not isinstance(wanted, bool) else None
        if target is None or not target["available"]:
            return _refused("choice_not_available", f"{wanted!r} isn't one of the choices that can be made now.",
                            dialogue=dialogue)
        selected = dialogue.get("selected") or 0
        steps: list[tuple[str, Any, int]] = []
        delta = target["index"] - selected
        key = self._key("move_down" if delta > 0 else "move_up")
        if delta and key is None:
            return _refused("no_key", "The game binds no key to move the choice cursor.")
        for _ in range(abs(delta)):  # (the cursor skips choices that can't be made, so check where it ends)
            steps += [("press", key, TAP_FRAMES), ("wait", None, TAP_FRAMES)]
        steps += [("check", None, 0)] + tap
        return {"request": {"action": "choose", "choice": target["index"], "text": target["text"]},
                "steps": steps, "target": target["index"]}

    # ------------------------------------------------------------------ running it, a frame at a time
    def tick(self) -> None:
        """One frame: Studio's on_update, before the game updates."""
        run = self.running
        if run is None:
            return
        if self.studio.mode != "play":
            self.cancel("the play-test stopped")
            return
        problem = self._game_problem()
        if problem:
            self.cancel(problem["message"])
            return
        run["frames"] += 1
        steps = run["steps"]
        while True:
            if run["left"] is not None:  # (in a step: a key held, or frames waited, for its frames)
                run["left"] -= 1
                if run["left"] > 0:
                    return
                if steps[run["step"]][0] == "press":
                    self._release()
                run["step"], run["left"] = run["step"] + 1, None
            if run["step"] >= len(steps):
                self._finish("done")
                return
            kind, key, frames = steps[run["step"]]
            if kind == "check":  # (the cursor skips choices that can't be made: confirm only where it was meant)
                selected = dialogue_view(self.window).get("selected")
                if selected != run["target"]:
                    self.cancel(f"the choice cursor is on {selected}, not {run['target']}: nothing was chosen")
                    return
                run["step"] += 1
                continue
            if kind == "press":
                self._press(key)  # (down for this frame's update and the next frames - 1)
            run["left"] = frames
            return

    def cancel(self, why: str) -> None:
        """Stop the running action, if any, and let go of its key."""
        if self.running is not None:
            self._finish("cancelled", why)

    def status(self, action_id: str) -> Doc:
        if self.running is not None and self.running["id"] == action_id:
            return {"ok": True, "mode": "live_studio", "action_id": action_id, "status": "running",
                    "frames": self.running["frames"]}
        result = self.results.get(action_id)
        if result is None:
            return _refused("action_not_found", f"No action {action_id!r} (Studio keeps the last {RESULTS_KEPT}).")
        return result

    def _finish(self, status: str, why: str = "") -> None:
        run = self.running
        assert run is not None
        self._release()
        self.running = None
        result: Doc = {"ok": status == "done", "mode": "live_studio", "action_id": run["id"], "status": status,
                       "action": run["request"], "frames": run["frames"], "before": run["before"],
                       "after": _where(self.window), "dialogue": dialogue_view(self.window)}
        if why:
            result.update(reason="cancelled", message=f"Cancelled: {why}.")
        self.results[run["id"]] = result
        for old in list(self.results)[:-RESULTS_KEPT]:
            del self.results[old]

    # ------------------------------------------------------------------ the game's own controls
    def _manager(self) -> Any:
        return getattr(getattr(self.window, "input_controller", None), "manager", None)

    def _key(self, action: str) -> int | None:
        """The first key the game binds to ``action``."""
        manager = self._manager()
        bindings = manager.get_bindings() if manager is not None and hasattr(manager, "get_bindings") else {}
        keys = bindings.get(action) or []
        return int(keys[0]) if keys else None

    def _keys_down(self) -> set[int]:
        manager = self._manager()
        getter = getattr(manager, "get_keys_down", None)
        return set(getter()) if callable(getter) else set()

    def _press(self, key: int) -> None:
        run = self.running
        if run is not None:
            run["held"] = key
            self.window.dispatch_event("on_key_press", key, 0)

    def _release(self) -> None:
        run = self.running
        if run is not None and run.get("held") is not None:
            key, run["held"] = run["held"], None
            self.window.dispatch_event("on_key_release", key, 0)

    def _game_problem(self) -> Doc | None:
        window = self.window
        if getattr(window, "paused", False):
            return _refused("game_paused", "The game is paused (its menu is open): it takes no play until it's "
                                           "resumed.")
        if getattr(window, "game_over", False):
            return _refused("game_over", "The game is over: stop and start a new play-test.")
        controller = getattr(window, "input_controller", None)
        locked = getattr(controller, "is_input_locked", None)
        if callable(locked) and locked():
            return _refused("input_locked", "The game has taken the player's controls (a cutscene): wait for it.")
        return None


# --------------------------------------------------------------------- from outside (the MCP tool)

def request_action(root: str | Path = ".", request: Doc | None = None, *, wait: float = WAIT_SECONDS,
                   poll: float = 0.05) -> Doc:
    """Start ``request`` in the Mesh Studio that has the project open, wait for it, and add a snapshot of the game
    afterwards (``runtime_debug``): ``{"ok", "action": <its result>, "snapshot": ...}``, or the refusal."""
    from engine import authoring_session  # noqa: PLC0415

    info, failure = authoring_session._studio(root)
    if failure:
        return failure
    started = authoring_session._call(info, "POST", "/live/debug/act", dict(request or {}))
    if started.get("ok") is not True:
        return started
    action_id = str(started["action_id"])
    deadline = time.monotonic() + wait
    result = started
    while result.get("status") == "running":
        if time.monotonic() > deadline:
            authoring_session._call(info, "POST", "/live/debug/act/cancel", {"action_id": action_id})
            result = authoring_session._call(info, "GET", f"/live/debug/act?id={action_id}")
            return {**result, "ok": False, "reason": "action_timeout",
                    "message": f"The action didn't finish within {wait:g} s, so it was cancelled."}
        time.sleep(poll)
        result = authoring_session._call(info, "GET", f"/live/debug/act?id={action_id}")
        if result.get("ok") is False and result.get("status") is None:  # (Studio didn't answer, or forgot it)
            return result
    snapshot = authoring_session._call(info, "GET", "/live/debug/snapshot?events=10")
    return {"ok": result.get("ok") is True, "mode": "live_studio", "action": result, "snapshot": snapshot}
