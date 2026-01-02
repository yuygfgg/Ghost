from __future__ import annotations

import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from packages.db import Resource
from packages.worker.site_repo import SiteRepo

logger = logging.getLogger(__name__)

_SAFE_EXT = re.compile(r"^[a-z0-9]{1,5}$", re.IGNORECASE)


@dataclass(frozen=True)
class DownloadedFile:
    content: bytes
    content_type: str | None


def _default_fetch(url: str, timeout_s: int) -> DownloadedFile:
    req = urllib.request.Request(url, headers={"User-Agent": "Ghost/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        content_type = resp.headers.get("Content-Type")
        return DownloadedFile(content=resp.read(), content_type=content_type)


def _ext_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return "bin"
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
        "image/avif": "avif",
    }
    return mapping.get(ct, "bin")


def _maybe_convert_to_webp(raw: bytes) -> bytes | None:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    try:
        from io import BytesIO

        img = Image.open(BytesIO(raw))
        out = BytesIO()
        img.save(out, format="WEBP", quality=82, method=6)
        return out.getvalue()
    except Exception:
        return None


def localize_cover_images(
    session: Session,
    repo: SiteRepo,
    *,
    fetch: Callable[[str, int], DownloadedFile] = _default_fetch,
    timeout_s: int | None = None,
) -> int:
    """Download remote cover_image_url into the Hugo repo and set cover_image_path.

    This is best-effort: failures are logged and skipped to keep builds resilient.
    """
    timeout_s = timeout_s or int(os.getenv("GHOST_COVER_FETCH_TIMEOUT_S", "15"))
    covers_dir = repo.static_dir / "assets" / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)

    updated = 0
    q = session.query(Resource).filter(
        Resource.takedown_at.is_(None), Resource.cover_image_url.isnot(None)
    )
    for resource in q:
        url = (resource.cover_image_url or "").strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue

        if resource.cover_image_path:
            # If already localized, nothing to do.
            continue

        try:
            downloaded = fetch(url, timeout_s)
        except Exception as exc:
            logger.info("Cover download failed (id=%s): %s", resource.id, exc)
            continue

        webp = _maybe_convert_to_webp(downloaded.content)
        if webp is not None:
            out_name = f"{resource.id}.webp"
            out_bytes = webp
        else:
            ext = _ext_from_content_type(downloaded.content_type)
            ext = ext if _SAFE_EXT.match(ext) else "bin"
            out_name = f"{resource.id}.{ext}"
            out_bytes = downloaded.content

        out_path = covers_dir / out_name
        out_path.write_bytes(out_bytes)
        resource.cover_image_path = f"assets/covers/{out_name}"
        session.add(resource)
        updated += 1

    if updated:
        session.flush()
    return updated


__all__ = ["localize_cover_images", "DownloadedFile"]
