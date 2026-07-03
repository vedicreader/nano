"""Turso + Vercel deployment for nano: creates DBs, pushes secrets, deploys via the Vercel SDK."""
import os, sys, json, hashlib, secrets
import httpx
from fastcore.all import Path, L
from setup import ROOT, mk_env, env2push, push_gh_vars, env_get, env_set, APP_ENV_KEYS, ENV_KEYS

root = Path(__file__).resolve().parent
blocks = ['auth', 'blog']
inc = ['nano/', 'static/', 'main.py', 'pyproject.toml', 'uv.lock', 'vercel.json', '.python-version']
exc = ('data/', 'backups/', '.venv', '__pycache__', '.git')

# === Turso resources ===
class Turso:
    'Minimal Turso Platform API client (no official Python SDK).'
    def __init__(self, tok=None, org=None):
        self.org = org or env_get('TURSO_ORG')
        tok = tok or env_get('TURSO_API_TOKEN')
        if not (self.org and tok): raise SystemExit('TURSO_ORG and TURSO_API_TOKEN are required')
        self.c = httpx.Client(base_url=f'https://api.turso.tech/v1/organizations/{self.org}',
                              headers={'Authorization': f'Bearer {tok}'}, timeout=30)

    def ensure_group(self, nm, location):
        r = self.c.post('/groups', json=dict(name=nm, location=location))
        if r.status_code not in (200, 201, 409): r.raise_for_status()
        return nm

    def ensure_db(self, nm, group):
        r = self.c.post('/databases', json=dict(name=nm, group=group))
        if r.status_code == 409 or (r.status_code == 400 and 'exists' in r.text): r = self.c.get(f'/databases/{nm}')
        r.raise_for_status()
        d = r.json()['database']
        return d.get('Hostname') or d.get('hostname')

    def group_token(self, group):
        r = self.c.post(f'/groups/{group}/auth/tokens', params=dict(expiration='never', authorization='full-access'))
        r.raise_for_status()
        return r.json()['jwt']

    def delete_db(self, nm):
        r = self.c.delete(f'/databases/{nm}')
        if r.status_code != 404: r.raise_for_status()

def mk_turso():
    'Idempotent: ensure group + one DB per block, mint a group token, write conn strings to .env.'
    t = Turso()
    grp = t.ensure_group(env_get('TURSO_GROUP', default='nano'), env_get('TURSO_GROUP_LOCATION', default='iad'))
    app = env_get('VERCEL_PROJECT', default='nano')
    for nm in blocks:
        host = t.ensure_db(f'{app}-{nm}', grp)
        env_set(f'TURSO_URL_{nm.upper()}', f'sqlite+libsql://{host}?secure=true')
        print(f'turso: {app}-{nm} -> {host}')
    env_set('TURSO_AUTH_TOKEN', t.group_token(grp))
    print(f'turso: group {grp} token written to .env')

def seed():
    'Seed blog posts into Turso (runs once per deploy; runtime seeding is dev-only).'
    for k in [f'TURSO_URL_{nm.upper()}' for nm in blocks] + ['TURSO_AUTH_TOKEN']: os.environ[k] = env_get(k)
    from nano.blog.data import seed_posts
    seed_posts(True)
    print('turso: seeded blog posts')

# === Vercel ===
def _vc(): return dict(token=env_get('VERCEL_TOKEN'), team_id=env_get('VERCEL_TEAM_ID') or None)

def ensure_project(nm):
    from vercel.projects import create_project
    try: create_project(body=dict(name=nm, framework='fasthtml'), **_vc()); print(f'vercel: created project {nm}')
    except Exception as e:
        if 'already exists' not in str(e) and '409' not in str(e): raise
        print(f'vercel: project {nm} exists')

def push_vercel_env(nm):
    'Upsert app env vars on the Vercel project. None-default schema keys → encrypted, rest plain.'
    envs = env2push()
    body = [dict(key=k, value=str(envs[k]), type='encrypted' if ENV_KEYS[k] is None else 'plain',
                 target=['production', 'preview']) for k in APP_ENV_KEYS if envs.get(k)]
    tok, team = env_get('VERCEL_TOKEN'), env_get('VERCEL_TEAM_ID')
    r = httpx.post(f'https://api.vercel.com/v10/projects/{nm}/env', json=body, timeout=30,
                   params=dict(upsert='true') | (dict(teamId=team) if team else {}),
                   headers={'Authorization': f'Bearer {tok}'})
    r.raise_for_status()
    print(f'vercel: upserted {len(body)} env vars on {nm}')

def _files():
    for it in inc:
        p = root/it
        if not p.exists(): continue
        for f in ([p] if p.is_file() else p.rglob('*')):
            rel = str(f.relative_to(root))
            if f.is_file() and not any(x in rel for x in exc): yield rel, f.read_bytes()

def deploy_app(nm):
    'Upload files and create a production deployment via the Vercel SDK.'
    from vercel.deployments import create_deployment, upload_file
    vc, files = _vc(), []
    for rel, data in _files():
        sha = hashlib.sha1(data).hexdigest()
        upload_file(content=data, content_length=len(data), x_vercel_digest=sha, **vc)
        files.append(dict(file=rel, sha=sha, size=len(data)))
    print(f'vercel: uploaded {len(files)} files')
    d = create_deployment(body=dict(name=nm, project=nm, target='production', files=files,
                                    projectSettings=dict(framework='fasthtml')), **vc)
    url = d.get('url') or d.get('alias', [''])[0]
    print(f'deployed: https://{url}')
    return d

def mk_compose():
    'Write vercel.json (the compose-file analog for the Vercel runtime).'
    (root/'vercel.json').mk_write(json.dumps({
        '$schema': 'https://openapi.vercel.sh/vercel.json',
        'functions': {'main.py': {'maxDuration': 60}}}, indent=2) + '\n')
    print('wrote vercel.json')

def deploy2prod():
    'Idempotent: provisions Turso group/DBs + token, seeds posts, pushes env to Vercel, deploys.'
    mk_env(env2push(), path=root/'.env')
    mk_compose()
    mk_turso()
    seed()
    nm = env_get('VERCEL_PROJECT', default='nano')
    ensure_project(nm)
    push_vercel_env(nm)
    deploy_app(nm)
    if (ROOT/'.gheasy/config.json').exists(): push_gh_vars()

def nuke_prod():
    'Delete the Vercel project and Turso databases. Use with caution!'
    typ = secrets.token_urlsafe(8)
    ans = input(f'WARNING: This will irreversibly delete the Vercel project and Turso databases. Type {typ} to proceed: ')
    if ans != typ: return print('Aborting nuke.')
    nm = env_get('VERCEL_PROJECT', default='nano')
    from vercel.projects import delete_project
    try: delete_project(nm, **_vc()); print(f'vercel: project {nm} deleted')
    except Exception as e: print(f'vercel: {e}')
    t = Turso()
    for b in blocks: t.delete_db(f'{nm}-{b}'); print(f'turso: {nm}-{b} deleted')

def deploy_cli():
    args = sys.argv[1:]
    cmd = args[0] if args else ''
    if cmd == 'compose': mk_compose()
    elif cmd == 'deploy': deploy2prod()
    elif cmd == 'turso': mk_turso()
    elif cmd == 'seed': seed()
    elif cmd == 'nuke': nuke_prod()
    elif cmd == 'env': mk_env(env2push(), path=root/'.env')
    else: print('usage: nano-deploy compose | deploy | turso | seed | env | nuke')

if __name__ == '__main__': deploy_cli()
