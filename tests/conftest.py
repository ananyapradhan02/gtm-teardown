import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXAMPLES_CSV = ROOT / "examples" / "companies.csv"


@pytest.fixture
def examples_csv() -> Path:
    return EXAMPLES_CSV


@pytest.fixture
def store_path(tmp_path) -> str:
    return str(tmp_path / "snapshots.json")


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Tests never hit the network: make sure the LLM backend has no key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
