from __future__ import annotations


def history_reset_cursor() -> int | None:
    return None


def history_push(history: list[str], command: str, *, cap: int, history_index: int | None) -> int | None:
    command = str(command or "").strip()
    if not command:
        return history_reset_cursor()
    if history and history[-1] == command:
        return history_reset_cursor()
    history.append(command)
    if cap > 0 and len(history) > cap:
        excess = len(history) - cap
        del history[:excess]
    return history_reset_cursor()


def history_previous(history: list[str], history_index: int | None) -> tuple[str | None, int | None]:
    if not history:
        return None, history_index
    if history_index is None:
        history_index = len(history) - 1
    elif history_index > 0:
        history_index -= 1
    return history[history_index], history_index


def history_next(history: list[str], history_index: int | None) -> tuple[str | None, int | None]:
    if not history:
        return None, history_index
    if history_index is None:
        return "", history_index
    if history_index >= len(history) - 1:
        return "", history_reset_cursor()
    history_index += 1
    return history[history_index], history_index

