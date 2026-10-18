"""Block real model requests in every test."""

from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False
