from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Auth(Base):
    __tablename__ = "auth"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    scope_team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("team.id"), nullable=True
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    scope_team: Mapped[Team | None] = relationship(
        "Team", back_populates="members", foreign_keys=[scope_team_id]
    )


class Team(Base):
    __tablename__ = "team"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_token_hash: Mapped[str] = mapped_column(
        String, ForeignKey("auth.token_hash"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, nullable=False
    )

    owner: Mapped[Auth] = relationship("Auth", foreign_keys=[owner_token_hash])
    members: Mapped[list[Auth]] = relationship(
        "Auth", back_populates="scope_team", foreign_keys=[Auth.scope_team_id]
    )
    resources: Mapped[list[Resource]] = relationship(
        "Resource", back_populates="team", cascade="all,delete-orphan"
    )


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    root_id: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("category.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, nullable=False
    )

    parent: Mapped[Category | None] = relationship(
        "Category", remote_side=[id], back_populates="children"
    )
    children: Mapped[list[Category]] = relationship(
        "Category", back_populates="parent", cascade="all,delete-orphan"
    )
    resources: Mapped[list[Resource]] = relationship(
        "Resource", back_populates="category"
    )


class Resource(Base):
    __tablename__ = "resource"
    __table_args__ = (UniqueConstraint("magnet_hash", name="uq_resource_magnet_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    magnet_uri: Mapped[str] = mapped_column(Text, nullable=False)
    magnet_hash: Mapped[str] = mapped_column(String, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("category.id"), nullable=False
    )
    publisher_token_hash: Mapped[str] = mapped_column(
        String, ForeignKey("auth.token_hash"), nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("team.id"), nullable=True
    )
    dht_status: Mapped[str] = mapped_column(String, nullable=False, default="Unknown")
    last_dht_check: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, nullable=False
    )
    takedown_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    category: Mapped[Category] = relationship("Category", back_populates="resources")
    publisher: Mapped[Auth] = relationship("Auth", foreign_keys=[publisher_token_hash])
    team: Mapped[Team | None] = relationship("Team", back_populates="resources")


class BuildState(Base):
    __tablename__ = "build_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pending_changes: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    pending_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_build_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_build_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


@event.listens_for(Resource, "before_update", propagate=True)
def update_timestamp(mapper: Any, connection: Any, target: Resource) -> None:
    target.updated_at = now_utc()


def ensure_build_state(session: Session) -> BuildState:
    """Guarantee there is a singleton build_state row with id=1."""
    state = session.get(BuildState, 1)
    if state:
        return state
    state = BuildState(id=1, pending_changes=False)
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


def create_all(engine: Engine) -> None:
    """Create tables and ensure singleton rows."""
    Base.metadata.create_all(engine)
