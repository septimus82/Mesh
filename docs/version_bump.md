# Version Bump CLI

## Command

```bash
python -m mesh_cli version bump patch
```

Supported bump kinds:

- `patch`: `X.Y.Z -> X.Y.(Z+1)`
- `minor`: `X.Y.Z -> X.(Y+1).0`
- `major`: `X.Y.Z -> (X+1).0.0`

Flags:

- `--dry-run`: preview bump without writing
- `--json`: deterministic JSON output (`{"old","new","file"}`)
- `--quiet`: suppress text output

## Safety Rules

The bump command only replaces the exact quoted version literal once in the canonical file.

It fails if:

- current version is not strict semver (`X.Y.Z`)
- literal is not found exactly once
- file cannot be read or written

## RC Integration

`mesh_cli release rc` supports:

- `--bump patch|minor|major` (mutually exclusive with `--version`)
- `--no-write-version` to preview the bumped version without modifying files
- `--no-rollback` to disable automatic rollback on RC failure

Default RC behavior is fail-safe rollback:

- when bump writes the version file and RC later fails, the original version file is restored.

Example:

```bash
python -m mesh_cli release rc --bump patch --out artifacts/rc_bundle.zip --seed 123 --quiet
```

