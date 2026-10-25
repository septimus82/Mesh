# M17 Stage 1B: PixelLab licence and provenance review

Reviewer: Claude, as the licence and provenance reviewer. Date: 2026-10-25. Repository: `D:\Games\Mesh-m17`, branch
`feature/m17-stage1b`, HEAD `be13ad1`. I worked read-only: no repo edits, no git writes, no PixelLab API calls, and I
contacted nobody.

**I am not a lawyer.** This is a reading of the published texts. The points marked **[legal advice]** need a
qualified IP or contract lawyer. PixelLab's terms are governed by Swedish law (ToS §7.1), and Mesh's own licence is
undefined (see §3.3).

---

## 0. Bottom line

- **The outputs are not forbidden.** Under PixelLab's ToS the subscriber owns its outputs and may use, modify and
  distribute them commercially, "for any purpose" (§1.3, §3.3). The ToS sets no plan-tier condition and has no
  "no asset packs" clause.
- **The outputs are not unrestricted either.** Three restrictions apply:
  1. **No training of AI models** on the outputs without PixelLab's written permission (§1.2, §3.3).
  2. **The CreativeML Open RAIL-M use restrictions** (Attachment A) govern how outputs are used (ToS §4.1, plus
     §6 of that licence).
  3. **No warranty**: PixelLab gives none on IP (§5.1), and the subscriber carries the third-party-rights risk
     (§3.3).
- **Mesh cannot re-grant the training permission.** It can pass both restrictions on as conditions in a separate
  notice for those files.
- **The repo has no licence text.** `pyproject.toml` says `license = "LicenseRef-Proprietary"`, but there is no
  LICENSE file. The repo is **public** on GitHub. Stage 1's premise that "an open engine licence can't pass those
  restrictions on" is wrong about the facts: Mesh's licence is proprietary and undefined, not open.
- **The pilot outputs are already public.** Commit `be13ad1` is on `origin/feature/m17-visual-quality` in a public
  repo. That is distribution, and ToS §3.3 permits it, but there is no notice beside the files yet.
- **Recommendation:** Option A for now: don't ship the files, and add a notice to the pilot folder. If the owner
  wants the stronger assets (stone, slate roof, door, window, hero), take Option B: send the drafted email, then
  ship under a separate notice once PixelLab replies in writing.

---

## 1. Sources (all fetched 2026-10-25)

| # | Source | URL | Last updated | What it contributes |
|---|---|---|---|---|
| S1 | PixelLab Terms of Service | https://www.pixellab.ai/termsofservice | **2025-11-23** (unchanged since the previous review) | §1.2 training, §1.3 ownership and commercial use, §2.1–2.3 limits and changes, §2.2 API use, §3.3 ownership and distribution, §3.4 storage, §4.1 Open RAIL-M, §5.1 no warranty, §6.1 liability, §7.1 Swedish law, §8.1 termination |
| S2 | PixelLab FAQ | https://www.pixellab.ai/docs/faq | none shown | "Can I use the generated images commercially?"; "Does PixelLab use my inputs…for training?"; "Can I use AI assets on Steam?" (links Valve's AI disclosure rules); subscription questions |
| S3 | PixelLab home and pricing | https://www.pixellab.ai/ (`/#checkout`) | none shown | Plans load dynamically, and the fetched page showed no plan names or per-tier licence terms; "Tier 2: Pixel Artisan" is not visible there |
| S4 | PixelLab API page | https://www.pixellab.ai/pixellab-api | none shown | Characters and objects are saved server-side; tier notes; "Powered by MiniMax H3" for PixMiniMax only (not used by the pilot); no licence terms |
| S5 | PixelLab API v2 docs | https://api.pixellab.ai/v2/docs | none shown | Rendered no fetchable text (a JavaScript app); no licence terms found |
| S6 | PixelLab Docs index | https://www.pixellab.ai/docs | none shown | Links to the FAQ only; no licensing page |
| S7 | PixelLab Refund Policy | https://www.pixellab.ai/refundpolicy | 2026-01-14 | Refunds only; silent on rights after cancellation |
| S8 | **CreativeML Open RAIL-M** (the licence the ToS links to) | https://github.com/CompVis/stable-diffusion/blob/main/LICENSE (raw: https://raw.githubusercontent.com/CompVis/stable-diffusion/main/LICENSE) | dated 22 Aug 2022 | Definitions (§1), distribution conditions (§4), use restrictions (§5 and Attachment A), Output (§6), updates (§7) |
| S9 | RAIL initiative licence list | https://www.licenses.ai/ai-licenses | none shown | Confirms the RAIL family is several licences (BigScience Open RAIL-M, AIPubs OpenRAIL-M and others) and that "Open RAIL-M" alone doesn't identify one text |
| S10 | US Copyright Office, *Copyright and Artificial Intelligence, Part 2: Copyrightability* | https://www.copyright.gov/ai/ | published 2025-01-29 | Background on whether AI outputs can be copyrighted. The landing page doesn't state the conclusions; my summary below is from the report and should be checked **[legal advice]** |

