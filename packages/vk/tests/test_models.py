"""Guards against drift between the Pydantic models and the legacy JSON schemas."""

from typing import Any

import pytest
from pydantic import BaseModel

from vk import models, schemas


def resolve(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        return resolve(defs[node["$ref"].rsplit("/", 1)[1]], defs)
    return node


def shape(node: dict[str, Any], defs: dict[str, Any]) -> Any:
    """Reduce a schema to property names, required sets, enums, and array shape."""
    node = resolve(node, defs)
    if "properties" in node:
        return {
            "required": set(node.get("required", [])),
            "props": {k: shape(v, defs) for k, v in node["properties"].items()},
        }
    if node.get("type") == "array":
        return ["array", node.get("minItems", 0), shape(node["items"], defs)]
    if "enum" in node:
        return set(node["enum"])
    return None


@pytest.mark.parametrize(
    ("model", "schema"),
    [
        (models.Classification, schemas.CLASSIFIER_OUTPUT_SCHEMA),
        (models.Research, schemas.RESEARCHER_OUTPUT_SCHEMA),
        (models.Analysis, schemas.ANALYST_OUTPUT_SCHEMA),
        (models.Implementation, schemas.IMPLEMENTER_OUTPUT_SCHEMA),
        (models.Review, schemas.REVIEWER_OUTPUT_SCHEMA),
    ],
)
def test_model_matches_legacy_schema(model: type[BaseModel], schema: dict[str, Any]) -> None:
    generated = model.model_json_schema()
    assert shape(generated, generated.get("$defs", {})) == shape(schema, {})
    assert generated["additionalProperties"] is False
