# Versioning & Provenance

Every Mesh Engine artifact embeds a **provenance block** — a compact
record of the tool version, Python runtime, platform, git state, and
timestamp that produced it.  This closes the trust loop: given any
report, bundle, or manifest, you can trace it back to an exact build
environment.

## Version source of truth

The canonical version lives in `engine/version.py`:

```python
ENGINE_VERSION = "0.4.0"
```

This value is imported by the provenance module, the CLI `--version`
flag, and `pyproject.toml` (via `version = attr:engine.version.ENGINE_VERSION`).

## Provenance module

`engine/provenance.py` exposes:

| Symbol                    | Description                                     |
|---------------------------|-------------------------------------------------|
| `Provenance`              | Frozen dataclass with all provenance fields      |
| `get_provenance()`        | Build a snapshot (pass `deterministic=True` to   |
|                           | omit timestamps for reproducible output)         |
| `provenance_to_dict(p)`   | Convert to a dict (omits `None` fields)          |
| `format_provenance_text(p)` | Human-readable multi-line string               |

### Fields

| Field                | Type          | Notes                                  |
|----------------------|---------------|----------------------------------------|
| `tool_name`          | `str`         | Always `"Mesh Engine"`                 |
| `tool_version`       | `str`         | `ENGINE_VERSION` from `engine/version` |
| `build_timestamp_utc`| `str \| None` | ISO-8601 UTC; `None` in deterministic  |
| `python_version`     | `str`         | e.g. `"3.13.3"`                        |
| `platform`           | `str`         | `sys.platform` value                   |
| `git_commit`         | `str \| None` | Full SHA; `None` outside a git repo    |
| `git_dirty`          | `bool \| None`| `True` if uncommitted changes          |
| `git_describe`       | `str \| None` | `git describe --always --dirty`        |

### Git safety

All git helpers wrap `subprocess.run` in `try/except` and return `None`
on failure.  Provenance works correctly outside a git repository — the
git fields are simply omitted from the output dict.

## Artifacts with provenance

Every major output now contains a `"provenance"` key:

- **Demo report** (`mesh_cli demo pipeline`) — JSON and text
- **Release check report** (`mesh_cli release check`) — JSON and text
- **Package manifest** (`mesh_cli release bundle`) — embedded in ZIP
- **Export bundle manifest** (`tooling.export_bundle build`) — `bundle_manifest.json`

### Example JSON block

```json
{
  "provenance": {
    "tool_name": "Mesh Engine",
    "tool_version": "0.4.0",
    "python_version": "3.13.3",
    "platform": "win32",
    "build_timestamp_utc": "2025-01-15T12:34:56Z",
    "git_commit": "a1b2c3d4e5f6...",
    "git_dirty": false,
    "git_describe": "v0.4.0-7-ga1b2c3d"
  }
}
```

### Example text block

```
Tool: Mesh Engine 0.4.0
Python: 3.13.3
Platform: win32
Timestamp: 2025-01-15T12:34:56Z
Git: a1b2c3d4e5f6... 
Describe: v0.4.0-7-ga1b2c3d
```

## CLI commands

### `mesh_cli version`

Prints provenance info to stdout.

```
> mesh_cli version
Tool: Mesh Engine 0.4.0
Python: 3.13.3
Platform: win32
Git: a1b2c3d...
```

With `--json`:

```
> mesh_cli version --json
{"git_commit":"a1b2c3d...","platform":"win32","python_version":"3.13.3","tool_name":"Mesh Engine","tool_version":"0.4.0"}
```

### `mesh_cli version bump`

Safely bump semantic version in the canonical version file:

```bash
python -m mesh_cli version bump patch
python -m mesh_cli version bump minor --dry-run --json
```

See `docs/version_bump.md` for full details and RC integration behavior.

### `mesh_cli bundle verify <zip>`

Verifies the integrity of a release bundle ZIP.

Checks performed:
1. ZIP is readable
2. `package_manifest.json` exists and parses
3. Every listed file exists in the archive
4. SHA-256 hashes match
5. No absolute paths or `..` path traversal
6. Warns about unlisted files

```
> mesh_cli bundle verify dist/mesh_release.zip
Mesh Bundle Verify: dist/mesh_release.zip
  Result: OK (42/43 files verified)
```

With `--json`:

```
> mesh_cli bundle verify --json dist/mesh_release.zip
{"errors":[],"file_count":43,"ok":true,"verified_count":42,"warnings":[],"zip":"dist/mesh_release.zip"}
```

## Deterministic mode

When provenance is embedded during deterministic pipelines (e.g.
`release bundle`), the `build_timestamp_utc` field is populated
but the **rest** of the report maintains determinism via stable
JSON serialization (`dumps_json_deterministic`), sorted keys, and
fixed ZIP timestamps.

For test assertions that require byte-identical output across runs,
use `get_provenance(deterministic=True)` to omit the timestamp.

## Tests

| Test file                              | What it covers            |
|----------------------------------------|---------------------------|
| `test_provenance_contract.py`           | Dataclass, dict, text     |
| `test_cli_version_command.py`           | `mesh_cli version`        |
| `test_cli_bundle_verify_command.py`     | `mesh_cli bundle verify`  |