Secondary results were used only to find the pages above, never as sources. One of them, a third-party GitHub
asset-pack licence, claims commercial rights depend on a paid plan. PixelLab's own texts don't say that.

**Which Open RAIL-M?** ToS §4.1 says "the Open RAIL-M license" and links to the CompVis Stable Diffusion
repository's LICENSE. That file is the **CreativeML Open RAIL-M** of 22 Aug 2022, the Stable Diffusion v1 licence.
The ToS doesn't name a model. It doesn't say whether pixflux, bitforge, tiles-pro, inpaint-v3 or the character
and animation generators are Stable Diffusion v1 derivatives, and the API docs don't either. This is ambiguity Q1.

---

## 2. Findings

### 2.1 Ownership and commercial use

- **Ownership.** ToS §1.3: "You own the copyrights to your creations" (S1). Commercial and non-commercial use need no
  permission. §3.3 repeats that the user keeps ownership of content they create. It also says the user may use,
  modify and distribute outputs for any purpose, except training other models without explicit permission.
- **Commercial use.** Permitted (ToS §1.3). The FAQ agrees, with one condition: "we only ask that you do not train
  new models with the images" (S2).
- **Plan tier.** The ToS and FAQ don't tie ownership or commercial use to any tier. The pricing page (S3) showed no
  per-tier licence terms. Tiers affect which tools and limits are available (S2, S4), not rights. The pilot used a
  paid plan, so the free-trial question doesn't arise.
- **After the subscription ends.** Nothing in the ToS says rights in existing outputs lapse when a subscription ends.
  §8.1 lets PixelLab end *access to the service* at any time. The ownership wording is stated as ownership, not as a
  licence that depends on the subscription. The ToS has **no survival clause**, though, and §2.1/§2.3 let PixelLab
  change terms with "reasonable notice", without saying whether changes reach outputs already made. This is
  ambiguity Q5. My reading is that the risk is low, but PixelLab should confirm it in writing.
- **Is there copyright at all? [legal advice]** PixelLab can only give the user what the law recognises. My summary
  of S10, from the report itself: in the US, material determined by an AI from prompts alone isn't protected, while
  human-authored contributions (creative edits, selection and arrangement) can be. EU and Swedish law likewise
  require human intellectual creation. Unedited pilot outputs may therefore carry **weak or no copyright**. Mesh's
  hand edits, and the arrangement in the cottage model, are the parts most likely to be protected. In practice:
  Mesh can't promise downstream users exclusivity or enforceable copyright in the raw outputs, and anyone could
  generate similar art.

### 2.2 Restrictions

**Training (the strictest one).**
- ToS §1.2: the user may not train their own models on PixelLab images without PixelLab's written permission.
- ToS §3.3: the "any purpose" distribution right excludes training other models without explicit permission.
- The FAQ makes the same request.
- **For the subscriber (the Mesh owner):** no training, fine-tuning or LoRA on the outputs without written
  permission. Using an image as *input context* for an AI at inference time (an MCP tool showing Claude a texture,
  for example) isn't training in the ordinary sense. The ToS doesn't define "train", though (ambiguity Q3).
- **For downstream recipients:** the ToS is a contract between PixelLab and its user, so it doesn't bind recipients
  directly. The distribution right in §3.3 carries the training exception, however. The prudent reading is that the
  subscriber should not hand outputs on in a way that authorises training, so the restriction should be **passed on
  as a condition**. Whether PixelLab requires this is ambiguity Q3.
- **CreativeML adds a reason.** Its §1 definition of "Derivatives of the Model" covers any model created by
  transferring the Model's outputs, explicitly including training on synthetic data the Model generated. A model
  trained on these outputs could therefore itself be a Derivative, carrying all of Open RAIL-M's distribution
  conditions.
