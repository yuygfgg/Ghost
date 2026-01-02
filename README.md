# Ghost

Ghost is a **zero-footprint, resilient publishing system** for indexing Magnet links. It separates a private management plane (API + admin console) from a public distribution plane (a **pure static site** generated with Hugo), so the public site can be hosted anywhere (GitHub Pages / Cloudflare Pages / CDN) without exposing secrets.

## What you get

- **Private management API** (FastAPI) secured by bearer tokens (no username/password accounts).
- **Built-in admin console** (`/admin`) rendered with Jinja2 + HTMX.
- **Static public site generation** (Hugo) from database content.
- **Sharded client search index** (`static/index/manifest.json` + `index-YYYY-MM.json`) for low memory usage.
- **Cover image localization** (best-effort) to keep public pages working even when external image hosts disappear.
- **DHT health scanning** (best-effort) to label Magnet availability (`Active` / `Stale` / `Unknown`).
- **Encrypted DB backups** using `age` (best-effort).

## Architecture (high level)

- **ghost-server** (this repo): a single Python process that runs:
  - FastAPI under `/api/*`
  - Admin console under `/admin/*`
  - Background jobs via APScheduler (build pipeline + DHT scan)
- **Public site workdir** (`GHOST_SITE_WORKDIR`): a Hugo project directory that Ghost writes into and builds to `public/`.
  - In **standard** mode Ghost can publish the built `public/` directory to a Pages branch using `git`.
  - In **integrated** mode Ghost can serve `public/` directly from `/` (useful for local preview).

## Quick start (local)

### Configure environment

1. Copy `.env.example` to `.env` and edit values as needed.
2. Start the server:

```bash
python serve.py
```

### URLs

- API docs (OpenAPI/Swagger): `http://localhost:8000/docs`
- Admin console: `http://localhost:8000/admin`
- API base: `http://localhost:8000/api`

On first startup, if no Admin token exists, the server auto-generates one and logs it to stdout.

## Authentication model (tokens)

All API endpoints require `Authorization: Bearer <token>`.

Roles:

- **Admin**: system operator; can trigger builds, create Publisher tokens, revoke tokens, run full DHT scans.
- **Publisher**: can manage their own resources; can create Teams and Team invites.
- **TeamMember**: scoped to one Team; can only operate within that Team.

The database stores only a **hash** of each token (never the raw token).

## Key workflows

### Publish content

1. Admin creates a Publisher token via `POST /api/admin/tokens/publisher`.
2. Publisher creates categories, then creates resources (`POST /api/resources`).
3. Changes mark the build state as pending; the scheduler (or Admin) triggers a build.

### Build & publish the public site

- Build pipeline exports content into the Hugo workdir, generates search indices, runs `hugo`, optionally creates an `age` backup, and (in `standard` mode) can publish to a Pages branch.
- Configure with env vars in `.env.example`. See `docs/DEPLOYMENT.md` for deployment patterns.

## Documentation

- API reference: `docs/API.md`
- Database reference: `docs/DATABASE.md`
- Deployment & operations: `docs/DEPLOYMENT.md`
- Operations (scheduler, DHT scanning, cover localization): `docs/OPERATIONS.md`
