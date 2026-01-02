from __future__ import annotations

import os
import subprocess
from pathlib import Path
from textwrap import dedent

from packages.worker.site_repo import SiteRepo


def ensure_hugo_scaffold(repo: SiteRepo, base_url: str = "/") -> None:
    """Write Hugo config, layouts, and static assets for local preview."""
    repo.ensure_base()

    _write_if_changed(
        repo.root / "config.toml",
        dedent(
            f"""
            baseURL = "{base_url}"
            languageCode = "zh-cn"
            title = "Ghost Index"
            enableRobotsTXT = true
            disableKinds = ["taxonomy", "term"]

            [pagination]
            pagerSize = 30

            [markup.goldmark.renderer]
            unsafe = true
            """
        ).strip()
        + "\n",
    )

    assets_root = Path(__file__).parent / "hugo_assets"

    # Layouts
    layouts_src = assets_root / "layouts" / "_default"
    _write_if_changed(
        repo.layouts_dir / "_default" / "baseof.html",
        (layouts_src / "baseof.html").read_text(encoding="utf-8"),
    )
    _write_if_changed(
        repo.layouts_dir / "_default" / "list.html",
        (layouts_src / "list.html").read_text(encoding="utf-8"),
    )
    _write_if_changed(
        repo.layouts_dir / "_default" / "single.html",
        (layouts_src / "single.html").read_text(encoding="utf-8"),
    )

    # Static Assets
    _write_if_changed(
        repo.static_dir / "css" / "main.css",
        (assets_root / "static" / "css" / "main.css").read_text(encoding="utf-8"),
    )
    for js_file in ["index-loader.js", "search.js", "catalog.js", "relative-time.js"]:
        _write_if_changed(
            repo.static_dir / "js" / js_file,
            (assets_root / "static" / "js" / js_file).read_text(encoding="utf-8"),
        )

    # Static Pages (Tags/Categories)
    _write_if_changed(
        repo.static_dir / "tags" / "index.html",
        (assets_root / "static" / "tags" / "index.html").read_text(encoding="utf-8"),
    )
    _write_if_changed(
        repo.static_dir / "categories" / "index.html",
        (assets_root / "static" / "categories" / "index.html").read_text(
            encoding="utf-8"
        ),
    )


def run_hugo_build(repo: SiteRepo, hugo_bin: str = "hugo") -> None:
    """Invoke Hugo to build the public site."""
    repo.public_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("HUGO_ENV", "production")
    cmd = [
        hugo_bin,
        "-s",
        str(repo.root.resolve()),
        "-d",
        str(repo.public_dir.resolve()),
        "--cleanDestinationDir",
    ]
    try:
        subprocess.run(cmd, check=True, env=env)
    except FileNotFoundError as exc:  # pragma: no cover - dependent on host
        raise RuntimeError(
            "Hugo binary not found. Install it and ensure it is on PATH."
        ) from exc


def _write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


__all__ = ["ensure_hugo_scaffold", "run_hugo_build"]
