"""Web preview server utility."""

from __future__ import annotations

import http.server
import logging
import socket
import socketserver
import threading
from pathlib import Path

_LOG = logging.getLogger(__name__)

_SERVER_THREAD: threading.Thread | None = None
_SERVER_PORT: int | None = None
_SERVER_ROOT: str | None = None

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    pass

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        _, port = s.getsockname()
        return int(port)

def start_web_preview(root: Path, port: int | None = None) -> tuple[int, str]:
    """Start a local HTTP server serving root/build/web.
    
    Returns:
        (port, url)
    """
    global _SERVER_THREAD, _SERVER_PORT, _SERVER_ROOT

    web_root = root / "build/web"
    if not web_root.exists():
        raise FileNotFoundError(f"Web build directory not found: {web_root}")

    # If server is running on same root, reuse it
    if _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
        if _SERVER_ROOT == str(web_root) and _SERVER_PORT:
            _LOG.info("Reusing existing preview server at port %s", _SERVER_PORT)
            return _SERVER_PORT, f"http://localhost:{_SERVER_PORT}"
        # If different root, technically we should shut down the old one,
        # but serving multiple servers is complex without tracking instances.
        # For this tool, let's just spin up a new one on a new port.

    if port is None:
        port = _find_free_port()

    directory = str(web_root)

    class SilentHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, format, *args):
            pass

    try:
        server = ThreadedHTTPServer(("127.0.0.1", port), SilentHandler)
    except OSError as e:
        _LOG.error("Failed to bind port %s: %s", port, e)
        # Try one more random port if strict port wasn't requested
        if port is not None:
             port = _find_free_port()
             server = ThreadedHTTPServer(("127.0.0.1", port), SilentHandler)
        else:
            raise

    _SERVER_PORT = port
    _SERVER_ROOT = str(web_root)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _SERVER_THREAD = thread

    url = f"http://localhost:{port}"
    _LOG.info("Started web preview at %s", url)

    return port, url