- **The public repo.** The repo is public, so scrapers can take the files whatever a notice says. A notice still
  documents that Mesh didn't authorise training. That is all Mesh can reasonably do; it isn't a guarantee.

**Redistribution as editable source files.**
- ToS §3.3 permits distribution "for any purpose", with only the training exception. That text doesn't limit
  distribution to finished games.
- There is **no "no asset packs / no resale as stand-alone assets" clause** in the ToS, the FAQ or the API page
  (S1, S2, S4).
- ToS §2.2 does require prior contact for using the **API** to build your own service or to resell. My reading is
  that this governs use of the API, not of outputs. Two cases sit close to it, though: a free engine bundling an
  editable kit, and any future Mesh feature that calls PixelLab for Mesh's users. This is ambiguity Q4/Q6.

**Attribution.**
- PixelLab requires none (S1, S2).
- CreativeML §4(d) (keep notices) applies to distributing the *Model or its Derivatives*, not outputs.
- "Powered by MiniMax H3" appears only for PixMiniMax (S4), which the pilot didn't use.
- **A downstream disclosure duty is likely.** The FAQ points to Valve's Steam rules, which require games to disclose
  pre-generated AI content. Engine users who ship kit art on Steam need to know which files are AI-generated. That
  is a practical reason to label the files, even though PixelLab doesn't require it.

**Open RAIL-M (CreativeML Open RAIL-M, S8).**
- **Definitions (§1).**
  - "Output" means the results of operating the Model.
  - "Derivatives of the Model" covers modifications, works based on the Model, and models trained on its outputs or
    weights (including distillation and training on synthetic data).
  - **Outputs as such are not Derivatives.** They become relevant to that definition only when used to train another
    model.
- **Pass-through (§4(a)–(d), §5).** §4(a) requires the use restrictions to be included as an enforceable provision
  when distributing the **Model or Derivatives**, with a copy of the licence (§4(b)), change notices (§4(c)) and
  retained notices (§4(d)). §5 requires the licensee to make **its users of the Model** comply. PixelLab is the
  licensee here, and its users are bound through ToS §4.1. None of these clauses requires passing restrictions to
  **recipients of outputs**.
- **Outputs (§6).** The quote: "Licensor claims no rights in the Output You generate using the Model". The user is
  accountable for the output and its later uses, and no use of the output may contravene the licence.
  - So the Attachment A restrictions **do attach to how the Mesh owner uses the outputs**.
  - Through "subsequent uses", the owner arguably carries some responsibility for what downstream users do with
    them **[legal advice]**.
- **Attachment A, in practice.** It prohibits:
  - illegal use;
  - exploiting or harming minors;
  - harmful disinformation;
  - harmful disclosure of personal data;
  - defamation or harassment;
  - fully automated decisions that affect legal rights;
  - discrimination or harm based on social behaviour or personal characteristics;
  - exploiting vulnerable groups;
  - discrimination on protected characteristics;
  - medical advice;
  - law-enforcement, justice or immigration uses.

  None plausibly affects using a stone texture or a walking hero in a game. Passing them on costs nothing and
  removes the "subsequent uses" exposure. **Prudent, not clearly required.**
- **§7 (updates).** The licensor may restrict or update the Model remotely. This concerns the service, not
  outputs already made.

**Other points.**
- **Hand-edited outputs.** The ToS is silent. The owner's edits are the owner's own authorship. The generated
  parts keep the training and RAIL restrictions after editing; nothing in the texts says editing removes them.
- **Mixing with other works.**
  - `cottage_m17.glb` mixes Mesh's own geometry and starter textures (timber, plaster, floorboards) with PixelLab
    textures: `stone_b_seamfix`, `roof_slate` and `window_a`. I confirmed these by the image names inside the GLB.
  - The contact sheets and `walk_preview.webp` put Mesh's baseline art beside PixelLab outputs.
  - The texts don't restrict mixing, but mixed files need **mixed licence lines**: the PixelLab restrictions attach
    to the PixelLab parts.
- **Inputs.** All image inputs were palette swatches from Mesh's own textures, or earlier PixelLab outputs (an
  `init_image` for `moss_roof_slate`; the inpaint source for `stone_b_seamfix`). There were no third-party images,
  and the prompts are generic descriptions. That lowers the §3.3 third-party-rights risk, but it doesn't remove it,
  because PixelLab gives no IP warranty (§5.1).
