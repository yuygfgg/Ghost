import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from packages.db import models

try:
    from argon2.low_level import Type, hash_secret  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    hash_secret = None  # type: ignore
    Type = None  # type: ignore


class Role(str, Enum):
    ADMIN = "Admin"
    PUBLISHER = "Publisher"
    TEAM_MEMBER = "TeamMember"


@dataclass
class Principal:
    token_hash: str
    role: Role
    display_name: str
    scope_team_id: Optional[int] = None


def hash_token(token: str) -> str:
    """Derive a deterministic hash for token storage/lookup."""
    pepper = os.getenv("GHOST_TOKEN_PEPPER", "")
    salt = os.getenv("GHOST_TOKEN_SALT", "ghost-static-salt").encode()
    if hash_secret and Type:
        derived = hash_secret(
            secret=(token + pepper).encode(),
            salt=salt,
            time_cost=2,
            memory_cost=2**16,
            parallelism=2,
            hash_len=32,
            type=Type.ID,
        )
        return hashlib.sha256(derived).hexdigest()

    return hashlib.sha256((token + pepper).encode()).hexdigest()


def verify_token(session: Session, token: str) -> Optional[Principal]:
    """Return Principal if token is valid and not revoked."""
    token_hash = hash_token(token)
    record = session.get(models.Auth, token_hash)
    if not record or record.revoked_at is not None:
        return None
    return Principal(
        token_hash=record.token_hash,
        role=Role(record.role),
        display_name=record.display_name,
        scope_team_id=record.scope_team_id,
    )


def require_role(principal: Principal, allowed: list[Role]) -> None:
    if principal.role not in allowed:
        raise PermissionError("Insufficient role")


def assert_resource_scope(
    principal: Principal, team_id: Optional[int], publisher_hash: str
) -> None:
    """Ensure a principal can operate on a resource."""
    if principal.role == Role.ADMIN:
        return
    if principal.role == Role.PUBLISHER and principal.token_hash == publisher_hash:
        return
    if principal.role == Role.TEAM_MEMBER and principal.scope_team_id == team_id:
        return
    raise PermissionError("Forbidden")
