from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Auth(Base):
    __tablename__ = "auth"

    token_hash = Column(String, primary_key=True, index=True)
    role = Column(String, nullable=False)
    scope_team_id = Column(Integer, ForeignKey("team.id"), nullable=True)
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    scope_team = relationship(
        "Team", back_populates="members", foreign_keys=[scope_team_id]
    )


class Team(Base):
    __tablename__ = "team"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    owner_token_hash = Column(String, ForeignKey("auth.token_hash"), nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)

    owner = relationship("Auth", foreign_keys=[owner_token_hash])
    members = relationship(
        "Auth", back_populates="scope_team", foreign_keys=[Auth.scope_team_id]
    )
    resources = relationship(
        "Resource", back_populates="team", cascade="all,delete-orphan"
    )


class Category(Base):
    __tablename__ = "category"

    id = Column(Integer, primary_key=True, autoincrement=True)
    root_id = Column(Integer, nullable=False)
    parent_id = Column(Integer, ForeignKey("category.id"), nullable=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, nullable=False)

    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship(
        "Category", back_populates="parent", cascade="all,delete-orphan"
    )
    resources = relationship("Resource", back_populates="category")


class Resource(Base):
    __tablename__ = "resource"
    __table_args__ = (UniqueConstraint("magnet_hash", name="uq_resource_magnet_hash"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    magnet_uri = Column(Text, nullable=False)
    magnet_hash = Column(String, nullable=False)
    content_markdown = Column(Text, nullable=False, default="")
    cover_image_url = Column(Text, nullable=True)
    cover_image_path = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=False, default="[]")
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False)
    publisher_token_hash = Column(String, ForeignKey("auth.token_hash"), nullable=False)
    team_id = Column(Integer, ForeignKey("team.id"), nullable=True)
    dht_status = Column(String, nullable=False, default="Unknown")
    last_dht_check = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, nullable=False)
    published_at = Column(DateTime, default=now_utc, nullable=False)
    takedown_at = Column(DateTime, nullable=True)

    category = relationship("Category", back_populates="resources")
    publisher = relationship("Auth", foreign_keys=[publisher_token_hash])
    team = relationship("Team", back_populates="resources")


class BuildState(Base):
    __tablename__ = "build_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pending_changes = Column(Boolean, default=False, nullable=False)
    pending_reason = Column(Text, nullable=True)
    last_build_at = Column(DateTime, nullable=True)
    last_build_commit = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)


@event.listens_for(Resource, "before_update", propagate=True)
def update_timestamp(mapper, connection, target: Resource) -> None:  # type: ignore[override]
    target.updated_at = now_utc()


def ensure_build_state(session) -> BuildState:
    """Guarantee there is a singleton build_state row with id=1."""
    state = session.get(BuildState, 1)
    if state:
        return state
    state = BuildState(id=1, pending_changes=False)
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


def create_all(engine) -> None:
    """Create tables and ensure singleton rows."""
    Base.metadata.create_all(engine)
