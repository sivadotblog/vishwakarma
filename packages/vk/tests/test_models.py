"""Every model the agents return rejects fields it does not declare."""

import pytest
from pydantic import BaseModel

from vk import models


@pytest.mark.parametrize(
    "model",
    [
        models.Classification,
        models.Research,
        models.Analysis,
        models.Implementation,
        models.Review,
        models.Triage,
        models.CommentDecision,
        models.PrBody,
        models.CiDiagnosis,
    ],
)
def test_models_forbid_extra_fields(model: type[BaseModel]) -> None:
    assert model.model_json_schema()["additionalProperties"] is False
