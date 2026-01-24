from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _write_presets(tmp_path: Path, payload) -> Path:
    path = tmp_path / "packs" / "core_regions" / "data" / "encounter_presets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_preset_file_shape_validation_is_deterministic() -> None:
    from engine.validators.encounter_budget_validator import EncounterBudgetValidator

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        presets_path = _write_presets(tmp_path, {"presets": "nope"})

        validator = EncounterBudgetValidator()
        with patch("engine.validators.encounter_budget_validator.resolve_path", return_value=presets_path):
            results = validator.validate({"settings": {}}, "scenes/x.json", strict=True)

        messages = [r.message for r in results if r.level == "ERROR"]
        assert "packs/core_regions/data/encounter_presets.json: 'presets' must be a list or object" in messages


def test_unknown_preset_keys_warn_or_error_based_on_strict() -> None:
    from engine.validators.encounter_budget_validator import EncounterBudgetValidator

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        presets_path = _write_presets(tmp_path, {"presets": [{"id": "normal", "extra_key": 1}]})

        validator = EncounterBudgetValidator()
        with patch("engine.validators.encounter_budget_validator.resolve_path", return_value=presets_path):
            results = validator.validate({"settings": {}}, "scenes/x.json", strict=False)
        messages = [r.message for r in results if r.level == "WARN"]
        assert (
            "packs/core_regions/data/encounter_presets.json: preset 'normal' has unknown keys: extra_key" in messages
        )

        validator_strict = EncounterBudgetValidator()
        with patch("engine.validators.encounter_budget_validator.resolve_path", return_value=presets_path):
            results_strict = validator_strict.validate({"settings": {}}, "scenes/x.json", strict=True)
        messages_strict = [r.message for r in results_strict if r.level == "ERROR"]
        assert (
            "packs/core_regions/data/encounter_presets.json: preset 'normal' has unknown keys: extra_key"
            in messages_strict
        )


def test_unknown_preset_id_is_error() -> None:
    from engine.validators.encounter_budget_validator import EncounterBudgetValidator

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        presets_path = _write_presets(tmp_path, {"presets": [{"id": "normal"}]})

        validator = EncounterBudgetValidator()
        with patch("engine.validators.encounter_budget_validator.resolve_path", return_value=presets_path):
            results = validator.validate(
                {"settings": {"encounter_preset_id": "missing"}}, "scenes/x.json", strict=True
            )

        messages = [r.message for r in results if r.level == "ERROR"]
        assert "Unknown encounter_preset_id 'missing'" in messages

