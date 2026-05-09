"""Editor build subprocess controller."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from engine.swallowed_exceptions import _log_swallow

BuildPopen = Callable[..., subprocess.Popen[str]]
OpenFolder = Callable[[str], None]


class EditorBuildController:
    """Runs one-click editor builds without embedding release pipeline code."""

    def __init__(
        self,
        editor: Any,
        *,
        popen_factory: BuildPopen | None = None,
        open_folder: OpenFolder | None = None,
    ) -> None:
        self._editor = editor
        self._popen_factory = popen_factory or subprocess.Popen
        self._open_folder = open_folder or self._default_open_folder
        self._process: subprocess.Popen[str] | None = None
        self._previous_active: bool = False

    def build_windows(self) -> bool:
        """Start a Windows player package build in a subprocess."""
        editor = self._editor
        session = getattr(editor, "build_session", None)
        if session is not None and getattr(session, "is_running", False):
            self._feedback_warning("Build already running.")
            return False

        repo_root = self._repo_root()
        output_path = repo_root / "artifacts" / "player_pkg"
        stderr_log_path = repo_root / "artifacts" / "editor_build_windows_stderr.log"
        stderr_log_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "mesh_cli",
            "package-player",
            "--out",
            str(output_path),
            "--smoke",
        ]

        self._previous_active = bool(getattr(editor, "active", False))
        if session is not None:
            session.is_running = True
            session.output_path = str(output_path)
            session.stderr_log_path = str(stderr_log_path)
        editor.active = False
        self._set_window_paused(True)

        try:
            self._process = self._popen_factory(
                cmd,
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            self._process = None
            self._finish(returncode=1, stdout="", stderr=f"{type(exc).__name__}: {exc}")
            return False

        self._feedback_info("Build started: Windows player package.")
        return True

    def tick(self) -> None:
        """Poll the running build and finish it when the subprocess exits."""
        process = self._process
        if process is None:
            return
        returncode = process.poll()
        if returncode is None:
            return
        try:
            stdout, stderr = process.communicate()
        except Exception as exc:
            _log_swallow("EDIT-BUILD-001", "engine/editor/editor_build_controller.py communicate failed")
            stdout, stderr = "", f"{type(exc).__name__}: {exc}"
        self._finish(returncode=int(returncode), stdout=stdout or "", stderr=stderr or "")

    def _finish(self, *, returncode: int, stdout: str, stderr: str) -> None:
        editor = self._editor
        session = getattr(editor, "build_session", None)
        output_path = Path(str(getattr(session, "output_path", "") or self._repo_root() / "artifacts" / "player_pkg"))
        stderr_log = Path(
            str(getattr(session, "stderr_log_path", "") or self._repo_root() / "artifacts" / "editor_build_windows_stderr.log")
        )

        if session is not None:
            session.is_running = False
        editor.active = self._previous_active
        self._set_window_paused(True)
        self._process = None

        if returncode == 0:
            self._feedback_info(f"Build complete: {output_path}")
            try:
                self._open_folder(str(output_path))
            except Exception:
                _log_swallow("EDIT-BUILD-002", "engine/editor/editor_build_controller.py open folder failed")
            return

        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        combined = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        stderr_log.write_text(combined or f"Build failed with exit code {returncode}\n", encoding="utf-8")
        self._feedback_error(f"Build failed: {returncode}. See {stderr_log}")

    def _repo_root(self) -> Path:
        getter = getattr(self._editor, "_get_repo_root", None)
        if callable(getter):
            try:
                return Path(getter()).resolve()
            except Exception:
                _log_swallow("EDIT-BUILD-003", "engine/editor/editor_build_controller.py repo root failed")
        return Path.cwd().resolve()

    def _set_window_paused(self, value: bool) -> None:
        try:
            self._editor.window.paused = bool(value)
        except Exception:
            _log_swallow("EDIT-BUILD-004", "engine/editor/editor_build_controller.py pause failed")

    def _feedback_info(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
        info = getattr(feedback, "info", None) if feedback is not None else None
        if callable(info):
            info(message)

    def _feedback_warning(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
        warning = getattr(feedback, "warning", None) if feedback is not None else None
        if callable(warning):
            warning(message)

    def _feedback_error(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
        error = getattr(feedback, "error", None) if feedback is not None else None
        if callable(error):
            error(message)

    @staticmethod
    def _default_open_folder(path: str) -> None:
        starter = getattr(os, "startfile", None)
        if callable(starter):
            starter(path)
