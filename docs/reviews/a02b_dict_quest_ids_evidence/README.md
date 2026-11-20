# A-02b evidence: dict-form quests load with their key as id

Base 0e05bd94723f8eb137acd900b1bc03ada0ba59e2.

- base_run.txt.txt: tests/test_quest_dict_form_ids.py on the base loader: 5 failed, 3 passed (id==key, list form and
  the 8th case pass on the base, as intended).
- head_run.txt.txt: same file with the fix: 8 passed.
- fault_injection.txt: 5 mutations of the fix, 4 caught; the 5th (mutating `raw` in place) is equivalent because the
  loader re-reads the file on every load; `engine/quests.py` restored byte for byte (sha256 prefix c6d80f559818cfbe).
- suites.txt: every test referencing QuestManager / load_definitions / quest_runtime.normalize plus
  test_ai_quest_forms, test_test_lanes_contract, test_logging_policy_contract: 465 passed, 5 deselected (marker).
- gates.txt: ruff_gate, mypy_gate, scan_exception_policies.
