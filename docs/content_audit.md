# Content Integrity Audit

`mesh_cli content audit` validates content registries and cross-file references with deterministic output.

## Command

```bash
python -m mesh_cli content audit --out-dir artifacts/content_audit
```

Options:

- `--out-dir <dir>`: required output directory for report artifacts.
- `--json`: print deterministic JSON to stdout instead of the text summary.
- `--quiet`: suppress stdout summary (reports are still written).

## Artifacts

The command always writes:

- `content_audit_report.json`
- `content_audit_report.txt`

Both files are deterministic for the same repo state.

## What It Checks

- Event registry uniqueness and naming conventions.
- Quest/cutscene/dialogue/prefab identifier uniqueness.
- Dialogue graph integrity (`start_node`, node links, choices).
- Scene prefab references.
- Cross-registry references:
  - event references/emissions must exist in `assets/data/events.json`
  - `dialogue_id` references must resolve from `assets/data/dialogues.json` or inline dialogue scripts
  - `cutscene_id` references must resolve from `cutscenes.json`
- Basic ratchets to catch accidental large content deletions.
- SHA256 digests for each scanned content file.

## Verify-All / Release Integration

- `mesh_cli verify-all` includes a `content-audit` step.
- `mesh_cli release ship` runs a preflight content audit and stops release artifacts on audit errors.

## Recommended Workflow

1. Run `mesh_cli verify-all`.
2. If `content-audit` fails, run `mesh_cli content audit --out-dir artifacts/content_audit`.
3. Fix reported file+pointer issues.
4. Re-run `verify-all` and then `release ship`.
