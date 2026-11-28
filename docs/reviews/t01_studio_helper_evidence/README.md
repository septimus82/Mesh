# T-01 evidence

Reproduction (`repro_sharing_violation.py.txt`, run with `py -3.13`, Windows 11):
- A file opened with `CreateFileW(..., share mode 0)` makes `Path.read_text` raise `PermissionError: [Errno 13]`
  with `winerror None` (the C runtime's open reports a sharing violation as errno 13 only), while `is_file()` stays True.
  So the helper's `waiting.is_file()` then `waiting.read_text()` fails exactly as the one local death did.
- Not reproduced: a 3000-round replace-then-read stress with a concurrent no-share scanner thread gave 0 errors
  (the window is too narrow to hit on demand). The CI exception (run 44589776415) stays unconfirmed: its stderr log was never shown.
- Fault injection: with the retry disabled, `test_a_sharing_violation_that_clears_is_retried` fails (PermissionError).

Tests: adjacent suites (ownership, MCP ownership, ai_write_paths*, lanes/logging/exception-policy contracts + new tests)
3 rounds, `-W error`: 124 passed, 1 skipped each. GPU save/tileset ownership (MESH_GL_SMOKE=1): 2 passed.
