import secrets
from datetime import datetime, timezone

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api import schemas
from apps.api.deps import get_db, get_principal, require_roles
from packages.core.auth import Role, hash_token
from packages.db import Auth, Team

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=List[schemas.TeamResponse])
def list_teams(session: Session = Depends(get_db), principal=Depends(get_principal)):
    query = session.query(Team)
    if principal.role == Role.ADMIN:
        teams = query.order_by(Team.created_at.desc()).all()
    elif principal.role == Role.PUBLISHER:
        teams = (
            query.filter(Team.owner_token_hash == principal.token_hash)
            .order_by(Team.created_at.desc())
            .all()
        )
    else:
        team = (
            session.get(Team, principal.scope_team_id)
            if principal.scope_team_id
            else None
        )
        teams = [team] if team else []
    return [schemas.TeamResponse.model_validate(team) for team in teams]


@router.post(
    "", response_model=schemas.TeamResponse, status_code=status.HTTP_201_CREATED
)
def create_team(
    payload: schemas.TeamCreate,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.PUBLISHER)),
):
    team = Team(name=payload.name, owner_token_hash=principal.token_hash)
    session.add(team)
    session.commit()
    session.refresh(team)
    return schemas.TeamResponse.model_validate(team)


@router.post("/{team_id}/invites", response_model=schemas.InviteResponse)
def create_invite(
    team_id: int,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.PUBLISHER)),
):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )
    if team.owner_token_hash != principal.token_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can invite"
        )
    raw_token = secrets.token_urlsafe(24)
    token_hash = hash_token(raw_token)
    invite = Auth(
        token_hash=token_hash,
        role=Role.TEAM_MEMBER.value,
        scope_team_id=team.id,
        display_name=f"{team.name} member",
        created_at=datetime.now(timezone.utc),
    )
    session.add(invite)
    session.commit()
    return schemas.InviteResponse(
        token=raw_token,
        token_hash=token_hash,
        role=Role.TEAM_MEMBER,
        scope_team_id=team.id,
    )
