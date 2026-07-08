"""Deploy nano to Vercel with vercello.

Requires VERCEL_TOKEN (and VERCEL_TEAM_ID for team accounts). Project env vars
are copied from the local environment — set TURSO_DATABASE_URL/TURSO_AUTH_TOKEN
so the app runs against Turso (the local-sqlite fallback breaks on Vercel's
read-only filesystem), and pin JWT_SCRT or sessions won't survive across
serverless instances.

Caveat: fire-and-forget @threaded work (Resend emails, last-active updates) can
be cut short when a serverless invocation freezes; fluid compute usually lets
it finish.
"""
import os
from vercello.core import *

root = Path(__file__).resolve().parent
ENV_KEYS = ['TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN', 'JWT_SCRT', 'MODE', 'DOMAIN',
            'RESEND_API_KEY', 'APP_NAME', 'APP_SH', 'GITHUB_REPO', 'TOKEN_EXP',
            'WANT_GOOGLE', 'GOOGLE_CLI', 'GOOGLE_SCRT', 'WANT_GIT', 'GIT_CLI', 'GIT_SCRT']

def deploy2prod():
    env = {k: os.environ[k] for k in ENV_KEYS if os.getenv(k)}
    env.setdefault('MODE', 'production')
    env.setdefault('TURSO_SYNC', '0')
    if 'JWT_SCRT' not in env: print('⚠ JWT_SCRT not set — sessions will break across serverless instances')
    if 'TURSO_DATABASE_URL' not in env: print('⚠ TURSO_* not set — the app cannot use local sqlite on Vercel')
    r = vercel_deploy('nano', root, env=env)
    print(f'deployed: {r.url}')

if __name__ == '__main__': deploy2prod()
