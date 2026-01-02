import json
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api import schemas
from apps.api.deps import get_db, get_principal, require_roles
from packages.core import magnet
from packages.core.auth import Role, assert_resource_scope
from packages.db import Category, Resource, Team, ensure_build_state

router = APIRouter(prefix="/resources", tags=["resources"])


def _serialize_resource(resource: Resource) -> schemas.ResourceResponse:
    tags = []
    if resource.tags_json:
        try:
            tags = json.loads(resource.tags_json)
        except json.JSONDecodeError:
            tags = []
    return schemas.ResourceResponse(
        id=resource.id,
        title=resource.title,
        magnet_uri=resource.magnet_uri,
        magnet_hash=resource.magnet_hash,
        content_markdown=resource.content_markdown,
        cover_image_url=resource.cover_image_url,
        cover_image_path=resource.cover_image_path,
        tags=tags,
        category_id=resource.category_id,
        publisher_token_hash=resource.publisher_token_hash,
        team_id=resource.team_id,
        dht_status=resource.dht_status,
        last_dht_check=resource.last_dht_check,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
        published_at=resource.published_at,
        takedown_at=resource.takedown_at,
    )


def _mark_pending(session: Session, reason: str) -> None:
    state = ensure_build_state(session)
    state.pending_changes = True
    state.pending_reason = reason
    session.add(state)


@router.get("", response_model=List[schemas.ResourceResponse])
def list_resources(
    session: Session = Depends(get_db), principal=Depends(get_principal)
):
    query = session.query(Resource).filter(Resource.takedown_at.is_(None))
    if principal.role == Role.ADMIN:
        pass
    elif principal.role == Role.PUBLISHER:
        query = query.filter(Resource.publisher_token_hash == principal.token_hash)
    elif principal.role == Role.TEAM_MEMBER:
        query = query.filter(Resource.team_id == principal.scope_team_id)
    records = query.order_by(Resource.created_at.desc()).all()
    return [_serialize_resource(r) for r in records]


@router.get("/{resource_id}", response_model=schemas.ResourceResponse)
def get_resource(
    resource_id: int,
    session: Session = Depends(get_db),
    principal=Depends(get_principal),
):
    resource = session.get(Resource, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )
    try:
        assert_resource_scope(
            principal, resource.team_id, resource.publisher_token_hash
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return _serialize_resource(resource)


@router.post(
    "", response_model=schemas.ResourceResponse, status_code=status.HTTP_201_CREATED
)
def create_resource(
    payload: schemas.ResourceCreate,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.PUBLISHER, Role.TEAM_MEMBER, Role.ADMIN)),
):
    category = session.get(Category, payload.category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found"
        )

    try:
        info_hash = magnet.extract_info_hash(payload.magnet_uri)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    team_id = payload.team_id
    if principal.role == Role.TEAM_MEMBER:
        if team_id and team_id != principal.scope_team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Team mismatch"
            )
        team_id = principal.scope_team_id
    elif principal.role == Role.PUBLISHER and team_id is not None:
        team = session.get(Team, team_id)
        if not team or team.owner_token_hash != principal.token_hash:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Team mismatch"
            )
    elif principal.role == Role.ADMIN and team_id is not None:
        team = session.get(Team, team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Team not found"
            )

    tags_json = json.dumps(payload.tags or [])
    resource = Resource(
        title=payload.title,
        magnet_uri=payload.magnet_uri,
        magnet_hash=info_hash,
        content_markdown=payload.content_markdown,
        cover_image_url=payload.cover_image_url,
        tags_json=tags_json,
        category_id=payload.category_id,
        publisher_token_hash=principal.token_hash,
        team_id=team_id,
        published_at=payload.published_at or datetime.now(timezone.utc),
    )
    session.add(resource)
    _mark_pending(session, "New resource added")
    session.commit()
    session.refresh(resource)
    return _serialize_resource(resource)


@router.put("/{resource_id}", response_model=schemas.ResourceResponse)
def update_resource(
    resource_id: int,
    payload: schemas.ResourceUpdate,
    session: Session = Depends(get_db),
    principal=Depends(get_principal),
):
    resource = session.get(Resource, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )
    try:
        assert_resource_scope(
            principal, resource.team_id, resource.publisher_token_hash
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if payload.title is not None:
        resource.title = payload.title
    if payload.magnet_uri is not None:
        try:
            resource.magnet_hash = magnet.extract_info_hash(payload.magnet_uri)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        resource.magnet_uri = payload.magnet_uri
    if payload.content_markdown is not None:
        resource.content_markdown = payload.content_markdown
    if payload.cover_image_url is not None:
        resource.cover_image_url = payload.cover_image_url
    if payload.tags is not None:
        resource.tags_json = json.dumps(payload.tags)
    if payload.category_id is not None:
        category = session.get(Category, payload.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found"
            )
        resource.category_id = payload.category_id
    if payload.team_id is not None:
        if (
            principal.role == Role.TEAM_MEMBER
            and payload.team_id != principal.scope_team_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Team mismatch"
            )
        if principal.role == Role.PUBLISHER:
            team = (
                session.get(Team, payload.team_id)
                if payload.team_id is not None
                else None
            )
            if payload.team_id is not None and (
                not team or team.owner_token_hash != principal.token_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Team mismatch"
                )
        if principal.role == Role.ADMIN and payload.team_id is not None:
            team = session.get(Team, payload.team_id)
            if not team:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Team not found"
                )
        resource.team_id = payload.team_id

    _mark_pending(session, "Resource updated")
    session.commit()
    session.refresh(resource)
    return _serialize_resource(resource)


@router.post("/{resource_id}/takedown", response_model=schemas.ResourceResponse)
def takedown_resource(
    resource_id: int,
    session: Session = Depends(get_db),
    principal=Depends(require_roles(Role.ADMIN)),
):
    resource = session.get(Resource, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )
    resource.takedown_at = datetime.now(timezone.utc)
    _mark_pending(session, "Resource takedown")
    session.commit()
    session.refresh(resource)
    return _serialize_resource(resource)
