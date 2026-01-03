import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from packages.core.auth import Role, hash_token
from packages.core.public_export import resource_to_public
from packages.db import (
    Auth,
    BuildState,
    Category,
    Resource,
    ensure_build_state,
    session_scope,
)
from packages.worker.build.backup import (
    create_age_encrypted_db_backup,
    restore_age_encrypted_db_backup,
)
from packages.worker.build.covers import DownloadedFile, localize_cover_images
from packages.worker.dht.scan import run_dht_health_scan
from packages.worker.site_repo import SiteRepo


_ONE_BY_ONE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc``\x00"
    b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)

_AGE_KEYGEN_RECIPIENT_PREFIXES = ("# public key: ", "Public key: ")


def _require_on_path(bin_name: str) -> str:
    path = shutil.which(bin_name)
    if path is None:
        pytest.fail(f"Required binary `{bin_name}` not found in PATH", pytrace=False)
    return path


def _generate_age_identity_and_recipient(*, identity_file: Path) -> str:
    _require_on_path(os.getenv("GHOST_AGE_BIN", "age"))
    age_keygen = _require_on_path("age-keygen")
    res = subprocess.run(
        [age_keygen, "-o", str(identity_file)],
        check=True,
        capture_output=True,
        text=True,
    )
    # age-keygen prints the recipient like: "Public key: age1...." (version-dependent).
    text_out = (res.stdout or "") + "\n" + (res.stderr or "")
    for line in text_out.splitlines():
        for prefix in _AGE_KEYGEN_RECIPIENT_PREFIXES:
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
    pytest.fail("Failed to parse recipient from `age-keygen` output", pytrace=False)