- **PixelLab's own use.** The FAQ says PixelLab doesn't train on user content. ToS §3.4 says it won't do so without
  notice in the interface, and may keep images for debugging. Characters are kept server-side by design (S4).
  Nothing in the texts gives PixelLab a licence over the outputs.

### 2.3 Independent check of the Stage 1 licence finding

`docs/reviews/milestone17_stage1_evidence/tech_qa.md` D3/D6 and `milestone17_stage1_visual_quality.md`:

- **Correct:**
  - the ToS date;
  - ownership and distribution (§3.3);
  - the training restriction;
  - §4.1;
  - that the NOTICE, PROVENANCE and catalog lines would become false if these files moved into `assets/`;
  - D6: reimport keeps the licence string. I confirmed it: `engine/hd2d/catalog.py` `reimport_model` updates
    `preview`, facts and `source`, and never `license`.
- **Incorrect or incomplete:**
  1. "An open engine licence can't pass those restrictions on." Mesh's licence isn't open: it is
     `LicenseRef-Proprietary`, with no licence text in the repo. The real problem is that **no licence grant exists**
     for downstream users, for the existing kit as well.
  2. It didn't identify the Open RAIL-M variant (CreativeML, the Stable Diffusion v1 text), or that outputs aren't
     "Derivatives" under its definitions.
  3. It missed two facts:
     - the pilot outputs are **already published** on a public GitHub branch;
     - `MANIFEST.in` has `recursive-include assets *.png`, so anything moved into `assets/` would ship in the
       **sdist** whether or not it is on the wheel allow-list.
  4. D6 has a second effect. A reimport also replaces `source` (`{"kit": …}` becomes a local file path), so the kit
     provenance is lost as well as the licence going stale.

---

## 3. If PixelLab files were included in Mesh's starter kit

### 3.1 How the kit reaches users today (repo facts)

- **The wheel.** It ships only the files listed in `pyproject.toml` `[tool.setuptools.data-files]` (178 files;
  `docs/packaging.md` "The allow-list"). They install under `share/mesh-engine`, and the engine finds them with
  `engine.repo_root.bundled_file` / `bundled_dir`.
- **The sdist.** `MANIFEST.in` includes `assets/**/*.png|json|wav`, so the sdist ships everything in `assets/`,
  allow-list or not, except files excluded by name (line 92 excludes the three legacy sprites).
- **New HD-2D projects.** `engine/hd2d/starter_village.py` calls `catalog.install_kit`, which copies each model and
  preview and writes a project catalog entry. The entry copies the kit's `license` string verbatim, and `source` is
  `{"kit", "sha256"}`. The ground textures, `hd2d_hero.png` and the other sprites are copied as **plain files with no
  licence metadata**.
- **No notice file goes into projects.** `assets/NOTICE.md` and `assets/hd2d_starter/PROVENANCE.md` stay in the
  install (a grep of `engine/` finds no copy step).
- **Licence lines.**
  - `tooling/hd2d_assets/make_starter_kit.py` stamps **one constant** on every model: `LICENSE = "Mesh HD-2D starter
    kit: original, made by Mesh's own scripts; ships with Mesh"`, line 25. All 14 entries in
    `assets/hd2d_starter/catalog.json` carry it.
  - Studio's import form has a free-text "Licence / source" field (`engine/studio_hd2d.py`).
  - A reimport keeps whatever licence line was there and replaces `source`.
- **The current texts claim sole authorship.**
  - `assets/NOTICE.md` lists `assets/hd2d_starter/**` as "Mesh's own".
  - `PROVENANCE.md` says "original work made for Mesh by Mesh's own scripts … no third-party art" and "licensed like
    the rest of the Mesh repository".
  - `docs/packaging.md` says "Everything is Mesh's own work, except two groups".
  - All of these would become **false** for PixelLab files.

### 3.2 What Mesh could and could not grant to engine users

**Could grant**, as owner of the outputs to whatever extent copyright exists:
- use, copying and modification of the files;
- inclusion in their own games, commercial or not, and redistribution of the games;
- redistribution of the files themselves, edited or not, as part of their projects.

**Could not grant:**
- **Permission to train AI models** on the files. Only PixelLab can permit that, in writing (ToS §1.2/§3.3), and a
  model trained on them could fall under CreativeML's Derivatives definition.
