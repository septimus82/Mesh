# B-01 design: stable entity identity in saves (#462 reliability)

Status: DESIGN ONLY (no production code or tests changed), revision 3 (+ 2026-11-20 correction: duplicate ids bind by
unique position only, never by occurrence order). Revision 2: owner feedback on id-less entities,
duplicate ids, backward-compatible recovery. Revision 3 (master, from the owner's decisions of 2026-11-19): legacy
position binding only when provably unique (Q2), manual recovery only (Q7), the `.v2.bak` must be created **and
verified** or the v2 slot is not overwritten (Q8), B-01b lands first as its own PR (Q9), and unresolved records survive
every later save (§3 "Unresolved records"). Base `ad91e28c665ae6adc22be4ce0b2c4e7d26e1817b`.
Agent: mesh-gameplay-reliability. This is a **save-format migration**: owner approval needed before implementation.
Evidence: `docs/reviews/b01_entity_save_identity_evidence/` (`repro_b01*.py.txt` + `*_output.txt`; the base-written v2 save
`v2_save_idless_dupname_dupid.json` is a real-save candidate fixture).

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

**Runtime spawns and id-less sprites today** (all go through `_create_sprite`; a grep of `_create_sprite(` finds only these):

| Source | file:line | name / id | state on base |
|---|---|---|---|
| Authored entity with no `id` | `scene_lifecycle_controller.py:353` | name or prefab id / none | see below (run) |
| Projectile | `shooter.py:150-184` | `proj_<name>` / none | run: spawned by `_create_sprite`+`add_sprite_to_layer` as the behaviour does (behaviour not fired) |
| Hitbox (0.2 s life) | `combat.py:205-238` | `hitbox_<name>` / none | read only: same path as projectile |
| Console `spawn` | `console_runtime/handlers_entity.py:150-170` | `spawned_N` / none | run (same dict shape) |
| Console `clone` | `handlers_entity.py:185-196` | `<name>_clone` / **copies the source `id`** | run: duplicate id (below) |
| Monster companions / eggs | `monster/egg_lifecycle.py:39-61`, `companion_mind.py:494` | not sprites: plain data in game-state variables | read only; no `_create_sprite` call in `engine/monster/` |
| Spawner behaviours | none found | | read only (grep) |

Verified by running on the base (`repro_b01_idless.py.txt`, hp set after spawn): an id-less sprite with a **unique** name
(`spawned_7`, hp 4) is saved by name, re-created from the save's scene snapshot (which also carries id-less sprites
with their x/y) and gets its state back (hp 4). Two id-less sprites sharing a name (`proj_Hero`, hp 2 and 6): both
records applied to the last sprite, the first came back at hp 5 (its spawn value, **2 lost**), no diagnostic. The
console-clone case shows a second defect: original `gob_a` and the clone (same id) were **merged into one entity at
the snapshot layer** (`scene_runtime/persistence.py:60-80`, `authored_entity_by_key` matches by id/name), so the room
had one `gob_a` at the clone's position, hp 20; the clone's hp 11 was lost before `saved_entities` is even applied.
This must keep working after the change: id-less state saved and restored by name as today, never worse.

**Entities whose id changes.** Lint rename (`rename_id`), duplicate (`__dupN`), hand edit. `remember_removed`
(`scene_runtime/room_memory.py:68-82`) and `saved_world.compose` (`:104-121`) already treat the authored `id` as
the identity of a room object across save/reload, so ids are already the de-facto key everywhere except
`saved_entities`.

**How saves reference scenes.** `meta.scene_path` = `room_path` (`payloads.py:529-554`), the save is itself loaded as a
scene (`save_manager.py:387`); its own `entities` list is the scene snapshot with ids and live x/y (fixtures show
`saved_entities` x/y equal the snapshot x/y for the same object, e.g. Elder 896/786). Entity state is applied
twice: at `load_game` to the room being left (`payloads.py:378-386`) and again once the saved room exists via
`controller._pending_saved_entities` (`save_manager.py:369`, `scene_lifecycle_controller.py:366-373`). Records
carry no scene identity, so the first apply can match same-named entities in the wrong room (design: validate scene).

**digest.py / payloads.py use of `entity_id`.** `digest.py:72` normalises `entity_id`; `:134` sorts by it only
(duplicates tie, so digest depends on input order). `payloads.py:512` calls `serialize_entities`; `:383` calls
`apply_entities`. The episode/replay golden digests do **not** go through `serialize_entities`: `mesh_cli/episode.py:1130-1163`
builds its own payload keyed by its own ids, then `compute_world_digest`. `compute_world_digest_from_scene`
(`digest.py:223-234`) and `DigestTracker` use `serialize_entities`; the tests found that use them
(`test_replay_determinism.py`, `test_debug_bundle_contract.py`) compare runs with each other, not stored goldens
(not exhaustively verified: see open question 5).

