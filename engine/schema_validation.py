"""Runtime JSON Schema validation for loader boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, ValidationError
from jsonschema.exceptions import best_match
from referencing import Registry as ReferencingRegistry
from referencing import Resource

_SCHEMA_DIR = Path(__file__).with_name("schemas")
_SCHEMA_CACHE: dict[str, Draft202012Validator] = {}


class SchemaValidationError(Exception):
    """Raised when a JSON payload fails schema validation."""

    def __init__(
        self,
        *,
        file_path: str | Path,
        json_pointer: str,
        message: str,
        schema_name: str,
    ) -> None:
        self.file_path = str(file_path)
        self.json_pointer = json_pointer
        self.message = str(message)
        self.schema_name = str(schema_name)
        super().__init__(self.__str__())

    def __str__(self) -> str:
        pointer = self.json_pointer if self.json_pointer else ""
        return (
            f"Schema validation failed for '{self.file_path}' "
            f"against '{self.schema_name}' at '{pointer}': {self.message}"
        )


def validate(data: Any, schema_name: str, file_path: str | Path) -> Any:
    """Validate *data* against the named schema and return it unchanged."""

    validator = _get_validator(schema_name)
    errors = list(validator.iter_errors(data))
    if not errors:
        return data

    error = _pick_relevant_error(errors)
    raise SchemaValidationError(
        file_path=file_path,
        json_pointer=_json_pointer(error.absolute_path),
        message=error.message,
        schema_name=schema_name,
    )


def _get_validator(schema_name: str) -> Draft202012Validator:
    validator = _SCHEMA_CACHE.get(schema_name)
    if validator is not None:
        return validator

    schema_path = _schema_path(schema_name)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry_factory = cast(Any, ReferencingRegistry)
    validator = Draft202012Validator(schema, registry=registry_factory(retrieve=_retrieve_schema))
    _SCHEMA_CACHE[schema_name] = validator
    return validator


def _retrieve_schema(uri: str) -> Resource[Any]:
    schema_path = _schema_path_from_uri(uri)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Resource.from_contents(schema)


def _schema_path(schema_name: str) -> Path:
    schema_path = _SCHEMA_DIR / schema_name
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    return schema_path


def _schema_path_from_uri(uri: str) -> Path:
    if uri.startswith("engine/schemas/"):
        schema_path = Path(uri)
    elif uri.startswith("file://"):
        schema_path = Path(uri.removeprefix("file://"))
    else:
        schema_path = _SCHEMA_DIR / uri

    if not schema_path.is_absolute():
        schema_path = Path.cwd() / schema_path if schema_path.parts[:2] == ("engine", "schemas") else _SCHEMA_DIR / schema_path.name

    if not schema_path.is_file():
        fallback = _SCHEMA_DIR / Path(uri).name
        if fallback.is_file():
            return fallback
        raise FileNotFoundError(f"Unable to resolve schema URI: {uri}")

    return schema_path


def _pick_relevant_error(errors: list[ValidationError]) -> ValidationError:
    candidate = best_match(errors)
    while candidate.context:
        candidate = best_match(candidate.context)
    return candidate


def _json_pointer(path: Any) -> str:
    return "".join(f"/{_escape_pointer_token(token)}" for token in path)


def _escape_pointer_token(token: Any) -> str:
    text = str(token)
    return text.replace("~", "~0").replace("/", "~1")
