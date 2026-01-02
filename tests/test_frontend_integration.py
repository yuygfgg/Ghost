import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from packages.core.auth import Role, hash_token
from packages.db import Auth, ensure_build_state, session_scope

_ONE_BY_ONE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc``\x00"
    b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def rebind_engine_for_test(db_url: str):
    """Reload DB and API modules against a temporary database."""
    import importlib
    import os

    os.environ["GHOST_DB_PATH"] = db_url
    db_engine_module = importlib.reload(importlib.import_module("packages.db.engine"))
    importlib.reload(importlib.import_module("packages.db"))
    importlib.reload(importlib.import_module("apps.api.deps"))
    api_main = importlib.reload(importlib.import_module("apps.api.main"))

    from packages.db import Base

    Base.metadata.create_all(db_engine_module.engine)
    return api_main.app


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_assets_served(test_client: TestClient):
    # Static assets should be reachable to boot the SPA logic.
    js = test_client.get("/admin/static/js/admin.js")
    assert js.status_code == 200
    assert "ghost_admin_token" in js.text
    css = test_client.get("/admin/static/css/admin.css")
    assert css.status_code == 200


def test_public_site_end_to_end(tmp_path, monkeypatch):
    """Publish data via API, run build, then read public site assets/search index."""
    workdir = tmp_path / "site"
    db_url = f"sqlite:///{tmp_path}/ghost.db"
    admin_token = "admin-e2e"
    publisher_token = "publisher-e2e"
    cover_url = "https://example.com/end-to-end-cover.jpg"

    monkeypatch.setenv("GHOST_DB_PATH", db_url)
    monkeypatch.setenv("GHOST_SITE_WORKDIR", str(workdir))
    monkeypatch.setenv("GHOST_DEPLOY_MODE", "integrated")
    monkeypatch.setenv("GHOST_ENABLE_SCHEDULER", "0")

    # Initial app to use API for data creation.
    app = rebind_engine_for_test(db_url)
    with session_scope() as session:
        session.add_all(
            [
                Auth(
                    token_hash=hash_token(admin_token),
                    role=Role.ADMIN.value,
                    display_name="Admin E2E",
                ),
                Auth(
                    token_hash=hash_token(publisher_token),
                    role=Role.PUBLISHER.value,
                    display_name="Publisher E2E",
                ),
            ]
        )
        ensure_build_state(session)
        session.commit()
    client = TestClient(app)

    # Create category and resource through API (publisher scope).
    res = client.post(
        "/api/categories",
        headers=auth_header(publisher_token),
        json={"name": "Docs", "slug": "docs", "parent_id": None, "sort_order": 0},
    )
    assert res.status_code == 201
    category_id = res.json()["id"]

    res = client.post(
        "/api/resources",
        headers=auth_header(publisher_token),
        json={
            "title": "End to End",
            "magnet_uri": "magnet:?xt=urn:btih:feedfeedfeedfeedfeedfeedfeedfeedfeedfeed",
            "content_markdown": "hello world",
            "cover_image_url": cover_url,
            "tags": ["docs"],
            "category_id": category_id,
            "team_id": None,
        },
    )
    assert res.status_code == 201
    resource_id = res.json()["id"]

    # Mock Hugo to avoid external binary but publish static + index content.
    hugo_calls = []

    def fake_hugo(repo, hugo_bin="hugo"):
        hugo_calls.append((str(repo.root), hugo_bin))
        repo.public_dir.mkdir(parents=True, exist_ok=True)
        if repo.static_dir.exists():
            shutil.copytree(repo.static_dir, repo.public_dir, dirs_exist_ok=True)
        # Minimal placeholder so / renders.
        (repo.public_dir / "index.html").write_text(
            "<html><body>home</body></html>", encoding="utf-8"
        )

    monkeypatch.setattr("packages.worker.build.pipeline.run_hugo_build", fake_hugo)

    def fake_fetch(url: str, timeout_s: int):
        from packages.worker.build.covers import DownloadedFile

        return DownloadedFile(content=_ONE_BY_ONE_PNG, content_type="image/png")

    def patched_localize(session, repo):
        from packages.worker.build.covers import localize_cover_images

        return localize_cover_images(session, repo, fetch=fake_fetch)

    monkeypatch.setattr(
        "packages.worker.build.pipeline.localize_cover_images", patched_localize
    )

    from packages.worker.build.pipeline import run_build_pipeline

    run_build_pipeline(force=True)
    assert hugo_calls

    # Recreate app to mount generated public site.
    app_public = rebind_engine_for_test(db_url)
    public_client = TestClient(app_public)

    # Public root served.
    res = public_client.get("/")
    assert res.status_code == 200

    # Search manifest and shard contain the resource and cover URL.
    manifest = public_client.get("/index/manifest.json")
    assert manifest.status_code == 200
    manifest_data = manifest.json()
    assert manifest_data["shards"], "manifest should list search shards"
    shard_file = manifest_data["shards"][0]["file"]
    shard = public_client.get(f"/index/{shard_file}")
    assert shard.status_code == 200
    items = shard.json()["items"]
    target = next((i for i in items if i["id"] == resource_id), None)
    assert target is not None
    assert target["cover_image_url"] is None
    cover_path = target["cover_image_path"]
    assert cover_path and cover_path.startswith("assets/covers/")
    cover_file = public_client.get(f"/{cover_path}")
    assert cover_file.status_code == 200


