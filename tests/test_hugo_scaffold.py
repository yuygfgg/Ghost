import re

from packages.worker.build.hugo import ensure_hugo_scaffold
from packages.worker.site_repo import SiteRepo


def _has_go_date_format(template: str, expected_format: str) -> bool:
    # Match `.Date.Format "..."` or `.Date.Format `...`` with arbitrary whitespace.
    pattern = re.compile(
        r"""\.Date\.Format\s+(?:(?:"([^"]*)")|(?:`([^`]*)`))""", re.MULTILINE
    )
    for match in pattern.finditer(template):
        value = match.group(1) or match.group(2) or ""
        if value.strip() == expected_format:
            return True
    return False


def test_homepage_relative_time_datetime_is_parseable(tmp_path):
    repo = SiteRepo(tmp_path / "site")
    ensure_hugo_scaffold(repo)
    list_template = (repo.layouts_dir / "_default" / "list.html").read_text(
        encoding="utf-8"
    )
    assert 'class="relative-time"' in list_template
    assert _has_go_date_format(list_template, "2006-01-02T15:04:05Z07:00")


def test_detail_page_uses_local_datetime_rendering(tmp_path):
    repo = SiteRepo(tmp_path / "site")
    ensure_hugo_scaffold(repo)
    template = (repo.layouts_dir / "_default" / "single.html").read_text(
        encoding="utf-8"
    )
    assert 'class="local-datetime"' in template
    assert _has_go_date_format(template, "2006-01-02T15:04:05Z07:00")

    relative_time_js = (repo.static_dir / "js" / "relative-time.js").read_text(
        encoding="utf-8"
    )
    assert 'Intl.DateTimeFormat("sv-SE"' in relative_time_js
    assert "raw.trim()" in relative_time_js
