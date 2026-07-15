"""Full JSON Schema validation (Draft 2020-12) via the ``jsonschema`` library.

v5.12 shipped a hand-rolled validator that understood seven keywords and
silently ignored everything else — string/number/boolean types, ``$ref``,
ranges, lengths, ``additionalProperties`` all passed unchecked (2026-07 audit
P1-3), so ``book_title=123`` saved fine. A validator that quietly skips most
of the schema is worse than none: it looks like a gate. ``jsonschema`` is now
a hard dependency.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def validate_json_object(data: Any, schema_name: str) -> list[str]:
    """Validate an in-memory object BEFORE it is written anywhere."""
    schema_path = _schema_path(schema_name)
    if not schema_path.exists():
        return [f"missing schema: {schema_path}"]
    try:
        validator = _validator(str(schema_path))
    except json.JSONDecodeError as exc:
        return [f"invalid schema JSON: {exc}"]
    errors: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        location = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path
        )
        errors.append(f"{location}: {error.message}")
    return errors


def require_valid_json_object(data: Any, schema_name: str) -> None:
    errors = validate_json_object(data, schema_name)
    if errors:
        raise ValueError("; ".join(errors))


def validate_json_file(path: str | Path, schema_name: str) -> list[str]:
    json_path = Path(path)
    if not json_path.exists():
        return [f"missing JSON file: {json_path}"]
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]
    return validate_json_object(data, schema_name)


def require_valid_json_file(path: str | Path, schema_name: str) -> None:
    errors = validate_json_file(path, schema_name)
    if errors:
        raise ValueError("; ".join(errors))


def _schema_path(schema_name: str) -> Path:
    name = schema_name if schema_name.endswith(".schema.json") else f"{schema_name}.schema.json"
    return SCHEMA_DIR / name


@lru_cache(maxsize=None)
def _validator(schema_path: str) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
