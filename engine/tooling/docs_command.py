import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, cast

from engine.tooling.metadata import get_command_metadata
from engine.tooling.recipes_command import RECIPES
from engine.tooling.release_command import PROFILES


def generate_markdown(parser: argparse.ArgumentParser) -> Dict[str, str]:
    """Generate markdown content for all documentation pages."""
    pages = {}

    # 1. Commands
    commands = get_command_metadata(parser)
    lines = ["# Mesh CLI Commands", "", "Reference documentation for all available CLI commands.", ""]

    for cmd in commands:
        lines.append(f"## `mesh {cmd['name']}`")
        lines.append(f"{cmd['description']}")
        lines.append("")

        if cmd['args']:
            lines.append("### Arguments")
            lines.append("| Flag | Name | Type | Required | Default | Help |")
            lines.append("|---|---|---|---|---|---|")
            for arg in cmd['args']:
                flags = ", ".join(arg['flags']) if arg['flags'] else ""
                req = "Yes" if arg['required'] else "No"
                default = f"`{arg['default']}`" if arg['default'] else "-"
                lines.append(f"| `{flags}` | `{arg['name']}` | `{arg['type']}` | {req} | {default} | {arg['help']} |")
            lines.append("")

    pages["commands.md"] = "\n".join(lines)

    # 2. Recipes
    lines = ["# Workflow Recipes", "", "Common workflows and how to execute them.", ""]
    for key, recipe in RECIPES.items():
        lines.append(f"## {recipe['title']}")
        lines.append("```bash")
        for step in recipe['steps']:
            lines.append(step)
        lines.append("```")
        lines.append("")
    pages["recipes.md"] = "\n".join(lines)

    # 3. Profiles
    lines = ["# Release Profiles", "", "Configuration profiles for `mesh release-check`.", ""]
    for name, config in PROFILES.items():
        lines.append(f"## {name.upper()}")
        lines.append("| Setting | Value |")
        lines.append("|---|---|")
        for k, v in config.items():
            lines.append(f"| `{k}` | `{v}` |")
        lines.append("")
    pages["profiles.md"] = "\n".join(lines)

    # 4. Audit (Static + Config explanation)
    lines = [
        "# Content Audit System", "",
        "The audit system ensures project hygiene by detecting unused assets and enforcing limits.",
        "",
        "## Key Concepts",
        "- **Baseline**: A snapshot of unused assets stored in `content.lock.json`.",
        "- **Delta**: The difference between current unused assets and the baseline.",
        "- **Categories**: Assets are grouped into `texture`, `audio`, `data`, etc.",
        "",
        "## Configuration",
        "Audit policies can be configured in `config.json` under `audit_policy`.",
    ]
    pages["audit.md"] = "\n".join(lines)

    # 5. Packs (Static explanation)
    lines = [
        "# Content Packs", "",
        "Mesh supports modular content via Packs.",
        "",
        "## Structure",
        "- `manifest.json`: Metadata (ID, version, dependencies).",
        "- `scenes/`: Scene files.",
        "- `assets/`: Raw assets.",
        "",
        "## Types",
        "- `core`: Base game content.",
        "- `mod`: User modifications.",
        "- `dlc`: Official expansions.",
        "- `demo`: Demo-specific content.",
    ]
    pages["packs.md"] = "\n".join(lines)

    # 6. Traces (Static explanation)
    lines = [
        "# Event Tracing", "",
        "The trace system records and replays game events for debugging and regression testing.",
        "",
        "## Commands",
        "- `mesh trace --record`: Capture a session.",
        "- `mesh trace --replay`: Replay a session.",
        "- `mesh check --replay-trace`: Validate a trace against current logic.",
    ]
    pages["traces.md"] = "\n".join(lines)

    return pages

def docs_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Generate documentation."""

    pages = generate_markdown(parser)

    if args.json:
        print(json.dumps(pages, indent=2))
        return

    out_dir = Path(args.out) if args.out else Path("docs/generated")

    if args.verify:
        print("[Mesh][Docs] Verifying documentation...")
        if not out_dir.exists():
            print(f"[Mesh][Docs] FAILURE: Output directory '{out_dir}' does not exist.")
            sys.exit(1)

        failed = False
        for filename, content in pages.items():
            file_path = out_dir / filename
            if not file_path.exists():
                print(f"[Mesh][Docs] FAILURE: Missing file '{filename}'")
                failed = True
                continue

            existing = file_path.read_text(encoding="utf-8")
            # Normalize newlines
            if existing.replace("\r\n", "\n").strip() != content.replace("\r\n", "\n").strip():
                print(f"[Mesh][Docs] FAILURE: Content mismatch in '{filename}'")
                failed = True

        if failed:
            print("[Mesh][Docs] Verification FAILED. Run 'mesh docs' to regenerate.")
            sys.exit(1)
        else:
            print("[Mesh][Docs] Verification PASSED.")
            return

    # Generate mode
    print(f"[Mesh][Docs] Generating documentation to '{out_dir}'...")
    out_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in pages.items():
        (out_dir / filename).write_text(content, encoding="utf-8")
        print(f"  - Wrote {filename}")

    print("[Mesh][Docs] Done.")

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate documentation")
    parser.add_argument("--out", help="Output directory")
    parser.add_argument("--verify", action="store_true", help="Verify docs are up-to-date")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args(argv)

    try:
        from mesh_cli import create_parser
        full_parser = create_parser()
    except ImportError:
        print("Error: Could not import create_parser from mesh_cli")
        return 1

    try:
        docs_command(args, full_parser)
        return 0
    except SystemExit as e:
        return cast(int, e.code)  # argparse exits with int codes; preserve runtime behavior
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
