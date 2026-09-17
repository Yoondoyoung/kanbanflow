# Kanban Flow — Slice 1

Engineering workflow tracker: accounts, projects, membership, tickets, a Kanban
board, chat notifications on ticket create/done, and a JSON sprint API. Built
with FastAPI, SQLModel, and SQLite. Velocity, AI reports, GitHub webhooks, and
the MCP server are **not** part of this slice — see "Out of scope" below.

## Prerequisites

- Docker and Docker Compose (for the one-command run), **or**
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) (for local development)

## Run locally (Docker)

```bash
cp .env.example .env          # then edit SESSION_SECRET, see below
docker compose up --build
```

Open <http://localhost:8000> in a browser. Register an account, create a
project, and add a ticket to the board.

## Web workspace

The dashboard lists every project you can access. Open a project to reach its
active sprint Board; if there is no active sprint, Kanban Flow opens its
planning sprint, then Backlog as a fallback. Project navigation includes:

- **Board** — four sprint columns, filters, compact cards, and ticket details.
- **Backlog** — unassigned tickets and the planning sprint.
- **Sprint History** — closed-sprint summaries and close-time ticket states.
- **Settings** — project details, webhook configuration, and membership.

Only project **OWNER**s can create, start, or close sprints. Members can view
sprint pages and work with tickets, but cannot run sprint lifecycle actions.

On small screens, the project sidebar becomes a menu drawer. Board columns
remain full-width and scroll horizontally instead of being compressed.

The SQLite database file lives at `./data/kanbanflow.db` on the host, bind-mounted
into the container at `/data`. Rebuilding or recreating the container does not
delete this directory, so data survives `docker compose up --build`.

### Generate a real `SESSION_SECRET`

`.env.example` ships a placeholder, not a usable default. Before running,
generate your own value and put it in `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Single worker, on purpose

The container always runs `uvicorn --workers 1`. SQLite allows exactly one
writer at a time; a second worker process reintroduces `database is locked`
errors under concurrent writes. Do not raise the worker count to improve
throughput — it will not, and it will break writes instead.

## Develop (without Docker)

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --workers 1
```

## Tests

```bash
uv run pytest                      # unit and integration tests
uv run pytest -m benchmark -s      # V-2 board-query latency benchmark (deselected by default)
uv run ruff check . && uv run ruff format --check .
```

The benchmark carries the `benchmark` marker and is excluded from the default
run (`addopts = "-m 'not benchmark'"` in `pyproject.toml`), so it must be
requested explicitly with `-m benchmark` as shown above.

## Chat notifications

In project settings, set `webhook_type` to `SLACK`, `DISCORD`, or `TEAMS` and
paste the channel's incoming-webhook URL (https only). Cards are sent when a
ticket is created and when one moves to `DONE`. Delivery runs in the
background: a failed webhook is logged as a `WARNING` and never reverses the
ticket change.

## Sprint API

Sprints are available through the JSON API. An `OWNER` creates a dated
`PLANNING` sprint, starts it with `PATCH /api/v1/sprints/{id}` and
`{"status": "ACTIVE"}`, then closes it with
`POST /api/v1/sprints/{id}/close` and a required `next_sprint_id` for an
existing `PLANNING` sprint. Closing snapshots the current sprint's tickets,
rolls unfinished tickets into that explicit next sprint, transitions the
current sprint to `CLOSED`, and leaves the next sprint in `PLANNING` until an
owner starts it.

The available commands are:

- `GET`/`POST /api/v1/projects/{slug}/sprints`
- `GET`/`PATCH /api/v1/sprints/{id}`
- `POST /api/v1/sprints/{id}/close`
- `GET /api/v1/sprints/{id}/history`

## MCP sprint tools

The local MCP server uses stdio and calls this application's API; it does not
open another network service. Start the web API first, then, while logged in,
issue a personal API token with `POST /api/v1/tokens` and a JSON body such as
`{"label":"local-mcp"}`. The response's `token` value is shown exactly once;
copy it into a local `.env.mcp` file (start from `.env.mcp.example`) and never
commit the plaintext token.

For session-cookie token issue or revoke JSON requests, an `Origin` header,
when present, must be same-origin or allowed by the middleware. MCP calls use
bearer authentication instead: an invalid bearer token returns `401` and never
falls back to a session cookie.

```dotenv
KANBANFLOW_BASE_URL=http://localhost:8000
KANBANFLOW_API_TOKEN=paste-the-token-shown-once
```

Configure your MCP client to launch the server as a stdio process, with those
two values in its environment:

```json
{
  "command": "uv",
  "args": ["run", "mcp", "run", "app/mcp_server.py:mcp", "--transport", "stdio"],
  "env": {
    "KANBANFLOW_BASE_URL": "http://localhost:8000",
    "KANBANFLOW_API_TOKEN": "paste-the-token-shown-once"
  }
}
```

Equivalently, after loading those variables in your shell, run:

```bash
uv run mcp run app/mcp_server.py:mcp --transport stdio
```

The tools list sprints available to the token's user and let project **OWNER**s
create, start, and close sprints. Revoke a lost or unused token with
`DELETE /api/v1/tokens/{token_id}`; deletion is idempotent and immediately
prevents further bearer-token use.

## Out of scope for this slice

AI reports, GitHub webhooks, and rate limiting are out of scope.

## Design documents

- `cs482_slice1_design.md` — the authoritative spec for this slice
- `cs482_slice1_plan.md` — the implementation plan
- `cs482_workflow.md`, `cs482_tool_review.md` — original product research and specification
