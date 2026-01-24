import json
from pathlib import Path
from typing import Optional


def generate_dot_graph(world_path: str) -> str:
    """Generate a DOT graph from a world file."""
    path = Path(world_path)
    if not path.exists():
        raise FileNotFoundError(f"World file not found: {world_path}")

    with path.open("r", encoding="utf-8") as f:
        world = json.load(f)

    scenes = world.get("scenes", {})
    links = world.get("links", [])

    lines = ["digraph World {", "  node [shape=box style=filled fillcolor=lightgrey];"]

    # Add nodes
    for key, data in scenes.items():
        label = key
        if "path" in data:
            label += f"\\n({data['path']})"
        lines.append(f'  "{key}" [label="{label}"];')

    # Add edges
    for link in links:
        src = link.get("from")
        dst = link.get("to")
        if src and dst:
            lines.append(f'  "{src}" -> "{dst}";')

    lines.append("}")
    return "\n".join(lines)

def export_graph(world_path: str, output_path: Optional[str] = None) -> bool:
    try:
        dot_content = generate_dot_graph(world_path)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dot_content)
            print(f"[Mesh][Graph] Exported world graph to '{output_path}'")
        else:
            print(dot_content)
        return True
    except Exception as e:
        print(f"[Mesh][Graph] ERROR: {e}")
        return False
