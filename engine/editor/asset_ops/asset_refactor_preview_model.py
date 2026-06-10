"""
Pure model for formatting refactor previews (rename/move/delete).
Provides deterministic grouping, sorting, and summary generation.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .asset_refactor_model import Replacement

def group_modifications_by_file(modifications: Dict[str, List[Replacement]]) -> List[Tuple[str, int]]:
    """
    Sort modifications map into a deterministic list of (path, count).
    """
    items = []
    for path, repls in modifications.items():
        items.append((path, len(repls)))
    
    # Sort by path
    items.sort(key=lambda x: x[0])
    return items

def flatten_examples(modifications: Dict[str, List[Replacement]], limit: int = 5) -> List[str]:
    """
    Extract a deterministic list of example replacements (old -> new).
    Format: "old... -> new..."
    Sort by file path, then by field path/entity id.
    """
    examples = []
    
    # Sort files
    sorted_files = sorted(modifications.keys())
    
    count = 0
    for file_path in sorted_files:
        repls = modifications[file_path]
        # Sort replacements within file for determinism
        # Key: entity_id, field_path
        sorted_repls = sorted(repls, key=lambda r: (r.entity_id or "", r.field_path or ""))
        
        for r in sorted_repls:
            if count >= limit:
                break
            
            # Smart truncation for long paths
            old_s = r.old_value
            new_s = r.new_value
            if len(old_s) > 30:
                old_s = "..." + old_s[-27:]
            if len(new_s) > 30:
                new_s = "..." + new_s[-27:]
            
            examples.append(f"{old_s} -> {new_s}")
            count += 1
        
        if count >= limit:
            break
            
    return examples

def format_refactor_preview(
    title: str, 
    kind: str,
    fs_summary: str,
    modifications: Dict[str, List[Replacement]],
    details_expanded: bool = False
) -> List[str]:
    """
    Generate the lines for the modal preview.
    """
    lines = []
    
    # 1. Header / FS Ops
    lines.append(f"Operation: {kind.upper()}")
    lines.append(fs_summary)
    lines.append("") # Spacer
    
    # 2. JSON Updates Stats
    sorted_groups = group_modifications_by_file(modifications)
    total_files = len(sorted_groups)
    total_repls = sum(c for _, c in sorted_groups)
    
    lines.append(f"Updating References: {total_repls} changes in {total_files} files.")
    
    # 3. File Breakdown (Top N)
    limit_files = 10 if not details_expanded else 100
    
    for path, count in sorted_groups[:limit_files]:
        lines.append(f"  • {path}: {count}")
        
    if len(sorted_groups) > limit_files:
        lines.append(f"  ... and {len(sorted_groups) - limit_files} more files.")
        
    lines.append("")
    
    # 4. Examples (Top K)
    lines.append("Reference Examples:")
    examples = flatten_examples(modifications, limit=5)
    for ex in examples:
        lines.append(f"  > {ex}")
        
    if not examples and total_repls > 0:
        lines.append("  (No clear text examples)")
    elif not examples and total_repls == 0:
        lines.append("  (None)")
        
    return lines
