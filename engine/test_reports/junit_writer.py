import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict


def write_junit_report(report: Dict[str, Any], output_path: str) -> None:
    """
    Convert a TestReport dict to JUnit XML format.

    Structure:
    <testsuites>
      <testsuite name="MeshPlanTests" tests="..." failures="..." errors="...">
        <testcase name="..." classname="..." time="...">
          <failure message="..."/>
        </testcase>
      </testsuite>
    </testsuites>
    """

    test_cases = report.get("tests", [])
    failures = sum(1 for t in test_cases if not t.get("passed"))
    errors = sum(1 for t in test_cases if t.get("error") and not t.get("passed")) # Assuming error implies failure

    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", {
        "name": "MeshPlanTests",
        "tests": str(len(test_cases)),
        "failures": str(failures),
        "errors": str(errors),
        "timestamp": datetime.now().isoformat()
    })

    for test in test_cases:
        case = ET.SubElement(suite, "testcase", {
            "name": test.get("name", "Unknown Test"),
            "classname": f"PlanTest.{test.get('type', 'generic')}",
            "time": "0.0" # We don't track time per test yet
        })

        if not test.get("passed"):
            error_msg = test.get("error", "Test failed")
            failure = ET.SubElement(case, "failure", {
                "message": str(error_msg),
                "type": "AssertionError"
            })
            failure.text = str(error_msg)

    tree = ET.ElementTree(root)
    try:
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
    except Exception as e:
        print(f"[Mesh][JUnit] Failed to write report: {e}")
