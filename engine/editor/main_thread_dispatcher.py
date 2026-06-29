from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class _QueuedCall:
    func: Callable[[], Any]
    event: threading.Event | None = None
    result: Any = None
    error: BaseException | None = None


class EditorMainThreadDispatcher:
    """Thread-safe queue for work that must run on the editor main thread."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_QueuedCall] = queue.Queue()
        self.main_thread_id = threading.get_ident()

    def is_main_thread(self) -> bool:
        return threading.get_ident() == self.main_thread_id

    def call_sync(self, func: Callable[[], Any], *, timeout: float = 5.0) -> Any:
        if self.is_main_thread():
            return func()
        call = _QueuedCall(func=func, event=threading.Event())
        self._queue.put(call)
        if call.event is None or not call.event.wait(timeout=float(timeout)):
            raise TimeoutError("Timed out waiting for editor main thread")
        if call.error is not None:
            raise call.error
        return call.result

    def post(self, func: Callable[[], Any]) -> None:
        self._queue.put(_QueuedCall(func=func))

    def drain(self, *, limit: int = 50) -> int:
        drained = 0
        for _ in range(max(0, int(limit))):
            try:
                call = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                call.result = call.func()
            except BaseException as exc:  # noqa: BLE001  # REASON: main-thread dispatch must capture worker failures for awaiters
                call.error = exc
            finally:
                if call.event is not None:
                    call.event.set()
            drained += 1
        return drained
