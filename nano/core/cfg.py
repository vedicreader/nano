import hashlib as hl
import logging
import os
import secrets
import tempfile
from dataclasses import dataclass
from fasthtml.core import Redirect
from fastcore.all import threaded, AttrDict, AttrDictDefault, str2bool, str2int, startthread, to_xml, Path, FT
from fastsql import Database, database as fdb

__all__ = ['cfg', 'database', 'AppErr', 'home', 'send_email', 'RouteOverrides', 'get_pth', 'get_db_pth', 'in_static',
           'get_db_dir', 'scratch_db_dir', 'turso_target', 'not_prod', 'slug']

def _env(*ks):
    'First of `ks` set to something non-blank.'
    return next((v for k in ks if (v := os.getenv(k, '').strip())), '')

def env_nm(nm): return ''.join(c if c.isalnum() else '_' for c in str(nm)).upper()

def turso_target(nm):
    '''The Turso database backing the logical database `nm`: url, token, and whether it is
    `nm`s alone. Empty url means no Turso at all.

    A libsql URL has no path component, so the *URL* is the database — one URL is one
    database however many paths get passed to `database()`. Give a block its own with:

        TURSO_CHINOOK_URL, TURSO_CHINOOK_AUTH_TOKEN

    `TURSO_DATABASE_URL` is the pair the Vercel marketplace integration attaches. It stays
    the default for the app's own data, so an existing deployment keeps its users and posts
    where they are.'''
    up = env_nm(nm)
    url = _env(f'TURSO_{up}_DATABASE_URL', f'TURSO_{up}_URL')
    if not url: return AttrDict(url=cfg.turso_url, token=cfg.turso_token, own=False)
    tok = _env(f'TURSO_{up}_DATABASE_TURSO_AUTH_TOKEN', f'TURSO_{up}_AUTH_TOKEN')
    # falling back to the shared token here would authenticate against the wrong database
    if not tok: raise AppErr(f'TURSO_{up}_URL is set without TURSO_{up}_AUTH_TOKEN')
    return AttrDict(url=url, token=tok, own=True)

_stores = {}   # turso host -> the first logical database that claimed it

def turso_cfg(nm, local_path, own=False):
    'Build (conn_str, engine_kws) for `nm`s Turso database, or None when it may not use one.'
    t = turso_target(nm)
    if not (t.url and t.token) or (own and not t.own): return None
    host = t.url.split('://', 1)[-1].rstrip('/')
    if _stores.setdefault(host, nm) != nm:
        logging.warning('turso: %r shares one database with %r (%s) — every table is visible to both. '
                        'Set TURSO_%s_URL and TURSO_%s_AUTH_TOKEN to split them.',
                        nm, _stores[host], host, env_nm(nm), env_nm(nm))
    ca = dict(auth_token=t.token)
    if cfg.turso_sync: conn = f'sqlite+libsql:///{local_path}'; ca['sync_url'] = f'https://{host}'
    else: conn = f'sqlite+libsql://{host}?secure=true'
    return conn, dict(connect_args=ca)

def database(path=None, own=False):
    '''fastsql `Database` for one logical database, named by `path`s stem.

    `own=True` bars it from the app's shared Turso database: it gets a Turso database of
    its own when one is configured under its name, and a local file otherwise. A reflected
    database needs that — sharing a store with auth would put `users` in the explorer.'''
    if not path and not isinstance(path, (str, Path)): return None
    t = turso_cfg(Path(path).stem, path, own=own)
    if t:
        conn, engine_kws = t
        if cfg.turso_sync: Path(path).parent.mkdir(parents=True, exist_ok=True)
        return Database(conn, engine_kws=engine_kws)
    if not Path(path).exists(): Path(path).parent.mkdir(parents=True,exist_ok=True)
    return fdb(path or cfg.db)

data_root, backups, static = Path('data'), Path('backups'), Path('static')
def get_pth(nm, sf='', mk=False):
    p = data_root / sf / nm
    if not p.exists() and mk: p.mk_write('')
    return p

def get_db_pth(nm='vr'): return get_pth(f'{nm}.db', 'db')
def in_static(nm, sf=''): return static / sf / nm

def generate_jwt_scrt(): return secrets.token_urlsafe(32)

def _env_url(k, default):
    v = os.getenv(k, default)
    return v if v.startswith(('http://','https://')) else f'https://{v}'

cfg = AttrDictDefault(app_nm=os.getenv('APP_NAME','Nano'),
                      app_sh=os.getenv('APP_SH','nano'),
                      site_author=os.getenv('SITE_AUTHOR','Karthik Rajgopal'),
                      site_description=os.getenv('SITE_DESCRIPTION','Build performant webapps one block at a time'),
                      site_keywords=os.getenv('SITE_KEYWORDS','nano, fastHTML, Oat, webapp, python'),
                      jwt_scrt=os.getenv('JWT_SCRT', generate_jwt_scrt()),
                      mode=os.getenv('MODE','dev'),
                      domain=_env_url('DOMAIN','http://localhost:5001'),
                      resend_api_key=os.getenv('RESEND_API_KEY', ''),
                      port=str2int(os.getenv('PORT', '5001')),
                      tkn_exp=str2int(os.getenv('TOKEN_EXP', '691200')),
                      typwrtr_dyn_txt='Build, Expand, Innovate',
                      typwrtr_stat_txt='like lego',
                      turso_url=os.getenv('TURSO_DATABASE_URL', ''),
                      turso_token=os.getenv('TURSO_DATABASE_TURSO_AUTH_TOKEN', ''),
                      turso_sync=str2bool(os.getenv('TURSO_SYNC', '0')),
                      data_root=data_root, backup_path=backups,
                      db=get_db_pth(), static=static,
                      svg=in_static('svg'), github_repo=os.getenv('GITHUB_REPO', 'vedicreader/nano'))

def not_prod(): return cfg.mode != 'production'
def get_db_dir(): return Path(cfg.db).parent if cfg.db else Path(data_root) / 'db'

_scratch = None
def scratch_db_dir():
    '''Where a database that can be rebuilt from its dump is allowed to live: the normal
    db dir, or the system temp dir when the deployment is read-only — serverless mounts
    the bundle read-only and gives you /tmp.'''
    global _scratch
    if _scratch is None:
        d = get_db_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
            (p := d / '.writable').touch(); p.unlink()
        except OSError:
            d = Path(tempfile.gettempdir()) / f'{cfg.app_sh}-db'
            d.mkdir(parents=True, exist_ok=True)
        _scratch = d
    return _scratch
def slug(word: str): return hl.md5(word.lower().encode()).hexdigest()[:11]

class AppErr(Exception):
    def __init__(self, msg=None, fields=None):
        super().__init__(msg)
        self.msg, self.fields = msg, fields or []

@threaded
def send_email(to, subject, html: FT, from_='accounts@nano.com'):
    if isinstance(html, FT): html = to_xml(html)
    import resend
    resend.api_key = cfg.resend_api_key
    r = resend.Emails.send({'from': from_, 'to': to, 'subject': subject, 'html': html})
    print(f'Resend Result: {r}')

def home(next=None): return Redirect(next or RouteOverrides.home)

@dataclass
class RouteOverrides:
    lgn, lgt, home, skip = '/lgn', '/lgt', cfg.domain, ['/health']
    nav = []   # (label, href) pairs; blocks append theirs in connect()
