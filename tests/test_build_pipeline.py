import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

COVER_URL = "https://example.com/cover.jpg"
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


def seed_data():
    from packages.core.auth import Role, hash_token
    from packages.db import Auth, Category, Resource, ensure_build_state, session_scope

    with session_scope() as session:
        cat = Category(
            name="Movies", slug="movies", parent_id=None, root_id=0, sort_order=0
        )
        session.add(cat)
        session.flush()
        cat.root_id = cat.id

        publisher = Auth(
            token_hash=hash_token("pub"),
            role=Role.PUBLISHER.value,
            display_name="Publisher",
        )
        session.add(publisher)
        session.flush()

        res = Resource(
            title="Test Item",
            magnet_uri="magnet:?xt=urn:btih:abcd1234",
            magnet_hash="abcd1234",
            content_markdown="Some description\n\nMore text",
            cover_image_url=COVER_URL,
            tags_json='["tag1","tag2"]',
            category_id=cat.id,
            publisher_token_hash=publisher.token_hash,
            team_id=None,
            published_at=datetime(2024, 1, 20, tzinfo=timezone.utc),
        )
        session.add(res)
        ensure_build_state(session)
        session.commit()
        return res.id


def test_run_build_pipeline_exports_content_and_index(db_url, tmp_path, monkeypatch):
    workdir = tmp_path / "site"
    monkeypatch.setenv("GHOST_DB_PATH", db_url)
    monkeypatch.setenv("GHOST_SITE_WORKDIR", str(workdir))
    monkeypatch.setenv("GHOST_ENABLE_SCHEDULER", "0")
    monkeypatch.setenv("GHOST_MAGNET_METADATA_BACKEND", "mock")
    monkeypatch.setenv("GHOST_MAGNET_METADATA_DIR", str(tmp_path / "magnet-metadata"))
    rebind_engine_for_test(db_url)
    resource_id = seed_data()

    def fake_fetch(url: str, timeout_s: int):
        from packages.worker.build.covers import DownloadedFile

        return DownloadedFile(content=_ONE_BY_ONE_PNG, content_type="image/png")

    def patched_localize(session, repo):
        from packages.worker.build.covers import localize_cover_images

        return localize_cover_images(session, repo, fetch=fake_fetch)

    monkeypatch.setattr(
        "packages.worker.build.pipeline.localize_cover_images", patched_localize
    )

    backup_calls = []

    def fake_backup():
        backup_calls.append(True)

    monkeypatch.setattr(
        "packages.worker.build.pipeline.create_age_encrypted_db_backup", fake_backup
    )

    hugo_calls = []

    def fake_hugo(repo, hugo_bin="hugo"):
        hugo_calls.append((str(repo.root), str(repo.public_dir), hugo_bin))
        repo.public_dir.mkdir(parents=True, exist_ok=True)
        (repo.public_dir / "index.html").write_text("ok", encoding="utf-8")

    monkeypatch.setattr("packages.worker.build.pipeline.run_hugo_build", fake_hugo)

    from packages.worker.build.pipeline import run_build_pipeline
    from packages.db import BuildState, session_scope

    run_build_pipeline(force=True)

    # Hugo invoked with expected paths
    assert hugo_calls
    assert backup_calls, "Build pipeline should attempt to create an age backup"
    root_path, public_path, _ = hugo_calls[0]
    assert root_path == str(workdir.resolve())
    assert Path(public_path).exists()
    assert not (workdir / "var").exists()  # guard against nested builds

    # Content markdown produced with front matter
    content_file = workdir / "content" / "resources" / f"{resource_id}.md"
    assert content_file.exists()
    content = content_file.read_text(encoding="utf-8")
    assert "magnet:?xt=urn:btih:abcd1234" in content
    assert "tag1" in content
    assert COVER_URL not in content

    # Search index manifest and shard
    manifest_path = workdir / "static" / "index" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["shards"]
    shard_file = manifest["shards"][0]["file"]
    shard = json.loads((manifest_path.parent / shard_file).read_text(encoding="utf-8"))
    assert shard["items"][0]["url"] == f"/resources/{resource_id}/"
    assert shard["items"][0]["published_at"].startswith("2024-01")
    assert shard["items"][0]["cover_image_url"] is None
    cover_path = shard["items"][0]["cover_image_path"]
    assert cover_path and cover_path.startswith("assets/covers/")
    assert (workdir / "static" / cover_path).exists()

    # Build state updated
    with session_scope() as session:
        state = session.get(BuildState, 1)
        assert state is not None
        assert state.pending_changes is False
        assert state.last_error is None
        assert state.last_build_at is not None


