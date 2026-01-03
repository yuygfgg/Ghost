# Operations

This document covers runtime behavior and operational tasks that are not strictly part of initial deployment (maintenance, background jobs, and tuning).

## Scheduling (APScheduler)

The server starts APScheduler automatically unless disabled:

- `GHOST_ENABLE_SCHEDULER=0` to disable scheduling (manual triggers only)
- `GHOST_BUILD_INTERVAL_MIN` controls build frequency
- `GHOST_DHT_SCAN_INTERVAL_HR` controls DHT scan frequency

Admins can also trigger a build via `POST /api/build/trigger`.

## DHT health scanning

Ghost can probe Magnet availability and store a status on each resource:

- `Active` / `Stale` / `Unknown`

Operational notes:

- The scanner is best-effort: if the checker backend is unavailable, resources are marked `Unknown`.
- `POST /api/admin/dht/scan-all` triggers a full scan (Admin only).
- The scheduled job samples resources (default size is configurable).
- DHT updates only mark a rebuild as pending when **statuses actually change** (not for timestamp-only updates).

Related env vars:

- `GHOST_DHT_SAMPLE_SIZE` (default `20`)
- `GHOST_DHT_TIMEOUT_S` (default `20`)

## Cover localization

If `resource.cover_image_url` is set, the build pipeline tries to download the image and store it under:

- `GHOST_SITE_WORKDIR/static/assets/covers/`

This is best-effort and non-fatal; failures are logged and the build continues.

Related env vars:

- `GHOST_COVER_FETCH_TIMEOUT_S` (default `15`)

## Magnet metadata probing

On resource creation (and when updating `magnet_uri`), Ghost can probe a Magnet to determine if it is reachable and to retrieve torrent metadata (total size + file list). This metadata is stored locally and is used to enrich:

- API responses (`/api/resources` and `/api/resources/{id}`)
- Public Hugo exports (resource pages + search index)

Operational notes:

- The probe retrieves metadata only; it does not intend to download content.
- The probe uses a temporary working directory and cleans it up after each probe.
- If the backend is unavailable (for example, `libtorrent` is not installed), resource creation/update will fail with `503`.

Related env vars:

- `GHOST_MAGNET_METADATA_BACKEND` (default `libtorrent`; `mock` available for tests/dev)
- `GHOST_MAGNET_METADATA_TIMEOUT_S` (default `25`)
- `GHOST_MAGNET_METADATA_DIR` (default `var/magnet-metadata`) stores JSON metadata per `magnet_hash`
- `GHOST_MAGNET_TMP_DIR` (default `var/magnet-tmp`) base directory for per-probe temp working dirs

## Additional environment variables

Common optional knobs (not all are listed in `.env.example`):

- `HOST`, `PORT`: server bind address/port (used by `serve.py`)
- `GHOST_HUGO_BIN`: Hugo binary path (default `hugo`)
- `GHOST_PUBLIC_BASEURL`: Hugo `baseURL` value for generated links
- `GHOST_BACKUP_DIR`: backup output directory (default `var/backups`)
- `GHOST_AGE_BIN`: `age` binary name/path (default `age`)
