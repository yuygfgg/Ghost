from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from packages.db import BuildState, ensure_build_state, session_scope
from packages.worker.build.export_content import export_content
from packages.worker.build.export_index import export_search_index
from packages.worker.build.hugo import ensure_hugo_scaffold, run_hugo_build
from packages.worker.build.pages import PagesDeployConfig, deploy_public_dir_to_pages
from packages.worker.build.backup import create_age_encrypted_db_backup
from packages.worker.build.covers import localize_cover_images
from packages.worker.site_repo import SiteRepo

logger = logging.getLogger(__name__)


@dataclass
class BuildConfig:
    site_workdir: str
    hugo_bin: str
    base_url: str
    deploy_mode: str
    pages_remote_url: str | None
    pages_branch: str
    pages_cname: str | None
    pages_force: bool
    pages_git_user_name: str
    pages_git_user_email: str


def load_build_config() -> BuildConfig:
    deploy_mode = os.getenv("GHOST_DEPLOY_MODE", "standard")
    pages_remote_url = (
        os.getenv("GHOST_PAGES_REMOTE_URL") or os.getenv("GHOST_SITE_REPO_URL") or None
    )

    return BuildConfig(
        site_workdir=os.getenv("GHOST_SITE_WORKDIR", "var/site-workdir"),
        hugo_bin=os.getenv("GHOST_HUGO_BIN", "hugo"),
        base_url=os.getenv("GHOST_PUBLIC_BASEURL", "/"),
        deploy_mode=deploy_mode,
        pages_remote_url=pages_remote_url,
        pages_branch=os.getenv("GHOST_PAGES_BRANCH", "gh-pages"),
        pages_cname=os.getenv("GHOST_PAGES_CNAME") or None,
        pages_force=os.getenv("GHOST_PAGES_FORCE", "0")
        in {"1", "true", "TRUE", "yes", "YES"},
        pages_git_user_name=os.getenv("GHOST_PAGES_GIT_USER_NAME", "ghost-bot"),
        pages_git_user_email=os.getenv(
            "GHOST_PAGES_GIT_USER_EMAIL", "ghost-bot@users.noreply.github.com"
        ),
    )


def _should_build(session: Session, force: bool) -> BuildState | None:
    state = ensure_build_state(session)
    if force:
        return state
    if not state.pending_changes:
        logger.info("No pending changes, skipping build.")
        return None
    return state


def run_build_pipeline(force: bool = False, config: BuildConfig | None = None) -> None:
    """Main entry for the background build job."""
    config = config or load_build_config()

    with session_scope() as session:
        state = _should_build(session, force)
        if state is None:
            return
        repo = SiteRepo(config.site_workdir)
        ensure_hugo_scaffold(repo, base_url=config.base_url)
        try:
            localized = localize_cover_images(session, repo)
            if localized:
                logger.info("Localized %s cover image(s)", localized)
            public_resources = export_content(session, repo)
            export_search_index(public_resources, repo)
            run_hugo_build(repo, hugo_bin=config.hugo_bin)
            create_age_encrypted_db_backup()
            pages_commit = None
            if config.deploy_mode == "standard":
                if not config.pages_remote_url:
                    logger.info(
                        "Deploy mode is standard but no Pages remote configured; skipping push. "
                        "Set GHOST_PAGES_REMOTE_URL or GHOST_SITE_REPO_URL to enable publishing."
                    )
                else:
                    pages_commit = deploy_public_dir_to_pages(
                        public_dir=repo.public_dir,
                        workdir=repo.root,
                        config=PagesDeployConfig(
                            remote_url=config.pages_remote_url,
                            branch=config.pages_branch,
                            cname=config.pages_cname,
                            force=config.pages_force,
                            git_user_name=config.pages_git_user_name,
                            git_user_email=config.pages_git_user_email,
                        ),
                    )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Build pipeline failed")
            state.last_error = str(exc)
            state.last_build_at = None
            session.add(state)
            session.commit()
            raise
        else:
            state.pending_changes = False
            state.pending_reason = None
            state.last_error = None
            state.last_build_at = datetime.now(timezone.utc)
            if pages_commit:
                state.last_build_commit = pages_commit
            session.add(state)
            session.commit()


__all__ = ["run_build_pipeline", "load_build_config", "BuildConfig"]


if __name__ == "__main__":  # pragma: no cover - manual entry
    logging.basicConfig(level=logging.INFO)
    run_build_pipeline(force=True)
