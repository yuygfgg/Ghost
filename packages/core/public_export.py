from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from packages.db import Auth, Category, Resource


@dataclass
class CategoryInfo:
    id: int
    slug: str
    path: str
    name: str


def _build_category_paths(categories: Iterable[Category]) -> dict[int, CategoryInfo]:
    """Return mapping of category id -> slug path string (e.g., root/child)."""
    category_map: Dict[int, Category] = {c.id: c for c in categories}
    cache: Dict[int, CategoryInfo] = {}

    def build_path(cat: Category) -> CategoryInfo:
        if cat.id in cache:
            return cache[cat.id]
        parts = [cat.slug]
        parent = category_map.get(cat.parent_id) if cat.parent_id else None
        while parent:
            parts.append(parent.slug)
            parent = category_map.get(parent.parent_id) if parent.parent_id else None
        path = "/".join(reversed(parts))
        info = CategoryInfo(id=cat.id, slug=cat.slug, path=path, name=cat.name)
        cache[cat.id] = info
        return info

    for category in categories:
        build_path(category)
    return cache


def build_category_paths(categories: Iterable[Category]) -> dict[int, CategoryInfo]:
    """Public wrapper to compute category path mapping."""
    return _build_category_paths(categories)


def parse_tags(resource: Resource) -> list[str]:
    """Safely parse tags_json to a list."""
    if not resource.tags_json:
        return []
    try:
        tags = json.loads(resource.tags_json)
        return tags if isinstance(tags, list) else []
    except json.JSONDecodeError:
        return []


def resource_to_public(
    resource: Resource,
    categories: Iterable[Category],
    auth_records: Iterable[Auth],
    category_paths: Optional[dict[int, CategoryInfo]] = None,
    publishers: Optional[dict[str, str]] = None,
) -> dict:
    """Serialize a Resource into a public-safe dict used for exports."""
    category_paths = category_paths or _build_category_paths(categories)
    category_info = category_paths.get(resource.category_id)
    publishers = publishers or {a.token_hash: a.display_name for a in auth_records}
    tags = parse_tags(resource)

    # NOTE: public exports must not leak sensitive/private upstream URLs.
    # cover_image_url stays in the private DB but is intentionally omitted from public output.
    return {
        "id": resource.id,
        "title": resource.title,
        "category_id": resource.category_id,
        "magnet_uri": resource.magnet_uri,
        "magnet_hash": resource.magnet_hash,
        "content_markdown": resource.content_markdown or "",
        "tags": tags,
        "category_path": category_info.path if category_info else "",
        "category_name": category_info.name if category_info else "",
        "cover_image_path": resource.cover_image_path,
        "cover_image_url": None,
        "publisher_name": publishers.get(resource.publisher_token_hash, "Anonymous"),
        "team_id": resource.team_id,
        "dht_status": resource.dht_status,
        "last_dht_check": resource.last_dht_check,
        "published_at": resource.published_at,
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
    }


__all__ = ["resource_to_public", "parse_tags", "CategoryInfo", "build_category_paths"]
