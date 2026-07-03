import hashlib as hl
import logging
import os
import secrets
from fasthtml.common import Redirect, FT, dataclass
from fastcore.all import threaded, AttrDictDefault, str2bool, str2int, startthread, to_xml, Path
from fastsql import database

__all__ = ['cfg', 'database', 'get_db', 'create_index', 'AppErr', 'home', 'send_email', 'RouteOverrides', 'get_pth', 'get_db_pth', 'in_static', 'get_db_dir', 'not_prod', 'slug']

# === Paths ===
data_root, backups, static = Path('data'), Path('backups'), Path('static')
def get_pth(nm, sf='', mk=False):
    p = data_root / sf / nm
    if not p.exists() and mk: p.mk_write('')
    return p

def get_db_pth(nm='vr'): return get_pth(f'{nm}.db', 'db')
def in_static(nm, sf=''): return static / sf / nm

# === Database ===
def db_url(nm):
    'Turso conn string for a block from TURSO_URL_{NM} (+TURSO_AUTH_TOKEN), empty when unset (local dev).'
    url = os.getenv(f'TURSO_URL_{nm.upper()}', '') or os.getenv('TURSO_URL', '')
    if not url: return ''
    tok = os.getenv('TURSO_AUTH_TOKEN', '')
    if tok: url += ('&' if '?' in url else '?') + f'authToken={tok}'
    return url

def get_db(nm='vr'):
    'fastsql Database for a block: Turso over libsql in prod, local sqlite file in dev.'
    if url := db_url(nm):
        import libsql_experimental  # libsql DBAPI lacks Binary; sqlalchemy needs it for bytes columns
        if not hasattr(libsql_experimental, 'Binary'): libsql_experimental.Binary = bytes
        return database(url)
    p = get_db_pth(nm)
    p.parent.mkdir(parents=True, exist_ok=True)
    return database(p)

def create_index(db, tbl, cols, unique=True):
    db.q(f'CREATE {"UNIQUE " if unique else ""}INDEX IF NOT EXISTS ix_{tbl}_{"_".join(cols)} ON {tbl} ({", ".join(cols)})')
    db.conn.commit()

def generate_jwt_scrt(): return secrets.token_urlsafe(32)

def _env_url(k, default):
    v = os.getenv(k, default)
    return v if v.startswith(('http://','https://')) else f'https://{v}'

cfg = AttrDictDefault(app_nm=os.getenv('APP_NAME','Nano'),
                      app_sh=os.getenv('APP_SH','nano'),
                      site_author=os.getenv('SITE_AUTHOR','Karthik Rajgopal'),
                      site_description=os.getenv('SITE_DESCRIPTION','Build performant webapps one block at a time'),
                      site_keywords=os.getenv('SITE_KEYWORDS','nano, fastHTML, MonsterUI, webapp, python'),
                      jwt_scrt=os.getenv('JWT_SCRT') or generate_jwt_scrt(),
                      mode=os.getenv('MODE','dev'),
                      domain=_env_url('DOMAIN','http://localhost:5001'),
                      resend_api_key=os.getenv('RESEND_API_KEY', ''),
                      port=str2int(os.getenv('PORT', '5001')),
                      tkn_exp=str2int(os.getenv('TOKEN_EXP', '691200')),
                      typwrtr_dyn_txt='Build, Expand, Innovate',
                      typwrtr_stat_txt='like lego',
                      data_root=data_root, backup_path=backups,
                      db=get_db_pth(), static=static,
                      svg=in_static('svg'), github_repo=os.getenv('GITHUB_REPO', 'vedicreader/nano'))

def not_prod(): return cfg.mode != 'production'
if not not_prod() and not os.getenv('JWT_SCRT'):
    logging.warning('JWT_SCRT unset in production: sessions and tokens will break on every cold start')
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
