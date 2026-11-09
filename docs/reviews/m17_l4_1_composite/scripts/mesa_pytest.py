"""pytest under Mesa llvmpipe: py -3.13 mesa_pytest.py <pytest args> (Mesa preloaded before pyglet)."""
import sys
sys.path.insert(0, r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4a")
import mesa_preload  # noqa: F401,E402
import pytest  # noqa: E402
sys.exit(pytest.main(sys.argv[1:]))
