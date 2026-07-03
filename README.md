# nano

A FastHTML + MonsterUI web app starter for serverless deployments. Powers [vedicreader.com](https://vedicreader.com/).

Runs on Vercel's Python runtime with [Turso](https://turso.tech) (libSQL) as the database — no file IO at runtime, so it fits a read-only serverless filesystem. Locally it falls back to plain SQLite files, zero setup. The data layer is [fastsql](https://github.com/AnswerDotAI/fastsql) (same MiniDataAPI surface as fastlite) over the [sqlalchemy-libsql](https://github.com/tursodatabase/sqlalchemy-libsql) dialect.

Clone it, connect your blocks, ship it.

## Getting started

```bash
git clone https://github.com/Karthik777/nano.git
cd nano
uv sync
uv run nano-setup       # scaffold .env.example, .github workflow, and SKILL.md files
uv run python main.py   # http://localhost:5001
```

`nano-setup` is idempotent and safe to re-run. The console scripts shipped with the package:

| script | purpose                                                                               |
|---|---------------------------------------------------------------------------------------|
| `uv run nano-setup` | init gheasy config, git-lfs patterns, `.env.example`, deploy workflow, install skills |
| `uv run nano-skill` | (re)install `SKILL.md` into `.claude/skills/nano/` and `.agents/skills/nano/`         |
| `uv run nano-push` | push values from `.env` to GitHub Actions secrets/vars (use `--dry-run` to preview)   |
| `uv run nano-deploy` | vercel + turso deploy (`compose` \| `deploy` \| `turso` \| `seed` \| `env` \| `nuke`) |

## How it works

Each feature is a block: a self-contained module with its own config, routes, and database. You connect blocks to the app in order. Auth reads the full skip list at connect time, so it goes last.

```python
# nano/app.py
b.connect(nano)   # blog
a.connect(nano)   # auth — always last
```

Each block exposes a `connect(app)` function that registers routes, seeds data, and wires up any middleware it needs. Blocks can share a database or borrow config from each other. They can also override routes registered by earlier blocks — first in line wins.

## What's included

**core** handles config, the database factory (Turso in prod, SQLite in dev), and the base UI (navbar, theme switcher, page layouts). Everything else builds on it.

**auth** covers email/password registration with Resend verification, Google OAuth, and GitHub OAuth. One `connect()` call sets up all routes and session middleware. Route paths are overridable via `RouteOverrides`.

**blog** is a full publishing block. Posts are seeded from Markdown files with YAML frontmatter. The list page uses a newspaper-style featured/sidebar/grid layout. Post detail pages support single-column or two-column newspaper layout, set per-post via `layout: newspaper` in the frontmatter. Code blocks never split across columns. To force a column break at a specific point in a post, add:

````md
```col
```
````

## Project structure

```
nano/
├── main.py
├── nano/
│   ├── app.py           # wire up blocks, scheduled jobs
│   ├── auth/            # auth block
│   ├── blog/            # blog block
│   └── core/            # config, cache, logging, backups, UI
├── data/
│   └── db/              # local SQLite databases (dev only; prod uses Turso)
└── static/
```

## Database

Each block gets its own database via `nano.core.get_db(name)`:

- **dev** (no `TURSO_URL_*` env): a local SQLite file at `data/db/{name}.db`
- **prod**: Turso over libsql, from `TURSO_URL_{NAME}` (e.g. `TURSO_URL_AUTH=sqlite+libsql://nano-auth-org.turso.io?secure=true`) plus `TURSO_AUTH_TOKEN`

`nano-deploy deploy` creates the Turso group, one database per block, and an auth token, and writes these values to `.env` for you. Set `JWT_SCRT` explicitly in production — without it every cold start mints a new secret and invalidates all sessions.

## Auth setup

Email/password:
```
RESEND_API_KEY=re_...
```

Google OAuth:
```
WANT_GOOGLE=true
GOOGLE_CLI=...
GOOGLE_SCRT=...
# callback: {DOMAIN}/a/google/callback
```

GitHub OAuth:
```
WANT_GIT=true
GIT_CLI=...
GIT_SCRT=...
# callback: {DOMAIN}/a/github/callback
```

Google and GitHub users are activated immediately. Email/password users get a verification link via Resend.

To change the default route paths:

```python
from nano.core import RouteOverrides
RouteOverrides.lgn = "/login"
RouteOverrides.home = "/dashboard"
RouteOverrides.skip += ["/public"]
```

## Extensions

The dev toolchain that ships with nano:

- **[kosha](https://github.com/vedicreader/kosha)** — indexes your repo and installed packages into a hybrid search + call graph database. Agents query it before writing code.
- **[fossick](https://github.com/vedicreader/fossick)** — get structured information from the web

## Deployment

nano is an ASGI app; `main.py` exports `app`, which Vercel's Python runtime serves directly. `deploy.py` uses the [Vercel Python SDK](https://pypi.org/project/vercel/) and the [Turso Platform API](https://docs.turso.tech/api-reference/introduction) for a full serverless deploy:

```bash
uv run nano-deploy deploy    # turso group/DBs/token, seed posts, vercel project/env/deploy
uv run nano-deploy compose   # generate vercel.json only
uv run nano-deploy turso     # provision turso resources and write conn strings to .env
uv run nano-deploy seed      # seed blog posts into turso (runs per deploy, not per cold start)
uv run nano-deploy nuke      # delete vercel project and turso DBs (irreversible)
uv run nano-push             # push .env values to GitHub Actions
```

Credentials it needs in `.env` (scaffolded by `nano-setup`): `VERCEL_TOKEN`, `TURSO_API_TOKEN`, `TURSO_ORG`, plus the app secrets. `nano-deploy deploy` is idempotent: it ensures the Turso group and per-block databases exist, mints a group auth token, seeds the blog, upserts the app env vars on the Vercel project (deploy-side credentials are never pushed to the runtime), uploads the files, and creates a production deployment. Pushing to `main` runs the same thing via `.github/workflows/deploy.yml`.

The app runs at [nano.sankalpa.sh](https://nano.sankalpa.sh)

## Style

No ruff, no PEP 8. The code uses fastai idioms: `store_attr`, `patch`, `AttrDict`, `L`. Short functions, no docstrings unless the function name isn't enough. It reads fine on a phone.

## License

MIT