## 3. Proposed key and migration

**Two record classes** (`saved_entities.schema_version` 1 -> 2; `SAVE_SCHEMA_VERSION` 2 -> 3). `entity_id` keeps
today's value (the display name), so `digest.normalize_entity_state` (`digest.py:72`) is untouched.
- `keying: "id"`: sprite has an authored `mesh_id`. Fields add `mesh_id` and `occurrence` (0-based rank among live
  sprites with that id in `all_sprites` order; 0 for a unique id).
- `keying: "name"`: sprite has no `mesh_id` (id-less authored, projectile, hitbox, console spawn). Written exactly as
  today (name + x, y + behaviour state), plus the marker. Nothing id-less is dropped.
- Container adds `scene_path` (room the records belong to) and counters `{id: n, name: n}`.
- Sort key `(keying, mesh_id or "", entity_id, x, y, occurrence)`: total, independent of sprite order.

**Writing.** One record per sprite, never dropped. Duplicate authored ids are kept as occurrences 0..k-1 and each
id gets a WARN `save.serialize.entity_id_duplicate` (context: id, count) in the diagnostics list and the log.

**Duplicate authored ids: policy = write all, bind only when counts match, otherwise refuse that id and report.**
Chosen over refusing the save: a clone or hand-edit mistake must not cost the player a save, and a hard error
would also block saves in games already shipped with duplicates. Over silently picking one: that is the bug.
On load, id `I` has `r` records and `s` live sprites. If `r == s == 1`, the record binds (the id is provable). If
`r == s > 1`, a record binds **only by provably unique position**: its (x, y) matches exactly one of those sprites
within 0.01 and no other record matches that sprite (the scene snapshot restores positions first). Occurrence order
is never identity (rev 3 correction, owner challenge 2026-11-20: twins at identical positions with different states
would otherwise be exchanged when the sprite order differs); it orders output only. Records not uniquely matched
(e.g. identical positions) are refused (`ambiguous_position`) and become unresolved. If `r != s` (as in the clone repro, where the snapshot already merged the pair into one
sprite), no record for `I` is applied: ERROR-level `save.restore.entity_id_ambiguous` (WARN non-strict; fails in
strict), with `{id, records, sprites}`. The refused records become unresolved (below): reported and carried in every
later save, never discarded. (The snapshot-layer merge of same-id sprites, `persistence.py:60-80`, is fixed first and
separately by B-01b (owner Q9): with it, both sprites survive the snapshot, so the counts can match.)

