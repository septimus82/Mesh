
import os
import re


def test_ui_module_is_thin_facade():
    """
    Ensure engine/ui.py remains a thin facade re-exporting symbols from submodules.
    It should not contain significant implementation logic or new class definitions.
    """
    ui_path = os.path.join("engine", "ui.py")
    if not os.path.exists(ui_path):
        # If running from tests dir
        ui_path = os.path.join("..", "engine", "ui.py")

    assert os.path.exists(ui_path), "engine/ui.py not found"

    with open(ui_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. Check line count budget
    # Current size is around ~290 lines. Setting budget to 400 to allow for imports/exports but prevent logic creep.
    non_empty_lines = [line for line in lines if line.strip()]
    line_count = len(non_empty_lines)
    assert line_count <= 400, f"engine/ui.py has {line_count} lines, exceeding budget of 400. Move logic to engine/ui_overlays/."

    # 2. Check for class definitions
    # Only InventoryOverlay is allowed for now (legacy).
    allowed_classes = {"InventoryOverlay"}

    class_def_pattern = re.compile(r"^\s*class\s+(\w+)")

    defined_classes = []
    for i, line in enumerate(lines):
        match = class_def_pattern.match(line)
        if match:
            class_name = match.group(1)
            if class_name not in allowed_classes:
                defined_classes.append((i + 1, class_name))

    if defined_classes:
        details = "\n".join([f"Line {line}: {name}" for line, name in defined_classes])
        raise AssertionError(
            f"Found unexpected class definitions in engine/ui.py. "
            f"Move these to engine/ui_overlays/ and re-export them:\n{details}"
        )