def test_taxonomy_pages_and_data(tmp_path, monkeypatch):
    """Ensure tag/category exports exist and static pages are reachable."""
    workdir = tmp_path / "site"
    db_url = f"sqlite:///{tmp_path}/ghost.db"
    admin_token = "admin-tax"
    publisher_token = "publisher-tax"

    monkeypatch.setenv("GHOST_DB_PATH", db_url)
    monkeypatch.setenv("GHOST_SITE_WORKDIR", str(workdir))
    monkeypatch.setenv("GHOST_DEPLOY_MODE", "integrated")
    monkeypatch.setenv("GHOST_ENABLE_SCHEDULER", "0")

    app = rebind_engine_for_test(db_url)
    with session_scope() as session:
        session.add_all(
            [
                Auth(
                    token_hash=hash_token(admin_token),
                    role=Role.ADMIN.value,
                    display_name="Admin Tax",
                ),
                Auth(
                    token_hash=hash_token(publisher_token),
                    role=Role.PUBLISHER.value,
                    display_name="Publisher Tax",
                ),
            ]
        )
        ensure_build_state(session)
        session.commit()

    client = TestClient(app)

    # Build categories and resources via API
    res = client.post(
        "/api/categories",
        headers=auth_header(publisher_token),
        json={"name": "Docs", "slug": "docs", "parent_id": None, "sort_order": 0},
    )
    assert res.status_code == 201
    docs_cat = res.json()["id"]
    res = client.post(
        "/api/categories",
        headers=auth_header(publisher_token),
        json={
            "name": "Guides",
            "slug": "guides",
            "parent_id": docs_cat,
            "sort_order": 1,
        },
    )
    assert res.status_code == 201
    guides_cat = res.json()["id"]

    res = client.post(
        "/api/resources",
        headers=auth_header(publisher_token),
        json={
            "title": "Guide Alpha",
            "magnet_uri": "magnet:?xt=urn:btih:1111feedface1111feedface1111feedface1111",
            "content_markdown": "Doc A",
            "cover_image_url": "https://example.com/guide-alpha.jpg",
            "tags": ["alpha", "beta"],
            "category_id": guides_cat,
            "team_id": None,
        },
    )
    assert res.status_code == 201
    res_one_id = res.json()["id"]

    res = client.post(
        "/api/resources",
        headers=auth_header(publisher_token),
        json={
            "title": "Doc Beta",
            "magnet_uri": "magnet:?xt=urn:btih:2222feedface2222feedface2222feedface2222",
            "content_markdown": "Doc B",
            "cover_image_url": None,
            "tags": ["beta"],
            "category_id": docs_cat,
            "team_id": None,
        },
    )
    assert res.status_code == 201
    res_two_id = res.json()["id"]

    hugo_calls = []

    def fake_hugo(repo, hugo_bin="hugo"):
        hugo_calls.append(str(repo.root))
        repo.public_dir.mkdir(parents=True, exist_ok=True)
        if repo.static_dir.exists():
            shutil.copytree(repo.static_dir, repo.public_dir, dirs_exist_ok=True)
        (repo.public_dir / "index.html").write_text(
            "<html><body>home</body></html>", encoding="utf-8"
        )

    monkeypatch.setattr("packages.worker.build.pipeline.run_hugo_build", fake_hugo)

    from packages.worker.build.pipeline import run_build_pipeline

    run_build_pipeline(force=True)
    assert hugo_calls

    # Static taxonomy data exported
    tags_json = json.loads(
        (workdir / "static" / "index" / "tags.json").read_text(encoding="utf-8")
    )
    assert tags_json["total_resources"] == 2
    beta_count = next((t["count"] for t in tags_json["tags"] if t["tag"] == "beta"), 0)
    assert beta_count == 2

    categories_json = json.loads(
        (workdir / "static" / "index" / "categories.json").read_text(encoding="utf-8")
    )
    roots = categories_json["categories"]
    docs_node = next((c for c in roots if c["slug"] == "docs"), None)
    assert docs_node is not None
    assert docs_node["count"] == 2
    guides_node = next(
        (c for c in docs_node["children"] if c["slug"] == "guides"), None
    )
    assert guides_node is not None
    assert guides_node["count"] == 1
    assert guides_node["path"] == "docs/guides"

    # Search shard carries category id for filtering
    manifest = json.loads(
        (workdir / "static" / "index" / "manifest.json").read_text(encoding="utf-8")
    )
    shard_file = manifest["shards"][0]["file"]
    shard = json.loads(
        (workdir / "static" / "index" / shard_file).read_text(encoding="utf-8")
    )
    first = next(i for i in shard["items"] if i["id"] == res_one_id)
    assert first["category_id"] == guides_cat
    assert first["category_path"] == "docs/guides"

    # Public pages are reachable via integrated mount
    app_public = rebind_engine_for_test(db_url)
    public_client = TestClient(app_public)
    res = public_client.get("/tags/")
    assert res.status_code == 200
    assert "标签云" in res.text
    res = public_client.get("/tags/beta/")
    assert res.status_code == 200
    assert "ghost-initial-tags" in res.text
    res = public_client.get("/categories/")
    assert res.status_code == 200
    assert "分类树" in res.text
    res = public_client.get("/categories/docs/guides/")
    assert res.status_code == 200
    assert "ghost-initial-category" in res.text

    # JS helper should dedupe duplicate hits (number vs string ids)
    node = shutil.which("node")
    if node is None:
        pytest.fail("Required binary `node` not found in PATH", pytrace=False)
    script = f"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("{(workdir / 'static' / 'js' / 'index-loader.js').as_posix()}", "utf8");
const ctx = {{ console }};
vm.createContext(ctx);
vm.runInContext(code, ctx);
const loader = ctx.GhostIndexLoader;
const hits = [{{ result: [{{ doc: 1 }}, {{ doc: "1" }}, {{ doc: {{ id: 1 }} }}] }}];
const map = new Map([["1", {{ id: "1", title: "dup" }}]]);
const docs = loader.collectDocsFromHits(hits, map);
console.log(JSON.stringify(docs));
"""
    proc = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, check=True
    )
    docs = json.loads(proc.stdout.strip() or "[]")
    assert len(docs) == 1
