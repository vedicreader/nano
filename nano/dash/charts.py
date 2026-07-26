import re
from fastcore.all import AttrDict, L
from .cfg import cfg
from .data import DBS, get_db, table_names, reflect, profile, rowcount, ident
from .infer import roles, label_col, fmt_of, _h

__all__ = ['payload', 'stats', 'sparkline', 'page_rows', 'row_get', 'child_rows', 'child_count', 'headline']

# Reads that name rows go through fastsql's table API; the aggregates below stay hand-written
# because GROUP BY is not something rows_where models. _scatter is hand-written for a different
# reason: its rows go straight out as JSON, and the driver's plain floats serialise where the
# typed Decimals the table API returns would not.
KINDS = {'bar', 'hbar', 'line', 'area', 'doughnut', 'scatter'}
AGGS = {'sum', 'count', 'hist', 'raw'}
BUCKETS = {'%Y', '%Y-%m', '%Y-%m-%d'}
NONE = '(none)'

def _cols(db, tbl): return {c.name for c in reflect(db, tbl).cols}

def _check(p):
    'Every identifier in a chart request has to match something the schema reported. Nothing else reaches SQL.'
    db = p.get('db')
    if db not in DBS: raise ValueError('unknown database')
    tbl = p.get('t')
    if tbl not in table_names(db): raise ValueError('unknown table')
    cols = _cols(db, tbl)
    q = AttrDict(db=db, t=tbl, tq=ident(tbl, table_names(db)), cols=cols,
                 kind=p.get('kind'), agg=p.get('agg'), bucket=p.get('bucket'))
    if q.kind not in KINDS: raise ValueError('unknown chart kind')
    if q.agg not in AGGS: raise ValueError('unknown aggregate')
    if q.bucket and q.bucket not in BUCKETS: raise ValueError('unknown bucket')
    q.x, q.y = p.get('x') or None, p.get('y') or None
    q.xq = ident(q.x, cols) if q.x else None
    q.yq = ident(q.y, cols) if q.y else None
    j = p.get('join')
    if j:
        if j not in table_names(db): raise ValueError('unknown join table')
        jcol, jlabel = p.get('jcol'), p.get('jlabel')
        fk = reflect(db, tbl).fk_by_col.get(jcol)
        if not fk or fk.ref_table != j: raise ValueError('join is not a declared foreign key')
        q.update(j=j, jq=ident(j, table_names(db)), jcolq=ident(jcol, cols),
                 jlabelq=ident(jlabel, _cols(db, j)), jrefq=ident(fk.ref_col, _cols(db, j)),
                 jlabel=jlabel)
    return q

def payload(p):
    'Run a validated chart spec and return the JSON the browser draws.'
    q = _check(p)
    if q.agg == 'hist': return _hist(q)
    if q.agg == 'raw': return _scatter(q)
    if q.get('j'): return _grouped_join(q)
    if q.bucket: return _timeseries(q)
    return _grouped(q)

def _out(q, labels, data, label, fmt):
    return dict(kind=q.kind, agg=q.agg, labels=labels, fmt=fmt, series=[dict(label=label, data=data)])

def _clip(s, n=32): return s if len(s) <= n else s[:n - 1] + '…'

def _timeseries(q):
    db = get_db(q.db)
    val = f'sum({q.yq})' if q.y else 'count(*)'
    rows = db.q(f'select strftime(:b, {q.xq}) as k, {val} as v from {q.tq} '
                f'where {q.xq} is not null group by k order by k', b=q.bucket)
    label = _h(q.y) if q.y else 'Records'
    return _out(q, [r['k'] for r in rows], [r['v'] for r in rows], label,
                fmt_of(q.y, '') if q.y else 'int')

