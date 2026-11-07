# L1b applied to `D:\Games\Lakeside Village` (owner-authorised 2026-11-07)

Owner approval: final visual sign-off of L1b at `55dbe59`, and authorisation to apply it with safeguards.

| Step | Result |
|---|---|
| 1. Original checksums | `cottage.json` 1a07a9cb…440f08 · `lakeside.json` 18a7ee94…7f3901 · `start.json` d2e8a80e…c401b |
| 2. Backup | whole project (67 files, 2.3 MB) copied to `D:\Games\Lakeside Village - backup 20261107-094306`. Every file's sha256 matched before and after the application (`inventory_before.txt` = `inventory_backup.txt`). |
| 3. Approved candidate | bytes from `git show 09bb78a:…/candidate/lakeside.json`; sha256 `dd850648923cb382bf2914a26f824c2c2d58410cdad9ccc52326154966f12213` (checked before installing) |
| 4. Replaced | `packs/core_regions/scenes/lakeside.json` only |
| 5. Installed hash | `dd850648923cb382bf2914a26f824c2c2d58410cdad9ccc52326154966f12213`, equal to the approved candidate |
| 6. Other rooms | `cottage.json` and `start.json` byte-identical. Whole-project inventory: only `lakeside.json` differs (`inventory_installed.txt`). |
| 7. Validation on the installed project | see below; all passed |
| 8. Restore | not needed |

**Validation details:**
- **Routes:** 7 of 7 behave as expected; 6 of 6 navigation queries succeed; feet never off the ground; GPU objects
  stable across room changes.
- **Studio:** reopen shows no differences apart from the shared player, and nothing is unsaved after opening or at
  the end. Play/Stop ×5 with GPU objects stable.
- **Export:** `mesh export build` exits 0. The bundle runs on its own engine, starts in the Village and walks east
  into Lakeside (arrives at 30.0, 3.44 m).
- **Transitions:** Lakeside → Village and Village → Lakeside both work. No lamps are lit; the lamp posts stay.
- **Side effects:** the validation wrote no file into the project (`inventory_after_validation.txt` =
  `inventory_installed.txt`).
