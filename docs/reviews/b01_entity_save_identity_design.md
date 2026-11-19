# B-01 design: stable entity identity in saves (#462 reliability)

Status: DESIGN ONLY (no production code or tests changed). Base `ad91e28c665ae6adc22be4ce0b2c4e7d26e1817b`.
Agent: mesh-gameplay-reliability. This is a **save-format migration**: owner approval needed before implementation.
Evidence: `docs/reviews/b01_entity_save_identity_evidence/` (`repro_b01.py.txt`, `repro_b01_output.txt`).

## 1. Reproduction on the base (production SaveManager, hidden GameWindow)

Disposable scaffolded game (`create_project`, blank). Scene "Arena": `hero`, and two entities both named `Goblin`
with ids `gob_a` / `gob_b`, each with a `Health` behaviour (max 20). Play state set: gob_a hp 3 at (111,122);
gob_b hp 20 at (333,344). Saved with `SaveManager.save_game`, fresh room loaded, then `load_game` plus
`handle_pending_scene_load` (the real load path).

What the save contains (`repro_b01_output.txt`): two records both with `entity_id: "Goblin"`, no id of any kind:

```
('Goblin', 111.0, 122.0, hp 3.0)   ('Goblin', 333.0, 344.0, hp 20.0)
```

What comes back:

| entity | saved | restored by `load_game` | restored by `apply_entities` on a pristine room |
|---|---|---|---|
| gob_a | hp 3, (111,122) | hp **20** (hurt state lost) | hp 20, (100,100) **untouched** |
| gob_b | hp 20, (333,344) | hp 20, (333,344) | hp 20, (333,344) |

`apply_entities` returned `(3, 0)` (3 applied, 0 missing) with **zero diagnostics**: both Goblin records landed on
gob_b (last sprite wins, record 2 overwrote record 1), gob_a received nothing, and the counters claim success.
Positions look right in the full load path only because the save's own scene snapshot (`entities`, keyed by `id`)
re-places objects; behaviour state (HP, dead flag, timers) has no such second channel, so it is lost. gob_b
is correct only by luck of ordering. A dead goblin saved next to a live one would come back live, or the reverse.

## 2. Facts for the design (file:line at base)

