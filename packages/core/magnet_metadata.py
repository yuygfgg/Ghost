from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from packages.core.magnet import extract_info_hash
from packages.libtorrent_utils import (
    add_magnet,
    create_dht_session,
    import_libtorrent,
    probe_magnet,
)


class MagnetMetadataError(RuntimeError):
    pass


class MagnetInactiveError(MagnetMetadataError):
    pass


class MagnetMetadataUnavailableError(MagnetMetadataError):
    pass


@dataclass(frozen=True)
class MagnetFile:
    path: str
    size_bytes: int


@dataclass(frozen=True)
class MagnetMetadata:
    magnet_hash: str
    total_size_bytes: int
    files: list[MagnetFile]
    num_peers: int = 0


class MagnetMetadataFetcher:
    def fetch(
        self, magnet_uri: str, timeout_s: int
    ) -> MagnetMetadata:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        return None


class MockMagnetMetadataFetcher(MagnetMetadataFetcher):
    """Deterministic backend for tests/dev without libtorrent.

    Rules:
    - info_hash starting with "stale" => inactive
    - otherwise => active with 2 fake files
    """

    def fetch(self, magnet_uri: str, timeout_s: int) -> MagnetMetadata:
        info_hash = extract_info_hash(magnet_uri)
        if info_hash.startswith("stale"):
            raise MagnetInactiveError("Magnet is not active")
        files = [
            MagnetFile(path=f"{info_hash}/README.txt", size_bytes=123),
            MagnetFile(path=f"{info_hash}/payload.bin", size_bytes=456),
        ]
        return MagnetMetadata(
            magnet_hash=info_hash,
            total_size_bytes=sum(f.size_bytes for f in files),
            files=files,
            num_peers=1,
        )


class LibtorrentMagnetMetadataFetcher(MagnetMetadataFetcher):
    def __init__(self) -> None:
        lt = import_libtorrent()
        self._lt = lt
        self._session = create_dht_session(lt)

        tmp_dir = os.getenv("GHOST_MAGNET_TMP_DIR", "var/magnet-tmp")
        self._save_path = Path(tmp_dir)
        self._save_path.mkdir(parents=True, exist_ok=True)

    def fetch(self, magnet_uri: str, timeout_s: int) -> MagnetMetadata:
        lt = self._lt
        info_hash = extract_info_hash(magnet_uri)

        workdir = tempfile.mkdtemp(prefix="magnet-", dir=str(self._save_path))
        try:
            handle = add_magnet(lt, self._session, magnet_uri, save_path=workdir)
        except Exception:
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass
            raise
        try:
            probe = probe_magnet(handle, timeout_s=timeout_s, poll_interval_s=1.0)
            if probe.got_metadata:
                ti = handle.get_torrent_info()
                fs = ti.files()
                files: list[MagnetFile] = []
                total = 0
                for i in range(fs.num_files()):
                    path = fs.file_path(i)
                    size = int(fs.file_size(i))
                    total += size
                    files.append(MagnetFile(path=path, size_bytes=size))
                return MagnetMetadata(
                    magnet_hash=info_hash,
                    total_size_bytes=total,
                    files=files,
                    num_peers=probe.max_peers,
                )
        finally:
            try:
                self._session.remove_torrent(handle)
            except Exception:
                pass
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass

        if probe.max_peers > 0:
            raise MagnetMetadataUnavailableError(
                "Magnet is active but metadata not available yet"
            )
        raise MagnetInactiveError("Magnet is not active")

    def close(self) -> None:
        try:
            self._session.pause()
        except Exception:
            pass


def format_bytes(num: int) -> str:
    num = int(num or 0)
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num} B"


