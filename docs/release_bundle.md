# Release Bundle — Reproducible Packaging

Package all release artifacts into a single deterministic ZIP.

## Quick Start

```bash
python -m mesh_cli release bundle --out artifacts/release_bundle.zip --seed 123
```

## What's Included

| ZIP Path | Source |
|----------|--------|
| `package_manifest.json` | Top-level manifest with SHA-256 hashes, sizes, versions |
| `package_manifest.txt` | Human-readable summary |
| `release_notes.json` | Deterministic release notes (machine-readable) |
| `release_notes.txt` | Deterministic release notes (human-readable) |
| `VERSION.json` | Engine version, git hash, Python version, platform |
| `release/` | Release check outputs (verify-all, asset audit, reports) |
| `demo/` | Demo pipeline outputs (new-game, replay traces, debug bundle, reports) |
| `bundle/` | Export build (shippable files + bundle manifest) |
| `audits/` | Collected audit reports (asset, brush, encounter, etc.) |

## Pipeline

The command runs these steps sequentially (fail-fast):

| # | Step | Description |
|---|------|-------------|
| 1 | `release-check` | Full release check (verify-all + asset audit + export + debug bundle) |
| 2 | `demo-run` | Demo pipeline (release check + new-game + replay + debug + export) |
| 3 | `export-build` | Standalone export build for the bundle directory |
| 4 | `collect-audits` | Gather audit files from release outputs + repo artifacts |

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--out PATH` | *(required)* | Output ZIP file path |
| `--seed N` | `42` | RNG seed for deterministic runs |
| `--campaign ID` | `mini_campaign_01` | Campaign identifier |
| `--deterministic-timestamp TS` | `1980-01-01T00:00:00Z` when `--seed` is set | Override manifest/provenance timestamp string |
| `--format json\|text` | `text` | Output format for final summary |
| `--quiet` | off | Suppress step output |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — ZIP produced |
| 1 | Pipeline step failed — ZIP not produced |
| 2 | Invalid arguments |

## Reproducibility Guarantees

The ZIP is **byte-identical** for the same repo state + seed + campaign:

- **Stable ordering**: Files sorted lexicographically by archive path
- **Fixed timestamps**: All `ZipInfo.date_time` set to `1980-01-01 00:00:00`
- **Consistent permissions**: `0o644` for all entries
- **Forward-slash paths**: No backslashes in archive names
- **No absolute paths**: All paths relative to the ZIP root
- **Deterministic JSON**: Sorted keys, stable formatting
- **Pinned metadata timestamp**: when `--seed` is set and no override is provided, timestamp defaults to `1980-01-01T00:00:00Z`

## Verifying Hashes

The `package_manifest.json` contains SHA-256 hashes for every file:

```python
import hashlib, json, zipfile

with zipfile.ZipFile("release_bundle.zip") as zf:
    manifest = json.loads(zf.read("package_manifest.json"))
    for path, entry in manifest["files"].items():
        content = zf.read(path)
        actual = hashlib.sha256(content).hexdigest()
        assert actual == entry["sha256"], f"Mismatch: {path}"
        assert len(content) == entry["size"], f"Size mismatch: {path}"
    print(f"All {manifest['file_count']} files verified.")
```

## Example Workflow

```bash
# 1. Build the release bundle
python -m mesh_cli release bundle --out dist/v0.4.0.zip --seed 42

# 2. Verify contents
python -c "
import zipfile
with zipfile.ZipFile('dist/v0.4.0.zip') as zf:
    zf.printdir()
"

# 3. Check reproducibility
python -m mesh_cli release bundle --out dist/v0.4.0_verify.zip --seed 42
# Compare: both ZIPs should be byte-identical
```

## CI Integration

```yaml
- name: Release Bundle
  run: |
    python -m mesh_cli release bundle \
      --out artifacts/release_bundle.zip \
      --seed 42 \
      --quiet \
      --format json
```

## Architecture

```
mesh_cli release bundle --out X.zip
        │
        ├─ 1. release check  ──→  release/
        ├─ 2. demo pipeline  ──→  demo/
        ├─ 3. export build   ──→  bundle/
        ├─ 4. collect audits ──→  audits/
        │
        ├─ package_manifest.json  (hashes + metadata)
        ├─ package_manifest.txt   (human-readable)
        ├─ release_notes.json     (deterministic notes)
        ├─ release_notes.txt      (deterministic notes)
        ├─ VERSION.json           (version + git hash)
        │
        └─ deterministic ZIP ──→  X.zip
```

The command creates a temporary work directory, runs all steps into it,
generates the manifest, writes the deterministic ZIP, then cleans up
the work directory.
