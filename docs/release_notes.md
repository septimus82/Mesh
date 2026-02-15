# Release Notes and Tagging

## Overview

`mesh_cli release notes` generates release notes from git commit subjects with a stable
section mapping and deterministic formatting.

`mesh_cli release tag` creates a **local annotated git tag** only. It does not push to any remote.

Release bundles also embed release notes at ZIP root:

- `release_notes.txt`
- `release_notes.json`

Both files are included in `package_manifest.json` hashing and strict bundle verification.

## Release Notes Generation

Command:

```bash
python -m mesh_cli release notes --deterministic
```

Options:

- `--since <ref>`: optional start ref (`tag`/`commit`)
- `--until <ref>`: optional end ref (default `HEAD`)
- `--json`: emit JSON instead of text
- `--out <path>`: optional file or directory output target
- `--deterministic`: deterministic mode (stable wording/ordering, no volatile timestamps)

Range selection behavior:

1. If `--since` is provided, uses `since..until` (or `since..HEAD`).
2. Otherwise, uses `last_tag..until` if tags exist.
3. If no tags exist, uses the latest 50 commits (up to `until`).

If git is unavailable, output is still valid with:

- section `Other`
- item `Git metadata unavailable; no commit log.`

## Section Mapping

Commit subjects are mapped by prefix:

- `feat:` -> `Features`
- `fix:` -> `Fixes`
- `perf:` -> `Performance`
- `refactor:` -> `Refactor`
- `chore:` -> `Tooling`
- `test:` -> `Tests`
- `docs:` -> `Docs`
- everything else -> `Other`

Section ordering is fixed and deterministic.

## Output Paths

When `--out` points to a directory (existing or inferred):

- text mode writes `release_notes.txt`
- JSON mode writes `release_notes.json`

When `--out` points to a file path, that exact file is written.

## Local Tagging

Command examples:

```bash
python -m mesh_cli release tag --auto
python -m mesh_cli release tag --name v0.4.0 --message "Mesh 0.4.0"
python -m mesh_cli release tag --auto --dry-run
```

Behavior:

- `--auto` uses `v<tool_version>` from canonical version source.
- `--name` sets explicit tag name.
- fails if git is unavailable.
- fails if the tag already exists.
- creates local annotated tag only (`git tag -a ...`), no network activity.