**id-less records on load (`keying: "name"`).** Applied by name against **id-less sprites only** (so an id-less
record can never land on an authored-id sprite, and vice versa):
1. One record, one id-less sprite with that name: apply (= today's behaviour for these entities).
2. Several id-less records and/or sprites share a name: bind a record to a sprite only when exactly one record and
   exactly one sprite in that group have equal (x, y) within 0.01; apply those. Every record not bound this way is
   **not applied** and reported (below). Never "last wins", never by order. (Repro: `proj_Hero` at (10,10) and (20,20)
   both bind by position, so 2 and 6 are both restored; two sprites at the same spot are refused and reported.)
3. No id-less sprite with that name: `save.restore.entity_missing` as today (an expired projectile).
Written vs applied is visible in the counters: `applied`, `missing` (as today), `unbound` (new).

**Reading v2 (name-keyed) saves** (`schema.py:82` migration v2 -> v3 runs **in memory only**: tags every record
`keying: "name"`, `legacy: true`; invents nothing). Resolution of a legacy record named `N`:
1. Exactly one record and one sprite named `N` (any id): apply (identical to today).
2. Duplicate names, record count and sprite count may differ: bind a record to a sprite only if its (x, y) equals
   exactly one live sprite's (x, y) named `N` and exactly one record claims that (x, y). For sprites with an id,
   the save's own snapshot (`entities`: id + x, y of the same instant) is the cross-check: a record bound to an id-ful
   sprite must also match that id's snapshot position. Binding happens only when this mapping is provably unique (Q2);
   anything else is not applied, reported, and preserved as unresolved (below), never guessed.
3. No sprite named `N`: `entity_missing`.

**Counts and diagnostics.** Codes: `save.restore.entity_id_ambiguous`, `save.restore.entity_legacy_ambiguous`
(v2 record unbound), `save.restore.entity_nameclash` (id-less group, v3), `save.restore.entities_wrong_room`,
`save.serialize.entity_id_duplicate`. Each carries `{name|id, records, sprites, x, y}`. A roll-up
`save.restore.entities_unbound` carries `{applied, missing, unbound}`. Channels: stderr log (as today), the
save-runtime diagnostics aggregator/sidecar (`io.py:74-105`), and **new**: one player toast through the existing
`_toast` (`save_manager.py:220`), "Loaded. N object states from this save could not be matched; see the log",
shown only when `unbound > 0`.

### Unresolved records (owner requirement: never silently discard unresolved gameplay state)

Every record a load does not apply (a v2 legacy record that doesn't bind, a v3 `entity_id_ambiguous` or
`entity_nameclash` record, a refused occurrence) becomes **unresolved**: kept verbatim with its keying, plus
`{reason, scene_path, first_seen}` (the save it first came from), and never treated as live state.
- **Kept across saves.** Unresolved records are held with the restored scene state and written back on every later
  save into `saved_entities.unresolved` (next to `entities`), deduplicated by `(scene_path, SHA-256 of the record)`,
  so repeated saves neither lose nor multiply them. A save writes back every unresolved record it holds, whichever
  room is current.
- **Retried on every load** with the same binding rules, but only against sprites that received no record in that
  load (an unresolved record never overwrites state that a resolved record just applied). When a scene fix makes one
  bind uniquely (an id corrected, a duplicate removed), it is applied and leaves the list.
- **Removed only by binding or by manual recovery** (a developer editing the save, §d). No expiry, no automatic
  discard. Each load reports the count (`save.restore.entities_unresolved`, log, sidecar, and the player toast when
  > 0).

### Backward-compatible recovery

(a) **Loading a v2 save never rewrites it.** The load path (`save_manager.py:238-409`) reads the slot, migrates in
memory, and the only writes it can make are failure diagnostics sidecars (`io.py:461-496`); the slot file is
byte-identical after a load. Test T20 hashes the file before and after.

(b) **First v3 save over a v2 slot (Q8).** `save_game` (`save_manager.py:179-218`), before writing v3 over a slot file
whose `save_schema_version < 3`: copy it to `<slot>.v2.bak`, then **verify** the copy (re-read it and compare its
SHA-256 with the original's). Only a verified backup lets the v3 write go ahead. If creating or verifying the backup
fails, the save is **refused**: the v2 slot is left byte-identical, the error `save.write.v2_backup_failed` is logged
and the toast says the game wasn't saved over the old save (saving to another slot still works). Existing backups are
never replaced: if `<slot>.v2.bak` already exists with different bytes, the new backup is
`<slot>.v2.<first 8 hex of its SHA-256>.bak` (verified the same way). Never for an installation-bundled legacy save
(`_is_legacy`: nothing is written next to it). The game never reads a `.bak`; it is the recovery record.

(c) **Unmatched legacy records are surfaced and preserved**: `entity_legacy_ambiguous` per record (name, x, y,
behaviour names), the roll-up counts and the toast; the records themselves become unresolved and are carried in every
later v3 save (§ "Unresolved records"), and the original file is the verified `.v2.bak`.

(d) **Recovering state that could not be applied: manual only (Q7; no new tool).** Developer: find the record in
`saved_entities.unresolved` (or in `<slot>.v2.bak`, `saved_entities.entities[]`) by the name, x, y from the diagnostic,
then give the entity an id or a distinct position in the scene so the next load binds it, or copy the behaviour
state into the entity's `behaviour_config`. Player: copy `<slot>.v2.bak` over the slot (only a v2-capable build
reads it, see (e)).

(e) **Downgrade.** A v3 save in a v2-only build is refused by `schema.py:145-150` with the existing "newer game
version" message, nothing partially loaded, and the `.v2.bak` is a loadable v2 file for that build (it lacks only
progress made after the first v3 save). Forward: the reader ignores unknown record fields except `x_*`.

**Determinism.** Output order is the total sort key above; v2/legacy matching uses exact coordinates, not
iteration order, so reordering `all_sprites` changes nothing.

**Impact on digests/replays.** `digest.py` unchanged. `serialize_entities`-derived digests change only where records
were previously dropped/reordered; unique-named scenes keep identical values. Episode goldens use their own payload
(`mesh_cli/episode.py:1130-1163`). New fields (`keying`, `mesh_id`, `occurrence`) are not in the digest projection.

