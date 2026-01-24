from __future__ import annotations


def single_line_error(text: str) -> str:
    cleaned = str(text).replace("\r\n", "\n").replace("\r", "\n")
    cleaned = " ".join(cleaned.splitlines())
    return " ".join(cleaned.split())

