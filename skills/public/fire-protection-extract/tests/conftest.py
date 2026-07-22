import pytest
from ._fixtures import build_tiny_spec


@pytest.fixture
def tiny_spec(tmp_path):
    return build_tiny_spec(tmp_path / "tiny.docx")