def _seed_minimal_resource(
    *,
    magnet_uri: str = "magnet:?xt=urn:btih:abcd1234",
    dht_status: str = "Unknown",
    cover_image_url: str | None = None,
    cover_image_path: str | None = None,
) -> int:
    with session_scope() as session:
        cat = Category(name="Cat", slug="cat", parent_id=None, root_id=0, sort_order=0)
        session.add(cat)
        session.flush()
        cat.root_id = cat.id

        pub_hash = hash_token("pub")
        pub = session.get(Auth, pub_hash)
        if pub is None:
            pub = Auth(
                token_hash=pub_hash, role=Role.PUBLISHER.value, display_name="Publisher"
            )
            session.add(pub)
            session.flush()

        res = Resource(
            title="Item",
            magnet_uri=magnet_uri,
            magnet_hash=magnet_uri.split("btih:")[-1],
            content_markdown="hello",
            cover_image_url=cover_image_url,
            cover_image_path=cover_image_path,
            tags_json=json.dumps(["t1"]),
            category_id=cat.id,
            publisher_token_hash=pub.token_hash,
            team_id=None,
            dht_status=dht_status,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        session.add(res)
        ensure_build_state(session)
        session.commit()
        return res.id


def test_public_export_omits_cover_url_and_includes_dht_fields(test_client):
    resource_id = _seed_minimal_resource(
        cover_image_url="https://example.com/secret.png",
        cover_image_path="assets/covers/1.png",
        dht_status="Active",
    )
    with session_scope() as session:
        res = session.get(Resource, resource_id)
        cats = session.query(Category).all()
        auths = session.query(Auth).all()
        public = resource_to_public(res, cats, auths)

    assert public["cover_image_url"] is None
    assert public["cover_image_path"] == "assets/covers/1.png"
    assert public["dht_status"] == "Active"
    assert public["last_dht_check"] is None


def test_cover_localization_writes_static_file_and_sets_db_path(
    test_client, tmp_path, monkeypatch
):
    resource_id = _seed_minimal_resource(
        cover_image_url="https://example.com/a.png", cover_image_path=None
    )
    repo = SiteRepo(tmp_path / "site")
    repo.ensure_base()

    def fake_fetch(url: str, timeout_s: int) -> DownloadedFile:
        return DownloadedFile(content=_ONE_BY_ONE_PNG, content_type="image/png")

    monkeypatch.setattr(
        "packages.worker.build.covers._maybe_convert_to_webp", lambda raw: None
    )

    with session_scope() as session:
        updated = localize_cover_images(session, repo, fetch=fake_fetch)
        assert updated == 1

    with session_scope() as session:
        res = session.get(Resource, resource_id)
        assert res.cover_image_path == f"assets/covers/{resource_id}.png"

    out_path = repo.static_dir / "assets" / "covers" / f"{resource_id}.png"
    assert out_path.exists()
    assert out_path.read_bytes() == _ONE_BY_ONE_PNG

    # Running again is a no-op when cover_image_path is already set.
    with session_scope() as session:
        assert localize_cover_images(session, repo, fetch=fake_fetch) == 0


def test_cover_localization_relocalizes_when_file_missing(
    test_client, tmp_path, monkeypatch
):
    resource_id = _seed_minimal_resource(
        cover_image_url="https://example.com/a.png",
        cover_image_path="assets/covers/missing.png",
    )
    repo = SiteRepo(tmp_path / "site")
    repo.ensure_base()

    def fake_fetch(url: str, timeout_s: int) -> DownloadedFile:
        return DownloadedFile(content=_ONE_BY_ONE_PNG, content_type="image/png")

    monkeypatch.setattr(
        "packages.worker.build.covers._maybe_convert_to_webp", lambda raw: None
    )

    with session_scope() as session:
        updated = localize_cover_images(session, repo, fetch=fake_fetch)
        assert updated == 1

    with session_scope() as session:
        res = session.get(Resource, resource_id)
        assert res.cover_image_path == f"assets/covers/{resource_id}.png"

    out_path = repo.static_dir / "assets" / "covers" / f"{resource_id}.png"
    assert out_path.exists()
    assert out_path.read_bytes() == _ONE_BY_ONE_PNG


def test_cover_localization_prefers_webp_when_converter_returns_bytes(
    test_client, tmp_path, monkeypatch
):
    resource_id = _seed_minimal_resource(
        cover_image_url="https://example.com/a.png", cover_image_path=None
    )
    repo = SiteRepo(tmp_path / "site")
    repo.ensure_base()

    def fake_fetch(url: str, timeout_s: int) -> DownloadedFile:
        return DownloadedFile(content=_ONE_BY_ONE_PNG, content_type="image/png")

    monkeypatch.setattr(
        "packages.worker.build.covers._maybe_convert_to_webp", lambda raw: b"WEBP!"
    )

    with session_scope() as session:
        updated = localize_cover_images(session, repo, fetch=fake_fetch)
        assert updated == 1

    with session_scope() as session:
        res = session.get(Resource, resource_id)
        assert res.cover_image_path == f"assets/covers/{resource_id}.webp"

    out_path = repo.static_dir / "assets" / "covers" / f"{resource_id}.webp"
    assert out_path.exists()
    assert out_path.read_bytes() == b"WEBP!"


def test_cover_localization_skips_non_http_and_fetch_errors(test_client, tmp_path):
    # Non-http scheme => skip, never calls fetch.
    _seed_minimal_resource(
        magnet_uri="magnet:?xt=urn:btih:abcd1234",
        cover_image_url="file:///tmp/x.png",
        cover_image_path=None,
    )
    repo = SiteRepo(tmp_path / "site")
    repo.ensure_base()

    with session_scope() as session:
        assert (
            localize_cover_images(
                session, repo, fetch=lambda *_: (_ for _ in ()).throw(AssertionError())
            )
            == 0
        )

    # Fetch error => best-effort skip.
    _seed_minimal_resource(
        magnet_uri="magnet:?xt=urn:btih:beadbead",
        cover_image_url="https://example.com/boom.png",
        cover_image_path=None,
    )

    def boom(url: str, timeout_s: int) -> DownloadedFile:
        raise RuntimeError("boom")

    with session_scope() as session:
        assert localize_cover_images(session, repo, fetch=boom) == 0


def test_age_backup_and_restore_skips_and_runs(monkeypatch, tmp_path):
    db_file = tmp_path / "ghost.db"
    db_plain = b"sqlite"
    db_file.write_bytes(db_plain)

    # Missing recipient => skip.
    monkeypatch.delenv("GHOST_AGE_RECIPIENT", raising=False)
    res = create_age_encrypted_db_backup(
        db_path_or_url=str(db_file), recipient=None, backup_dir=tmp_path
    )
    assert res.skipped is True

    # Use the real `age` binary from PATH for the happy path; fail fast if unavailable.
    _require_on_path(os.getenv("GHOST_AGE_BIN", "age"))
    identity_file = tmp_path / "identity.txt"
    recipient = _generate_age_identity_and_recipient(identity_file=identity_file)
    monkeypatch.setenv("GHOST_AGE_RECIPIENT", recipient)
    enc = create_age_encrypted_db_backup(
        db_path_or_url=str(db_file), backup_dir=tmp_path
    )
    assert enc.skipped is False
    assert enc.output_path
    enc_path = Path(enc.output_path)
    assert enc_path.exists()

    # restore skip without identity.
    monkeypatch.delenv("GHOST_AGE_IDENTITY_FILE", raising=False)
    restored = restore_age_encrypted_db_backup(
        input_path=enc_path, output_path=tmp_path / "restored.db"
    )
    assert restored.skipped is True

    # restore success with identity and real `age`.
    monkeypatch.setenv("GHOST_AGE_IDENTITY_FILE", str(identity_file))
    restored = restore_age_encrypted_db_backup(
        input_path=enc_path, output_path=tmp_path / "restored.db"
    )
    assert restored.skipped is False
    assert restored.output_path
    assert Path(restored.output_path).read_bytes() == db_plain


def test_age_backup_restore_roundtrip_with_generated_sqlite_data(monkeypatch, tmp_path):
    _require_on_path(os.getenv("GHOST_AGE_BIN", "age"))
    db_file = tmp_path / "ghost.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("create table t(id integer primary key, v text not null)")
        conn.execute("insert into t(v) values (?)", ("hello",))
        conn.commit()
    original_bytes = db_file.read_bytes()

    identity_file = tmp_path / "identity.txt"
    recipient = _generate_age_identity_and_recipient(identity_file=identity_file)

    monkeypatch.setenv("GHOST_AGE_RECIPIENT", recipient)
    monkeypatch.setenv("GHOST_AGE_IDENTITY_FILE", str(identity_file))

    enc = create_age_encrypted_db_backup(
        db_path_or_url=str(db_file), backup_dir=tmp_path
    )
    assert enc.skipped is False
    assert enc.output_path
    enc_path = Path(enc.output_path)
    assert enc_path.stat().st_size > 0

    restored_path = tmp_path / "restored.db"
    restored = restore_age_encrypted_db_backup(
        input_path=enc_path, output_path=restored_path
    )
    assert restored.skipped is False
    assert restored_path.read_bytes() == original_bytes

    with sqlite3.connect(restored_path) as conn:
        row = conn.execute("select v from t where id=1").fetchone()
        assert row == ("hello",)


@pytest.mark.parametrize(
    "initial,expected,should_pending",
    [("Unknown", "Active", True), ("Active", "Active", False)],
)
def test_dht_scan_updates_status_and_marks_pending(
    test_client, initial, expected, should_pending
):
    resource_id = _seed_minimal_resource(
        magnet_uri="magnet:?xt=urn:btih:feedface", dht_status=initial
    )

    class FakeChecker:
        def check(self, magnet_uri: str, timeout_s: int):
            assert timeout_s == 1
            return type("Probe", (), {"status": expected})()

        def close(self) -> None:
            return None

    asyncio.run(
        run_dht_health_scan(
            sample_size=10, timeout_s=1, checker_factory=lambda: FakeChecker()
        )
    )

    with session_scope() as session:
        res = session.get(Resource, resource_id)
        state = session.get(BuildState, 1)
        assert res.dht_status == expected
        assert res.last_dht_check is not None
        assert state.pending_changes is should_pending


def test_dht_scan_checker_unavailable_keeps_pending_false_when_already_unknown(
    test_client,
):
    _seed_minimal_resource(magnet_uri="magnet:?xt=urn:btih:aaaa", dht_status="Unknown")
    asyncio.run(
        run_dht_health_scan(
            sample_size=10,
            timeout_s=1,
            checker_factory=lambda: (_ for _ in ()).throw(RuntimeError("no")),
        )
    )

    with session_scope() as session:
        state = session.get(BuildState, 1)
        assert state.pending_changes is False


def test_dht_scan_no_resources_is_noop(test_client):
    # Do not seed resources.
    asyncio.run(
        run_dht_health_scan(
            sample_size=10,
            timeout_s=1,
            checker_factory=lambda: (_ for _ in ()).throw(AssertionError()),
        )
    )
