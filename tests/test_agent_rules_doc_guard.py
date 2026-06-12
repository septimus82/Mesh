from pathlib import Path

import pytest


def test_agent_rules_content():
    """
    Guard test to ensure AGENT_RULES.md exists and contains non-negotiable rules.
    """
    rules_path = Path("AGENT_RULES.md")
    if not rules_path.exists():
        pytest.fail(f"{rules_path} not found in repo root")

    content = rules_path.read_text(encoding="utf-8")

    required_phrases = [
        "Reuse-first",
        "Test Integrity",
        "Determinism",
        "plan.meta.touches",
        "full suite must be green",
    ]

    for phrase in required_phrases:
        assert phrase in content, f"AGENT_RULES.md missing required phrase: '{phrase}'"

def test_readme_links_rules():
    """
    Guard test to ensure README.md links to AGENT_RULES.md.
    """
    readme_path = Path("README.md")
    if not readme_path.exists():
        pytest.fail(f"{readme_path} not found in repo root")

    content = readme_path.read_text(encoding="utf-8")

    assert "AGENT_RULES.md" in content, "README.md must reference AGENT_RULES.md"
