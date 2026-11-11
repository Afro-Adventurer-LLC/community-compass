from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.store import MemoryStore, reset_store  # noqa: E402
from app.services.retrieval import LocalRetriever, reset_retriever  # noqa: E402
from app.services.index import LocalIndex  # noqa: E402


@pytest.fixture
def store():
    reset_store()
    return MemoryStore()


@pytest.fixture(scope="session")
def index():
    return LocalIndex(ROOT / "kb")


@pytest.fixture
def retriever(index):
    reset_retriever()
    return LocalRetriever(index)


@pytest.fixture
def client(retriever, store, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import store as storemod
    from app.services import retrieval as retmod
    from app.routes import api as apimod

    monkeypatch.setattr(storemod, "_store", store)
    monkeypatch.setattr(retmod, "_retriever", retriever)
    monkeypatch.setattr(apimod, "get_store", lambda: store)
    monkeypatch.setattr(apimod, "get_retriever", lambda: retriever)
    return TestClient(app)
