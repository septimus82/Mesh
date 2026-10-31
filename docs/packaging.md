# Packaging: what a pip-installed Mesh carries

A wheel only contains files inside its Python packages (`engine`, `mesh_cli`); `MANIFEST.in` lists the source
distribution's data, and none of it reached the wheel. Since Milestone 16 Stage 6B a pip-installed Mesh carries exactly
the engine's own files that installed workflows need, and nothing else. It was ported and extended from the earlier
packaging change (PR #345), which was built on an older `main`.

## What an installed engine reads from itself (measured)

A game's content resolves only inside its project (since `643970a`). The engine reads its own files in these
places, all through one lookup (`engine.repo_root.bundled_file` / `bundled_dir`):

| Reader | What it reads |
|---|---|
| `project_scaffold.create_project` / `ensure_starter_files` | The starter files every new project gets, and `config.json` for the default input bindings |
| `project_templates` (HD-2D RPG: `engine.hd2d.starter_village`) | The HD-2D starter kit (installed into the project's model catalogue), the HD-2D characters, ground textures, interface sounds |
| `project_scaffold` (monster template) | The monster data, battle sounds and music |
| `paths.resolve_engine_bundled_path` | `assets/data/monster_*` (the one fallback content isolation keeps) |
| `studio_ui` | Mesh Studio's branding and button icons |
| `launcher` | The template pictures |
| The `engine` package itself | `engine/schemas/*.json`, the schemas every scene, prefab, entity, cutscene and config is validated against (`[tool.setuptools.package-data]`; before Stage 6B a pip-installed Mesh couldn't create a project at all without them) |

**How it was measured:** every template's project was created from the source tree, and each file in it was matched
by content to the engine file it came from. Then the wheel was installed into a clean environment outside any
repository, where creating projects, Mesh Studio, play and export were all exercised
(`tooling/hd2d_install_acceptance.py`). It now finds everything it uses.

## The allow-list

`pyproject.toml`'s `[tool.setuptools.data-files]` names **178 files** (1.07 MB) by path, so nothing goes in by accident.
pip installs them under `<prefix>/share/mesh-engine/`, the conventional place for an application's shared data.

| Group | Files | Size |
|---|---|---|
| `config.json` | 1 | 35 KB |
| Monster data (`assets/data/monster_*.json`) | 3 | 2 KB |
| Sounds (`attack`, `die`, `hit`, `ui_*`) and music (`dungeon_theme`) | 8 | 468 KB |
| Sprites: starter hero, villager, sign; HD-2D hero, villager, merchant; door | 7 | 12 KB |
| Starter tileset | 2 | 9 KB |
| Launcher template pictures (Blank, Top-down Adventure, HD-2D RPG Preview) | 3 | 86 KB |
| The HD-2D RPG (Preview)'s creator help (`docs/hd2d_preview.md`, copied into new HD-2D projects) | 1 | 6 KB |
| HD-2D starter kit: 14 models, 14 previews, 2 textures, catalogue, provenance | 32 | 272 KB |
| Mesh Studio branding, with its notice | 10 | 122 KB |
| Mesh Studio icons: PNGs, the Lucide SVGs, `NOTICE.md` and the ISC `LICENSE` | 110 | 61 KB |
| `assets/NOTICE.md`: provenance and licence of every bundled file | 1 | 2 KB |

**Licences:** see `assets/NOTICE.md`.

- Everything is Mesh's own work, except two groups:
  - **The branding** is © MeshMind Studios and not covered by the code licence (`assets/branding/NOTICE.md`).
  - **The icons** are Lucide's, under ISC. The licence text is shipped with them, as ISC requires.
- **Never bundled:** `animated_player.png`, `sproutling.png` and `shelltide.png`, whose provenance is unverified.
  - No template's new project uses `animated_player.png`, so new projects no longer get it, from a checkout or an
    install. An older project that names it still does.
  - The developer-only monster template names the other two. In a pip install its creatures fall back to the
    placeholder (PR #311) until they are replaced with Mesh's own art.

**Size:** the wheel is 2.55 MB without the bundled files and **3.24 MB** with them. `packs/` is not bundled, and
isn't needed.

**To bundle another file:**

1. Check its licence.
2. Add it to `assets/NOTICE.md` and to `[tool.setuptools.data-files]`.
3. `tests/test_wheel_bundles_engine_data.py` then expects it.

## Exporting a game from an installed Mesh (issue #357)

`mesh export build`, run in a project folder, writes a standalone game to `dist/bundle`:

- the project's `main.py`, `config.json`, `packs/`, `locales/*.json` and every file in its `assets/`;
- the installed `engine` package as its runtime;
- the engine's interface text, `share/mesh-engine/locales/*.json` (the installed Mesh's allow-listed copy);
- `bundle_manifest.json`, with each file's hash and no path of the maker's machine.

It runs with `python main.py` wherever Mesh's dependencies (arcade, pillow, jsonschema) are installed, without Mesh.
It replaces only an earlier bundle or an empty folder, never other files.

**Replacing an earlier export (F4, #422).** A failed export never costs the last good one:

- **Built aside first.** The new bundle is built in `.bundle~new/b` beside the output folder: every file copied and
  hashed as it is copied (a file saved mid-export stops it), the manifest written and read back, and the folder checked
  against it. Nothing in `dist/bundle` is touched until all of that has succeeded; any failure deletes `.bundle~new`
  and leaves the earlier export as it was.
- **Then handed over.** The earlier bundle is moved to `.bundle~old/b`, the new one to `bundle`, and both working
  folders are deleted. On Windows a folder briefly in use is retried for about 1.5 s; one that stays in use (the game
  running from it) stops the export with the earlier one unchanged. If the second move fails, the first is undone. If
  that fails too, both are kept and the error names them: the earlier export in `.bundle~old/b`, the new one in
  `.bundle~new/b`. If a working folder can't be deleted at the end, the export still succeeds and a warning names it.
- **Which folders are the export's own.** Each export picks a random token, records it in a journal beside the output
  (`.bundle~export.json`, written whole and renamed into place) and writes it into each working folder
  (`.mesh-export-owner`) the moment it makes it, before anything of value is in it. A working folder is the export's
  only if its owner file holds the journal's token and it holds nothing else but its `b`. A folder's name proves
  nothing, and nor does its identity (a deleted folder's inode is handed to the next new folder at once on Linux). A
  folder named like a working folder that isn't the export's, or a journal it can't read, stops the export and is
  left untouched.
- **Stopped between the two moves.** The moves aren't atomic together. An export killed between them leaves no `bundle`,
  the earlier one in `.bundle~old/b` and the journal; the next export to that folder moves it back before anything else
  (and says so). The export's own `.bundle~new` left behind is an unfinished or unpublished build and is deleted. Its
  own `.bundle~old/b` beside a complete, unchanged `bundle` is a superseded copy and is deleted, but only if it is
  unchanged too; beside an empty or foreign `bundle`, or changed, it is kept and the export stops, naming both. An empty
  working folder (made just before an export stopped) is removed.
- **What counts as an earlier bundle.** A folder whose `bundle_manifest.json` is well formed (every entry a path inside
  the folder with its SHA-256 and size, no entry twice) and matches it exactly: every listed file there, of its size and
  SHA-256, and nothing else but the bytecode Python writes beside a listed `.py` when the game runs. A changed, missing
  or truncated file, an older game's `saves/`, or a user's files beside a copied manifest stop the export with the
  problems named and nothing changed; so does a link or junction anywhere in it, or as the output folder: they are
  never followed or emptied.
- One export at a time per output folder.

**Where an exported game saves (H9, #422).** Never in its installation, which may be read-only. Each player's saves
go to their own application-data folder, under the game's `game_id` (from `config.json`):

| Platform | Saves |
|---|---|
| Windows | `%APPDATA%\MeshMind Studios\<game id>\saves` |
| macOS | `~/Library/Application Support/MeshMind Studios/<game id>/saves` |
| Linux | `$XDG_DATA_HOME/MeshMind Studios/<game id>/saves` (`~/.local/share/...` when unset) |

- **What counts as an export:** a game counts as exported when its folder holds `bundle_manifest.json`, which only
  `mesh export build` writes. A project run in Mesh Studio or with `python main.py` keeps saving to its own `saves`
  folder.
- **Moving and reinstalling:** the game can be moved or reinstalled and keeps its saves. Two games never share
  saves, even with the same title.
- **The game id:** new projects get a `game_id` when they are made. An older project without one gets an id
  derived from its title, start room and world file. Two such projects that match in all three share a folder;
  give one a `game_id` (lowercase letters, digits, `.`, `_`, `-`) to separate them.
- **Saves made before H9:** saves an export kept in `<installation>/saves` are still listed and loaded, and are
  never changed. Saving that slot again writes the player's folder, whose copy then loads first.
- **Overrides:** `MESH_SAVE_DIR` names the saves folder (tests, automation). The policy is in
  `engine.save_runtime.storage`.

**Where an exported game keeps its player's settings (H9.1).** The settings are music, effects and ambience
volumes, fog and calmer flickering. They go in `user_settings.json`, beside `saves` in the same per-player game
folder (`%APPDATA%\MeshMind Studios\<game id>\user_settings.json` and so on).

- **Precedence:** a path given in code, then `MESH_RUNTIME_SETTINGS_PATH`, then this file. `MESH_SAVE_DIR` doesn't
  move it. A project keeps `user_settings.json` in its own folder, as before.
- **Settings from older exports:** a `user_settings.json` an export made before H9.1 kept in its installation is
  read only when the player has no valid settings of their own. It is never changed.
- **Unreadable files:** a player's own file that can't be read is not written over. The next change first sets it
  aside as `user_settings.json.invalid`.
- **Failed saves:** when the settings can't be written, the menu says *Settings not saved*, the change stays in
  effect until the game closes, and the diagnostics say why. The policy is in `engine.runtime_settings_storage`.

**An exported game's interface text (H9.2).** Before H9.2, exports carried neither the engine's
`locales/en.json` (an installed Mesh keeps it in `share/mesh-engine`, outside the `engine` package) nor the project's
`locales/`, so their players read keys such as `UI_SETTINGS_SAVED`.

- **Where it is now:** the export ships the engine's text at `share/mesh-engine/locales/` in the game's folder, the
  same layout as an install. It is found before any Mesh the player's Python may hold.
- **The game's own text:** a project's `locales/<code>.json` ship at `locales/` and are laid over the engine's key
  by key, as in Mesh Studio. A language without a message falls back to English.
- **Broken files:** a translation of the game's that can't be read is ignored, and the engine's text shows.
- **Integrity:** the bundle's manifest lists every one of these files with its hash.

The exporter and the asset manifest moved from the repository's `tooling/` into the package
(`engine.tooling.export_bundle`, `engine.tooling.asset_manifest`). The names in `tooling/` remain for repository
scripts.

**Still repository-only (#357):**

- `mesh campaign` and `mesh replays` (`tooling.campaign_replay`);
- the main menu's web demo export and preview (`tooling.release_web_demo`, `tooling.web_preview`). The menu shows
  those items only where the tools exist, and the HD-2D renderer's desktop shaders are not a web target.
- developer gates (`mypy_gate`, `ruff_gate` and others).

## What each check proves (H5, #422)

Running Mesh from a checkout, from an installed wheel and as an exported game are different guarantees. A `python`
started in a checkout imports the checkout's `engine`/`mesh_cli` (the current folder comes first on `sys.path`), even
inside a virtual environment that has the wheel installed: so only a run outside the checkout, isolated, tests the
wheel.

| Guarantee | Checks |
|---|---|
| The source works | The full default suite (`pytest` jobs), verify-all (`verify` jobs), the Arcade 3 canary's pytest and replay smoke |
| The installed product works | `installed (<os>, py3.11)`: the wheel test above, both OSes, required. The Arcade 3 canary's installed-wheel replay (Linux, `python -I`, checked to run the wheel's code; its replay content is the checkout's). `tooling/hd2d_install_acceptance.py` (manual) |
| An exported game works | `tests/test_export_bundle.py` and verify-all's `player-package-gate` (both export with the checkout's engine), the release bundle's strict verification (`bundle verify --strict`). A game exported **from an installed Mesh** is run only by `tooling/hd2d_install_acceptance.py` (manual) |

## Tests

| Test | What it checks |
|---|---|
| `tests/test_wheel_bundles_engine_data.py` (slow; builds a wheel; **required in CI** as `installed (<os>, py3.11)`, H5) | The wheel bundles exactly the allow-list, plus the schemas. Installed with its declared dependencies in a fresh environment and run isolated (`python -I`, no PYTHONPATH or MESH_*) from an empty folder, via `tooling/installed_product_check.py`: every `engine`/`mesh_cli` module and bundled file comes from the installation, `tooling` is absent, a blank and an HD-2D RPG project get everything they use (starter files, input bindings, the 14-model kit, no unverified sprite), and the installed `mesh new` / `mesh doctor` work. It also proves the check fails on a wheel missing a module, with a broken module, or missing an asset the checkout still has, and that the old way of running (from the checkout, not isolated) is caught. |
| `tests/test_bundled_data_roots.py` (fast) | The source tree comes first, then an install's `share/mesh-engine`, for files and folders |
| `tests/test_export_bundle.py` (fast) | A project exports as a standalone game; an export never replaces a folder that isn't an earlier bundle |
| `tests/test_export_bundle_replacement.py` (integration, F4) | A failed copy (first or later file), manifest write or check, a file changed mid-export, a failed handover, a failed rollback (both copies kept and named, then recovered), a failed cleanup, an interrupt, and an export killed between the renames (a real child process): none loses the earlier export. Absent, empty and earlier-export folders are filled or replaced; a changed (same length), missing or truncated file, a malformed or duplicate manifest entry, saves, foreign files, unlisted bytecode and links or junctions are never replaced or followed; folders named like an export's working folders but without its owner file (or with anything else in them), even the very folder emptied, and a changed backup, are never deleted; a replacement is byte for byte a fresh export |
| `tooling/hd2d_install_acceptance.py` (manual, hidden windows) | The whole HD-2D workflow from a clean install, including running the exported game with Mesh's dependencies only. Evidence: `docs/reviews/milestone16_stage6b_distribution.md`. |
