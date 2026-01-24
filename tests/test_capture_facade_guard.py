import os

def test_capture_is_thin_facade():
    """
    Enforce that engine/input_runtime/capture.py remains a thin facade
    and does not accumulate logic or definitions.
    """
    path = os.path.join("engine", "input_runtime", "capture.py")
    assert os.path.exists(path), f"File not found: {path}"

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. Line count check (excluding empty lines)
    non_empty_lines = [line for line in lines if line.strip()]
    line_count = len(non_empty_lines)
    
    # Current count is ~40. Setting budget to 60 to allow for some imports but prevent logic regrowth.
    # User suggested <= 250, but since we know it's ~40, 100 is a safe upper bound that is still strict.
    BUDGET = 100
    assert line_count <= BUDGET, (
        f"capture.py has {line_count} non-empty lines, exceeding budget of {BUDGET}. "
        "It should only contain imports and re-exports."
    )

    content = "".join(lines)

    # 2. Forbid definitions of core handlers
    forbidden_defs = [
        "def handle_key_press",
        "def handle_mouse_",
        "def handle_text",
        "def ui_blocks_input",
        "def player_input_blocked",
    ]
    
    for forbidden in forbidden_defs:
        assert forbidden not in content, (
            f"Found forbidden definition '{forbidden}' in capture.py. "
            "Move logic to capture_runtime.py."
        )

    # 3. Forbid large constants
    forbidden_constants = [
        "ACTIONS_ALLOWED_WHEN_BLOCKED =",
        "GAMEPLAY_ACTIONS =",
    ]

    for forbidden in forbidden_constants:
        # Check for assignment at start of line or after whitespace
        # Simple substring check is usually enough for this guard
        assert forbidden not in content, (
            f"Found forbidden constant definition '{forbidden}' in capture.py. "
            "Move constants to capture_models.py."
        )

    # 4. Ensure it imports from the new modules
    required_imports = [
        "from engine.input_runtime.capture_models import",
        "from engine.input_runtime.capture_io import",
        "from engine.input_runtime.capture_runtime import",
    ]
    
    for req in required_imports:
        assert req in content, f"capture.py must import from {req.split(' ')[1]}"
