
import os
import re
import pytest

pytestmark = [pytest.mark.fast]

# Files that are allowed to import arcade directly/statically
# engine/optional_arcade.py is the bridge, so it must import it.
EXCLUSIONS = {
    os.path.normpath("engine/optional_arcade.py"),
}

# Directories to scan
SCAN_DIRS = [
    "engine",
    "mesh_cli",
    "tooling",
]

# Forbidden patterns
FORBIDDEN_REGEX = [
    (re.compile(r'^\s*import\s+arcade\b'), "Direct 'import arcade' is forbidden"),
    (re.compile(r'^\s*from\s+arcade\b'), "Direct 'from arcade ...' is forbidden"),
    (re.compile(r'from\s+engine\.optional_arcade\s+import\s+arcade\b'), "Stashing 'arcade' from optional_arcade is forbidden"),
]

def is_file_excluded(rel_path):
    norm_path = os.path.normpath(rel_path)
    for excl in EXCLUSIONS:
        if norm_path.endswith(excl):
            return True
    return False

def get_indentation(line):
    return len(line) - len(line.lstrip())

def test_no_arcade_imports():
    root_dir = os.getcwd()
    violations = []
    
    files_to_scan = []
    for d in SCAN_DIRS:
        start_dir = os.path.join(root_dir, d)
        if not os.path.exists(start_dir):
            continue
        for root, _, files in os.walk(start_dir):
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), root_dir)
                    if not is_file_excluded(rel_path):
                        files_to_scan.append(rel_path)

    for rel_path in sorted(files_to_scan):
        abs_path = os.path.join(root_dir, rel_path)
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            continue # Skip binary/weird files if any

        in_type_checking = False
        type_checking_indent = -1
        
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            
            current_indent = get_indentation(line)
            
            # Check if we are exiting a TYPE_CHECKING block
            if in_type_checking:
                if current_indent <= type_checking_indent:
                    in_type_checking = False
            
            # Check if we are entering a TYPE_CHECKING block
            if "TYPE_CHECKING" in line and stripped_line.startswith("if"):
                # Rough check for 'if TYPE_CHECKING:' or 'if typing.TYPE_CHECKING:'
                in_type_checking = True
                type_checking_indent = current_indent
                continue
            
            if in_type_checking:
                continue

            # Check for violations
            for pattern, msg in FORBIDDEN_REGEX:
                if pattern.search(line):
                    # Double check it's not a comment
                    # Rough comment check: if '#' is present before the match
                    match = pattern.search(line)
                    start_idx = match.start()
                    # Check if there is a hash before the match match
                    line_pre_match = line[:start_idx]
                    if '#' in line_pre_match:
                        continue # It's in a comment
                    
                    violations.append(f"{rel_path}:{i+1}: {msg} -> {stripped_line}")
                    break

    if violations:
        pytest.fail("\n".join(violations))

if __name__ == "__main__":
    # Allow running directly for quick check
    try:
        test_no_arcade_imports()
        print("No violations found.")
    except Exception as e:
        print(e)
        exit(1)
