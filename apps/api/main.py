import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from apps import admin_web
from apps.api.routers import admin, build, categories, resources, session, teams
from packages.core.auth import Role, hash_token
from packages.db import Auth, create_all, engine, ensure_build_state, session_scope
from packages.worker.build import run_build_pipeline
from packages.worker.dht import run_dht_health_scan

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all(engine)
    with session_scope() as db:
        ensure_build_state(db)
    ensure_admin_token()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="Ghost API", lifespan=lifespan)


app.include_router(session.router, prefix="/api")
app.include_router(build.router, prefix="/api")
app.include_router(resources.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(teams.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(admin_web.router)
app.mount(
    "/admin/static", StaticFiles(directory=admin_web.STATIC_DIR), name="admin-static"
)


# Integrated deployment can optionally mount the generated static site.
def maybe_mount_public_site(app: FastAPI) -> bool:
    deploy_mode = os.getenv("GHOST_DEPLOY_MODE", "standard").lower()
    public_dir = Path(os.getenv("GHOST_SITE_WORKDIR", "var/site-workdir")) / "public"
    should_mount = deploy_mode == "integrated"
    if not should_mount:
        return False
    if not public_dir.exists():
        logger.warning("Integrated mode enabled but public dir missing: %s", public_dir)
        return False
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="ghost-public")
    logger.info("Mounted public site at / from %s", public_dir)
    return True


public_mounted = maybe_mount_public_site(app)

# Provide a tiny landing page only when public site is not mounted.
if not public_mounted:

    @app.get("/", tags=["meta"])
    async def root():
        return JSONResponse(
            {
                "app": "ghost",
                "status": "ok",
                "api_base": "/api",
                "docs": "/docs",
                "message": "Ghost server running. Use /docs for API docs or /api for endpoints.",
            }
        )


def start_scheduler() -> None:
    if os.getenv("GHOST_ENABLE_SCHEDULER", "1") == "0":
        logger.info("APScheduler disabled via env")
        return
    interval = int(os.getenv("GHOST_BUILD_INTERVAL_MIN", "60"))
    if scheduler.get_job("build"):
        scheduler.remove_job("build")
    scheduler.add_job(
        run_build_pipeline, "interval", minutes=interval, id="build", next_run_time=None
    )

    dht_interval_hr = int(os.getenv("GHOST_DHT_SCAN_INTERVAL_HR", "24"))
    if scheduler.get_job("dht-scan"):
        scheduler.remove_job("dht-scan")
    scheduler.add_job(
        run_dht_health_scan,
        "interval",
        hours=dht_interval_hr,
        id="dht-scan",
        next_run_time=None,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info(
        "APScheduler started, build interval=%s minutes, dht scan interval=%s hours",
        interval,
        dht_interval_hr,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def ensure_admin_token() -> None:
    """Auto-create an Admin token if none exists and log it to console."""
    with session_scope() as session:
        has_admin = (
            session.query(Auth)
            .filter(Auth.role == Role.ADMIN.value, Auth.revoked_at.is_(None))
            .first()
            is not None
        )
        if has_admin:
            return
        raw = secrets.token_urlsafe(24)
        admin = Auth(
            token_hash=hash_token(raw),
            role=Role.ADMIN.value,
            display_name="Admin",
            created_at=datetime.now(timezone.utc),
        )
        session.add(admin)
        session.commit()
        logger.warning("No admin token found; generated new Admin token: %s", raw)
