from fastapi.testclient import TestClient

from packages.core.auth import Role, hash_token
from packages.db import Auth, Category, session_scope


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def seed_categories():
    with session_scope() as session:
        root = Category(
            name="Root", slug="root", parent_id=None, root_id=0, sort_order=0
        )
        session.add(root)
        session.flush()
        root.root_id = root.id
        session.commit()
        return root.id


def test_session_verify(test_client: TestClient, seeded_tokens):
    res = test_client.post(
        "/api/session/verify", headers=auth_header(seeded_tokens["admin"])
    )
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == Role.ADMIN.value


def test_build_status_and_trigger(test_client: TestClient, seeded_tokens):
    res = test_client.get(
        "/api/build/status", headers=auth_header(seeded_tokens["admin"])
    )
    assert res.status_code == 200
    assert res.json()["pending_changes"] is False

    res = test_client.post(
        "/api/build/trigger",
        headers=auth_header(seeded_tokens["admin"]),
        json={"reason": "test"},
    )
    assert res.status_code == 200
    assert res.json()["pending_changes"] is True


def test_resource_crud_scope(test_client: TestClient, seeded_tokens):
    category_id = seed_categories()
    # Publisher creates
    payload = {
        "title": "Test Resource",
        "magnet_uri": "magnet:?xt=urn:btih:abc123",
        "content_markdown": "hello",
        "cover_image_url": None,
        "tags": ["a"],
        "category_id": category_id,
        "team_id": None,
    }
    res = test_client.post(
        "/api/resources", headers=auth_header(seeded_tokens["publisher"]), json=payload
    )
    assert res.status_code == 201
    created = res.json()
    rid = created["id"]
    assert created["magnet_hash"] == "abc123"

    # Team member cannot update publisher resource if different team
    res = test_client.put(
        f"/api/resources/{rid}",
        headers=auth_header(seeded_tokens["team_member"]),
        json={"title": "nope"},
    )
    assert res.status_code == 403

    # Admin can update
    res = test_client.put(
        f"/api/resources/{rid}",
        headers=auth_header(seeded_tokens["admin"]),
        json={"title": "updated"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "updated"

    # Admin takedown
    res = test_client.post(
        f"/api/resources/{rid}/takedown", headers=auth_header(seeded_tokens["admin"])
    )
    assert res.status_code == 200
    assert res.json()["takedown_at"] is not None


def test_team_invite_and_scope(test_client: TestClient, seeded_tokens):
    # Create team via publisher
    res = test_client.post(
        "/api/teams",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"name": "Team B"},
    )
    assert res.status_code == 201
    team_id = res.json()["id"]

    # Owner issues invite
    res = test_client.post(
        f"/api/teams/{team_id}/invites",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == Role.TEAM_MEMBER.value
    assert data["scope_team_id"] == team_id


def test_category_crud(test_client: TestClient, seeded_tokens):
    res = test_client.post(
        "/api/categories",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"name": "Root", "slug": "root", "parent_id": None, "sort_order": 0},
    )
    assert res.status_code == 201
    root = res.json()
    assert root["root_id"] == root["id"]

    res = test_client.put(
        f"/api/categories/{root['id']}",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"name": "Root Updated"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Root Updated"

    res = test_client.get(
        "/api/categories/tree", headers=auth_header(seeded_tokens["publisher"])
    )
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_resource_list_scopes(test_client: TestClient, seeded_tokens):
    category_id = seed_categories()
    # Publisher-owned resource
    res = test_client.post(
        "/api/resources",
        headers=auth_header(seeded_tokens["publisher"]),
        json={
            "title": "Pub Resource",
            "magnet_uri": "magnet:?xt=urn:btih:pubhash",
            "content_markdown": "pub",
            "cover_image_url": None,
            "tags": [],
            "category_id": category_id,
            "team_id": None,
        },
    )
    pub_id = res.json()["id"]

    # Team member resource
    res = test_client.post(
        "/api/resources",
        headers=auth_header(seeded_tokens["team_member"]),
        json={
            "title": "Team Resource",
            "magnet_uri": "magnet:?xt=urn:btih:teamhash",
            "content_markdown": "team",
            "cover_image_url": None,
            "tags": [],
            "category_id": category_id,
            "team_id": seeded_tokens["team_id"],
        },
    )
    team_id = res.json()["id"]

    res = test_client.get("/api/resources", headers=auth_header(seeded_tokens["admin"]))
    assert res.status_code == 200
    ids = {item["id"] for item in res.json()}
    assert {pub_id, team_id}.issubset(ids)

    res = test_client.get(
        "/api/resources", headers=auth_header(seeded_tokens["publisher"])
    )
    assert res.status_code == 200
    assert {item["id"] for item in res.json()} == {pub_id}

    res = test_client.get(
        "/api/resources", headers=auth_header(seeded_tokens["team_member"])
    )
    assert res.status_code == 200
    assert {item["id"] for item in res.json()} == {team_id}


def test_resource_validation_and_get(test_client: TestClient, seeded_tokens):
    category_id = seed_categories()
    bad_payload = {
        "title": "Bad",
        "magnet_uri": "not-a-magnet",
        "content_markdown": "x",
        "cover_image_url": None,
        "tags": [],
        "category_id": category_id,
        "team_id": None,
    }
    res = test_client.post(
        "/api/resources",
        headers=auth_header(seeded_tokens["publisher"]),
        json=bad_payload,
    )
    assert res.status_code == 400

    res = test_client.post(
        "/api/resources",
        headers=auth_header(seeded_tokens["team_member"]),
        json={
            **bad_payload,
            "magnet_uri": "magnet:?xt=urn:btih:teamhash",
            "team_id": seeded_tokens["team_id"] + 1,
        },
    )
    assert res.status_code == 403

    res = test_client.get(
        "/api/resources/999", headers=auth_header(seeded_tokens["admin"])
    )
    assert res.status_code == 404


def test_category_delete_constraints(test_client: TestClient, seeded_tokens):
    # Root + child
    res = test_client.post(
        "/api/categories",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"name": "Root", "slug": "root", "parent_id": None, "sort_order": 0},
    )
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
    child = res.json()
    res = test_client.delete(
        f"/api/categories/{root['id']}",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 400

    # Delete child, then tie a resource to root to block deletion
    res = test_client.delete(
        f"/api/categories/{child['id']}",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 204

    res = test_client.post(
        "/api/resources",
        headers=auth_header(seeded_tokens["publisher"]),
        json={
            "title": "Using Root",
            "magnet_uri": "magnet:?xt=urn:btih:rootres",
            "content_markdown": "content",
            "cover_image_url": None,
            "tags": [],
            "category_id": root["id"],
            "team_id": None,
        },
    )
    assert res.status_code == 201

    res = test_client.delete(
        f"/api/categories/{root['id']}",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 400

    # New category that can be deleted
    res = test_client.post(
        "/api/categories",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"name": "Solo", "slug": "solo", "parent_id": None, "sort_order": 0},
    )
    solo = res.json()
    res = test_client.delete(
        f"/api/categories/{solo['id']}",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 204


def test_team_invite_permissions(test_client: TestClient, seeded_tokens):
    # Team already exists from fixture; invite as owner works
    res = test_client.post(
        f"/api/teams/{seeded_tokens['team_id']}/invites",
        headers=auth_header(seeded_tokens["publisher"]),
    )
    assert res.status_code == 200

    res = test_client.post(
        f"/api/teams/{seeded_tokens['team_id']}/invites",
        headers=auth_header(seeded_tokens["team_member"]),
    )
    assert res.status_code == 403

    # Another publisher cannot invite for someone else's team
    other_token = "publisher-two"
    with session_scope() as session:
        session.add(
            Auth(
                token_hash=hash_token(other_token),
                role=Role.PUBLISHER.value,
                display_name="Other Publisher",
            )
        )
        session.commit()

    res = test_client.post(
        f"/api/teams/{seeded_tokens['team_id']}/invites",
        headers=auth_header(other_token),
    )
    assert res.status_code == 403


def test_admin_revoke_and_build_trigger_permissions(
    test_client: TestClient, seeded_tokens
):
    res = test_client.post(
        "/api/admin/tokens/revoke",
        headers=auth_header(seeded_tokens["admin"]),
        json={"token": "missing"},
    )
    assert res.status_code == 404

    target_token = "temp-token"
    with session_scope() as session:
        session.add(
            Auth(
                token_hash=hash_token(target_token),
                role=Role.PUBLISHER.value,
                display_name="Temp",
            )
        )
        session.commit()

    res = test_client.post(
        "/api/admin/tokens/revoke",
        headers=auth_header(seeded_tokens["admin"]),
        json={"token": target_token},
    )
    assert res.status_code == 200
    assert res.json()["token_hash"] == hash_token(target_token)

    res = test_client.post(
        "/api/build/trigger",
        headers=auth_header(seeded_tokens["publisher"]),
        json={"reason": "nope"},
    )
    assert res.status_code == 403