def _grouped(q):
    db = get_db(q.db)
    val = f'sum({q.yq})' if q.y else 'count(*)'
    # a "(none)" bar for a half-empty column outranks every real category and says
    # nothing the column profile doesn't already report
    rows = db.q(f'select {q.xq} as k, {val} as v from {q.tq} where {q.xq} is not null '
                f'group by k order by v desc')
    return _topn(q, rows, _h(q.y) if q.y else 'Rows', fmt_of(q.y, '') if q.y else 'int')

def _grouped_join(q):
    db = get_db(q.db)
    val = f'sum(c.{q.yq})' if q.y else 'count(*)'
    rows = db.q(f'select p.{q.jlabelq} as k, {val} as v from {q.tq} c '
                f'join {q.jq} p on c.{q.jcolq} = p.{q.jrefq} group by k order by v desc')
    return _topn(q, rows, _h(q.y) if q.y else 'Rows', fmt_of(q.y, '') if q.y else 'int')

def _topn(q, rows, label, fmt):
    '''Wide categories become a top-N list, not a top-N plus an "Other" bar that
    dwarfs everything it is meant to contextualise. The chart says it is a top N.'''
    keep = rows if q.kind != 'hbar' else rows[:cfg.top_n]
    out = _out(q, [NONE if r['k'] is None else _clip(str(r['k'])) for r in keep],
               [r['v'] for r in keep], label, fmt)
    out['omitted'] = len(rows) - len(keep)
    return out

def _hist(q):
    db = get_db(q.db)
    s = profile(q.db, q.t)['cols'][q.x]
    lo, hi = s.get('lo'), s.get('hi')
    if lo is None or hi is None or hi == lo: raise ValueError('column has no spread to bin')
    bins = cfg.hist_bins
    w = (hi - lo) / bins
    rows = db.q(f'select min(cast(({q.xq} - :lo) / :w as integer), :top) as b, count(*) as v '
                f'from {q.tq} where {q.xq} is not null group by b order by b', lo=lo, w=w, top=bins - 1)
    counts = {r['b']: r['v'] for r in rows}
    fmt = fmt_of(q.x, s['type'])
    labels = [_edge(lo + i * w, fmt) for i in range(bins)]
    return dict(kind='bar', agg='hist', labels=labels, fmt='int', xfmt=fmt,
                series=[dict(label='Rows', data=[counts.get(i, 0) for i in range(bins)])])

def _edge(v, fmt):
    if fmt == 'ms': return f'{v / 60000:.1f}m'
    if fmt == 'bytes': return f'{v / 1048576:.1f}MB'
    if fmt == 'money': return f'{v:,.2f}'
    return f'{v:,.0f}' if abs(v) >= 100 else f'{v:,.2f}'.rstrip('0').rstrip('.')

def _scatter(q):
    db = get_db(q.db)
    rows = db.q(f'select {q.xq} as x, {q.yq} as y from {q.tq} '
                f'where {q.xq} is not null and {q.yq} is not null limit 2000')
    return dict(kind='scatter', agg='raw', labels=[], fmt=fmt_of(q.y, ''), xfmt=fmt_of(q.x, ''),
                series=[dict(label=f'{_h(q.y)} vs {_h(q.x)}', data=[dict(x=r['x'], y=r['y']) for r in rows])])

# ── stats & sparklines (server-rendered, no JS) ───────────────────────────────

def stats(db, tbl, col):
    'Mean, σ and the quantiles that make a stat tile worth reading.'
    s = profile(db, tbl)['cols'][col]
    if s['kind'] != 'num' or not s.get('sd'): return None
    t, qc = _t(db, tbl), ident(col, _cols(db, tbl))
    nn = f'{qc} is not null'
    n = t.count_where(nn)
    if not n: return None
    def pick(frac):
        r = list(t.rows_where(nn, order_by=qc, select=qc, limit=1, offset=max(0, int(n * frac) - 1)))
        return r[0][col] if r else None
    return AttrDict(n=n, mean=s['mean'], sd=s['sd'], lo=s['lo'], hi=s['hi'],
                    median=pick(0.5), p95=pick(0.95), fmt=fmt_of(col, s['type']))

