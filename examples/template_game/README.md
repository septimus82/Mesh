# Template Game (Public API v1)

This template demonstrates consuming Mesh through the stable public API only.

## Run

From repo root:

```powershell
python examples/template_game/main.py
```

Optional scene path:

```powershell
python examples/template_game/main.py scenes/main_menu.json
```

## Installed-Mode Run

Build/install first:

```powershell
python -m build
python -m pip install dist/*.whl
```

Run from installed package:

```powershell
python -m examples.template_game.main --project-root examples/template_game/sample_project --scene scenes/cellar.json
```

## Import Rule

`examples/template_game/main.py` imports only:

- Python stdlib
- `engine.public_api`

It does not import internal engine modules directly.
