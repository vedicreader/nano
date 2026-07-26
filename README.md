# nano

A FastHTML + Oat web app starter for serverless deployments. Powers [vedicreader.com](https://vedicreader.com/).

Clone it, connect your blocks, ship it.

## Getting started

```bash
git clone https://github.com/Karthik777/nano.git
cd nano
uv sync
uv run nano-setup       # link Vercel, scaffold .env.example, install skills
uv run python main.py   # http://localhost:5001
```

`nano-setup` is idempotent and safe to re-run. The console scripts shipped with the package:

| script | purpose |
|---|---|
| `uv run nano-setup` | link Vercel, scaffold `.env.example`, install `SKILL.md` skills |
| `uv run nano-skill` | (re)install `SKILL.md` into `.claude/skills/nano/` and `.agents/skills/nano/` |
| `uv run nano-push` | push `.env` values to the Vercel project (production + preview); `--dry-run` to preview |

## How it works

Each feature is a block: a self-contained module with its own config, routes, and database. You connect blocks to the app in order. Auth reads the full skip list at connect time, so it goes last.

```python
# nano/app.py
b.connect(nano)   # blog
d.connect(nano)   # dashboards
a.connect(nano)   # auth — always last
```

Each block exposes a `connect(app)` function that registers routes, seeds data, and wires up any middleware it needs. Blocks can share a database or borrow config from each other. They can also override routes registered by earlier blocks — first in line wins.

The folder is the unit of reuse. A block owns its routes, its data, and its assets: CSS and JS live in the block and load only on that block's pages, via `asset_css()` / `asset_js()`. No block imports another — `nano.core` is the only shared dependency, and it owns design tokens rather than any block's components. Copying a block folder into another nano app and adding one `connect()` line is meant to be the whole job.

## What's included

**core** handles config and the base UI (navbar, theme switcher, page layouts). Everything else builds on it.

**auth** covers email/password registration with Resend verification, Google OAuth, and GitHub OAuth. One `connect()` call sets up all routes and session middleware. Route paths are overridable via `RouteOverrides`.

**dash** turns a database into a dashboard without being told what's in it. It reflects the schema, profiles every column, works out which ones are dates, measures, categories or foreign keys, and picks the charts that fit — revenue over time, top-N by category, share-of-total doughnuts, histograms with mean and σ. It also ships a table explorer with per-column profiles and a row view that lazily unfolds nested foreign-key relations. The Chinook sample database is seeded on first use.

Routes live under `/dash` and are behind auth by default; set `DASH_PUBLIC=true` to open them up. Only databases listed in `nano/dash/data.py`'s `DBS` registry are reachable, and only through the tables their own seed dump defines. That second half matters in production: a Turso URL carries no path, so every block's `database(...)` call lands on one remote database and the dash block would otherwise see — and serve — the auth and blog tables. Seeding is resumable and safe to run concurrently, so a cold start cut short part-way through the dump is picked up by the next request.

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
│   ├── dash/            # dashboards block
│   └── core/            # config, UI
├── data/
│   └── db/              # SQLite databases
└── static/
```

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

nano deploys through Vercel's native Git integration — push to `main` and Vercel builds.

1. Connect the GitHub repo to a Vercel project.
2. Attach Turso via the Vercel marketplace integration (provides `TURSO_DATABASE_URL` and `TURSO_DATABASE_TURSO_AUTH_TOKEN`).
3. `uv run nano-push` loads your `.env` into the Vercel project (production + preview). It leaves the Turso vars alone when an instance is already attached.
4. Push to `main` to deploy.

Local dev uses a SQLite file under `data/db/`; production persistence is Turso.

### One Turso database per block

A libsql URL has no path component. `sqlite+libsql://host?secure=true` addresses *the* database, so passing different paths to `database()` does nothing in production — locally `auth.db`, `blog.db` and `dash.db` are three files, and on Turso they are one database with everyone's tables in it.

Each logical database is therefore named, and looks for its own pair before falling back:

| variable | database |
|---|---|
| `TURSO_AUTH_URL` · `TURSO_AUTH_AUTH_TOKEN` | auth |
| `TURSO_BLOG_URL` · `TURSO_BLOG_AUTH_TOKEN` | blog |
| `TURSO_DASH_URL` · `TURSO_DASH_AUTH_TOKEN` | dash's profile cache |
| `TURSO_CHINOOK_URL` · `TURSO_CHINOOK_AUTH_TOKEN` | the Chinook sample data — set these, see below |
| `TURSO_DATABASE_URL` · `TURSO_DATABASE_TURSO_AUTH_TOKEN` | the default for any of the above with no pair of its own |

`TURSO_<NAME>_DATABASE_URL` and `TURSO_<NAME>_DATABASE_TURSO_AUTH_TOKEN` also work, matching what the Vercel integration names things when you attach a second instance. Setting a URL without its token is an error rather than a silent fall back to the shared credentials, which would authenticate against the wrong database.

Nothing needs splitting for the app's own data — auth, blog and dash have distinct table names and sharing one database is a fine deployment. It is logged at startup so it is a choice rather than a surprise. What must never share is a database the dash block *reflects*: it reports whatever tables it finds, so a shared store would put `users` in the explorer. Those are opened with `own=True`, which takes the named pair or a local file and never the shared default.

Give Chinook its own Turso database and the dump is written once, ever: the first request fills it, and every cold start after that finds it populated and just loads it. Without `TURSO_CHINOOK_URL` it still works — it falls back to a local file and logs a warning — but that file is per-instance and re-seeds on every cold start.

## Style

No ruff, no PEP 8. The code uses fastai idioms: `store_attr`, `patch`, `AttrDict`, `L`. Short functions, no docstrings unless the function name isn't enough. It reads fine on a phone.

## License

MIT