- **Release from the CreativeML Open RAIL-M Attachment A use restrictions** (Open RAIL-M §6).
- **Any warranty** of copyright, exclusivity or non-infringement. PixelLab gives none (§5.1), and copyright in raw
  AI output is uncertain (S10).
- **Any right to use PixelLab's service or API.** The licence concerns files, not service access.

### 3.3 Compatibility with the repo's licence "as written"

- There is **no LICENSE file**: `git ls-files` finds only `assets/icons/lucide/LICENSE`. `README.md` has no licence
  statement.
- The only licence statement is `pyproject.toml` `license = "LicenseRef-Proprietary"`. A `LicenseRef-` identifier is
  supposed to point to an included licence text, and none exists.
- So the default (all rights reserved) applies. Read strictly, downstream users have **no written permission** to
  redistribute even the existing Mesh-made starter kit. `PROVENANCE.md`'s "ships with Mesh for every creator to use
  in their own games" is an informal statement of intent, not a licence.
- **Compatibility.** There is nothing to conflict with. A proprietary or undefined licence can carry the PixelLab
  restrictions, unlike permissive open-source licences.
- **The gap is the problem.** The kit needs an explicit **asset licence** for creators, with or without PixelLab art.
  If the engine code later goes open source (MIT or Apache, say), the PixelLab files must be **carved out** under
  their own notice, as `assets/branding/NOTICE.md` already does for the brand. **[legal advice]** for the wording of
  the creator asset licence.

### 3.4 What would have to change (for Options B and C)

1. **A separate notice for the PixelLab files.** For example, `assets/hd2d_starter/NOTICE-PixelLab.md`, shipped with
   the files and **copied into every project** that receives them. It should state:
   - which files were generated with PixelLab (pixellab.ai), under a paid subscription, on 2026-10-25, under the ToS
     version of 2025-11-23;
   - that they are AI-generated, with or without hand edits, and that Steam and similar stores may require
     disclosure;
   - **the permission**: use, modify and redistribute in your games, commercially or not;
   - **the restriction**: no use to train, fine-tune or distil AI models (PixelLab ToS §1.2/§3.3);
   - **the restriction**: no use for the purposes listed in CreativeML Open RAIL-M Attachment A (the list or a link
     to S8);
   - a pass-through duty: anyone redistributing the files must pass these two restrictions on;
   - that the files come with no warranty of copyright or non-infringement.
2. **A new `assets/NOTICE.md` row for the PixelLab files, and a corrected `assets/hd2d_starter/**` row.** The second
   should read "Mesh's own except the files listed in NOTICE-PixelLab.md". Fix `docs/packaging.md` "Everything is
   Mesh's own work, except two groups" to say three groups.
3. **`PROVENANCE.md`.** Add a section listing each PixelLab-derived file, with a link to sanitised per-file records
   (endpoint, date, prompt, seed, cost, post-processing, hand edits). Remove "no third-party art" for those files,
   or qualify it as AI-generated output owned by Mesh's owner.
4. **Per-model catalog licence lines.**
   - `make_starter_kit.py` must stop stamping one constant.
   - Mixed models such as a re-dressed cottage need a line like: *"Mesh geometry; textures stone/roof/window
     generated with PixelLab (AI); see NOTICE-PixelLab.md: no AI training; Open RAIL-M use restrictions"*.
   - Sprites and ground textures copied as plain files need a sidecar or a catalog entry. At present they carry no
     licence metadata in projects.
5. **The allow-list and its test.** Add each file and the notice to `[tool.setuptools.data-files]`, and update
   `tests/test_wheel_bundles_engine_data.py`. Also decide on the **sdist**: `MANIFEST.in`'s
   `recursive-include assets *.png` ships every PNG regardless of the allow-list. Line 92 already excludes the three
   unverified legacy sprites the same way. Any PixelLab file kept out of the kit, or kept in `assets/` only for
   development, needs the same `exclude` line.
6. **`install_kit` and the project template.** Copy the notice into the project, for example
   `assets/models/NOTICE-PixelLab.md`, and keep it with exports. Then check that `mesh export build` keeps it in
   `dist/bundle`. I didn't verify the export path.
7. **Studio reimport (`catalog.reimport_model`).** On reimport, clear the licence line or ask for a new one, and
   don't silently drop the `source.kit` provenance. Otherwise reimporting a kit model leaves a false licence.