## 4. Test plan (to be written at implementation; none committed here)

Default lane, production `SaveManager`, hidden `GameWindow` as in `tests/test_hot_reload_preflight.py`.

| # | Name | Setup | Assertions |
|---|---|---|---|
| T1 | `dup_names_roundtrip_v3` | repro 1: gob_a hp 3, gob_b hp 20 | restored exactly; fails on base |
| T2 | `dup_names_sprite_order_independent` | reverse entity order before restore | identical result |
| T3 | `unnamed_same_prefab` | 3 unnamed same-prefab entities, differing hp | each restored |
| T4 | `real_old_saves_load` | `tests/fixtures/saved_world/pre390_2d.json`, `pre390_hd2d.json` (v2; none has an id-less entity) | schema 3 in memory, all applied, 0 unbound, no new diagnostics |
| T5 | `real_v2_save_with_idless_fixture` | `evidence/v2_save_idless_dupname_dupid.json` (base-written v2, scrubbed) | `spawned_7` hp 4 restored; both `proj_Hero` restored by position; the same-id clone reported, never silently applied |
| T6 | `v2_dup_names_bound_by_xy` | hand-built v2, two `Goblin` records, snapshot ids | bound by position, no cross-apply |
| T7 | `v2_dup_names_unbindable_refused` | record xy matches nothing | none applied, one diagnostic per record, counts honest |
| T8 | `v2_unique_name_unchanged` | v2 unique names | applied values equal base golden |
| T9 | `idless_unique_name_roundtrip` | `spawned_7` | state back (as base), record `keying: name` |
| T10 | `idless_same_name_distinct_xy` | two `proj_X` | both restored by position; fails on base (2 lost) |
| T11 | `idless_same_name_same_xy` | two `proj_X` at one spot | neither applied, `entity_nameclash` x2, `unbound` 2 |
| T12 | `idless_never_hits_id_sprite` | id-less record named like an id-ful sprite | id-ful sprite untouched |
| T13 | `projectile_hitbox_expired` | record for a projectile gone at load | `entity_missing`, no error, as base |
| T14 | `dup_authored_ids_all_written` | clone with copied id | 2 records (occurrence 0, 1), WARN `entity_id_duplicate` |
| T15 | `dup_authored_ids_counts_match_binds` | two live sprites, same id, distinct positions, sprite order reversed | each bound by its unique position |
| T15b | `dup_authored_ids_same_position_never_by_order` | two live sprites, same id, identical positions, different states, order reversed (and not) | neither applied, both unresolved and reported, carried by the next save; nothing exchanged |
| T16 | `dup_authored_ids_count_mismatch_refused` | 2 records saved, 1 sprite at load | none applied, ERROR code, `unbound` 2, records still in the file |
| T17 | `renamed_entity_survives` | rename via `ops.rename_entity` | state follows the id; fails on base |
| T18 | `id_renamed_reports_missing` | lint-rename an id | `entity_missing` by id, no cross-apply |
| T19 | `wrong_room_guard` | room A records, room B live (`payloads.py:378`) | skipped `entities_wrong_room` |
| T20 | `v2_load_never_rewrites_slot` | v2 file, load, hash before/after | byte-identical, no sidecar on success |
| T21 | `first_v3_save_makes_v2_bak` | load v2 slot, save | `<slot>.v2.bak` equals the original bytes; v3 written |
| T22 | `second_save_keeps_first_bak` | save again | `.bak` unchanged |
| T23 | `bak_copy_failure_refuses_overwrite` | make `.bak` unwritable | save refused, v2 slot byte-identical, `v2_backup_failed`, toast |
| T24 | `legacy_installation_save_not_touched` | `_is_legacy` path | no `.bak`, no write |
| T25 | `unbound_toast_only_when_unbound` | T7 vs T8 | toast only for T7 |
| T26 | `future_version_refused` | v4 payload | `schema.py` error, state untouched |
| T27 | `v2_bak_is_loadable` | load the `.v2.bak` again | same result as the first v2 load |
| T28 | `serialization_order_total` | duplicate names/ids, shuffled sprites | identical list |
| T29 | `digest_stable_unique_names` | unique-named scene | digest equals recorded value; episode goldens unchanged |
| T30 | `v3_roundtrip_stable` | save, load, save | `saved_entities` equal |
| T31 | `bak_verify_failure_refuses_overwrite` | the copy's bytes differ from the slot (fault-injected) | save refused, v2 slot byte-identical |
| T32 | `existing_different_bak_kept` | a `.v2.bak` with other bytes already there | it is unchanged; new verified `<slot>.v2.<sha8>.bak` |
| T33 | `unresolved_survive_repeated_saves` | T7's unbound records; save, load, save, load | records in `saved_entities.unresolved` each time, byte-equal, counted, never duplicated |
| T34 | `unresolved_bind_after_scene_fix` | T33, then give the entity a distinct position/id in the scene | the record binds on the next load and leaves `unresolved` |
| T35 | `unresolved_never_overwrite_resolved_state` | an unresolved record and a resolved record for one sprite | the resolved state stays; the unresolved record stays unresolved |
| T36 | `unresolved_across_rooms` | unresolved in room A, save while in room B | room A's unresolved records still written |

