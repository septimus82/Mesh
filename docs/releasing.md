# Releasing

Use the **Release Draft** workflow to create a draft GitHub Release from CI artifacts.

## Prerequisite
- The tag must already exist on `origin` (for example `v0.4.1`).

## Workflow
1. Open **Actions → Release Draft → Run workflow**.
2. Fill inputs:
   - `tag`: required existing tag (example: `v0.4.1`)
   - `target_ref`: optional checkout ref (default `main`)
   - `artifacts_run_id`: optional CI run id to reuse artifacts
     - Leave empty to generate fresh artifacts in this workflow.
3. Run workflow.

## What it does
- Generates (or downloads) verify artifacts.
- Requires `release_notes.md` in the artifact set.
- Creates `artifacts_bundle.zip` from artifacts with deterministic entry ordering.
- Creates a **draft** GitHub Release with:
  - Title: `Mesh Engine <package_version>`
  - Body: first 120 lines of `release_notes.md`
  - Attached asset: `artifacts_bundle.zip`

## Publish
- Open the created draft release in GitHub and click **Publish release**.
