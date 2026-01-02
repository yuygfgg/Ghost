from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal

from sqlalchemy import func

from packages.db import Resource, ensure_build_state, session_scope

logger = logging.getLogger(__name__)

DhtStatus = Literal["Active", "Stale", "Unknown"]
_SCAN_ALL_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class MagnetProbe:
    status: DhtStatus
    num_peers: int = 0
    has_metadata: bool = False
    error: str | None = None


class MagnetHealthChecker:
    def check(
        self, magnet_uri: str, timeout_s: int
    ) -> MagnetProbe:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        return None


def _default_checker_factory() -> MagnetHealthChecker:
    from packages.worker.dht.libtorrent_checker import LibtorrentMagnetChecker

    return LibtorrentMagnetChecker()


def _pick_resources(limit: int | None) -> list[tuple[int, str, str, str]]:
    with session_scope() as session:
        q = session.query(Resource).filter(Resource.takedown_at.is_(None))
        if limit is None:
            rows = q.order_by(Resource.id.asc()).all()
        else:
            rows = q.order_by(func.random()).limit(limit).all()
        return [(r.id, r.magnet_uri, r.magnet_hash, r.dht_status) for r in rows]


def _apply_results(results: list[tuple[int, DhtStatus]]) -> int:
    now = datetime.now(timezone.utc)
    changed = 0
    with session_scope() as session:
        state = ensure_build_state(session)
        for resource_id, new_status in results:
            resource = session.get(Resource, resource_id)
            if not resource:
                continue
            prev = resource.dht_status
            resource.dht_status = new_status
            resource.last_dht_check = now
            session.add(resource)
            if prev != new_status:
                changed += 1

        if changed:
            state.pending_changes = True
            state.pending_reason = "DHT status updated"
            session.add(state)
        else:
            # Still ensure the singleton exists, but avoid triggering rebuilds for timestamp-only updates.
            session.add(state)
    return changed


def _run_scan_sync(
    *,
    limit: int | None,
    timeout_s: int,
    checker_factory: Callable[[], MagnetHealthChecker],
) -> int:
    resources = _pick_resources(limit)
    if not resources:
        return 0

    try:
        checker = checker_factory()
    except Exception as exc:
        logger.warning("DHT checker unavailable: %s", exc)
        results = [(rid, "Unknown") for rid, _, _, _ in resources]
        _apply_results(results)
        return 0

    results: list[tuple[int, DhtStatus]] = []
    try:
        for resource_id, magnet_uri, _magnet_hash, _prev in resources:
            try:
                probe = checker.check(magnet_uri, timeout_s=timeout_s)
                results.append((resource_id, probe.status))
            except Exception as exc:
                logger.info("DHT check failed (id=%s): %s", resource_id, exc)
                results.append((resource_id, "Unknown"))
    finally:
        try:
            checker.close()
        except Exception:
            pass

    return _apply_results(results)


async def run_dht_health_scan(
    *,
    sample_size: int | None = None,
    timeout_s: int | None = None,
    checker_factory: Callable[[], MagnetHealthChecker] = _default_checker_factory,
) -> int:
    """Background DHT scan job (AsyncIOScheduler-friendly)."""
    sample_size = sample_size or int(os.getenv("GHOST_DHT_SAMPLE_SIZE", "20"))
    timeout_s = timeout_s or int(os.getenv("GHOST_DHT_TIMEOUT_S", "20"))

    changed = await asyncio.to_thread(
        _run_scan_sync,
        limit=sample_size,
        timeout_s=timeout_s,
        checker_factory=checker_factory,
    )
    logger.info("DHT scan completed: %s status change(s)", changed)
    return changed


async def run_dht_health_scan_all(
    *,
    timeout_s: int | None = None,
    checker_factory: Callable[[], MagnetHealthChecker] = _default_checker_factory,
) -> int:
    """Force a full scan over all non-takedown resources."""
    timeout_s = timeout_s or int(os.getenv("GHOST_DHT_TIMEOUT_S", "20"))
    async with _SCAN_ALL_LOCK:
        changed = await asyncio.to_thread(
            _run_scan_sync,
            limit=None,
            timeout_s=timeout_s,
            checker_factory=checker_factory,
        )
    logger.info("DHT full scan completed: %s status change(s)", changed)
    return changed


__all__ = [
    "run_dht_health_scan",
    "run_dht_health_scan_all",
    "MagnetProbe",
    "MagnetHealthChecker",
    "DhtStatus",
]