Adjacent suites: `test_save_entity_quest_state`, `test_save_serialization_strictness`, `test_save_format_versioning`,
`test_save_load_roundtrip`, `test_room_memory`, `test_replay_determinism`, `test_debug_bundle_contract`,
`test_health_save_restore`, `test_runtime_save_load_diagnostics_contract`, the `saved_world` fixture tests.

### Failure scenarios

| What could go wrong | How the design prevents or reports it |
|---|---|
| Two authored entities share a name (base: last wins, silent) | Keyed by id; nothing depends on the name |
| Authored ids duplicated (clone, hand edit) | All records written with occurrence + WARN; bind only on equal counts and matching xy; else refuse that id with ERROR + counts; records stay in the file |
| Id-less sprites share a name (projectiles) | Bound only by unique (x, y); the rest `entity_nameclash`, counted, never applied |
| Id-less record lands on an authored-id sprite | Impossible: id-less records match id-less sprites only (T12) |
| Id-less runtime sprite state worse than base | Same name-keyed record as base; better for shared names (T9, T10) |
| Entity renamed after save | Name irrelevant for id records |
| Entity id renamed/removed after save | `entity_missing` by id; no cross-apply |
| v2 save, ambiguous names | Not applied, reported, carried as unresolved in every later save, and in the verified `.v2.bak`; snapshot still places objects |
| A later save silently drops state that couldn't be applied | Unresolved records are written back on every save, deduplicated, removed only by binding or manual recovery (T33-T36) |
| Load rewrites or damages the v2 file | Load is read-only (T20) |
| First v3 save overwrites the only copy of v2 progress | One-time `.v2.bak` (T21-23) |
| `.bak` cannot be written or doesn't verify | The save is refused; the v2 slot stays byte-identical (T23, T31) |
| Records applied to the wrong room (`payloads.py:378` pre-apply) | `scene_path` guard on v3 (T19); v2 unchanged (flagged) |
| Old game opens a v3 save | Refused clearly (`schema.py:145`); `.v2.bak` is loadable there |
| Ordering differs across machines | Total sort key; position-based matching |
| Digest drift | `digest.py` untouched; T29 |
| Migration invents data | In-memory tagging only |

## 5. Interaction with B-02

B-02 (primary tag from sorted `tags[0]`, `entity_state.py` ~309/~413) is independent of the key; both touch
`SavedEntityState.to_dict/from_dict` and `serialize_entity`. Separate PRs, B-01 first; B-02 may add a `tag` field
to v3 records. Merge conflicts only, no semantic overlap.

## 6. Open questions

Answered by this revision (the owner confirms by approving the design):
1. Runtime-spawned / id-less entities: **answered**: kept as name-keyed records, applied by unique name or unique position.
3. Duplicate/missing authored ids at save time: **answered**: write all, WARN; no save refusal.
4. Bump to v3 rather than an additive v2 field: **answered** (clean downgrade refusal plus `.v2.bak`).
5. Digest: **answered** (unchanged; episode goldens independent; only `episode.py` was traced).
6. Wrong-room guard for v2 saves: **answered**: not backported, so v2 loading stays identical to today.

Decided by the owner (2026-11-19):
2. Legacy duplicate names: bind by position only when the mapping is provably unique; otherwise refuse and preserve.
7. Recovery: manual first; no new CLI tool yet.
8. Player warning and `.v2.bak`: approved, but failing to create and verify the backup refuses the overwrite of the v2
   save (§3 (b)).
9. B-01b: fixed as a separate PR **before** the v3 migration is implemented.
10. (Added) Unmatched records survive repeated v3 saves; unresolved gameplay state is never silently discarded.

Not yet decided: authorisation to implement the v3 migration itself (this design is documentation only).
