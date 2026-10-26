# Asset licensing: status and open requirements

Recorded at the owner's decision on Milestone 17 Stage 1B (2026-10-26). This page records project decisions; it is
not legal advice.

## What ships today

- **Mesh's own work only.** Everything Mesh distributes is made by its own scripts: the HD-2D starter kit
  (`assets/hd2d_starter`, see its `PROVENANCE.md`) and the template's characters, door and sounds.
- **The rules.** `assets/NOTICE.md` lists what ships and what never does, and `docs/packaging.md` describes the
  bundling allow-list.
- **The kit's cottage.** It was refined in Milestone 17 using the existing starter textures only, so it is still
  Mesh's own work.

**No PixelLab-generated or other AI-generated asset is in the starter kit or the package allow-list.** The Milestone
17 pilot outputs stay review records: PR #370, PR #371, and `tooling/hd2d_assets/pilot_m17/` on those branches, with
their provenance and licence review. They are not merged.

## Open requirements, to settle before any third-party or AI-generated asset ships

1. **Written clarification from PixelLab.**
   - The questions: whether editable outputs may be redistributed in a downloadable starter kit; what downstream
     users may do with them; how the no-AI-training condition and the CreativeML Open RAIL-M use restrictions
     (Terms of Service §1.2, §3.3, §4.1) must be passed on; and whether rights survive the subscription.
   - A request is drafted (licence review §4.2, PR #371). Sending it is the owner's decision.
2. **A clear Mesh Engine code licence, and separate starter-asset usage terms.**
   - The repository has no LICENSE file; `pyproject.toml` says `LicenseRef-Proprietary`. What engine users may do
     even with today's starter kit is undefined.
   - The kit needs its own usage terms: the rights to use, modify and redistribute it in games. They should be
     copied into every new project beside the kit, which today copies no notice.
3. **Accurate provenance whenever third-party or AI-generated assets are distributed.**
   - For each such file:
     - a provenance record: source or generator, endpoint, date, prompt or seed, edits;
     - a separate notice passing on any conditions, such as PixelLab's no-training clause;
     - a catalog licence line that says so.
   - Two code changes are needed first:
     - Studio's model reimport keeps the old "made by Mesh's own scripts" licence line, and must stop;
     - `make_starter_kit.py` must stop stamping one licence line on every model.

## Safeguards already in place

- **Raw generator records are never committed.**
  - `tooling/hd2d_assets/**/raw/` is git-ignored: PixelLab job dumps hold the account id inside storage URLs.
  - `tests/test_generated_asset_hygiene.py` (fast tier) fails on any of these in a tracked file:
    - a raw record;
    - a storage URL or signed URL containing an id;
    - a bearer-token literal;
    - the owner's token or account id, recognised by their SHA-256 digests.
- **Generation runs on one shared budget.**
  - `tooling/pixellab_budget.py`: every request reserves its cost before it is sent.
  - Endpoints without an established cost are refused, and so is anything over the approved budget or the agent's
    own cap.
  - QA agents are never in the ledger, so they are read-only.
  - A subtask spends from its parent agent's cap, so delegating can't add budget.
  - Results are stored sanitized.
