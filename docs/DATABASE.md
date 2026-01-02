# Ghost Database (SQLite)

Ghost uses SQLite via SQLAlchemy. By default the DB file is `var/db/ghost.db` (see `GHOST_DB_PATH`).

## Tables

### `auth`

Token storage and identity. **Only hashed tokens are stored** (`token_hash`); raw tokens never persist.

Columns:

- `token_hash` (PK, indexed): hashed token used for lookup
- `role`: `Admin` / `Publisher` / `TeamMember`
- `scope_team_id` (FK → `team.id`, nullable): required for `TeamMember`
- `display_name`: used in public exports as publisher name
- `created_at`
- `revoked_at` (nullable): when set, the token is invalid

### `team`

Teams allow multiple scoped publishers (TeamMembers) to publish under a shared scope.

Columns:

- `id` (PK)
- `name`
- `owner_token_hash` (FK → `auth.token_hash`): the Publisher that owns the team
- `created_at`

Relationships:

- `team.members` ↔ `auth.scope_team_id`
- `team.resources` ↔ `resource.team_id`

### `category`

Tree-structured categories. Each resource belongs to exactly one category.

Columns:

- `id` (PK)
- `root_id`: root node id for the tree (root’s `root_id == id`)
- `parent_id` (FK → `category.id`, nullable)
- `name`
- `slug`
- `sort_order` (default `0`)
- `created_at`
- `updated_at`

Note: `updated_at` is application-managed (it is not automatically updated by SQLite triggers). For `resource`, Ghost updates it automatically on update; for `category`, it is currently only set on insert unless the application updates it.

### `resource`

The core content record (Magnet index entry).

Constraints:

- `magnet_hash` is unique (`uq_resource_magnet_hash`)

Columns:

- `id` (PK)
- `title`
- `magnet_uri`
- `magnet_hash` (unique): extracted from `magnet_uri`
- `content_markdown`
- `cover_image_url` (nullable): private upstream URL (used only to fetch a cover)
- `cover_image_path` (nullable): relative path inside the public site workdir (e.g. `assets/covers/123.webp`)
- `tags_json`: JSON array string (default `[]`)
- `category_id` (FK → `category.id`)
- `publisher_token_hash` (FK → `auth.token_hash`)
- `team_id` (FK → `team.id`, nullable)
- `dht_status` (default `Unknown`)
- `last_dht_check` (nullable)
- `created_at`
- `updated_at` (auto-updated on update by the application)
- `published_at`
- `takedown_at` (nullable): when set, excluded from public exports

Privacy note:

- Public exports intentionally omit `cover_image_url` (only `cover_image_path` is used publicly).

### `build_state`

Singleton build state row used by the scheduler and build pipeline.

Invariant:

- The singleton row has `id = 1` and is created automatically.

Columns:

- `id` (PK)
- `pending_changes` (bool): whether a build should run
- `pending_reason` (nullable text)
- `last_build_at` (nullable datetime)
- `last_build_commit` (nullable text): Pages deploy commit SHA (when applicable)
- `last_error` (nullable text)

## Operational semantics

- Any write that affects public content sets `build_state.pending_changes = true`.
- The build pipeline clears the pending flag on success and records `last_build_at` (and optionally `last_build_commit`).
- DHT scans update `resource.dht_status` and set pending only when statuses change (not for timestamp-only updates).