**Where `mesh_id` comes from.** `engine/scene_controller_parts/entity_factory.py:120`:
`sprite.mesh_id = entity_data.get("id")` (the scene file's `id`). It is `None` when the entity has no `id`.
Behaviours address entities by it (`engine/behaviours/*.py`, e.g. `trigger_volume.py:220`, `health.py:173`).
`mesh_name` (`entity_factory.py:101-105`) is `mesh_name or name or prefab_id`: it falls back to the **prefab id**,
so every unnamed entity of one prefab (ten trees) shares one name.

**Save/load keying.** `serialize_entity` keys by `mesh_name` (`save_runtime/entity_state.py:220`), falling back to
`entity_data.id/name`; `serialize_entities` sorts by `entity_id` only (`:350`, ties keep sprite order);
`apply_entities` builds `sprite_by_id` keyed by `mesh_name` (`:527-531`), last wins, looks up at `:538`. An
absent entity is counted as missing with a WARN; a duplicate is never detected.

**Does anything guarantee unique ids per scene?**
- Strict validation only: `engine/validators/schema_validation.py:105-121` (`entity.id.required`, `entity.id.duplicate`,
  strict mode). Default load does not enforce it. `SceneIndex` records `duplicate_ids` and `duplicate_mesh_names`
  (`engine/scene_index.py:54-58, 80-119`) but nothing consumes them for saves.
- Studio add: `project_ops.py:1789-1792` builds `unique_entity_id(...)` (`:166`) **and** a `_unique_name`
  (`:1716`), so Studio-made objects have unique ids and unique names. Studio rename (`project_ops.py:297`)
  changes `name` only, never `id`: today a renamed entity breaks its name-keyed save record (the id would not).
- Paint/duplicate: `entity_paint_mode.py:69-73` position-derived id, refuses an existing id (`:246-249`);
  `spawn_ops.py:95-103` duplicates to `<id>__dupN`; lint fixer renames duplicates `_fix_` (`scene_lint_model.py:81-103`).
- Scaffold templates give fixed distinct ids (`project_templates.py:136, 193, 214-215, 242`).
- Hand-edited / AI-authored scenes: not guaranteed (strict mode off by default). Real saved fixtures exist where
  names are unique by luck (`tests/fixtures/saved_world/pre390_*.json`).

**Entities with no authored id (runtime-spawned).** `combat.py:225-234` (hitbox), `shooter.py:150-181`
(projectile, name `proj_<name>`) create sprites through `_create_sprite` with no `id`; so do console spawn
(`console_runtime/handlers_entity.py:166,195`). Today these are saved under `proj_goblin` etc. and, on load, are
reported missing (the room does not contain them). Not verified: whether monster companions/eggs spawn with
ids (their persistence may use the game-state variables rather than `saved_entities`).

**Entities whose id changes.** Lint rename (`rename_id`), duplicate (`__dupN`), hand edit. `remember_removed`
(`scene_runtime/room_memory.py:68-82`) and `saved_world.compose` (`:104-121`) already treat the authored `id` as
the identity of a room object across save/reload, so ids are already the de-facto key everywhere except
`saved_entities`.

**How saves reference scenes.** `meta.scene_path` = `room_path` (`payloads.py:529-554`), the save is itself loaded as a
scene (`save_manager.py:387`); its own `entities` list is the scene snapshot with ids and live x/y (fixtures show
`saved_entities` x/y equal the snapshot x/y for the same object, e.g. Elder 896/786). Entity state is applied
twice: at `load_game` to the room being left (`payloads.py:378-386`) and again once the saved room exists via
`controller._pending_saved_entities` (`save_manager.py:369`, `scene_lifecycle_controller.py:366-373`). Records
carry no scene identity, so the first apply can match same-named entities in the wrong room (design below: validate scene).

**digest.py / payloads.py use of `entity_id`.** `digest.py:72` normalises `entity_id`; `:134` sorts by it only
(duplicates tie, so digest depends on input order). `payloads.py:512` calls `serialize_entities`; `:383` calls
`apply_entities`. The episode/replay golden digests do **not** go through `serialize_entities`: `mesh_cli/episode.py:1130-1163`
builds its own payload keyed by its own ids, then `compute_world_digest`. `compute_world_digest_from_scene`
(`digest.py:223-234`) and `DigestTracker` use `serialize_entities`; the tests found that use them
(`test_replay_determinism.py`, `test_debug_bundle_contract.py`) compare runs with each other, not stored goldens
(not exhaustively verified: see open question 5).

## 3. Proposed key and migration

**Key.** An entity's save identity is its authored scene `id` (`mesh_id`), unique within a scene. `mesh_name`
stays a human label and a fallback only for v2 records.

**New record fields** (`saved_entities.schema_version` 1 -> 2; `SAVE_SCHEMA_VERSION` 2 -> 3):
- `mesh_id` (str, required for v3 records): the authored id. A sprite with no `mesh_id` gets **no** `saved_entities`
  record (see below).
- `entity_id` kept, now the display name (unchanged value), so v3 files stay readable as before and
  `digest.normalize_entity_state` (`digest.py:72`) is untouched.
- Container gains `scene_path` (the room the records belong to) for the wrong-room guard.

**Writing (v3).** One record per sprite that has a `mesh_id`; sort key `(mesh_id, entity_id)`, so ordering is
total and independent of sprite order. Sprites with no id (runtime-spawned) are omitted from `entities` and
counted: `saved_entities.unkeyed_skipped: N` plus an INFO diagnostic `save.serialize.entity_unkeyed`
(open question 1: owner may prefer a persisted "runtime spawn" record class instead).
Duplicate `mesh_id` among live sprites at save time: write the first by sprite order, **omit the rest** and
emit a WARN `save.serialize.entity_id_duplicate` per id (never two records for one key).

**Reading v3.** Match `mesh_id` -> sprite via a dict built once per apply; duplicate sprite ids in the live scene
(or a duplicate `mesh_id` in the file) mark that id **ambiguous**: apply neither, ERROR-level diagnostic
`save.restore.entity_id_ambiguous` (WARN in non-strict, fail in strict), counted as missing. If
`saved_entities.scene_path` is set and differs from the room being applied to, skip the whole block with
`save.restore.entities_wrong_room`. Records without a live sprite stay `entity_missing` (now by id, as today).

**Reading v2 (name-keyed) saves** (`migrate_save`, `schema.py:82` registers v2 -> v3; it only tags records
`legacy_keying: "name"` and bumps the version, no data invented). `apply_entities` then resolves a legacy record:
1. Name `N` has exactly one record and exactly one live sprite named `N`: apply (identical to today).
2. One record, several sprites named `N`: the save cannot say which; try the save's own scene snapshot
   (the save file's `entities` list holds `id` + live x/y written from the same instant). If exactly one snapshot
   entity with `name == N` has matching (x, y) to 0.01, bind to that id's sprite; else **do not apply**,
   `save.restore.entity_legacy_ambiguous` ERROR/WARN.
3. k records, k sprites, same name: bind each record by exact (x, y) against the snapshot as in rule 2; any record
   not uniquely bound is not applied and reported (never "last wins").
4. No sprite named `N`: `entity_missing` WARN with the legacy name (as today).
5. Records and sprites for a name with count mismatch (e.g. 2 records, 1 sprite): apply only through rule 2/3,
   rest reported.
All v2 diagnostics carry `legacy_keying` so a player-facing summary can say "N object states from an old save
could not be matched". Nothing is rewritten on disk by loading; the next save writes v3.

**Determinism.** Output order `(mesh_id, entity_id)`; v2 matching iterates records in file order and sprites in
`all_sprites` order, tie-free because ambiguity is refused rather than resolved by order.

**Impact on digests/replays.** `digest.py` is left unchanged (still `entity_id`, then x/y, ...). Digests derived
from `serialize_entities` change for scenes that previously had missing ids or duplicate names (those records
disappear/reorder); unique-named scenes with ids keep identical digests because `entity_id`, x, y, tags and
behaviour state are the same values. Episode goldens use their own payload (`episode.py:1163`) and are unaffected.
Adding `mesh_id` to the digest was rejected: it would churn every scene-derived digest for no gain, as sort ties
no longer occur.

**Downgrade / forward-compat.** A v3 save opened by a v2-only game is refused by `schema.py:145-150`
("newer game version") with the existing clear message: nothing is half-loaded. The reader ignores unknown
record fields except `x_*`, so later additive fields are safe. Rollback of the migration = keep the reader,
stop writing v3.

## 4. Old-save compatibility test plan (to be written at implementation; none committed here)

Default lane, through the production `SaveManager` where a window is needed (hidden `GameWindow` as in
`tests/test_hot_reload_preflight.py`), plain `apply_entities` otherwise.

| # | Name | Setup | Assertions |
|---|---|---|---|
| T1 | `test_dup_names_roundtrip_v3` | the repro: gob_a hp 3, gob_b hp 20 | after load a=3 at (111,122), b=20 at (333,344); fails on base |
| T2 | `test_dup_names_swapped_sprite_order` | load a scene whose entity order is reversed before restore | same result (order-independent) |
| T3 | `test_unnamed_same_prefab` | 3 entities, no `name`, same prefab, differing hp | each restored |
| T4 | `test_real_old_saves_load` | `tests/fixtures/saved_world/pre390_2d.json`, `pre390_hd2d.json` (v2, unique names) | schema -> 3, all records applied, 0 missing, no new diagnostics |
| T5 | `test_v2_duplicate_names_bound_by_snapshot_xy` | hand-built v2 save with two `Goblin` records, snapshot ids/xy present | each bound by position; no cross-apply |
| T6 | `test_v2_duplicate_names_unbindable_refused` | same, but record xy match no snapshot entity | nothing applied to either, one `entity_legacy_ambiguous` diagnostic per record, counts honest |
| T7 | `test_v2_unique_name_unchanged` | v2, unique names | behaviour identical to base (golden of applied values) |
| T8 | `test_runtime_spawned_not_keyed` | projectile with no `id` | no record, `unkeyed_skipped` counted, INFO diag, save loads without missing-warnings |
| T9 | `test_renamed_entity_survives` | save, rename entity (`ops.rename_entity`), reload | state follows the id (fails on base) |
| T10 | `test_id_renamed_reports_missing` | save, lint-rename the id, reload | `entity_missing` by id, others fine, no cross-apply |
| T11 | `test_duplicate_live_ids_ambiguous` | scene with two sprites sharing an id | save writes one record + WARN; load refuses ambiguous id |
| T12 | `test_wrong_room_guard` | records from room A applied while room B is live (first apply of `payloads.py:378`) | skipped with `entities_wrong_room`, no state changes |
| T13 | `test_future_version_refused` | v4 payload | `schema.py` error, game state untouched |
| T14 | `test_serialization_order_total` | duplicate names, shuffled sprites | serialized list identical across orderings |
| T15 | `test_digest_stable_for_unique_names` | unique-named scene before/after | digest equals recorded value; episode goldens (`tests/` replay suite) unchanged |
| T16 | `test_v3_roundtrip_byte_stable` | save, load, save | second file's `saved_entities` equal the first |

Adjacent suites to run at implementation: `test_save_entity_quest_state`, `test_save_serialization_strictness`,
`test_save_format_versioning`, `test_save_load_roundtrip`, `test_room_memory`, `test_replay_determinism`,
`test_debug_bundle_contract`, `test_health_save_restore`, `test_runtime_save_load_diagnostics_contract`,
and the `saved_world` fixture tests.

### Failure scenarios

| What could go wrong | How the design prevents or reports it |
|---|---|
| Two entities share a name (today: last wins, silent) | Keyed by id; v2 duplicates refused or position-bound, diagnostics + honest counts |
| Authored ids duplicated in a scene | Save writes one + WARN; load treats id ambiguous; strict mode fails; lint already flags |
| Scene has an entity with no id | No record, counted, INFO diagnostic; never keyed by name for v3 |
| Entity renamed after save | Name no longer matters in v3 |
| Entity id renamed/removed after save | Reported `entity_missing` by id; never applied elsewhere |
| v2 save, ambiguous names | Not applied, ERROR/WARN `entity_legacy_ambiguous`; the scene snapshot still places objects |
| Records applied to the wrong room (`payloads.py:378` runs before the saved room loads) | `scene_path` guard on v3; v2 keeps today's behaviour (flagged limitation) |
| Old game opens a v3 save | Refused by `schema.py:145` with a clear message |
| Ordering differs across machines | Total sort key `(mesh_id, entity_id)`; no order-dependent ties |
| Digest drift | `digest.py` untouched; only duplicate/idless scenes change, covered by T15 |
| Migration writes data it cannot know | Migration only tags; no id is invented from a name |

## 5. Interaction with B-02 (not part of this task)

B-02 (primary tag from sorted `tags[0]`, `entity_state.py` ~309/~413) is independent of the key, but both touch
the same record: land them in separate PRs, B-01 first; B-02 may then add a `tag` field to v3 records or a v4
bump. They collide only in `SavedEntityState.to_dict/from_dict` and `serialize_entity` (merge conflicts, no semantic
overlap).

## 6. Open questions for the owner

1. Runtime-spawned entities (no id): skip them (recommended, matches what a room reload can recreate) or persist
   an "unbound" class that respawns them? Needs a look at monster companions/eggs (not verified here).
2. v2 duplicates: is position-binding via the save's own snapshot acceptable, or refuse every ambiguous v2 record
   outright (simpler, loses some HP states from old saves)?
3. Duplicate/missing authored ids at save time: WARN (proposed) or block the save in strict mode only?
4. Bump to `SAVE_SCHEMA_VERSION` 3 (proposed, clean downgrade refusal) versus staying at 2 with an additive
   `mesh_id` field (older games would then silently ignore it and keep misapplying).
5. Digest: leave `digest.py` untouched (proposed). Confirm no stored digest outside `replays/golden` derives
   from `serialize_entities` (only `episode.py` was traced).
6. Should the wrong-room guard also be backported to v2 saves (they carry `meta.scene_path`)?
