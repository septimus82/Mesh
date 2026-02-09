"""
Persistence utilities for editor data.
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
from pathlib import Path

def write_atomic_utf8(path: Path, content: str) -> bool:
    """
    Write content to path atomically (write to temp then rename).
    Safe for use where file might be read concurrently or system crash could corrupt.
    
    Returns True on success, False on failure.
    """
    if sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1":
        # Cannot write to disk in web context usually in this way
        print(f"[Persistence] Skipping atomic write to {path} (Web Runtime)")
        return False
        
    try:
        # Create temp file in same directory to ensure atomic move on same filesystem
        dir_name = path.parent
        dir_name.mkdir(parents=True, exist_ok=True)
        
        # Use tempfile to generate unique name
        fd, temp_path = tempfile.mkstemp(dir=str(dir_name), text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Atomic rename
            # On Windows, os.replace is atomic and allows overwrite
            os.replace(temp_path, str(path))
            return True
            
        except Exception as e:
            # Clean up temp if something failed before rename
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e
            
    except Exception as e:
        print(f"[Persistence] Failed atomic write to {path}: {e}")
        return False
