import hashlib as hl
import logging
import os
import secrets
from dataclasses import dataclass
from fasthtml.core import Redirect
from fastcore.all import threaded, AttrDictDefault, str2bool, str2int, startthread, to_xml, Path, FT
from fastsql import Database, database as fdb

__all__ = ['cfg', 'database', 'AppErr', 'home', 'send_email', 'RouteOverrides', 'get_pth', 'get_db_pth', 'in_static',
           'get_db_dir', 'not_prod', 'slug']

def turso_cfg(local_path):
    'Build (conn_str, engine_kws) for a Turso connection, or None when TURSO env is unset.'
    u, tok = cfg.turso_url, cfg.turso_token
    if not (u and tok): return None
    host = u.split('://', 1)[-1].rstrip('/')
    if cfg.turso_sync: conn, ca = f'sqlite+libsql:///{local_path}', dict(auth_token=tok, sync_url=f'https://{host}')
    else: conn, ca = f'sqlite+libsql://{host}?secure=true', dict(auth_token=tok)
    return conn, dict(connect_args=ca)

def database(path=None):
    'fastsql `Database`: local sqlite file, or Turso (remote/embedded replica) when TURSO env is set.'
    if not path and not isinstance(path, (str, Path)): return None
    t = turso_cfg(path)
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
                      site_keywords=os.getenv('SITE_KEYWORDS','nano, fastHTML, MonsterUI, webapp, python'),
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
class RouteOverrides: lgn, lgt, home, skip = '/lgn', '/lgt', cfg.domain, ['/health']
