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
a.connect(nano)   # auth — always last
```

Each block exposes a `connect(app)` function that registers routes, seeds data, and wires up any middleware it needs. Blocks can share a database or borrow config from each other. They can also override routes registered by earlier blocks — first in line wins.

## What's included

**core** handles config and the base UI (navbar, theme switcher, page layouts). Everything else builds on it.

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

## Style

No ruff, no PEP 8. The code uses fastai idioms: `store_attr`, `patch`, `AttrDict`, `L`. Short functions, no docstrings unless the function name isn't enough. It reads fine on a phone.

## License

MIT
