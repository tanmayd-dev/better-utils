import pytest
import os
from pathlib import Path

def run_tests_for_tool(tool_path: str):
    """
    Runs tests for a specific tool file.
    Assumes tests are in a 'tests' subdirectory or named 'test_<tool_name>.py' alongside.
    """
    p = Path(tool_path)
    tool_dir = p.parent
    test_dir = tool_dir / "tests"
    
    test_files = []
    
    # Look for tests/test_<name>.py
    if test_dir.exists():
        possible_test = test_dir / f"test_{p.name}"
        if possible_test.exists():
            test_files.append(str(possible_test))
            
    # Look for test_<name>.py in same dir
    sibling_test = tool_dir / f"test_{p.name}"
    if sibling_test.exists():
        test_files.append(str(sibling_test))
        
    if not test_files:
        return {"status": "no_tests", "output": "No tests found."}
        
    # Run pytest
    # We capture output to return it
    from _pytest.main import ExitCode
    
    class Plugin:
        def __init__(self):
            self.passed = 0
            self.failed = 0
            self.output = []
            
        def pytest_runtest_logreport(self, report):
            if report.when == 'call':
                if report.passed:
                    self.passed += 1
                elif report.failed:
                    self.failed += 1
                    
    plugin = Plugin()
    ret = pytest.main(test_files, plugins=[plugin])
    
    status = "passed" if ret == ExitCode.OK else "failed"
    
    return {
        "status": status,
        "passed": plugin.passed,
        "failed": plugin.failed,
        "files": test_files
    }
