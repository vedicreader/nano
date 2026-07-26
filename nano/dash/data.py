import gzip, hashlib, json
import sqlalchemy as sa
from fastcore.all import L, AttrDict, ifnone
from nano.core.cfg import database, get_db_pth
from .cfg import cfg

__all__ = ['DBS', 'get_db', 'seed', 'schema', 'table_names', 'reflect', 'profile', 'rowcount', 'qmark', 'ident']

# only databases listed here are reachable from /dash — auth.db and blog.db stay out
DBS = AttrDict(chinook=AttrDict(nm='Chinook', dump='chinook.sql.gz',
                                about='The classic digital-media store sample: artists, albums, tracks, invoices.'))

_conns, _meta = {}, database(get_db_pth('dash'))
_meta.t.dash_profile.create(k=str, body=str, pk='k', if_not_exists=True)
_cache = _meta.t.dash_profile

def get_db(nm):
    if nm not in DBS: raise KeyError(nm)
    if nm not in _conns:
        _conns[nm] = database(get_db_pth(nm))
        seed(nm)
    return _conns[nm]

def seed(nm):
    'Load the packaged dump once. Batched multi-row INSERTs, so this is ~70 statements, not 15k.'
    db, dump = _conns[nm], cfg.seed_dir / DBS[nm].dump
    if db.table_names(): return
    sql = gzip.decompress(dump.read_bytes()).decode()
    # exec_driver_sql, not text(): the data contains literals like ':Pines' that
    # SQLAlchemy would otherwise read as bind parameters
    for st in filter(None, (s.strip() for s in sql.split('\n--;--\n'))): db.conn.exec_driver_sql(st)
    db.conn.commit()
    db.meta.reflect(bind=db.engine)

def ident(name, allowed):
    'Quote an identifier, but only after it matches something the schema actually reported.'
    if name not in allowed: raise ValueError(f'unknown identifier: {name!r}')
    return '"%s"' % name.replace('"', '""')

def qmark(db, sql, **params): return db.q(sql, **params)

# ── reflection ────────────────────────────────────────────────────────────────

def table_names(nm): return sorted(sa.inspect(get_db(nm).engine).get_table_names())

def reflect(nm, tbl):
    'Columns, primary key and foreign keys for one table, straight from the dialect inspector.'
    ins = sa.inspect(get_db(nm).engine)
    if tbl not in ins.get_table_names(): raise KeyError(tbl)
    cols = [AttrDict(name=c['name'], type=str(c['type']), nullable=c['nullable']) for c in ins.get_columns(tbl)]
    pk = list(ins.get_pk_constraint(tbl).get('constrained_columns') or [])
    fks = [AttrDict(col=f['constrained_columns'][0], ref_table=f['referred_table'], ref_col=f['referred_columns'][0])
           for f in ins.get_foreign_keys(tbl) if f.get('constrained_columns') and f.get('referred_columns')]
    return AttrDict(name=tbl, cols=cols, pk=pk, fks=fks, fk_by_col={f.col: f for f in fks})

def schema(nm):
    'Whole-database shape: every table with its columns, keys and inbound child references.'
    tbls = {t: reflect(nm, t) for t in table_names(nm)}
    for t in tbls.values(): t.children = []
    for t in tbls.values():
        for f in t.fks:
            if f.ref_table in tbls: tbls[f.ref_table].children.append(AttrDict(table=t.name, col=f.col, ref_col=f.ref_col))
    return tbls

def rowcount(nm, tbl):
    db, names = get_db(nm), table_names(nm)
    return db.q(f'select count(*) as n from {ident(tbl, names)}')[0]['n']

# ── profiling ─────────────────────────────────────────────────────────────────

_NUM = ('INT', 'REAL', 'FLOA', 'DOUB', 'NUM', 'DEC')
_DATE = ('DATE', 'TIME', 'STAMP')

def _kind(sqltype):
    t = (sqltype or '').upper()
    if any(k in t for k in _DATE): return 'date'
    if any(k in t for k in _NUM): return 'num'
    return 'text'

_PROFILE_V = 2   # bump when the stats collected in _measure change

def _schema_hash(nm, tbl):
    r = reflect(nm, tbl)
    body = json.dumps([[c.name, c.type] for c in r.cols], sort_keys=True)
    return hashlib.md5(f'{_PROFILE_V}.{nm}.{tbl}.{body}.{rowcount(nm, tbl)}'.encode()).hexdigest()[:16]

def profile(nm, tbl, force=False):
    'Per-column stats used by the chart picker. Cached in dash.db against a schema+rowcount hash.'
    key = f'{nm}.{tbl}.{_schema_hash(nm, tbl)}'
    if not force:
        try: return AttrDict(json.loads(_cache[key]['body']))
        except Exception: pass
    p = _measure(nm, tbl)
    _cache.upsert(dict(k=key, body=json.dumps(p)))
    return AttrDict(p)

def _measure(nm, tbl):
    db, names = get_db(nm), table_names(nm)
    r, qt = reflect(nm, tbl), ident(tbl, names)
    allowed = {c.name for c in r.cols}
    n = rowcount(nm, tbl)
    src = qt if n <= cfg.sample_rows else f'(select * from {qt} limit {cfg.sample_rows})'
    out = dict(table=tbl, rows=n, cols={})
    for c in r.cols:
        qc, kind = ident(c.name, allowed), _kind(c.type)
        agg = [f'count({qc}) as nn', f'count(distinct {qc}) as nd']
        if kind == 'num':
            # sqlite has no stddev; one pass over sum(x) and sum(x*x) gives the population sigma
            agg += [f'min({qc}) as lo', f'max({qc}) as hi', f'avg({qc}) as mean',
                    f'avg({qc}*{qc}) as m2', f'sum({qc}) as total']
        elif kind == 'date':
            agg += [f'min({qc}) as lo', f'max({qc}) as hi']
        else:
            agg += [f'max(length({qc})) as maxlen', f'min({qc}) as lo', f'max({qc}) as hi']
        row = db.q(f'select {", ".join(agg)} from {src}')[0]
        seen = row['nn'] or 0
        d = dict(name=c.name, type=c.type, kind=kind, nullable=c.nullable, distinct=row['nd'] or 0,
                 nulls=(n if n <= cfg.sample_rows else cfg.sample_rows) - seen, sampled=min(n, cfg.sample_rows))
        if kind == 'num' and seen:
            var = max(0.0, (row['m2'] or 0) - (row['mean'] or 0) ** 2)
            d.update(lo=row['lo'], hi=row['hi'], mean=row['mean'], total=row['total'], sd=var ** 0.5)
        elif kind == 'date':
            d.update(lo=row['lo'], hi=row['hi'])
        else:
            d.update(maxlen=row['maxlen'] or 0, lo=row['lo'], hi=row['hi'])
        out['cols'][c.name] = d
    return out
