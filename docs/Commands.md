## Player build commands

### `package-player`

Builds a deterministic runtime-only "player package" and (optionally) runs a packaged smoke.

```bash
python -m mesh_cli package-player --out artifacts/player_pkg
python -m mesh_cli package-player --out artifacts/player_pkg --smoke
```

Outputs:

- `artifacts/player_pkg/manifest.json`
- `artifacts/player_pkg/package_check.json`
- `artifacts/player_pkg/runtime_smoke.json` (when `--smoke`)

### `play-runtime` (smoke)

Runs the runtime-only smoke without editor imports.

```bash
python -m mesh_cli play-runtime --headless-smoke --smoke-artifact artifacts/runtime_smoke.json
```

## Shipping readiness command

### `ship-check`

Runs shipping readiness orchestration and prints a deterministic summary.
By default it runs:

- `verify-all --ci-bundle`
- `package-player --smoke`
- `web-smoke`

```bash
python -m mesh_cli ship-check --artifacts artifacts
```

Useful optional flags:

- `--skip-package`
- `--skip-web`
- `--skip-perf`
- `--skip-verify`
- `--quiet`
