# Asset licensing: status and open requirements

Recorded at the owner's decision on Milestone 17 Stage 1B (2026-10-26), updated for owner decision D6 (2026-11-22).
This page records project decisions; it is not legal advice.

## Decision D6: PixelLab (owner, 2026-11-22)

Approved, with separate rules for development and for distribution. The owner holds a paid PixelLab subscription
(Pixel Artisan).

**(a) Development: authorised now.**

- PixelLab may generate original textures, sprites, style references and other assets for approved Mesh development.
- They may be used in the isolated M2 prototype and in future game projects, and Blender modelling, rigging, animation
  and sprite-sheet work may build on them.
- They are saved and versioned in a **separate private development project, never in this repository**. Each file
  gets a provenance record: generator, endpoint, date, prompt or seed, and later edits. Raw generator responses stay
  out of every repository (see the safeguards below).
- Every request goes through `tooling/pixellab_budget.py` within the approved allowance.
- A generated asset is described as generated, naming PixelLab, even after editing. It is never described as made by
  Mesh's own scripts.

**(b) Distribution: restricted.**

- No PixelLab-generated or other AI-generated artwork goes into Mesh's public starter kit, the engine distribution (the
  wheel's allow-list), downloadable templates or this public repository until the open requirements below are met.
- For bundled files this is enforced: `tests/test_distributed_asset_provenance.py` (fast tier) fails when a bundled
  file has no row in `assets/NOTICE.md`, when a starter-kit file is not on the allow-list, or when a NOTICE row, a row
  of the kit's `PROVENANCE.md` or a value in its `catalog.json` names an AI generator.

## What PixelLab's Terms of Service say

Read from the public page (pixellab.ai/termsofservice, "Last Updated: 2026-10-30") on 2026-11-22. Short phrases
are quoted from it; the rest is summary.

| Section | What it says | What it means for Mesh |
|---|---|---|
| §1.2 No training | Generated images may not be used to train your own models unless PixelLab permits it in writing. | A condition that travels with the outputs; the Terms don't say how a redistributor passes it on. |
| §1.3 Ownership | "You own the copyrights to your creations", for commercial and non-commercial use, without asking. | Supports development use and use in games. |
| §2.2 API usage | Programmatic use only through the official API; building a service or reselling needs a conversation first. | Our budgeted tooling uses the official API. An engine feature calling PixelLab for users would need their agreement. |
| §3.3 Output ownership | Outputs may be used, modified and distributed "for any purpose", except training other models without explicit permission. The user bears full responsibility for legality and third-party rights. | Supports distribution in principle, with the training exception attached. |
| §3.4 Inputs and stored images | PixelLab may store inputs and generated images (debugging, quality, service improvement). | Never send confidential material as input. |
| §4.1 Open RAIL-M | Users agree to comply with the Open RAIL-M licence. The link goes to the CompVis Stable Diffusion `LICENSE`, the CreativeML Open RAIL-M (2022-08-22). | That licence (§6) claims no rights in outputs but says no use of an output may break its terms, so its Attachment A use restrictions apply to how outputs are used. Its §4–5 pass-on duty is written for the model and its derivatives, and outputs are defined separately. Whether recipients of distributed outputs must be bound is unclear. |
| §8.1 Termination | PixelLab may terminate or suspend access at any time, without notice or liability. | The Terms say nothing about subscriptions, cancellation by the user, or rights to existing outputs afterwards. |

The Terms also say nothing about downstream recipients, sublicensing, asset packs or attribution.

**Against the owner's reading.** The published text matches it: §1.3 and §3.3 permit commercial use, modification and
distribution of outputs. Three conditions sit beside those permissions. §3.3 carries the training exception, as does
§1.2. §4.1 brings in the Open RAIL-M use restrictions. §3.3 puts legal responsibility on the user. Separately, the Terms
can assign whatever rights exist, but whether a generated image is protected by copyright is a question of law, not of
the Terms. The earlier review (PR #371) read the version updated 2025-11-23; the section numbers it cited (§1.2, §1.3,
§2.2, §3.3, §4.1) point to the same clauses today.

## What ships today

- **The record.** Every file Mesh distributes has a row in `assets/NOTICE.md` naming its source and licence, and
  `docs/packaging.md` describes the bundling allow-list.
