import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# SQLite file lives under var/db by default to match docs.
DEFAULT_DB_PATH = "var/db/ghost.db"


def _ensure_db_dir(db_path: str) -> None:
    """Create parent directory for SQLite if needed."""
    path = Path(db_path)
    if path.suffix == "":
        return
    path.parent.mkdir(parents=True, exist_ok=True)


def get_database_url() -> str:
    """Return SQLAlchemy database URL based on env config."""
    db_path = os.getenv("GHOST_DB_PATH", DEFAULT_DB_PATH)
    if "://" in db_path:
        return db_path
    _ensure_db_dir(db_path)
    return f"sqlite:///{db_path}"


engine = create_engine(get_database_url(), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