8. **The pilot folder, now** (Option A as well). It is public, so add a short notice to
   `tooling/hd2d_assets/pilot_m17/` with points (1)'s restrictions. Add licence fields to
   `characters/provenance.json` and `models/provenance.json`; only the textures have one.

### 3.5 Options, most to least conservative

**A. Don't ship the PixelLab files; use them as reference only. (Recommended for now.)**
- Mesh's own scripts or hand-drawing reproduce the ideas the pilot showed: stone plinth, slate roof, door, window,
  the hero's silhouette and stride.
- The current NOTICE, PROVENANCE, catalog lines and allow-list stay true unchanged.
- Add a notice to the public pilot folder (§3.4 item 8).
- Avoid copying outputs pixel for pixel into "Mesh's own" files. That would make the "Mesh's own" claim false
  again.
- The pilot found plaster, timber and moss **no better** than the starter art, so little of value is lost.

**B. Ship only after written confirmation from PixelLab, under a separate notice.**
- Send the drafted email (§4).
- If PixelLab confirms Q2–Q5 in writing, make every change in §3.4 and ship only the picked files: for example
  `stone_b_seamfix`, `roof_slate`, `door_a`, `window_a` and `hero_m17`, edited or not.
- Keep the reply with the provenance, as a non-public record.
- Have a lawyer review the creator asset licence wording **[legal advice]**.

**C. Ship now under a separate notice, with the restrictions passed on.**
- Make the changes in §3.4 without waiting for PixelLab, relying on ToS §3.3's "any purpose".
- **Risk:** the ambiguities in §4 stay open. Above all, it is unclear whether PixelLab expects the training
  restriction to bind recipients, and whether rights survive ToS changes.
- Defensible on the current text, but it puts Mesh's interpretation into a public download.

Separately, in every option, the repo needs a real licence text. That isn't caused by PixelLab, but it decides what
any starter-kit file grants.

---

## 4. Ambiguities and a draft clarification request

### 4.1 The open questions

- **Q1. Which model and licence.** ToS §4.1 refers to "the Open RAIL-M license" and links to the CreativeML Open
  RAIL-M in the CompVis Stable Diffusion repository. Is that the licence intended for all endpoints, including
  create-tiles-pro, create-image-pixflux, create-image-bitforge, inpaint-v3, create-character-with-4-directions and
  the template animations? Or do some endpoints use other models with other terms? Which model(s) does it cover?
- **Q2. Use restrictions downstream.** Must a subscriber who redistributes outputs impose the Open RAIL-M Attachment
  A use restrictions on recipients? Or do they bind only the subscriber's own use (Open RAIL-M §6)?
- **Q3. Training restriction downstream, and its scope.**
  - Does the §1.2/§3.3 restriction bind only the subscriber?
  - Must the subscriber impose it on people who receive the redistributed files?
  - Is a written notice in the distributed package enough?
  - What counts as "training": does it include fine-tuning, LoRA or embeddings, and does it exclude giving an image
    to an AI assistant as input at inference time?
- **Q4. Editable asset redistribution.** Does §3.3's "any purpose" cover redistributing outputs, edited or not, as
  editable source files in a free, downloadable game-engine starter kit? Engine users would copy the files into their
  own games and redistribute them, commercially. Do any limits apply to asset packs or stand-alone assets?
- **Q5. Durability.**
  - Do ownership and the §3.3 rights in outputs made on a paid plan survive the end of the subscription, or
    termination under §8.1?
  - Do later ToS changes (§2.1/§2.3) apply to outputs already generated?
- **Q6. §2.2 "building your own service".** Distributing outputs in an engine shouldn't count, but please confirm.
  Would a future engine feature that calls the PixelLab API for the engine's users need a separate agreement?
- **Q7. Attribution.** Is no attribution required? Does PixelLab have a preferred credit line?
- **Q8. Outputs made from outputs** (`init_image`, inpainting a previous output). Do the same terms apply,
  unchanged?
- **Q9. Plan and tier.** Do the rights differ between plans or the free trial? (They don't for the pilot, but it
  matters for anyone reproducing the kit.)

### 4.2 Draft email: NOT SENT

The owner sends this only if they choose to. I haven't contacted anyone. The ToS contact address is obfuscated on
the page, and the docs point to Discord, so the owner should take the address from pixellab.ai (Terms of Service
page or Enterprise contact) when sending.

