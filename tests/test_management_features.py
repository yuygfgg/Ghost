from fastapi.testclient import TestClient

from packages.core.auth import Role, hash_token
from packages.db import Auth, Team, session_scope


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_web_pages_accessible(test_client: TestClient):
    # Root should redirect to dashboard; other pages render HTML.
    res = test_client.get("/admin", follow_redirects=False)
    assert res.status_code in (301, 302, 307)
    res = test_client.get("/admin/login")
    assert res.status_code == 200
    res = test_client.get("/admin/dashboard")
    assert res.status_code == 200
    res = test_client.get("/admin/resources")
    assert res.status_code == 200
    res = test_client.get("/admin/categories")
    assert res.status_code == 200
    res = test_client.get("/admin/teams")
    assert res.status_code == 200
    res = test_client.get("/admin/system")
    assert res.status_code == 200


def test_admin_token_lifecycle_and_permissions(test_client: TestClient, seeded_tokens):
    # Admin can issue a publisher token.
    res = test_client.post(
        "/api/admin/tokens/publisher",
        headers=auth_header(seeded_tokens["admin"]),
        json={"display_name": "NewPub"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == Role.PUBLISHER.value
    raw_token = data["token"]
    token_hash = data["token_hash"]
    assert raw_token and token_hash

    # Non-admin cannot issue tokens.
    res = test_client.post(
        "/api/admin/tokens/publisher",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"display_name": "ShouldFail"},
    )
    assert res.status_code == 403

    # Admin can revoke; unknown token is 404.
    res = test_client.post(
        "/api/admin/tokens/revoke",
        headers=auth_header(seeded_tokens["admin"]),
        json={"token": raw_token},
    )
    assert res.status_code == 200
    assert "revoked_at" in res.json()

    res = test_client.post(
        "/api/admin/tokens/revoke",
        headers=auth_header(seeded_tokens["admin"]),
        json={"token": "does-not-exist"},
    )
    assert res.status_code == 404

    with session_scope() as session:
        record = session.get(Auth, token_hash)
        assert record is not None
        assert record.revoked_at is not None


def test_admin_can_trigger_full_dht_scan(
    test_client: TestClient, seeded_tokens, monkeypatch
):
    calls: list[int | None] = []

    async def fake_scan_all(timeout_s=None):
        calls.append(timeout_s)
        return 0

    monkeypatch.setattr("apps.api.routers.admin.run_dht_health_scan_all", fake_scan_all)

    res = test_client.post(
        "/api/admin/dht/scan-all?wait=1&timeout_s=7",
        headers=auth_header(seeded_tokens["admin"]),
    )
    assert res.status_code == 200
    assert res.json()["queued"] is False
    assert calls == [7]

    res = test_client.post(
        "/api/admin/dht/scan-all?wait=1",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 403


def test_team_listing_and_invite_rules(
    test_client: TestClient, seeded_tokens, db_session
):
    other_pub_token = "other-pub"
    other_pub = Auth(
        token_hash=hash_token(other_pub_token),
        role=Role.PUBLISHER.value,
        display_name="OtherPub",
    )
    other_team = Team(name="Other Team", owner_token_hash=other_pub.token_hash)
    db_session.add_all([other_pub, other_team])
    db_session.commit()

    # Admin sees all teams.
    res = test_client.get("/api/teams", headers=auth_header(seeded_tokens["admin"]))
    assert res.status_code == 200
    assert len(res.json()) >= 2

    # Publisher only sees their own team.
    res = test_client.get("/api/teams", headers=auth_header(seeded_tokens["publisher"]))
    assert res.status_code == 200
    names = {t["name"] for t in res.json()}
    assert names == {"Team A"}

    # Team member only sees scoped team.
    res = test_client.get(
        "/api/teams", headers=auth_header(seeded_tokens["team_member"])
    )
    assert res.status_code == 200
    assert {t["name"] for t in res.json()} == {"Team A"}

    # Inviting with wrong owner is forbidden; unknown team returns 404.
    res = test_client.post(
        f"/api/teams/{other_team.id}/invites",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 403

    res = test_client.post(
        "/api/teams/9999/invites",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 404


def test_category_crud_and_error_paths(test_client: TestClient, seeded_tokens):
    # Create root and child category.
    res = test_client.post(
        "/api/categories",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"name": "Root", "slug": "root", "parent_id": None, "sort_order": 0},
    )
    assert res.status_code == 201
    root = res.json()

    res = test_client.post(
        "/api/categories",
        headers=auth_header(seeded_tokens["publisher"]),
        json={
            "name": "Child",
            "slug": "child",
            "parent_id": root["id"],
            "sort_order": 0,
        },
    )
    assert res.status_code == 201
    child = res.json()

    # Updating with invalid parent fails.
    res = test_client.put(
        f"/api/categories/{child['id']}",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"parent_id": 9999},
    )
    assert res.status_code == 400

    # Cannot delete parent while children exist.
    res = test_client.delete(
        f"/api/categories/{root['id']}", headers=auth_header(seeded_tokens["publisher"])
    )
    assert res.status_code == 400

    # Create a resource to lock the category and block deletion.
    res = test_client.post(
        "/api/resources",
        headers=auth_header(seeded_tokens["publisher"]),
        json={
            "title": "Uses Child",
            "magnet_uri": "magnet:?xt=urn:btih:1234567890abcdef",
            "content_markdown": "desc",
            "cover_image_url": None,
            "tags": [],
            "category_id": child["id"],
            "team_id": None,
        },
    )
    assert res.status_code == 201

    res = test_client.delete(
        f"/api/categories/{child['id']}",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 400


def test_resource_permissions_and_listing(test_client: TestClient, seeded_tokens):
    # Missing auth yields 401.
    res = test_client.get("/api/resources")
    assert res.status_code == 401

    # Create category and resource.
    res = test_client.post(
        "/api/categories",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"name": "Docs", "slug": "docs", "parent_id": None, "sort_order": 0},
    )
    assert res.status_code == 201
    category_id = res.json()["id"]

    res = test_client.post(
        "/api/resources",
        headers=auth_header(seeded_tokens["publisher"]),
        json={
            "title": "Pub Item",
            "magnet_uri": "magnet:?xt=urn:btih:deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "content_markdown": "hello",
            "cover_image_url": "https://example.com/cover.png",
            "tags": ["one", "two"],
            "category_id": category_id,
            "team_id": None,
        },
    )
    assert res.status_code == 201
    resource_id = res.json()["id"]

    # Team member cannot update publisher-owned resource.
    res = test_client.put(
        f"/api/resources/{resource_id}",
        headers=auth_header(seeded_tokens["team_member"]),
        json={"title": "nope"},
    )
    assert res.status_code == 403

    # Admin can list all resources.
    res = test_client.get("/api/resources", headers=auth_header(seeded_tokens["admin"]))
    assert res.status_code == 200
    assert any(item["id"] == resource_id for item in res.json())

    # Publisher sees only their own resource.
    res = test_client.get(
        "/api/resources", headers=auth_header(seeded_tokens["publisher"])
    )
    assert res.status_code == 200
    assert {item["id"] for item in res.json()} == {resource_id}
