from packages.core.auth import Role, assert_resource_scope, hash_token, verify_token
from packages.db import Auth


def test_hash_token_deterministic(monkeypatch):
    monkeypatch.setenv("GHOST_TOKEN_PEPPER", "pepper")
    a = hash_token("token123")
    b = hash_token("token123")
    assert a == b
    c = hash_token("token1234")
    assert a != c


def test_verify_token(db_session):
    token = "secret"
    token_hash = hash_token(token)
    db_session.add(
        Auth(token_hash=token_hash, role=Role.ADMIN.value, display_name="Admin")
    )
    db_session.commit()
    principal = verify_token(db_session, token)
    assert principal is not None
    assert principal.role == Role.ADMIN


def test_assert_resource_scope():
    publisher = verify_dummy(Role.PUBLISHER, scope_team_id=None, token_hash="pub")
    member = verify_dummy(Role.TEAM_MEMBER, scope_team_id=2, token_hash="tmem")
    admin = verify_dummy(Role.ADMIN, scope_team_id=None, token_hash="admin")

    assert_resource_scope(admin, team_id=1, publisher_hash="pub")
    assert_resource_scope(publisher, team_id=None, publisher_hash="pub")
    assert_resource_scope(member, team_id=2, publisher_hash="pub")


class DummyPrincipal:
    def __init__(self, role, scope_team_id, token_hash):
        self.role = role
        self.scope_team_id = scope_team_id
        self.token_hash = token_hash


def verify_dummy(role, scope_team_id, token_hash):
    return DummyPrincipal(role=role, scope_team_id=scope_team_id, token_hash=token_hash)
