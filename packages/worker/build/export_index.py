from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from packages.worker.site_repo import SiteRepo


def _summarize(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def export_search_index(resources: Iterable[dict], repo: SiteRepo) -> None:
    """Generate sharded search index JSON files under static/index."""
    index_dir = repo.static_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    shards: dict[str, list[dict]] = defaultdict(list)
    for item in resources:
        published_at: datetime | None = item.get("published_at")
        shard_key = (
            published_at.strftime("%Y-%m")
            if isinstance(published_at, datetime)
            else "unknown"
        )
        shards[shard_key].append(item)

    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "shards": []}
    for shard_key, items in sorted(shards.items()):
        file_name = f"index-{shard_key}.json"
        manifest["shards"].append(
            {"key": shard_key, "file": file_name, "count": len(items)}
        )
        enriched = [_serialize_item(i) for i in items]
        (index_dir / file_name).write_text(
            json.dumps({"items": enriched}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (index_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _serialize_item(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "category_id": item.get("category_id"),
        "category_path": item.get("category_path", ""),
        "title": item.get("title"),
        "url": f"/resources/{item.get('id')}/",
        "magnet_uri": item.get("magnet_uri"),
        "magnet_hash": item.get("magnet_hash"),
        "dht_status": item.get("dht_status"),
        "last_dht_check": _iso(item.get("last_dht_check")),
        "total_size_bytes": item.get("total_size_bytes"),
        "total_size_human": item.get("total_size_human"),
        "file_count": item.get("file_count"),
        "files_tree_summary": item.get("files_tree_summary"),
        "tags": item.get("tags", []),
        "category": item.get("category_path", ""),
        "category_name": item.get("category_name", ""),
        "cover_image_path": item.get("cover_image_path"),
        "cover_image_url": item.get("cover_image_url"),
        "publisher": item.get("publisher_name"),
        "team_id": item.get("team_id"),
        "published_at": _iso(item.get("published_at")),
        "summary": _summarize(item.get("content_markdown", "")),
    }


def _iso(dt) -> str | None:
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return None


__all__ = ["export_search_index"]
