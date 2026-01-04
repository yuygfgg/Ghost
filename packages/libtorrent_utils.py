from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DHT_BOOTSTRAP_NODES = (
    "router.bittorrent.com:6881,router.utorrent.com:6881,dht.transmissionbt.com:6881"
)
DEFAULT_DHT_ROUTERS: tuple[str, ...] = (
    "router.bittorrent.com",
    "router.utorrent.com",
    "dht.transmissionbt.com",
)


def import_libtorrent() -> Any:
    try:
        import libtorrent as lt  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime env
        raise RuntimeError("libtorrent not installed") from exc
    return lt


def create_dht_session(
    lt: Any,
    *,
    bootstrap_nodes_env: str = "GHOST_DHT_BOOTSTRAP_NODES",
    default_bootstrap_nodes: str = DEFAULT_DHT_BOOTSTRAP_NODES,
    dht_routers: Iterable[str] = DEFAULT_DHT_ROUTERS,
    listen_ports: tuple[int, int] = (6881, 6891),
) -> Any:
    session = lt.session()

    try:
        session.listen_on(*listen_ports)
    except Exception:
        # Best-effort: some environments disallow binding these ports.
        session.listen_on(0, 0)

    session.apply_settings(
        {"dht_bootstrap_nodes": os.getenv(bootstrap_nodes_env, default_bootstrap_nodes)}
    )
    for host in dht_routers:
        try:
            session.add_dht_router(host, 6881)
        except Exception:
            pass
    session.start_dht()
    return session


def add_magnet(
    lt: Any,
    session: Any,
    magnet_uri: str,
    *,
    save_path: str | Path,
) -> Any:
    params = {
        "save_path": str(save_path),
        "storage_mode": lt.storage_mode_t.storage_mode_sparse,
    }
    return lt.add_magnet_uri(session, magnet_uri, params)


@dataclass(frozen=True)
class LibtorrentMagnetProbe:
    max_peers: int
    got_metadata: bool


def probe_magnet(
    handle: Any,
    *,
    timeout_s: int,
    poll_interval_s: float = 1.0,
) -> LibtorrentMagnetProbe:
    start = time.monotonic()
    max_peers = 0
    while (time.monotonic() - start) < timeout_s:
        status = handle.status()
        max_peers = max(max_peers, int(getattr(status, "num_peers", 0) or 0))
        if bool(handle.has_metadata()):
            return LibtorrentMagnetProbe(max_peers=max_peers, got_metadata=True)
        time.sleep(poll_interval_s)
    return LibtorrentMagnetProbe(max_peers=max_peers, got_metadata=False)


__all__ = [
    "DEFAULT_DHT_BOOTSTRAP_NODES",
    "DEFAULT_DHT_ROUTERS",
    "LibtorrentMagnetProbe",
    "add_magnet",
    "create_dht_session",
    "import_libtorrent",
    "probe_magnet",
]
