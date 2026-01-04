from __future__ import annotations

import os
from pathlib import Path

from packages.worker.dht.scan import MagnetHealthChecker, MagnetProbe
from packages.libtorrent_utils import (
    add_magnet,
    create_dht_session,
    import_libtorrent,
    probe_magnet,
)


class LibtorrentMagnetChecker(MagnetHealthChecker):
    def __init__(self) -> None:
        lt = import_libtorrent()
        self._lt = lt
        self._session = create_dht_session(lt)

        self._save_path = Path(os.getenv("GHOST_DHT_TMP_DIR", "var/dht-tmp"))
        self._save_path.mkdir(parents=True, exist_ok=True)

    def check(self, magnet_uri: str, timeout_s: int) -> MagnetProbe:
        lt = self._lt
        handle = add_magnet(lt, self._session, magnet_uri, save_path=self._save_path)
        try:
            probe = probe_magnet(handle, timeout_s=timeout_s, poll_interval_s=1.0)
        finally:
            try:
                self._session.remove_torrent(handle)
            except Exception:
                pass

        if probe.got_metadata or probe.max_peers > 0:
            return MagnetProbe(
                status="Active",
                num_peers=probe.max_peers,
                has_metadata=probe.got_metadata,
            )
        return MagnetProbe(status="Stale", num_peers=0, has_metadata=False)

    def close(self) -> None:
        try:
            self._session.pause()
        except Exception:
            pass


__all__ = ["LibtorrentMagnetChecker"]
