# Release Promote (RC -> Final)

`mesh_cli release promote` turns an existing RC bundle into a final release artifact with an auditable promotion report.

## Command

```bash
python -m mesh_cli release promote \
  --rc artifacts/rc_bundle.zip \
  --out artifacts/release_final.zip
```

Options:

- `--version <X.Y.Z>`: override target version (otherwise from RC provenance, fallback tool version)
- `--tag`: create local annotated tag `v<version>` (no network push)
- `--notes-since <ref>`: optional git ref for tag-message notes generation
- `--quiet`: suppress non-essential stdout
- `--json`: print promote report JSON to stdout
- `--dry-run`: verify RC and plan steps without writing output ZIP

## Fixed Pipeline

1. Strict verify RC ZIP (`bundle verify` core in-process).
2. Determine release version (`--version`, RC provenance, then tool version fallback).
3. Optional local tag step.
4. Rebuild deterministic final ZIP with:
   - `promote/promote_report.json`
   - `promote/promote_report.txt`
   - refreshed `package_manifest.*` and `manifest_seal.json`
5. Strict verify final ZIP.

If RC verification fails, promotion stops and no output ZIP is produced.

## No-Git Behavior

Promotion works without git. If `--tag` is set and git is unavailable:

- tag step is `skipped`
- reason is `git unavailable`
- promotion still succeeds if all verification checks pass

## Reports

Promotion writes reports next to the output ZIP:

- `<out>.promote_report.json`
- `<out>.promote_report.txt`

Reports include:

- RC and final ZIP filenames (no absolute paths)
- RC verify summary
- final verify summary
- target version
- tag result
- deterministic provenance block

## Verify Result

```bash
python -m mesh_cli bundle verify --zip artifacts/release_final.zip
```

