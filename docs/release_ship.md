# Release Ship (One Command)

`mesh_cli release ship` runs the deterministic release path end-to-end:

1. content audit preflight
2. RC build
3. RC -> final promotion
4. strict verification for both artifacts
5. unified ship report output

## Command

```bash
python -m mesh_cli release ship --out-dir artifacts/ship --seed 123 --quiet
```

Options:

- `--out-dir <dir>`: output directory (required)
- `--seed <N>`: deterministic seed (default `123`)
- `--bump patch|minor|major`: optional semantic bump routed through RC
- `--tag`: request final local tag creation during promote
- `--since <ref>`: optional release-notes start ref
- `--quiet`: suppress non-essential stdout
- `--json`: print `ship_report.json` payload to stdout
- `--dry-run`: plan-only mode; no ZIP outputs created

## Outputs

Inside `<out-dir>`:

- `rc_bundle.zip`
- `rc_bundle.zip.rc_report.json`
- `rc_bundle.zip.rc_report.txt`
- `content_audit_report.json` (when canonical content roots are present)
- `content_audit_report.txt` (when canonical content roots are present)
- `release_final.zip`
- `release_final.zip.promote_report.json`
- `release_final.zip.promote_report.txt`
- `ship_report.json`
- `ship_report.txt`

All report references use relative filenames only.

## Behavior Without Git

If git is unavailable:

- RC/promotion still run
- tag steps are marked `skipped` with reason
- shipping succeeds if strict verification passes

## Failure Semantics

- Fail-fast at first failing stage
- No "success-looking" final ZIP left behind on failure
- If `--bump` was requested and a later step fails, ship restores the original version file

## Verify Final Artifact

```bash
python -m mesh_cli bundle verify --zip artifacts/ship/release_final.zip
```
