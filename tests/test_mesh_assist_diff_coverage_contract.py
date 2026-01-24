import json
import pytest
from pathlib import Path
from engine.tooling import assist_command
from engine.tooling.plan_linter import WRITING_ACTIONS

def test_diff_coverage_contract():
    """
    Enforce contract:
    WRITING_ACTIONS == DIFF_SUPPORTED ∪ DIFF_SKIPPED
    DIFF_SUPPORTED ∩ DIFF_SKIPPED == ∅
    """
    # 1. WRITING_ACTIONS is imported from plan_linter
    
    # 2. Get lists from assist_command
    supported = assist_command.DIFF_SUPPORTED_ACTIONS
    skipped = assist_command.DIFF_SKIPPED_ACTIONS
    
    # 3. Verify Contract
    
    # Check for overlap
    overlap = supported & skipped
    assert not overlap, f"Actions overlap in supported and skipped: {overlap}"
    
    # Check for coverage
    covered = supported | skipped
    
    missing = WRITING_ACTIONS - covered
    extra = covered - WRITING_ACTIONS
    
    assert not missing, f"Writing actions missing from diff logic: {missing}"
    assert not extra, f"Extra actions in diff logic (not in schema or non-writing): {extra}"
