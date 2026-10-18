"""Block real model requests in every test."""

from pathlib import Path

import pytest
from pydantic_ai import models

from vk.config import Config

from .helpers import sh

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    sh("git", "init", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    sh("git", "clone", str(bare), str(seed))
    (seed / "README.md").write_text("hi\n")
    sh("git", "add", ".", cwd=seed)
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init", cwd=seed)
    sh("git", "push", "origin", "HEAD:main", cwd=seed)
    return bare


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        repo="o/r", github_token="tok", model="m", clan_models={}, state_dir=tmp_path / "state"
    )
