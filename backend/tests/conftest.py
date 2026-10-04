"""Fixtures shared across the whole backend test suite."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
ML_SRC = REPO_ROOT / "ml" / "src"
for path in (str(BACKEND_DIR), str(ML_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

# NullPool under test: pooled connections belong to the loop that opened them.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("MODEL_LOAD_ON_STARTUP", "false")
os.environ.setdefault("ENABLE_API_KEY_AUTH", "false")

from app.core.database import Base, async_session_factory, engine  # noqa: E402
from app.ml.registry import model_registry  # noqa: E402
from tests.factories import make_active_model  # noqa: E402

ARTIFACT_ROOT = REPO_ROOT / "ml" / "artifacts"
DATA_DIR = REPO_ROOT / "data" / "processed"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires a live PostgreSQL database")


@pytest.fixture(scope="session")
def artifact_root() -> Path:
    if not ARTIFACT_ROOT.exists() or not any(ARTIFACT_ROOT.iterdir()):
        pytest.skip("no model artifacts; run scripts/run_training.py first")
    return ARTIFACT_ROOT


@pytest.fixture(scope="session")
def trained_artifact(artifact_root: Path) -> Path:
    versions = sorted(p for p in artifact_root.iterdir() if (p / "metadata.json").exists())
    if not versions:
        pytest.skip("no trained model version available")
    return versions[-1]


@pytest.fixture(scope="session")
def demo_observations() -> Path:
    path = DATA_DIR / "observations.csv"
    if not path.exists():
        pytest.skip("no demo dataset; run scripts/generate_demo_dataset.py first")
    return path


@pytest.fixture(scope="session")
def demo_districts() -> Path:
    path = DATA_DIR / "districts.csv"
    if not path.exists():
        pytest.skip("no demo district file; run scripts/generate_demo_dataset.py first")
    return path


@pytest_asyncio.fixture
async def session():
    async with async_session_factory() as db_session:
        yield db_session
        await db_session.rollback()


@pytest_asyncio.fixture
async def shared_model(session, trained_artifact: Path):
    """One active model version per test, reused by every row that test seeds.

    Tables are truncated between tests, so the record must be created per test
    rather than cached for the session.
    """
    record = await make_active_model(session, trained_artifact)
    await session.commit()
    return record


@pytest_asyncio.fixture
async def client():
    """HTTP client bound to the app with the real database session factory."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture(autouse=True)
def _reset_model_registry():
    """Leave the in-process model cache as it was found.

    The registry is module-level state; a test that loads a model must not leak
    it into an unrelated test that expects "no model loaded".
    """
    previous = model_registry.active_version
    yield
    model_registry.set_active(previous)


_SCHEMA_READY = False


@pytest_asyncio.fixture(autouse=True)
async def _database():
    """Create the schema once and truncate every table after each test.

    The readiness flag is cached rather than the fixture being session-scoped
    because pytest-asyncio gives each test a fresh event loop, and a
    session-scoped async fixture cannot hold a connection across loops.
    """
    global _SCHEMA_READY
    if not _SCHEMA_READY:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        _SCHEMA_READY = True

    yield

    async with engine.begin() as connection:
        tables = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
        if tables:
            await connection.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
