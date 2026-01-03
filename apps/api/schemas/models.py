from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from packages.core.auth import Role


class PrincipalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: Role
    display_name: str
    scope_team_id: Optional[int] = None


class VerifyResponse(PrincipalResponse):
    token_hash: str


class BuildStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pending_changes: bool
    pending_reason: Optional[str] = None
    last_build_at: Optional[datetime] = None
    last_build_commit: Optional[str] = None
    last_error: Optional[str] = None


class ResourceBase(BaseModel):
    title: str
    magnet_uri: str
    content_markdown: str = ""
    cover_image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    category_id: int
    team_id: Optional[int] = None


class ResourceCreate(ResourceBase):
    published_at: Optional[datetime] = None


class ResourceUpdate(BaseModel):
    title: Optional[str] = None
    magnet_uri: Optional[str] = None
    content_markdown: Optional[str] = None
    cover_image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    category_id: Optional[int] = None
    team_id: Optional[int] = None


class FileTreeNode(BaseModel):
    name: str
    type: Literal["dir", "file"]
    size_bytes: int = 0
    file_count: Optional[int] = None
    children: Optional[List[FileTreeNode]] = None


class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    magnet_uri: str
    magnet_hash: str
    content_markdown: str
    cover_image_url: Optional[str]
    cover_image_path: Optional[str]
    tags: List[str]
    category_id: int
    publisher_token_hash: str
    team_id: Optional[int]
    dht_status: str
    last_dht_check: Optional[datetime]
    total_size_bytes: Optional[int] = None
    total_size_human: Optional[str] = None
    file_count: Optional[int] = None
    files_tree_summary: Optional[str] = None
    files_tree: Optional[List[FileTreeNode]] = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime
    takedown_at: Optional[datetime]


class ResourceMetadataResponse(BaseModel):
    magnet_hash: str
    total_size_bytes: int
    total_size_human: Optional[str] = None
    file_count: int
    files_tree_summary: str = ""
    files_tree: List[FileTreeNode] = Field(default_factory=list)
    num_peers: int = 0
    fetched_at: Optional[str] = None
    backend: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str
    slug: str
    parent_id: Optional[int] = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    sort_order: Optional[int] = None
    parent_id: Optional[int] = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    root_id: int
    parent_id: Optional[int]
    name: str
    slug: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TeamCreate(BaseModel):
    name: str


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_token_hash: str
    created_at: datetime


class InviteResponse(BaseModel):
    token: str
    token_hash: str
    role: Role
    scope_team_id: Optional[int]
