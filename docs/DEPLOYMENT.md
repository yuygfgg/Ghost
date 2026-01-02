# Deployment & Operations

Ghost is designed to keep the **public surface purely static** while keeping management and automation private.

## Recommended deployment model

1. Run `ghost-server` on a small private host (VPS / home server).
2. Do **not** expose it directly to the public Internet:
   - Put it behind Cloudflare Tunnel, Tailscale, or another authenticated tunnel.
3. Host the public site output (`public/`) on:
   - GitHub Pages, Cloudflare Pages, or any static hosting/CDN.

Operational behavior (scheduler, DHT scanning, cover localization) is documented in `docs/OPERATIONS.md`.

## Deploy modes

### `GHOST_DEPLOY_MODE=standard` (recommended)

- Ghost builds the site into `GHOST_SITE_WORKDIR/public`.
- If a remote is configured, Ghost publishes `public/` to a Pages-friendly branch using `git`.
- The public site is served by your static host (Pages/CDN), not by `ghost-server`.

Configure publishing:

- `GHOST_PAGES_REMOTE_URL` (preferred) or `GHOST_SITE_REPO_URL`
- `GHOST_PAGES_BRANCH` (default `gh-pages`)
- `GHOST_PAGES_CNAME` (optional)
- `GHOST_PAGES_FORCE` (optional)
- `GHOST_PAGES_GIT_USER_NAME`, `GHOST_PAGES_GIT_USER_EMAIL`

### `GHOST_DEPLOY_MODE=integrated` (for local preview / small setups)

- Ghost serves `GHOST_SITE_WORKDIR/public/` directly from `/`.
- Useful for local development or simple single-host deployments.
- Pages publishing is skipped.

## Scheduling

See `docs/OPERATIONS.md` for scheduler details.

## Backups (age-encrypted)

Ghost can generate encrypted DB backups during builds (best-effort):

- Set `GHOST_AGE_RECIPIENT` (age public key)
- Ensure `age` is installed (or set `GHOST_AGE_BIN`)
- Backups are written to `GHOST_BACKUP_DIR` (default `var/backups`)

Restoring is supported by the helper in `packages/worker/build/backup.py` and requires an identity file:

- `GHOST_AGE_IDENTITY_FILE` (age identity file path)

## Cover localization

See `docs/OPERATIONS.md` for cover localization and related tuning knobs.
