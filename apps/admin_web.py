from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# Template and static asset locations are kept in the data-only admin-web folder.
ADMIN_WEB_ROOT = Path(__file__).resolve().parent / "admin-web"
TEMPLATES_DIR = ADMIN_WEB_ROOT / "templates"
STATIC_DIR = ADMIN_WEB_ROOT / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/admin", tags=["admin-web"], include_in_schema=False)


@router.get("", response_class=RedirectResponse)
async def admin_root() -> RedirectResponse:
    return RedirectResponse(url="/admin/dashboard")


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "login.html", {"request": request, "page": "login", "title": "登录"}
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "page": "dashboard", "title": "仪表盘"}
    )


@router.get("/resources", response_class=HTMLResponse)
async def resources(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "resources.html", {"request": request, "page": "resources", "title": "资源管理"}
    )


@router.get("/categories", response_class=HTMLResponse)
async def categories(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "categories.html",
        {"request": request, "page": "categories", "title": "分类管理"},
    )


@router.get("/teams", response_class=HTMLResponse)
async def teams(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "teams.html", {"request": request, "page": "teams", "title": "团队与邀请"}
    )


@router.get("/system", response_class=HTMLResponse)
async def system(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "system.html", {"request": request, "page": "system", "title": "系统管理"}
    )
