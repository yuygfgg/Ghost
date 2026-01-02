from __future__ import annotations

import json
import textwrap
from collections import Counter
from datetime import datetime
from pathlib import Path
from html import escape as html_escape
from urllib.parse import quote

import yaml
from sqlalchemy.orm import Session

from packages.core.public_export import (
    CategoryInfo,
    build_category_paths,
    resource_to_public,
)
from packages.db import Auth, Category, Resource
from packages.worker.site_repo import SiteRepo


def _write_markdown(path: Path, front_matter: dict, body: str) -> None:
    front = yaml.safe_dump(
        front_matter, sort_keys=False, default_flow_style=False
    ).strip()
    content = f"---\n{front}\n---\n\n{body.strip()}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_static_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _clean_generated_taxonomy_pages(repo: SiteRepo) -> None:
    """Remove previously generated /tags/* and /categories/* pages while keeping their index pages."""
    for subdir in [repo.static_dir / "tags", repo.static_dir / "categories"]:
        if not subdir.exists():
            continue
        for child in subdir.iterdir():
            if child.name == "index.html":
                continue
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()


def export_content(session: Session, repo: SiteRepo) -> list[dict]:
    """Export resources into Hugo content markdown files."""
    repo.clean_export_dirs()
    _clean_generated_taxonomy_pages(repo)
    resources = (
        session.query(Resource)
        .filter(Resource.takedown_at.is_(None))
        .order_by(Resource.published_at)
        .all()
    )
    categories = session.query(Category).all()
    auth_records = session.query(Auth).all()

    category_paths = build_category_paths(categories)
    publishers = {a.token_hash: a.display_name for a in auth_records}
    exported: list[dict] = []
    for resource in resources:
        public = resource_to_public(
            resource,
            categories,
            auth_records,
            category_paths=category_paths,
            publishers=publishers,
        )
        front_matter = {
            "title": public["title"],
            "date": _format_dt(public["published_at"]),
            "slug": str(public["id"]),
            "url": f"/resources/{public['id']}/",
            "magnet_uri": public["magnet_uri"],
            "magnet_hash": public["magnet_hash"],
            "dht_status": public.get("dht_status"),
            "last_dht_check": _format_dt(public.get("last_dht_check")),
            "tags": public["tags"],
            "category": public["category_path"],
            "category_name": public["category_name"],
            "cover_image_path": public["cover_image_path"],
            "cover_image_url": public.get("cover_image_url"),
            "publisher": public["publisher_name"],
            "team_id": public["team_id"],
        }
        body = textwrap.dedent(public["content_markdown"] or "")
        _write_markdown(repo.content_dir / f"{public['id']}.md", front_matter, body)
        exported.append(public)

    _write_taxonomy_exports(repo, exported, categories, category_paths)

    # Create homepage placeholder if missing.
    _write_markdown(
        repo.root / "content" / "_index.md",
        {"title": "Ghost Index"},
        "欢迎来到 Ghost 公开站点。本页由构建任务生成。",
    )
    return exported


def _write_taxonomy_exports(
    repo: SiteRepo,
    resources: list[dict],
    categories: list[Category],
    category_paths: dict[int, CategoryInfo],
) -> None:
    """Emit tag counts and category tree for front-end navigation."""
    index_dir = repo.static_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    tags = Counter()
    for res in resources:
        tags.update(res.get("tags") or [])
    tags_payload = {
        "total_resources": len(resources),
        "tags": [
            {"tag": tag, "count": count}
            for tag, count in sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }
    (index_dir / "tags.json").write_text(
        json.dumps(tags_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    categories_payload = {
        "categories": _build_category_tree(categories, resources, category_paths)
    }
    (index_dir / "categories.json").write_text(
        json.dumps(categories_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _write_tag_pages(repo, tags_payload["tags"])
    _write_category_pages(repo, categories_payload["categories"])


def _write_tag_pages(repo: SiteRepo, tags: list[dict]) -> None:
    base = repo.static_dir / "tags"
    for item in tags:
        tag = item["tag"]
        segment = quote(tag, safe="")
        page = (
            (base / "index.html").read_text(encoding="utf-8")
            if (base / "index.html").exists()
            else "<!doctype html><html><head></head><body></body></html>"
        )
        meta = (
            f'<meta name="ghost-initial-tags" content="{html_escape(tag, quote=True)}">'
        )
        page = page.replace("<head>", "<head>\n        " + meta, 1)
        _write_static_file(base / segment / "index.html", page)


def _write_category_pages(repo: SiteRepo, category_tree: list[dict]) -> None:
    base = repo.static_dir / "categories"
    template = (
        (base / "index.html").read_text(encoding="utf-8")
        if (base / "index.html").exists()
        else "<!doctype html><html><head></head><body></body></html>"
    )

    def walk(node: dict):
        path = node.get("path") or ""
        if path:
            meta = f'<meta name="ghost-initial-category" content="{html_escape(path, quote=True)}">'
            page = template.replace("<head>", "<head>\n        " + meta, 1)
            _write_static_file(base / path / "index.html", page)
        for child in node.get("children") or []:
            walk(child)

    for root in category_tree:
        walk(root)


def _format_dt(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat()


def _build_category_tree(
    categories: list[Category],
    resources: list[dict],
    category_paths: dict[int, CategoryInfo],
) -> list[dict]:
    """Construct a nested category tree with aggregated resource counts."""
    category_map = {c.id: c for c in categories}
    counts: dict[int, int] = {c.id: 0 for c in categories}

    for res in resources:
        cid = res.get("category_id")
        while cid:
            cat = category_map.get(cid)
            if not cat:
                break
            counts[cid] = counts.get(cid, 0) + 1
            cid = cat.parent_id

    node_map: dict[int, dict] = {}
    for cat in categories:
        info = category_paths.get(cat.id)
        node_map[cat.id] = {
            "id": cat.id,
            "name": cat.name,
            "slug": cat.slug,
            "path": info.path if info else cat.slug,
            "parent_id": cat.parent_id,
            "root_id": cat.root_id,
            "sort_order": cat.sort_order,
            "count": counts.get(cat.id, 0),
            "children": [],
        }

    roots: list[dict] = []
    ordered = sorted(categories, key=lambda c: (c.root_id, c.sort_order, c.id))
    for cat in ordered:
        node = node_map[cat.id]
        if cat.parent_id and cat.parent_id in node_map:
            node_map[cat.parent_id]["children"].append(node)
        else:
            roots.append(node)

    def _sort_children(node: dict) -> None:
        node["children"].sort(key=lambda n: (n.get("sort_order", 0), n.get("name", "")))
        for child in node["children"]:
            _sort_children(child)

    for root in roots:
        _sort_children(root)

    return roots


__all__ = ["export_content"]
