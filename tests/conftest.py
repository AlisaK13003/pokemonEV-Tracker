from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def tmp_path(request) -> Path:
    scratch_root = Path.cwd() / ".test-scratch"
    scratch_root.mkdir(exist_ok=True)
    test_directory = scratch_root / f"{request.node.name}-{uuid4().hex}"
    test_directory.mkdir()
    yield test_directory
    shutil.rmtree(test_directory)
