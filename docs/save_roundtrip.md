# Save Round-Trip Policy

The save runtime now has a policy ratchet that treats save payload stability as a contract:

- Slot policy (`SLOT_POLICY`): strict schema + strict restore.
- Snapshot policy (`SNAPSHOT_POLICY`): strict schema + non-strict restore.
- Legacy upgrade path: deterministic one-time normalization, then stable output.

## Why this exists

Round-trip stability catches representation drift early:

- optional fields toggling between missing/empty/default
- key ordering churn creating noisy diffs
- legacy aliases repeatedly reappearing
- runner wrapper upgrades not becoming sticky

## Contract checks

`tests/test_save_roundtrip_policy.py` enforces:

1. Slot strict round-trip writes byte-identical JSON on repeated save/load cycles.
2. Snapshot non-strict round-trip preserves unknown keys and remains byte-identical.
3. Legacy payload upgrade (scene alias + dialogue runner v0) emits deterministic first-pass warnings, then becomes clean and byte-identical on the second pass.

## Run locally

```bash
python -m pytest -q tests/test_save_roundtrip_policy.py
python -m pytest -q
python -m mesh_cli verify-all --artifacts artifacts
```
