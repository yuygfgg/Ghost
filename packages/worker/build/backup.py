from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupResult:
    skipped: bool
    output_path: str | None
    reason: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    skipped: bool
    output_path: str | None
    reason: str | None = None


def _resolve_sqlite_path(db_path_or_url: str) -> Path | None:
    if "://" not in db_path_or_url:
        return Path(db_path_or_url)
    parsed = urlparse(db_path_or_url)
    if parsed.scheme != "sqlite":
        return None
    if parsed.path in {"", ":memory:"}:
        return None
    # sqlite:////abs/path or sqlite:///rel/path
    return Path(parsed.path)


def create_age_encrypted_db_backup(
    *,
    db_path_or_url: str | None = None,
    recipient: str | None = None,
    backup_dir: str | Path | None = None,
) -> BackupResult:
    """Best-effort encrypted backup of the SQLite DB using the `age` CLI.

    This is intentionally non-fatal: build should continue even if backup is unavailable.
    """
    recipient = recipient or os.getenv("GHOST_AGE_RECIPIENT") or None
    if not recipient:
        return BackupResult(
            skipped=True, output_path=None, reason="GHOST_AGE_RECIPIENT not set"
        )

    age_bin = os.getenv("GHOST_AGE_BIN", "age")
    if not shutil.which(age_bin):
        return BackupResult(
            skipped=True, output_path=None, reason=f"`{age_bin}` not found in PATH"
        )

    db_path_or_url = db_path_or_url or os.getenv("GHOST_DB_PATH") or "var/db/ghost.db"
    db_path = _resolve_sqlite_path(db_path_or_url)
    if not db_path or not db_path.exists():
        return BackupResult(
            skipped=True, output_path=None, reason="SQLite DB file not found"
        )

    backup_dir_value = backup_dir or os.getenv("GHOST_BACKUP_DIR") or "var/backups"
    backup_dir_path = Path(backup_dir_value)
    backup_dir_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    out = backup_dir_path / f"ghost-db-{ts}.db.age"

    try:
        subprocess.run(
            [age_bin, "-r", recipient, "-o", str(out), str(db_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "age backup failed: %s", (exc.stderr or exc.stdout or str(exc)).strip()
        )
        return BackupResult(skipped=True, output_path=None, reason="age command failed")

    logger.info("Created encrypted DB backup: %s", out)
    return BackupResult(skipped=False, output_path=str(out), reason=None)


def restore_age_encrypted_db_backup(
    *,
    input_path: str | Path,
    output_path: str | Path,
    identity_file: str | Path | None = None,
) -> RestoreResult:
    """Decrypt an `.age` backup into a target path using the `age` CLI."""
    age_bin = os.getenv("GHOST_AGE_BIN", "age")
    if not shutil.which(age_bin):
        return RestoreResult(
            skipped=True, output_path=None, reason=f"`{age_bin}` not found in PATH"
        )
    identity_file = identity_file or os.getenv("GHOST_AGE_IDENTITY_FILE") or None
    if not identity_file:
        return RestoreResult(
            skipped=True, output_path=None, reason="No identity file configured"
        )

    in_path = Path(input_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [
                age_bin,
                "-d",
                "-i",
                str(identity_file),
                "-o",
                str(out_path),
                str(in_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "age restore failed: %s", (exc.stderr or exc.stdout or str(exc)).strip()
        )
        return RestoreResult(
            skipped=True, output_path=None, reason="age command failed"
        )

    return RestoreResult(skipped=False, output_path=str(out_path), reason=None)


__all__ = [
    "create_age_encrypted_db_backup",
    "restore_age_encrypted_db_backup",
    "BackupResult",
    "RestoreResult",
]
