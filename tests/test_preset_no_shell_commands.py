import pytest
from engine.config import load_config

def test_preset_no_shell_commands():
    """
    Asserts no preset step contains shell metacharacters or uses cmd="shell".
    """
    config = load_config()
    presets = getattr(config, "presets", {})
    
    forbidden_chars = ["&&", ";", "|", ">", "<", "$(", "`"]
    
    for preset_name, preset in presets.items():
        steps = []
        if isinstance(preset, list):
            steps = preset
        elif isinstance(preset, dict):
            steps = preset.get("steps", [])
            
        if not steps:
            continue
            
        for step in steps:
            cmd = step.get("cmd")
            args = step.get("args", [])
            
            # 1. No cmd="shell"
            assert cmd != "shell", f"Preset '{preset_name}' uses forbidden cmd='shell'"
            
            # 2. No shell metacharacters in args
            for arg in args:
                if not isinstance(arg, str):
                    continue
                for char in forbidden_chars:
                    assert char not in arg, f"Preset '{preset_name}' arg '{arg}' contains forbidden shell char '{char}'"
