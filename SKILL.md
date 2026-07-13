---
name: nano
description: >
  Build serverless FastHTML + MonsterUI webapps on Vercel with Turso persistence and a full
  auth system. Each feature is a block: a folder with cfg/data/ui/app and a connect(app) function.
---

# nano

nano is a FastHTML + MonsterUI webapp template built for serverless deployment on Vercel. Features are organised as blocks — self-contained folders, each exporting a `connect(app)` function that registers routes. Blocks are wired in `nano/app.py`; auth always connects last so it can read the accumulated `RouteOverrides.skip` list. Persistence is Turso (libsql); local dev falls back to SQLite.

## CLI entrypoints

| command | purpose |
|---|---|
| `uv run python main.py` | start dev server (live reload) |
| `uv run nano-setup` | link Vercel project, write `.env.example`, install SKILL.md into `.claude/` and `.agents/` |
| `uv run nano-skill` | (re)copy SKILL.md into `.claude/skills/nano/` and `.agents/skills/nano/` |

`SKILL.md` at the repo root is the canonical source. The copies under `.claude/skills/nano/` and `.agents/skills/nano/` are generated — edit the root file, then run `nano-skill` to propagate.

## Block pattern

Each block folder exposes a `connect(app)` function. Inside it: extend the auth skip list, then register routes.

```python
# my_block/app.py
from nano.core import RouteOverrides
from .cfg import Routes

def connect(app):
    RouteOverrides.skip += Routes.skip   # keep auth out of these paths
    app.get(Routes.index)(index_handler)
    app.post(Routes.action)(action_handler)
```

Connect order in `nano/app.py` — earlier blocks win on overlapping routes; auth must be last:

```python
b.connect(nano)   # blog (or any other block)
a.connect(nano)   # auth last — reads the complete RouteOverrides.skip list
```

## Core imports

```python
from nano.core import (
    # config & db
    cfg, database, AppErr,
    # routing helpers
    home, RouteOverrides,
    # paths
    get_pth, get_db_pth, in_static, get_db_dir,
    # predicates
    not_prod, slug,
    # email
    send_email,
    # ui layouts
    base, landing, welcome, welcome_page, not_found,
    # ui components
    navbar, theme_switcher, mode_switcher, logout, placeholder,
    svg_img, montage, typewriter, email_template, main,
    themes, github_star,
    Badge, BadgeT, BadgePresetsT, PresetsT,
    # utils
    init_js_then_use, get_usr_ini, loadX, clean_dev, rm_special, arun,
)
```

## Config

`cfg` is an `AttrDictDefault` populated from environment variables. Access keys as attributes.

| env var | cfg key | default | notes |
|---|---|---|---|
| `APP_NAME` | `app_nm` | `Nano` | |
| `APP_SH` | `app_sh` | `nano` | short name for navbar |
| `SITE_AUTHOR` | `site_author` | `Karthik Rajgopal` | |
| `SITE_DESCRIPTION` | `site_description` | `Build performant webapps one block at a time` | |
| `SITE_KEYWORDS` | `site_keywords` | `nano, fastHTML, MonsterUI, webapp, python` | |
| `MODE` | `mode` | `dev` | set to `production` in prod |
| `DOMAIN` | `domain` | `http://localhost:5001` | full URL; auto-prefixed with `https://` if no scheme |
| `PORT` | `port` | `5001` | int |
| `TOKEN_EXP` | `tkn_exp` | `691200` | seconds (8 days) |
| `JWT_SCRT` | `jwt_scrt` | random on startup | set explicitly in production |
| `RESEND_API_KEY` | `resend_api_key` | `''` | required for email |
| `TURSO_DATABASE_URL` | `turso_url` | `''` | libsql URL |
| `TURSO_DATABASE_TURSO_AUTH_TOKEN` | `turso_token` | `''` | auth token |
| `TURSO_SYNC` | `turso_sync` | `0` | `1` = embedded replica mode |
| `GITHUB_REPO` | `github_repo` | `vedicreader/nano` | shown as star count in navbar |

`not_prod()` returns `True` when `cfg.mode != 'production'`. Use it to gate dev-only behaviour (e.g. live reload).

## Database (Turso)

`database(path)` returns a `fastsql.Database`:

- **Dev** (no Turso env vars): local SQLite file at `path`.
- **Prod, `TURSO_SYNC=0`** (default): remote Turso connection — no local file.
- **Prod, `TURSO_SYNC=1`**: embedded replica — syncs the remote into a local file at `path` for low-latency reads.

```python
db = database(get_db_pth('auth'))   # data/db/auth.db locally; Turso in production
```

The Vercel serverless filesystem is ephemeral — production persistence must go through Turso. Set `TURSO_DATABASE_URL` and `TURSO_DATABASE_TURSO_AUTH_TOKEN` via the Vercel marketplace integration (they are injected automatically when Turso is attached). Only set `TURSO_SYNC=1` when you need embedded replica mode.

## Paths

```python
get_pth('name', sf='subdir', mk=False)   # data/subdir/name; mk=True creates empty file
get_db_pth('auth')                        # data/db/auth.db
in_static('logo.svg', sf='img')          # static/img/logo.svg
get_db_dir()                              # Path to the directory containing cfg.db
```

## Slug

```python
slug("some title")   # 11-char md5 hex, lowercase input
```

Use for stable, short URL keys from arbitrary strings.

## UI layouts / components

**Layouts**

```python
base(content, usr=None, title=cfg.app_nm, sh=cfg.app_sh, style=NavBarT.glass)
landing(content, title=cfg.app_nm, usr=None)   # base + welcome_page background
welcome(usr=None)                               # landing with default placeholder
not_found()                                     # landing with 404 message
```

