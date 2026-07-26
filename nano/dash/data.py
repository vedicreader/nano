import gzip, hashlib, json, re
import sqlalchemy as sa
from fastcore.all import L, AttrDict, ifnone
from nano.core.cfg import database, get_db_pth, scratch_db_dir
from .cfg import cfg

__all__ = ['DBS', 'get_db', 'seed', 'owned', 'schema', 'table_names', 'reflect', 'profile', 'rowcount', 'qmark', 'ident']

# only databases listed here are reachable from /dash, and only through the tables
# their own dump defines — see owned()
DBS = AttrDict(chinook=AttrDict(nm='Chinook', dump='chinook.sql.gz',
                                about='The classic digital-media store sample: artists, albums, tracks, invoices.'))

_conns, _seeded, _owned, _meta = {}, set(), {}, database(get_db_pth('dash'))
_meta.t.dash_profile.create(k=str, body=str, pk='k', if_not_exists=True)
_cache = _meta.t.dash_profile

def get_db(nm):
    '''`own=True`: a database the explorer reflects gets its own store or none at all.
    Left to the shared default it would be the app's own database, and /dash would be
    reflecting auth and blog. Without TURSO_<NM>_URL it falls to a local file, which is
    the right home for data rebuilt from a packaged dump anyway.'''
    if nm not in DBS: raise KeyError(nm)
    if nm not in _conns: _conns[nm] = database(scratch_db_dir() / f'{nm}.db', own=True)
    if nm not in _seeded: seed(nm)
    return _conns[nm]

# ── seeding ───────────────────────────────────────────────────────────────────

_CREATE_T = re.compile(r'(?is)^create\s+table(?:\s+if\s+not\s+exists)?\s+[\["`]?([A-Za-z_]\w*)')
_CREATE_I = re.compile(r'(?is)^create\s+(?:unique\s+)?index(?:\s+if\s+not\s+exists)?\s+.*?\bon\s+[\["`]?([A-Za-z_]\w*)')
_INSERT   = re.compile(r'(?is)^insert\s+into\s+[\["`]?([A-Za-z_]\w*)')
_INTO     = re.compile(r'(?is)^insert\s+into\b')

def _dump(nm):
    'The packaged dump, split into the tables it defines, their rows, and their indexes.'
    sql = gzip.decompress((cfg.seed_dir / DBS[nm].dump).read_bytes()).decode()
    d = AttrDict(tables={}, rows={}, indexes=[])
    for st in filter(None, (s.strip() for s in sql.split('\n--;--\n'))):
        if m := _CREATE_T.match(st): d.tables[m.group(1)] = st
        elif m := _INSERT.match(st): d.rows.setdefault(m.group(1), []).append(st)
        elif _CREATE_I.match(st): d.indexes.append(st)
        else: raise ValueError(f'{DBS[nm].dump}: unrecognised statement {st[:60]!r}')
    return d

def owned(nm):
    '''The tables this database consists of, from its `tables` list or its dump.
    In production every block shares one Turso database (the libsql URL carries no
    path, so get_db_pth is ignored), which puts auth and blog tables on the same
    connection as the sample data. This is what keeps them apart.'''
    if nm not in _owned:
        d = DBS[nm]
        _owned[nm] = tuple(d.tables) if d.get('tables') else tuple(_dump(nm).tables)
    return _owned[nm]

def seed(nm):
    '''Load the packaged dump: ~70 batched multi-row statements, not 15k.

    Resumable and safe to race. A serverless cold start can be cut off part-way
    through 480KB of inserts over a remote connection, so progress is tracked per
    table and INSERT OR IGNORE lets a retry — or a second worker — converge instead
    of erroring on a duplicate key or double-loading a half-filled table.'''
    if not DBS[nm].get('dump'): _seeded.add(nm); return
    db, d = _conns[nm], _dump(nm)
    _owned.setdefault(nm, tuple(d.tables))
    have = set(sa.inspect(db.engine).get_table_names())
    made = [t for t in d.tables if t not in have]
    for t in made: _exec(db, d.tables[t])
    if made: db.conn.commit()
    todo = [t for t, n in _counts(db, d.tables).items() if not n and d.rows.get(t)]
    for t in todo:
        for st in d.rows[t]: _exec(db, _INTO.sub('INSERT OR IGNORE INTO', st, count=1))
        db.conn.commit()
    if made or todo:
        for st in d.indexes: _exec(db, st)
        db.conn.commit()
        db.meta.reflect(bind=db.engine)
    _seeded.add(nm)

# exec_driver_sql, not text(): the data contains literals like ':Pines' that
# SQLAlchemy would otherwise read as bind parameters
def _exec(db, st): db.conn.exec_driver_sql(st)

def _counts(db, tables):
    'Row counts for every dump table in one round trip — the remote connection makes each one expensive.'
    sel = ', '.join(f'(select count(*) from {ident(t, tables)}) as {ident(t, tables)}' for t in tables)
    return db.q(f'select {sel}')[0]

def ident(name, allowed):
    'Quote an identifier, but only after it matches something the schema actually reported.'
    if name not in allowed: raise ValueError(f'unknown identifier: {name!r}')
    return '"%s"' % name.replace('"', '""')

def qmark(db, sql, **params): return db.q(sql, **params)

# ── reflection ────────────────────────────────────────────────────────────────

def table_names(nm):
    'Dump tables that are actually there — the intersection is both the seed check and the boundary.'
    live = set(sa.inspect(get_db(nm).engine).get_table_names())
    return sorted(live & set(owned(nm)))

def reflect(nm, tbl):
    'Columns, primary key and foreign keys for one table, straight from the dialect inspector.'
    if tbl not in table_names(nm): raise KeyError(tbl)
    ins = sa.inspect(get_db(nm).engine)
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