def build_file_tree(files: list[MagnetFile]) -> list[dict]:
    root: dict[str, dict] = {}

    def ensure_dir(parent: dict[str, dict], name: str) -> dict:
        node = parent.get(name)
        if node is None:
            node = {"name": name, "type": "dir", "children": {}}
            parent[name] = node
        return node

    for f in files:
        parts = [p for p in f.path.replace("\\", "/").split("/") if p]
        if not parts:
            continue
        parent = root
        for seg in parts[:-1]:
            dir_node = ensure_dir(parent, seg)
            parent = dir_node["children"]
        parent[parts[-1]] = {
            "name": parts[-1],
            "type": "file",
            "size_bytes": int(f.size_bytes),
        }

    def finalize(node_map: dict[str, dict]) -> list[dict]:
        nodes: list[dict] = []
        for name, node in node_map.items():
            if node.get("type") == "dir":
                children = finalize(node.get("children") or {})
                size_bytes = 0
                file_count = 0
                for child in children:
                    size_bytes += int(child.get("size_bytes") or 0)
                    if child["type"] == "file":
                        file_count += 1
                    else:
                        file_count += int(child.get("file_count") or 0)
                nodes.append(
                    {
                        "name": name,
                        "type": "dir",
                        "size_bytes": size_bytes,
                        "size_human": format_bytes(size_bytes),
                        "file_count": file_count,
                        "children": children,
                    }
                )
            else:
                size_bytes = int(node.get("size_bytes") or 0)
                nodes.append(
                    {
                        "name": name,
                        "type": "file",
                        "size_bytes": size_bytes,
                        "size_human": format_bytes(size_bytes),
                    }
                )

        nodes.sort(
            key=lambda n: (
                0 if n["type"] == "dir" else 1,
                str(n.get("name") or "").lower(),
            )
        )
        return nodes

    return finalize(root)


def file_tree_summary(file_tree: list[dict], max_entries: int = 4) -> str:
    names = []
    for node in file_tree or []:
        if not node.get("name"):
            continue
        names.append(str(node["name"]))
        if len(names) >= max_entries:
            break
    if not names:
        return ""
    more = max(0, len(file_tree) - len(names))
    suffix = f" +{more}" if more else ""
    return ", ".join(names) + suffix


class MagnetMetadataStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        env_dir = os.getenv("GHOST_MAGNET_METADATA_DIR")
        base = base_dir or env_dir or "var/magnet-metadata"
        self._base = Path(base)

    def path_for(self, magnet_hash: str) -> Path:
        return self._base / f"{magnet_hash}.json"

    def save(self, magnet_hash: str, payload: dict) -> None:
        self._base.mkdir(parents=True, exist_ok=True)
        tmp = self.path_for(magnet_hash).with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path_for(magnet_hash))

    def load(self, magnet_hash: str) -> dict | None:
        path = self.path_for(magnet_hash)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None


def get_metadata_fetcher() -> MagnetMetadataFetcher:
    backend = os.getenv("GHOST_MAGNET_METADATA_BACKEND", "libtorrent").lower()
    if backend in {"mock", "fake", "test"}:
        return MockMagnetMetadataFetcher()
    if backend == "libtorrent":
        return LibtorrentMagnetMetadataFetcher()
    raise ValueError(f"Unknown magnet metadata backend: {backend}")


def probe_and_store_magnet_metadata(
    magnet_uri: str,
    *,
    timeout_s: int | None = None,
    store: MagnetMetadataStore | None = None,
) -> dict:
    timeout_s = timeout_s or int(os.getenv("GHOST_MAGNET_METADATA_TIMEOUT_S", "25"))
    store = store or MagnetMetadataStore()
    fetcher = get_metadata_fetcher()
    try:
        meta = fetcher.fetch(magnet_uri, timeout_s=timeout_s)
    finally:
        try:
            fetcher.close()
        except Exception:
            pass

    tree = build_file_tree(meta.files)
    payload = {
        "magnet_hash": meta.magnet_hash,
        "total_size_bytes": int(meta.total_size_bytes),
        "total_size_human": format_bytes(int(meta.total_size_bytes)),
        "file_count": len(meta.files),
        "files_tree": tree,
        "files_tree_summary": file_tree_summary(tree),
        "num_peers": int(meta.num_peers),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "backend": os.getenv("GHOST_MAGNET_METADATA_BACKEND", "libtorrent"),
    }
    store.save(meta.magnet_hash, payload)
    return payload


__all__ = [
    "MagnetMetadataStore",
    "MagnetMetadataFetcher",
    "MagnetMetadata",
    "MagnetFile",
    "MagnetInactiveError",
    "MagnetMetadataUnavailableError",
    "MagnetMetadataError",
    "probe_and_store_magnet_metadata",
]
