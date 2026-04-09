# How to ship a player build (runtime-only)

This repo ships "player builds" as a deterministic runtime-only package that excludes all editor code. The package is validated by `verify-all` via the `player-package-gate` step and includes a runtime smoke artifact.

## Quick start

### 1) Build a player package (local)

```bash
python -m mesh_cli package-player --out artifacts/player_pkg
```

This writes:

- `artifacts/player_pkg/manifest.json`
- `artifacts/player_pkg/package_check.json`

### 2) Build + run packaged smoke (recommended)

```bash
python -m mesh_cli package-player --out artifacts/player_pkg --smoke
```

This additionally writes:

- `artifacts/player_pkg/runtime_smoke.json`

## What "player-only" means

A player package must:

- include only runtime Python sources and the minimal content needed to boot
- exclude all editor code paths and editor-only UI/actions
- be deterministic (stable file ordering + stable manifest)
- be runnable via runtime-only entry points

## Exclusion rules

Packaging enforces "no editor imports/files" using the same forbidden-prefix boundary list used by runtime-only gates. If forbidden hits are detected, packaging fails.

## Package outputs

### `manifest.json` (deterministic)

Fields (`schema_version` 1):

- `schema_version`
- `created_by`
- `package_root`
- `included_files` (sorted)
- `excluded_prefixes` (sorted)
- `runtime_entry`
- `content_roots_included`
- `checks` (`file_count`, `total_bytes`, `forbidden_hits`)

### `package_check.json`

A deterministic validation payload produced by the packaging gate. It must report:

- `ok: true`
- `forbidden_hits: []`

### `runtime_smoke.json`

Produced when `--smoke` is used (or by CI gate). Confirms:

- runtime launch succeeds
- smoke scene loads
- no forbidden editor imports occurred
- diagnostics are captured deterministically

## CI / verify gate

```bash
python -m mesh_cli verify-all --artifacts artifacts --ci-bundle
```

Includes:

- `player-package-gate`
- `web-smoke`
- builds `artifacts/player_pkg`
- validates cleanliness + manifest determinism
- runs packaged runtime smoke

If this step fails, the build is not considered shippable.

## Troubleshooting

### Packaging fails with forbidden hits

Check `artifacts/player_pkg/package_check.json` for `forbidden_hits`.

Root cause is usually an unintended import chain from runtime into editor modules.

Fix by moving the import behind an editor-only code path or removing the dependency.

### Smoke fails but package builds

Inspect `artifacts/player_pkg/runtime_smoke.json`:

- `diagnostics` for structured errors/warnings
- `forbidden_imports_found` must be empty

Ensure required smoke scene/content is included in the package.

## Suggested release workflow

1. Ensure working tree is clean.
2. Run:

```bash
python -m mesh_cli verify-all --artifacts artifacts --ci-bundle
```

3. Build package:

```bash
python -m mesh_cli package-player --out artifacts/player_pkg --smoke
```

4. Distribute `artifacts/player_pkg/` as the player build artifact.
