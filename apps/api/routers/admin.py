from datetime import datetime, timezone
import asyncio
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api import schemas
from apps.api.deps import get_db, require_roles
from packages.core.auth import Role, hash_token
from packages.db import Auth
from packages.worker.dht.scan import run_dht_health_scan_all

router = APIRouter(prefix="/admin", tags=["admin"])


class RevokeRequest(BaseModel):
    token: str


class PublisherInviteRequest(BaseModel):
    display_name: str | None = "Publisher"


@router.post("/tokens/revoke")
def revoke_token(
    payload: RevokeRequest,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.ADMIN)),
):
    token_hash = hash_token(payload.token)
    record = session.get(Auth, token_hash)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Token not found"
        )
    record.revoked_at = datetime.now(timezone.utc)
    session.add(record)
    session.commit()
    return {"token_hash": token_hash, "revoked_at": record.revoked_at.isoformat()}


@router.post("/tokens/publisher", response_model=schemas.InviteResponse)
def create_publisher_token(
    payload: PublisherInviteRequest,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.ADMIN)),
):
    raw_token = secrets.token_urlsafe(24)
    token_hash = hash_token(raw_token)
    invite = Auth(
        token_hash=token_hash,
        role=Role.PUBLISHER.value,
        display_name=payload.display_name or "Publisher",
        created_at=datetime.now(timezone.utc),
    )
    session.add(invite)
    session.commit()
    return schemas.InviteResponse(
        token=raw_token,
        token_hash=token_hash,
        role=Role.PUBLISHER,
        scope_team_id=None,
    )


@router.post("/dht/scan-all")
async def scan_all_magnets(
    wait: bool = False,
    timeout_s: int | None = None,
    principal=Depends(require_roles(Role.ADMIN)),
):
    """Trigger a full DHT scan for all magnets (Admin only)."""
    if wait:
        changed = await run_dht_health_scan_all(timeout_s=timeout_s)
        return {"queued": False, "changed": changed}

    # Fire-and-forget so the admin UI stays responsive.
    asyncio.create_task(run_dht_health_scan_all(timeout_s=timeout_s))
    return {"queued": True}
