"""One-shot project setup: git-lfs, .env scaffolding, secrets push to GitHub."""
import os, sys
from fastcore.all import Path, parse_env, filter_keys, in_, first
from gheasy import GheasyConfig, gh_lfs, gh_push_env
from gheasy.workflow import Workflow

__all__ = ['setup', 'push_gh_vars', 'mk_env', 'env2push', 'env_get', 'env_set']

def repo_root() -> Path:
	'Find the root of the current git repository, or None if not in a repo.'
	return first((Path.cwd(), *Path.cwd().parents), lambda p: (p/'.git').exists())

def mv_skill_md(dry_run=True, dir=None) -> None:
	'Copy bundled SKILL.md into `.agents/skills/nano/` and `.claude/skills/nano/` at project root or specified dir.'
	base = Path(__file__).parent if '__file__' in globals() else Path.cwd()
	if not (src := base.joinpath('SKILL.md')).exists(): return
	root = Path(dir or repo_root() or '.')
	ts = [root/'.agents/skills/nano/SKILL.md', root/'.claude/skills/nano/SKILL.md']
	if dry_run: print(f'Would copy {src} to: {list(map(str,ts))}')
	else:
		for p in ts: p.mk_write(src.read_text(encoding='utf-8'))
		print(f'Installed -> {list(map(str,ts))}')

ROOT = repo_root()
LFS_PATTERNS = ['*.mp3', '*.ogg', '*.wav', '*.flac', '*.ico', '*.png', '*.jpg', '*.jpeg', '*.webp', '*.xml']
# None-default keys become GitHub/Vercel secrets; string-default keys become variables.
ENV_KEYS = dict(MODE='production', DOMAIN='nano.sankalpa.sh', TOKEN_EXP='691200',
    JWT_SCRT=None, RESEND_API_KEY=None, WANT_GOOGLE='true', WANT_GIT='false', GOOGLE_CLI=None, GOOGLE_SCRT=None,
    GIT_CLI=None, GIT_SCRT=None, VERCEL_TOKEN=None, VERCEL_TEAM_ID='', VERCEL_PROJECT='nano',
    TURSO_API_TOKEN=None, TURSO_ORG='', TURSO_GROUP='nano', TURSO_GROUP_LOCATION='iad',
    TURSO_AUTH_TOKEN=None, TURSO_URL_AUTH='', TURSO_URL_BLOG='')
# keys the running app needs on Vercel (deploy-side credentials stay out of the runtime env)
APP_ENV_KEYS = [k for k in ENV_KEYS if not k.startswith(('VERCEL_', 'TURSO_API', 'TURSO_ORG', 'TURSO_GROUP'))]

def env_get(k, path=None, default=''):
	envs = parse_env(fn=str(p)) if (p := Path(path or ROOT/'.env')).exists() else {}
	return envs.get(k) or os.getenv(k, default)

def env_set(k, v, path=None):
	p = Path(path or ROOT/'.env')
	lines = p.read_text().splitlines() if p.exists() else []
	ln = f'{k}={"" if v is None else v}'
	ks = [l.split('=', 1)[0] for l in lines]
	lines = [ln if nm == k else l for nm, l in zip(ks, lines)] + ([] if k in ks else [ln])
	p.mk_write('\n'.join(lines) + '\n')

def _load_env(): return dict(os.environ) | (parse_env(fn=str(envf)) if (envf := ROOT / '.env').exists() else {})
def env2push(): return ENV_KEYS | filter_keys(_load_env(), in_(ENV_KEYS))

def _init_gheasy():
	if app := GheasyConfig.load(ROOT).app: return print(f'gheasy: config already initialized for {app}')
	gh = GheasyConfig(app='nano', env_schema=ENV_KEYS).save(ROOT)
	print(f'gheasy: initialized config for {gh.app} with env schema keys: {len(gh.env_schema)}')

def lfs():
	gh_lfs(LFS_PATTERNS, path=str(ROOT))
	print(f'lfs: tracking {len(LFS_PATTERNS)} patterns')

def mk_env(env: dict = None, path=None):
	'Create/refresh .env.example (or `path`) with keys from ENV_KEYS.'
	env = env or ENV_KEYS
	path = Path(path or ROOT/'.env.example')
	for k, v in env.items(): env_set(k, v, path)
	print(f'env: wrote/updated {path}')

def push_gh_vars(dry_run=False):
	"Push local .env values to GitHub. None-default keys → secrets; string-default → variables."
	to_push = env2push()
	if not to_push: return print('push: nothing to push (no matching keys with values in .env)')
	gh_push_env(to_push, dry_run=dry_run, path=ROOT)
	print(f'push: {"would push" if dry_run else "pushed"} {len(to_push)} keys to GitHub')

def push_cli(): push_gh_vars('--dry-run' in sys.argv)

def gen_deploy_workflow():
	wf = Workflow('deploy')
	wf.on.push(branches=['main'])
	env = {k: (f'${{{{ secrets.{k} }}}}' if v is None else f'${{{{ vars.{k} }}}}') for k, v in ENV_KEYS.items()}
	(wf.job('deploy').runs_on('ubuntu-latest')
	 .env(**env).checkout().with_(lfs=True).end_step()
	 .setup_uv().with_(python_version='3.13').end_step()
	 .uv_install('uv sync --group dev').end_step()
	 .step('Deploy').run('uv run python deploy.py deploy').end_job())
	p = ROOT / '.github' / 'workflows' / 'deploy.yml'
	wf.build().save(p)
	print(f'workflow: wrote {p}')

def setup():
	_init_gheasy()
	lfs()
	mk_env()
	gen_deploy_workflow()
	install_skills()
	print('Setup complete. Review .env.example, .github/workflows/deploy.yml, and SKILL.md files. '
	      'Fill .env with your secrets, run nano-push to sync them to GitHub, and push to main to deploy.')

def install_skills():
	import importlib
	mv_skill_md(dry_run=False)
	for nm in ('gheasy', 'kosha', 'fossick'):
		try: mod = importlib.import_module(nm)
		except ImportError: print(f'skip {nm}: not installed'); continue
		if mv := getattr(mod, 'mv_skill_md', None): mv(dry_run=False)
		else: print(f'skip {nm}: no mv_skill_md')

if __name__ == '__main__':
	if 'push' in sys.argv: push_cli()
	elif 'mkenv' in sys.argv: mk_env(env2push(), path=ROOT/'.env')
	elif 'workflow' in sys.argv: gen_deploy_workflow()
	elif 'skills' in sys.argv: install_skills()
	else: setup()
