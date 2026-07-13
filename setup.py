"""nano project setup: env scaffold, skill install, push env to Vercel."""
import os, sys, subprocess
from fastcore.all import Path, parse_env, filter_keys, in_, first, L, true

__all__ = ['setup', 'install_skills', 'mk_env', 'env2push']

def repo_root() -> Path:
    'Nearest ancestor containing .git, else cwd.'
    return first((Path.cwd(), *Path.cwd().parents), lambda p: (p/'.git').exists()) or Path.cwd()

ROOT = repo_root()

ENV_KEYS = dict(
    APP_NAME='Nano', APP_SH='nano', SITE_AUTHOR='Karthik Rajgopal',
    SITE_DESCRIPTION='Build performant webapps one block at a time',
    SITE_KEYWORDS='nano, fastHTML, MonsterUI, webapp, python',
    MODE='production', DOMAIN='nano.sankalpa.sh', PORT='5001', TOKEN_EXP='691200',
    GITHUB_REPO='vedicreader/nano', WANT_GOOGLE='true', WANT_GIT='false', TURSO_SYNC='0',
    JWT_SCRT=None, RESEND_API_KEY=None, GOOGLE_CLI=None, GOOGLE_SCRT=None,
    GIT_CLI=None, GIT_SCRT=None,
    TURSO_DATABASE_URL=None, TURSO_DATABASE_TURSO_AUTH_TOKEN=None)

TURSO_KEYS = ('TURSO_DATABASE_URL', 'TURSO_DATABASE_TURSO_AUTH_TOKEN')

def _load_env(): return dict(os.environ) | (parse_env(fn=str(f)) if (f:=ROOT/'.env').exists() else {})
def env2push(): return ENV_KEYS | filter_keys(_load_env(), in_(ENV_KEYS))

def env_set(key, value, path=None):
    'Upsert key=value into fastops .env file and os.environ. Returns True if changed.'
    from dotenv import get_key, set_key
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists(): p.touch(); os.chmod(p, 0o600)
    if get_key(str(p), key) != str(value): set_key(str(p), key, str(value))
    os.environ[key] = str(value)

def mk_env(env=None, path=Path(ROOT/'.env.example')):
    'Write/refresh a dotenv file from a dict (None values -> empty).'
    env = env or ENV_KEYS
    for k, v in env.items(): env_set(k, v, path)
    print(f'env: wrote/updated {path}')

def mv_skill_md(dry_run=True, dir=None):
    'Copy bundled SKILL.md into .claude/skills/nano/ and .agents/skills/nano/.'
    base = Path(__file__).parent
    if not (src := base/'SKILL.md').exists(): return print('skill: no SKILL.md to copy')
    root = Path(dir or ROOT)
    ts = [root/'.agents/skills/nano/SKILL.md', root/'.claude/skills/nano/SKILL.md']
    if dry_run: return print(f'Would copy {src} to: {list(map(str, ts))}')
    for p in ts: p.mk_write(src.read_text(encoding='utf-8'))
    print(f'skill: installed -> {list(map(str, ts))}')

def install_skills():
    import importlib
    mv_skill_md(dry_run=False)
    for nm in ('kosha', 'litesearch', 'fossick'):
        try: mod = importlib.import_module(nm)
        except ImportError: print(f'skip {nm}: not installed'); continue
        if mv := getattr(mod, 'mv_skill_md', None): mv(dry_run=False)
        else: print(f'skip {nm}: no mv_skill_md')

def setup():
    mk_env(path=ROOT/'.env.example')
    install_skills()
    print('Setup complete. Review .env.example, copy to .env and fill secrets, '
          'then `uv run nano-push` and push to main to deploy.')

if __name__ == '__main__':
    if 'mkenv' in sys.argv: mk_env(env2push(), path=ROOT/'.env')
    elif 'skills' in sys.argv: install_skills()
    else: setup()