def test_integrated_mode_mounts_public_site(db_url, tmp_path, monkeypatch):
    workdir = tmp_path / "site"
    public = workdir / "public"
    public.mkdir(parents=True)
    (public / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")

    monkeypatch.setenv("GHOST_DB_PATH", db_url)
    monkeypatch.setenv("GHOST_SITE_WORKDIR", str(workdir))
    monkeypatch.setenv("GHOST_DEPLOY_MODE", "integrated")
    monkeypatch.setenv("GHOST_ENABLE_SCHEDULER", "0")
    monkeypatch.setenv("GHOST_MAGNET_METADATA_BACKEND", "mock")
    monkeypatch.setenv("GHOST_MAGNET_METADATA_DIR", str(tmp_path / "magnet-metadata"))
    app = rebind_engine_for_test(db_url)

    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "Hello" in res.text


def test_full_flow_invite_and_build(db_url, tmp_path, monkeypatch):
    """Full path: seed admin/publisher, create team+invite, publish resource, build static site."""
    workdir = tmp_path / "site"
    monkeypatch.setenv("GHOST_DB_PATH", db_url)
    monkeypatch.setenv("GHOST_SITE_WORKDIR", str(workdir))
    monkeypatch.setenv("GHOST_DEPLOY_MODE", "integrated")
    monkeypatch.setenv("GHOST_ENABLE_SCHEDULER", "0")
    monkeypatch.setenv("GHOST_MAGNET_METADATA_BACKEND", "mock")
    monkeypatch.setenv("GHOST_MAGNET_METADATA_DIR", str(tmp_path / "magnet-metadata"))
    app = rebind_engine_for_test(db_url)

    from packages.core.auth import Role, hash_token
    from packages.db import Auth, ensure_build_state, session_scope

    admin_token = "admin-raw"
    publisher_token = "publisher-raw"
    with session_scope() as session:
        session.add_all(
            [
                Auth(
                    token_hash=hash_token(admin_token),
                    role=Role.ADMIN.value,
                    display_name="Admin",
                ),
                Auth(
                    token_hash=hash_token(publisher_token),
                    role=Role.PUBLISHER.value,
                    display_name="Publisher",
                ),
            ]
        )
        ensure_build_state(session)
        session.commit()

    client = TestClient(app)

    def auth_header(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    # Create category
    res = client.post(
        "/api/categories",
        headers=auth_header(publisher_token),
        json={"name": "Docs", "slug": "docs", "parent_id": None, "sort_order": 0},
    )
    assert res.status_code == 201
    category_id = res.json()["id"]

    # Create team and invite member
    res = client.post(
        "/api/teams", headers=auth_header(publisher_token), json={"name": "Team X"}
    )
    assert res.status_code == 201
    team_id = res.json()["id"]

    res = client.post(
        f"/api/teams/{team_id}/invites", headers=auth_header(publisher_token)
    )
    assert res.status_code == 200
    team_token = res.json()["token"]

    # Team member publishes resource
    magnet_uri = "magnet:?xt=urn:btih:feedfacefeedfacefeedfacefeedfacefeedface"
    res = client.post(
        "/api/resources",
        headers=auth_header(team_token),
        json={
            "title": "Team Published",
            "magnet_uri": magnet_uri,
            "content_markdown": "Hello world",
            "cover_image_url": None,
            "tags": ["x", "y"],
            "category_id": category_id,
            "team_id": team_id,
        },
    )
    assert res.status_code == 201
    resource_id = res.json()["id"]

    hugo_calls = []

    def fake_hugo(repo, hugo_bin="hugo"):
        hugo_calls.append((str(repo.root), str(repo.public_dir), hugo_bin))
        repo.public_dir.mkdir(parents=True, exist_ok=True)
        (repo.public_dir / "index.html").write_text("ok", encoding="utf-8")

    monkeypatch.setattr("packages.worker.build.pipeline.run_hugo_build", fake_hugo)

    from packages.worker.build.pipeline import run_build_pipeline

    run_build_pipeline(force=True)

    assert hugo_calls, "Hugo should be invoked during build"

    # Generated content and index include resource
    content_file = workdir / "content" / "resources" / f"{resource_id}.md"
    assert content_file.exists()
    assert magnet_uri in content_file.read_text(encoding="utf-8")

    manifest_path = workdir / "static" / "index" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shard_file = manifest["shards"][0]["file"]
    shard = json.loads((manifest_path.parent / shard_file).read_text(encoding="utf-8"))
    urls = {item["url"] for item in shard["items"]}
    assert f"/resources/{resource_id}/" in urls
    target = next(item for item in shard["items"] if item["id"] == resource_id)
    assert target["title"] == "Team Published"
    assert target["magnet_uri"] == magnet_uri
    assert target["magnet_hash"] == "feedfacefeedfacefeedfacefeedfacefeedface"
    assert target["tags"] == ["x", "y"]
    assert target["category_name"] == "Docs"
    assert target["publisher"] == "Team X member"
    assert target["team_id"] == team_id
    assert target["summary"] == "Hello world"

    # Front matter reflects publisher/category/tags
    content_text = content_file.read_text(encoding="utf-8")
    assert "category_name: Docs" in content_text
    assert "publisher: Team X member" in content_text
    assert "tags:\n- x\n- y" in content_text
