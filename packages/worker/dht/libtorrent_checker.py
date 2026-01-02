from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from packages.worker.dht.scan import MagnetHealthChecker, MagnetProbe


@dataclass(frozen=True)
class _ProbeAccum:
    max_peers: int = 0
    got_metadata: bool = False


class LibtorrentMagnetChecker(MagnetHealthChecker):
    def __init__(self) -> None:
        try:
            import libtorrent as lt  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on runtime env
            raise RuntimeError("libtorrent not installed") from exc

        self._lt = lt
        self._session = lt.session()

        try:
            self._session.listen_on(6881, 6891)
        except Exception:
            # Best-effort: some environments disallow binding these ports.
            self._session.listen_on(0, 0)

        settings = {
            "dht_bootstrap_nodes": os.getenv(
                "GHOST_DHT_BOOTSTRAP_NODES",
                "router.bittorrent.com:6881,router.utorrent.com:6881,dht.transmissionbt.com:6881",
            )
        }
        self._session.apply_settings(settings)
        for host in [
            "router.bittorrent.com",
            "router.utorrent.com",
            "dht.transmissionbt.com",
        ]:
            try:
                self._session.add_dht_router(host, 6881)
            except Exception:
                pass
        self._session.start_dht()

        self._save_path = Path(os.getenv("GHOST_DHT_TMP_DIR", "var/dht-tmp"))
        self._save_path.mkdir(parents=True, exist_ok=True)

    def check(self, magnet_uri: str, timeout_s: int) -> MagnetProbe:
        lt = self._lt

        params = {
            "save_path": str(self._save_path),
            "storage_mode": lt.storage_mode_t.storage_mode_sparse,
        }
        handle = lt.add_magnet_uri(self._session, magnet_uri, params)
        start = time.monotonic()
        acc = _ProbeAccum()
        try:
            while (time.monotonic() - start) < timeout_s:
                status = handle.status()
                max_peers = max(
                    acc.max_peers, int(getattr(status, "num_peers", 0) or 0)
                )
                got_metadata = acc.got_metadata or bool(handle.has_metadata())
                acc = _ProbeAccum(max_peers=max_peers, got_metadata=got_metadata)
                if got_metadata:
                    break
                time.sleep(1)
        finally:
            try:
                self._session.remove_torrent(handle)
            except Exception:
                pass

        if acc.got_metadata or acc.max_peers > 0:
            return MagnetProbe(
                status="Active", num_peers=acc.max_peers, has_metadata=acc.got_metadata
            )
        return MagnetProbe(status="Stale", num_peers=0, has_metadata=False)

    def close(self) -> None:
        try:
            self._session.pause()
        except Exception:
            pass


__all__ = ["LibtorrentMagnetChecker"]
