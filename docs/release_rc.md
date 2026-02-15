# Release Candidate Pipeline

## Command

```bash
python -m mesh_cli release rc --out artifacts/rc_bundle.zip --seed 123
```

Options:

- `--out <zip>`: required output bundle path
- `--seed <int>`: deterministic seed (default `123`)
- `--version <X.Y.Z>`: optional RC version override
- `--bump patch|minor|major`: optional semantic bump (mutually exclusive with `--version`)
- `--since <ref>`: optional release-notes start ref
- `--no-write-version`: compute bumped version but do not edit canonical version file
- `--no-rollback`: disable fail-safe rollback after a write bump
- `--quiet`: suppress non-essential stdout
- `--json`: print RC report JSON to stdout
- `--dry-run`: run planning steps only (no tag, no bundle build)

## Fixed Pipeline Order

1. Determine RC version (`--version` or `get_tool_version()`).
   - With `--bump`, computes the next semver and (by default) writes it before continuing.
2. Generate deterministic release notes (`release_notes.txt/json` in RC workdir).
3. Try local annotated tag `v<version>` (skipped when git is unavailable).
4. Build release bundle via existing `release bundle` pipeline (seeded, deterministic timestamp in RC mode).
5. Run strict post-build `bundle verify`.
6. Write unified RC reports next to the target ZIP:
   - `<zip>.rc_report.json`
   - `<zip>.rc_report.txt`

## Behavior Without Git

If git is missing:

- release notes still generate via fallback text
- tag step is marked `skipped` with reason `git unavailable`
- RC bundle build and strict verification still run normally

No network operations are performed by RC tagging.

## Version Bump Rollback

When `--bump` writes the version file and RC later fails, RC restores the original file by default.

Use `--no-rollback` only if you intentionally want to keep the bumped file after failure.

## Dry Run

`--dry-run` performs:

- version determination
- deterministic notes generation
- report emission

It does **not** create tags or produce a bundle ZIP.

## RC Report Contents

The RC report includes:

- selected version/seed/campaign and normalized args
- per-step results (`ok`, `skipped`, `reason`, `artifacts`)
- tag status (`created`, `skipped`, `existing`, `failed`)
- bundle verification summary (`file_count`, `verified_count`, `verifiable_files`, `sealed_manifest_verified`)
- deterministic provenance block

Paths stored in the report are filename-only (no absolute paths).