> **Subject:** Licensing question: PixelLab outputs in a downloadable game-engine starter kit
>
> Hello PixelLab team,
>
> I make Mesh, a game engine, and I'm a paid PixelLab subscriber (Tier 2: Pixel Artisan). I've generated some
> textures, a door, a window and a 4-direction walking character through your v2 API. I'd like to include some of
> them, possibly hand-edited, in the engine's free downloadable starter kit. Engine users would copy the files into
> their own games and might sell those games.
>
> I've read your Terms of Service (last updated 2025-11-23), especially §1.2, §1.3, §2.2, §3.3 and §4.1. Could you
> confirm the following in writing?
>
> 1. May I redistribute these outputs, edited or not, as editable image files in a free engine starter kit, so
>    that engine users can use them in their own commercial games? Do any limits apply to asset packs or stand-alone
>    assets?
> 2. On the training restriction (§1.2/§3.3): is it enough for my kit to include a notice saying the files may not
>    be used to train, fine-tune or distil AI models? Or do you need something else? Is giving an image to an AI
>    assistant as input, without training, acceptable?
> 3. §4.1 links to the CreativeML Open RAIL-M licence in the CompVis Stable Diffusion repository. Does it cover all
>    the endpoints I used (create-tiles-pro, create-image-pixflux, create-image-bitforge, inpaint-v3,
>    create-character-with-4-directions and the walking template animation)? Must I pass its Attachment A use
>    restrictions on to people who receive the outputs?
> 4. Do my rights in these outputs continue if my subscription ends, and are they unaffected by later changes to the
>    Terms?
> 5. Is attribution required, or do you have a preferred credit line?
> 6. For the future: if the engine offered an optional feature that calls your API with each user's own key, would
>    §2.2 require a separate agreement?
>
> Thank you very much. I'd like to get this right before anything ships.
>
> Kind regards,
> [owner's name], Mesh / MeshMind Studios

---

## 5. Provenance completeness

### 5.1 Per-file coverage of the tracked pilot files

| Folder | File(s) | Record? | Generator / endpoint | Date | Prompt / seed | Cost | Post-processing | Gaps |
|---|---|---|---|---|---|---|---|---|
| textures/ | 15 candidate PNGs (plaster_a/b/c, stone_a/b, stone_b_seamfix, timber_a/b, roof_slate/clay, moss_roof_slate, moss_plaster, door_a, window_a/b) | yes, one entry each in `textures/provenance.json` | yes (tiles-pro 4, pixflux 8, bitforge 2, inpaint-v3 1) | `utc_completed` yes; `utc_submitted` is "see record note" for the 4 tiles-pro files | yes, all have prompt and seed; `request_meta` records `init_image` and inpaint source and mask | `generations_used_by_call` (tiles-pro 15 is shared by 4 files) | yes (byte copies; seamfix offset, inpaint, unoffset) | (a) The 4 tiles-pro submit times point to `raw/`, which isn't in git. (b) `raw_file` and `init_image` paths point into untracked `raw/`, so they are dead references in a clone. (c) `ids` is empty for 11 of 15 (the synchronous endpoints returned none). Acceptable, but say so. (d) The licence note has no ToS version, no training restriction and no RAIL mention. |
| textures/ | `contact_sheet.png` | **no** | derived preview (PixelLab plus starter art) | – | – | – | – | Mixed-provenance preview with no record or licence line |
| textures/ | `tiling_report.json` | data, not art | – | – | – | – | – | none |
| characters/ | `hero_m17.png`, 16 × `hero_m17_frames/*.png` | yes: `calls` (3), `candidates`, `post_processing.per_frame` (16 entries: crop, shift) | yes (`/create-character-with-4-directions` ×2, `/characters/animations` template `walking-4-frames`) | yes (started and finished UTC) | prompt (`description`) and seed for both candidates; the walk request has **no seed** (template mode) | candidates 1 generation each; walk bounded at "6, worst 9" because the account was shared; walk jobs report USD | yes (crop x 12–44, shift y, alpha binarise, no edits) | (e) **No licence field** (textures have one). (f) The cost is only bounded. (g) The `generation_model` value of the walk jobs isn't recorded; only the key name is. Record the value, which isn't sensitive, because it bears on Q1. (h) The generation scripts are "kept in the session scratchpad", not in git, so the run can't be reproduced. (i) The rejected candidate A's files aren't tracked. Fine, but the README names it by a truncated ID. |
| characters/ | `palette_ref.png` | yes (`palette_reference.how`) | Mesh-made from repo textures and the baseline hero | – | – | – | – | none |
| characters/ | `contact_sheet.png`, `walk_preview.webp` | **no** | derived previews (baseline plus PixelLab) | – | – | – | – | Mixed-provenance previews with no record |
| characters/ | `measurements.json` | data | – | – | – | – | – | none |
| models/ | `cottage_m17.glb` | yes (`models/provenance.json`: sha256, build command, Blender version, textures used with their PixelLab endpoints, starter assets reused) | Mesh's Blender script plus 3 PixelLab textures | build date implicit | n/a | n/a | yes | (j) **No licence field.** It is mixed provenance: Mesh geometry and 3 starter textures, plus `stone_b_seamfix`, `roof_slate` and `window_a` from PixelLab. |
| docs/reviews/milestone17_stage1_evidence/ | compare_*.png, hero_m17_8x_grid.png, sprite_*_strip.png, corner_A_vs_B.png, walk_compare.webp | **no** | screenshots containing PixelLab outputs | – | – | – | – | (k) Tracked and public, with no notice. They're review evidence, not shipped (the sdist includes only `docs/*.md|json`). A one-line note in the review would cover it. |

**Hand edits:** none recorded, and the READMEs say none were made. If the owner edits files before shipping, each edit
needs a record: what changed, by whom, and the tool used.

### 5.2 Secrets and identifiers in committed files (counts only)

Scope:
- the 13 tracked text files: `tooling/hd2d_assets/pilot_m17/**` non-binary files, `docs/reviews/milestone17_stage1_visual_quality.md`, and `docs/reviews/milestone17_stage1_evidence/{art_qa.md,pilot.json,tech_qa.md}`;
- the tracked PNG, WEBP and GLB files under `pilot_m17`, scanned as bytes;
- `tooling/m17_visual_pilot.py` at HEAD.

`raw/`: **0 tracked files.** It is ignored by `.gitignore:39` (`tooling/hd2d_assets/**/raw/`), but that `.gitignore`
change is **uncommitted** in the working tree, so commit it. I read nothing inside `raw/`.

| Pattern | Matches | Where | Assessment |
|---|---|---|---|
| `backblaze` | 1 | `tech_qa.md` (D2) | A description of the URL *form*, with `<account>`/`<character>` placeholders. Not a real URL. |
| `pixellab-characters/` | 1 | `tech_qa.md` (the same sentence) | The same placeholder description |
| `?t=` | 1 | `tech_qa.md` (the same sentence) | Placeholder (`?t=…`). No token value. |
| `Bearer` | 1 | `characters/provenance.json` `api.auth` | Text only: the token came from an environment variable and wasn't recorded. No token value. |
| `PIXELLAB_API_TOKEN` | 3 | provenance and two review docs | The environment-variable name only |
| UUIDs inside URLs | **0** | – | – |
| URLs in total | 23 | 20 × `https://api.pixellab.ai/v2/<endpoint>` (provenance), 2 × the ToS page, 1 × github.com | Public endpoints only; no storage URLs |
| Bare UUIDs (not in URLs) | 31 occurrences, 15 distinct | textures 10 (4 distinct), characters 19 (9), models 2 (2) | PixelLab resource IDs: character, job, animation group, tile and generation. **None matches the account UUID** (checked by prefix and suffix, without printing values). They aren't credentials. Together with the owner's token they identify the owner's server-side characters, so the owner may prefer hashing or dropping them before anything ships. |
| Account-UUID fragment | **2** | `tech_qa.md` line 24 | A truncated form (the first 4 and last 5 hex digits) of the owner's account UUID. Not usable on its own, but it is part of an account identifier in a public file. Replace it with `<account>`. |
| Signed-URL markers (`X-Amz`, `Signature=`, `Expires=`, `token=`), API-key prefixes, email addresses, `account_id`/`user_id` fields | 0 | – | – |
| Tracked PNG, WEBP and GLB under `pilot_m17` | 0 hits | – | The GLB `asset` block has only generator and version |

**Result:** no committed file contains a storage URL, a token or a full account identifier. There are two small
clean-ups: the account-UUID fragment in `tech_qa.md`, and committing the `.gitignore` rule for `raw/`. Also consider
whether to keep the 15 resource IDs.
