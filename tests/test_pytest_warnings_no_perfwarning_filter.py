
import pytest
from pathlib import Path

def test_pytest_warnings_no_perfwarning_filter():
    ini_path = Path("pytest.ini")
    if not ini_path.exists():
        # Maybe running from tests/ ??
        ini_path = Path("../pytest.ini")
    
    if not ini_path.exists():
        pytest.skip("pytest.ini not found")
        
    content = ini_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or clean.startswith(";"):
            continue
        # Check for active filter
        if "ignore" in clean and "PerformanceWarning" in clean:
            pytest.fail(f"pytest.ini still contains ignore filter for PerformanceWarning: {line}")
