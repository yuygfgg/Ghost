from packages.worker.site_repo import SiteRepo


def test_clean_export_dirs_removes_stale_taxonomy_content(tmp_path):
    repo = SiteRepo(tmp_path / "site")
    repo.ensure_base()

    # Seed stale taxonomy/section content that could override static pages in Hugo.
    stale_dirs = [
        repo.root / "content" / "categories",
        repo.root / "content" / "tags",
        repo.root / "content" / "category",
        repo.root / "content" / "tag",
    ]
    for d in stale_dirs:
        d.mkdir(parents=True, exist_ok=True)
        (d / "_index.md").write_text("stale", encoding="utf-8")

    repo.clean_export_dirs()

    for d in stale_dirs:
        assert d.exists()
        assert not (d / "_index.md").exists()