- **Where those files come from.** They are:
  - Mesh's own work: made by Mesh's scripts, such as the HD-2D starter kit (`assets/hd2d_starter`, see its
    `PROVENANCE.md`) and the template's characters and sounds, or drawn for Mesh, like the door;
  - CC0 recordings in the ambience library;
  - Lucide's icons (ISC);
  - the MeshMind Studios brand.
- **None of them is AI-generated.** "Made by Mesh's own scripts" describes only files whose provenance names the
  script that makes them. It never describes a generated file, edited or not.
- **The kit's cottage.** It was refined in Milestone 17 using the existing starter textures only, so it is still
  Mesh's own work.

**No PixelLab-generated or other AI-generated asset is in the starter kit or the package allow-list**. The only PixelLab
outputs known to the project, Milestone 17's, were never merged. (The legacy sprites `animated_player.png`, `sproutling.png` and
`shelltide.png` are tracked but have unverified provenance, which is why they are never bundled.) The Milestone 17
pilot outputs stay review records: PR #370, PR #371, and
`tooling/hd2d_assets/pilot_m17/` on those branches, with their provenance and licence review. They are not merged.
Under D6, any that are kept belong in the private development project.

## Open requirements, to settle before any third-party or AI-generated asset is distributed

1. **Written clarification from PixelLab.**
   - The questions:
     - whether editable outputs may be redistributed in a downloadable game-engine starter kit;
     - what downstream game developers may do with them;
     - how the no-model-training condition (§1.2, §3.3) and the Open RAIL-M use restrictions (§4.1) apply to them;
     - whether rights in existing outputs continue after the subscription is cancelled (§8.1 is silent).
   - The request is drafted at `docs/licensing/pixellab_clarification_request.md`. It is not sent; sending it needs the
     owner's authorisation.
2. **A clear Mesh Engine code licence, and separate starter-asset terms.**
   - The repository has no LICENSE file; `pyproject.toml` says `LicenseRef-Proprietary`.
   - The starter-asset licence is drafted at `docs/licensing/STARTER_ASSETS_LICENSE.draft.md` for the owner's review.
     It covers only Mesh's own script-made starter assets, never third-party or AI-generated ones.
   - Once adopted, it should be copied into every new project beside the kit. Today no notice is copied.
3. **Accurate provenance whenever third-party or AI-generated assets are distributed.**
   - For each such file:
     - a provenance record: source or generator, endpoint, date, prompt or seed, edits;
     - a separate notice passing on any conditions: PixelLab's training exception, and the Open RAIL-M use
       restrictions as clarified;
     - a catalog licence line that says so.
   - **Done (D6).** The guard refuses bundling such a file, or any file without a NOTICE row
     (`tests/test_distributed_asset_provenance.py`).
   - **Still needed:** two code changes.
     - Studio's model reimport keeps the old "made by Mesh's own scripts" licence line, and must stop.
     - `make_starter_kit.py` must stop stamping one licence line on every model.
4. **Lifting the guard** happens only after items 1–3, by owner decision, as a reviewed change to that test.

## Safeguards already in place

- **Raw generator records are never committed.**
  - Every `raw/` folder is git-ignored: PixelLab job dumps hold the account id inside storage URLs.
  - `tests/test_generated_asset_hygiene.py` fails on any of these in a tracked file (its full scan runs in CI's whole-suite pytest step; its quick checks are in the fast tier):
    - a raw record;
    - a storage URL or signed URL containing an id;
    - a bearer-token literal;
    - the owner's token or account id, with or without hyphens, recognised by their SHA-256 digests.
  - Nothing can strip every identifier from a generator's response: a bare account id under an ordinary key looks
    like a job id. The digest check is the backstop.
- **Distributed files carry provenance.** `tests/test_distributed_asset_provenance.py` (D6).
- **Generation runs on one shared budget.**
  - `tooling/pixellab_budget.py`: every request reserves its cost before it is sent.
  - Endpoints without an established cost are refused, and so is anything over the approved budget or the agent's
    own cap.
  - QA agents are never in the ledger, so they are read-only.
  - A subtask spends from its parent agent's cap, so delegating can't add budget.
  - Results are stored sanitized.