**Badge**

```python
Badge("new", cls=BadgePresetsT.primary)
```

`BadgeT` — raw Tailwind class strings (colors, sizes, shapes).
`BadgePresetsT` — composed presets: `default`, `primary`, `sm`, `primary_sm`, `sm_strike`.
`PresetsT` — surface presets for cards/containers: `shine`, `primary`, `transparent`, `glass`, `standout`.

**Other components**

```python
placeholder(message, back_link='/', back_text='Go Back Home')
navbar(usr=None, title='', style=NavBarT.default)
theme_switcher()
mode_switcher()
logout(usr)            # renders only when usr is set
svg_img(svg_path, cls='', w=16, h=16)
montage(svg_paths)     # tiled SVG/image grid
typewriter(stat_txt=None, dyn_txt_lst=None)
github_star(repo=None) # live star count pill; repo defaults to cfg.github_repo
main(content, cls=None)
themes()               # returns header elements (franken-ui, tailwind, theme JS/CSS)
```

## Email

`send_email` runs in a background thread (fastcore `@threaded`). Requires `RESEND_API_KEY`.

```python
send_email(to='user@example.com', subject='Hello', html=email_template(content))
```

`email_template(content, title=cfg.app_nm, usr=None)` — renders a styled HTML email container. When `usr` is a dict, prepends a greeting using `usr['usr_name']`.

## Auth block

Import the auth module's public names via `from nano import auth as a`.

**Routes** (from `nano/auth/cfg.py` `Routes`):

| attribute | path |
|---|---|
| `Routes.auth_modal` | `/a/m` |
| `Routes.auth_ok` | `/a/ok` |
| `Routes.login` | `/a/lgn` |
| `Routes.logout` | `/a/lgt` |
| `Routes.register` | `/a/reg` |
| `Routes.verify_email` | `/a/ver-em` |
| `Routes.ver_ph` | `/a/ver-ph` |
| `Routes.ver_otp` | `/a/ver-otp` |
| `Routes.verified` | `/a/verfd` |
| `Routes.verification_error` | `/a/ver-err` |
| `Routes.resend_verification` | `/a/rsnd-ver` |
| `Routes.forgot_pw` | `/a/fgt-pw` |
| `Routes.reset_pw` | `/a/rst-pw` |
| `Routes.process_reset_pw` | `/a/pr-rst-pw` |
| `Routes.err` | `/a/err` |
| `Routes.google_clbk` | `/a/google/callback` |
| `Routes.git_clbk` | `/a/github/callback` |

**Auth env vars:**

| env var | purpose |
|---|---|
| `WANT_GOOGLE` | enable Google OAuth (default `true`) |
| `GOOGLE_CLI` | Google client ID |
| `GOOGLE_SCRT` | Google client secret |
| `WANT_GIT` | enable GitHub OAuth (default `false`) |
| `GIT_CLI` | GitHub client ID |
| `GIT_SCRT` | GitHub client secret |
| `RESEND_API_KEY` | required for email verification / password reset |

OAuth providers are silently disabled when the corresponding credentials are empty — no error is raised.

`a.connect(nano)` must always be the last `connect` call. It reads the final `RouteOverrides.skip` list to exempt public paths from the auth middleware, and sets `RouteOverrides.lgn = Routes.auth_modal` and `RouteOverrides.lgt = Routes.logout`.

## Blog block

The blog block seeds posts from markdown files in `nano/blog/posts/`. Each file uses YAML frontmatter:

| frontmatter key | required | notes |
|---|---|---|
| `slug` | no | defaults to filename stem |
| `title` | no | defaults to filename stem |
| `summary` | no | short description |
| `author_name` | no | defaults to `Karthik` |
| `visibility` | no | `public` or `private`; default `public` |
| `layout` | no | defaults to `single` |
| `date` | no | `YYYY-MM-DD`; falls back to file ctime |

**Routes** (from `nano/blog/cfg.py` `Routes`):

| attribute | path |
|---|---|
| `Routes.index` | `/blog` |
| `Routes.base` | `/blog` (also mounts at `/`) |
| `Routes.new` | `/blog/new` |
| `Routes.post` | `/blog/{slug}` |

The `/` route is registered alongside `/blog` — both serve the blog index. `b.connect(app)` calls `seed_posts()` on startup and uses `posts.upsert` so seeding is idempotent.

The blog UI uses a newspaper-style column break layout (`col` break) for post lists.

## Deployment

nano deploys through Vercel's native Git integration — push to `main` and Vercel builds and deploys automatically. No separate deploy step is needed.

**Setup steps:**

1. Connect the GitHub repo to a Vercel project via the Vercel dashboard.
2. Attach Turso via the Vercel marketplace integration. This injects `TURSO_DATABASE_URL` and `TURSO_DATABASE_TURSO_AUTH_TOKEN` automatically — do not set these manually when a Turso instance is attached.
3. Fill in the remaining env vars in `.env`, then run `uv run nano-push` to load them into the Vercel project (production + preview). `nano-push` skips the Turso vars when a Turso instance is already attached.
4. Push to `main` to trigger a deploy.

Local dev uses SQLite files under `data/db/`; production persistence is Turso.

## Conventions

- Register routes with `app.get(route)(handler)` / `app.post(route)(handler)` inside `connect()`.
- Auth block connects last — never register auth routes before calling `b.connect(app)`.
- Use fastai idioms throughout: `store_attr`, `patch`, `L`, `AttrDict`, `Path`. No ruff, no PEP8 enforcement.
- Seed functions (`seed_*`) must be idempotent — use `upsert` not `insert`.
- Keep functions short; prefer reusing existing helpers over new implementations.
