# Ghost API

Base URL: all endpoints are mounted under `/api`.

- OpenAPI JSON: `/openapi.json`
- Swagger UI: `/docs`

## Authentication

All endpoints require:

```
Authorization: Bearer <token>
```

If the header is missing or invalid, the API returns `401`.
If the token is valid but the role is insufficient, the API returns `403`.

## Roles

- `Admin`
- `Publisher`
- `TeamMember` (scoped to exactly one team via `scope_team_id`)

## Common data types

- All timestamps are ISO 8601 strings (UTC).
- `tags` is a JSON array of strings.
- `dht_status` is one of: `Active`, `Stale`, `Unknown`.

## Endpoints

### Session

#### `POST /api/session/verify`

Validate the current token and return principal info.

Response (200):

```json
{
  "token_hash": "…",
  "role": "Admin",
  "display_name": "Admin",
  "scope_team_id": null
}
```

### Build

#### `GET /api/build/status`

Return current build state.

Response (200):

```json
{
  "pending_changes": false,
  "pending_reason": null,
  "last_build_at": "2026-01-01T00:00:00+00:00",
  "last_build_commit": "…",
  "last_error": null
}
```

#### `POST /api/build/trigger` (Admin)

Mark the build as pending, optionally providing a reason.

Query parameters:

- `reason` (optional): string

Response (200): same as `GET /api/build/status`.

### Resources

Resources are private-scoped by role:

- `Admin`: sees all non-takedown resources
- `Publisher`: sees only their own resources
- `TeamMember`: sees only resources in their team

#### `GET /api/resources`

List resources in the current principal’s scope.

Response (200): array of resource objects.

#### `GET /api/resources/{resource_id}`

Get a single resource (scope-checked).

Errors:

- `404` if not found
- `403` if outside scope

#### `POST /api/resources` (Publisher / TeamMember / Admin)

Create a resource. `magnet_uri` must be a valid Magnet URL; the server extracts and stores `magnet_hash`.

Body:

```json
{
  "title": "Example",
  "magnet_uri": "magnet:?xt=urn:btih:…",
  "content_markdown": "…",
  "cover_image_url": "https://example.com/cover.png",
  "tags": ["tag1", "tag2"],
  "category_id": 1,
  "team_id": null,
  "published_at": "2026-01-01T00:00:00+00:00"
}
```

Notes:

- For `TeamMember`, `team_id` is forced to the token’s `scope_team_id` and mismatches are rejected.
- For `Publisher`, a non-null `team_id` must refer to a team they own.
- For `Admin`, a non-null `team_id` must exist.

Response (201): the created resource.

#### `PUT /api/resources/{resource_id}`

Update a resource (scope-checked).

Body: any subset of fields from create (all optional).

Response (200): updated resource.

#### `POST /api/resources/{resource_id}/takedown` (Admin)

Soft-remove a resource from public exports by setting `takedown_at`.

Response (200): updated resource.

### Categories

Categories form a tree. Each category stores:

- `root_id`: the id of the root node of its tree
- `parent_id`: null for roots
- `sort_order`: sibling ordering

#### `GET /api/categories/tree`

Return all categories (flat list) ordered for tree rendering.

Response (200): array of categories.

#### `POST /api/categories` (Publisher / Admin)

Create a category.

Body:

```json
{ "name": "Movies", "slug": "movies", "parent_id": null, "sort_order": 0 }
```

Response (201): created category.

#### `PUT /api/categories/{category_id}` (Publisher / Admin)

Update a category (including optional move by `parent_id`).

Response (200): updated category.

#### `DELETE /api/categories/{category_id}` (Publisher / Admin)

Delete a category.

Constraints:

- cannot delete if it has child categories
- cannot delete if any resource references it

Response: `204 No Content`.

### Teams

#### `GET /api/teams`

List teams in the current scope.

- `Admin`: all teams
- `Publisher`: teams owned by this publisher
- `TeamMember`: only the scoped team (if any)

#### `POST /api/teams` (Publisher)

Create a team.

Body:

```json
{ "name": "Team A" }
```

Response (201): created team.

#### `POST /api/teams/{team_id}/invites` (Publisher)

Create a TeamMember invite token for a team (owner-only).

Response (200):

```json
{
  "token": "raw-token-to-share",
  "token_hash": "…",
  "role": "TeamMember",
  "scope_team_id": 123
}
```

### Admin (system)

#### `POST /api/admin/tokens/publisher` (Admin)

Issue a new Publisher token.

Body:

```json
{ "display_name": "Publisher" }
```

Response (200): `InviteResponse` (includes the raw token).

#### `POST /api/admin/tokens/revoke` (Admin)

Revoke a token by raw token value.

Body:

```json
{ "token": "raw-token" }
```

Response (200):

```json
{ "token_hash": "…", "revoked_at": "2026-01-01T00:00:00+00:00" }
```

#### `POST /api/admin/dht/scan-all` (Admin)

Trigger a full DHT scan over all non-takedown resources.

Query parameters:

- `wait` (default `false`): if true, waits and returns `changed`
- `timeout_s` (optional): per-magnet timeout (seconds)

Response (200):

```json
{ "queued": true }
```

When `wait=true`:

```json
{ "queued": false, "changed": 0 }
```
