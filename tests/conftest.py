import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages import db  # noqa: E402
from packages.db import Base  # noqa: E402
from packages.core.auth import hash_token, Role  # noqa: E402


@pytest.fixture(scope="function")
def db_url() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield f"sqlite:///{tmpdir}/test.db"


@pytest.fixture(scope="function")
def magnet_metadata_dir() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def rebind_engine(db_url: str):
    # Reload engine/session makers with a fresh SQLite URL.
    import importlib

    os.environ["GHOST_DB_PATH"] = db_url
    db_engine_module = importlib.reload(importlib.import_module("packages.db.engine"))
    importlib.reload(importlib.import_module("packages.db"))
    importlib.reload(importlib.import_module("apps.api.deps"))
    api_main = importlib.reload(importlib.import_module("apps.api.main"))

    engine = db_engine_module.engine
    Base.metadata.create_all(engine)
    return api_main.app


@pytest.fixture(scope="function")
def test_client(db_url: str, magnet_metadata_dir: str, monkeypatch):
    monkeypatch.setenv("GHOST_DB_PATH", db_url)
    monkeypatch.setenv("GHOST_MAGNET_METADATA_BACKEND", "mock")
    monkeypatch.setenv("GHOST_MAGNET_METADATA_DIR", magnet_metadata_dir)
    app_instance = rebind_engine(db_url)
    client = TestClient(app_instance)
    yield client


@pytest.fixture(scope="function")
def seeded_tokens(test_client):
    admin_token = "admin-token"
    publisher_token = "publisher-token"
    team_token = "team-token"
    engine = db.engine
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        admin = db.Auth(
            token_hash=hash_token(admin_token),
            role=Role.ADMIN.value,
            display_name="Admin",
        )
        publisher = db.Auth(
            token_hash=hash_token(publisher_token),
            role=Role.PUBLISHER.value,
            display_name="Publisher",
        )
        team = db.Team(name="Team A", owner_token_hash=publisher.token_hash)
        session.add_all([admin, publisher, team])
        session.flush()
        team_member = db.Auth(
            token_hash=hash_token(team_token),
            role=Role.TEAM_MEMBER.value,
            scope_team_id=team.id,
            display_name="Team Member",
        )
        session.add(team_member)
        db.ensure_build_state(session)
        session.commit()
        return {
            "admin": admin_token,
            "publisher": publisher_token,
            "team_member": team_token,
            "team_id": team.id,
        }
    finally:
        session.close()


@pytest.fixture(scope="function")
def db_session(test_client):
    Session = sessionmaker(
        bind=db.engine, autoflush=False, autocommit=False, future=True
    )
    session = Session()
    try:
        yield session
    finally:
        session.close()