def sparkline(vals, w=120, h=28):
    'Inline SVG polyline — no canvas, no JS, inherits the theme through currentColor.'
    from fastcore.xml import Svg, Polyline, FT
    vals = [v for v in vals if v is not None]
    if len(vals) < 2: return None
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = w / (len(vals) - 1)
    pts = ' '.join(f'{i * step:.1f},{h - (v - lo) / rng * (h - 2) - 1:.1f}' for i, v in enumerate(vals))
    return Svg(Polyline(points=pts, fill='none', stroke='var(--chart-1)', stroke_width='1.5',
                        stroke_linejoin='round', stroke_linecap='round'),
               viewBox=f'0 0 {w} {h}', preserveAspectRatio='none', cls='spark', aria_hidden='true')

def headline(db):
    'The handful of numbers worth putting above the charts, found the same way the charts are.'
    from .data import schema
    from .infer import roles, _h
    sch = schema(db)
    tiles = [AttrDict(label='Tables', value=f'{len(sch):,}'),
             AttrDict(label='Rows', value=f'{sum(rowcount(db, t) for t in sch):,}')]
    # a summed *total* is revenue; a summed *unit price* is nothing anybody asked for,
    # so per-unit columns only get the headline when there is no true total anywhere
    best = None
    for rank, pat in enumerate((r'total|revenue|amount|sales', r'price|cost|balance')):
        for t in sch:
            rl = roles(db, t)
            money = [c for c, s in rl.items() if s.role == 'measure' and re.search(pat, c, re.I)
                     and (s.get('total') or 0) > 0]
            if not money: continue
            c = max(money, key=lambda c: rl[c].total)
            if not best or rl[c].total > best[2]: best = (t, c, rl[c].total)
        if best: break
    if not best: return tiles
    t, c, total = best
    st = stats(db, t, c)
    spark = None
    tcol = next((k for k, s in roles(db, t).items() if s.role == 'temporal'), None)
    if tcol:
        pl = payload(dict(db=db, t=t, kind='line', x=tcol, y=c, agg='sum', bucket='%Y-%m'))
        spark = pl['series'][0]['data']
    lbl = _h(c) if re.match(r'total', c, re.I) else f'Total {_h(c)}'
    tiles.append(AttrDict(label=lbl, value=_money(total), spark=spark,
                          sub=f'{_h(t)} · {rowcount(db, t):,} rows'))
    if st: tiles += [AttrDict(label=f'Mean {_h(c).lower()}', value=_money(st.mean), sub=f'median {_money(st.median)}'),
                     AttrDict(label='Std deviation', value=_money(st.sd), sub=f'p95 {_money(st.p95)}')]
    return tiles

def _money(v):
    try: return f'{float(v):,.2f}'
    except Exception: return str(v)

# ── row access for the explorer ───────────────────────────────────────────────

def _t(db, tbl):
    if tbl not in table_names(db): raise KeyError(tbl)
    return get_db(db).t[tbl]

def page_rows(db, tbl, page=0, sort=None, desc=False):
    order = f'{ident(sort, _cols(db, tbl))} {"desc" if desc else "asc"}' if sort else None
    return list(_t(db, tbl).rows_where(order_by=order, limit=cfg.rows_per_page, offset=page * cfg.rows_per_page))

def row_get(db, tbl, pk):
    if not reflect(db, tbl).pk: return None
    return _t(db, tbl).get(pk, as_cls=False, default=None)

def _where(db, child, col): return f'{ident(col, _cols(db, child))} = :v'

def child_count(db, child, col, val):
    return _t(db, child).count_where(_where(db, child, col), dict(v=val))

def child_rows(db, child, col, val, limit=None):
    return list(_t(db, child).rows_where(_where(db, child, col), dict(v=val), limit=limit or cfg.rel_preview))
