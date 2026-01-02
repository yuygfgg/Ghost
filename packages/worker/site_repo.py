from __future__ import annotations

import shutil
from pathlib import Path


class SiteRepo:
    """Helper for managing the local public site workdir."""

    def __init__(self, workdir: str | Path):
        self.root = Path(workdir)
        self.content_dir = self.root / "content" / "resources"
        self.static_dir = self.root / "static"
        self.layouts_dir = self.root / "layouts"
        self.assets_dir = self.root / "assets"
        self.data_dir = self.root / "data"
        self.public_dir = self.root / "public"

    def ensure_base(self) -> None:
        for path in [
            self.root,
            self.content_dir,
            self.static_dir,
            self.layouts_dir,
            self.assets_dir,
            self.data_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def clean_export_dirs(self) -> None:
        """Drop and recreate content/index export folders to avoid stale pages."""
        targets = [
            self.content_dir,
            self.root / "content" / "categories",
            self.root / "content" / "category",
            self.root / "content" / "tags",
            self.root / "content" / "tag",
            self.static_dir / "index",
            self.data_dir / "index",
        ]
        for target in targets:
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)


__all__ = ["SiteRepo"]
