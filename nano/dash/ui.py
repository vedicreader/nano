from decimal import Decimal
from urllib.parse import urlencode, quote
from fastcore.xml import *
from fasthtml.common import *
from fastcore.all import timed_cache
from nano.core import lc_icon, TextT, ButtonT, PresetsT, asset_js, asset_css, vendor_js, Badge, BadgePresetsT
from .cfg import Routes, cfg
from .data import DBS, schema, reflect, profile, table_names, rowcount
from .infer import roles, specs_for_db, specs_for_table, label_col, fmt_of, _h
from .charts import stats, sparkline, page_rows, row_get, child_rows, child_count, headline

__all__ = ['dash_head', 'index_view', 'db_view', 'table_view', 'row_view', 'rel_view']

@timed_cache(seconds=3600)
def dash_head():
    'Everything the block needs and nothing else asks for: its own styles, Chart.js, the nano wrapper.'
    from pathlib import Path
    here = Path(__file__).parent
    return [asset_css(here / 'dash.css'), vendor_js('chart.umd.min.js'), asset_js(here / 'chart.js', defer=True)]

# ── chrome ────────────────────────────────────────────────────────────────────

def crumbs(*parts):
    out = []
    for i, (txt, href) in enumerate(parts):
        if i: out.append(Span('/', cls='sep'))
        out.append(dlink(txt, href=href) if href else Span(txt))
    return Div(*out, cls='crumbs')

def dlink(*c, href, **kw):
    '''Every in-dashboard link is a real navigation, never an hx-boost body swap.
    Boost is the one step in this path that fails *silently*: on a non-2xx htmx fires
    htmx:responseError and does nothing at all — no navigation, no error page. That is
    exactly what "clicking does nothing" looks like. Unboosted, the browser shows
    whatever the server actually returned. Dash pages also carry their own
    <script src> for Chart.js, which a real load is guaranteed to run.'''
    return A(*c, href=href, hx_boost='false', **kw)

def wrap(*content, head=None): return Div(head, *content, cls='dash-wrap')

def _fmt_cell(v, kind='text'):
    # fastsql hands back the column's declared type, so money arrives as Decimal, not float
    if v is None: return Td('null', cls='null')
    if kind == 'num': return Td(f'{v:,}' if isinstance(v, int) else f'{v:,.2f}' if isinstance(v, (float, Decimal)) else str(v), cls='num')
    s = str(v)
    return Td(s if len(s) <= 60 else s[:57] + '…', title=s if len(s) > 60 else None)

def _pk_href(db, tbl, pk): return Routes.row.format(db=db, table=quote(tbl), pk=quote(str(pk)))

# ── /dash ─────────────────────────────────────────────────────────────────────

def index_view():
    cards = []
    for k, d in DBS.items():
        sch = schema(k)
        cards.append(dlink(Div(H3(d.nm), P(d.about, cls='chart-why'),
                           Div(*[Span(f'{t} · {rowcount(k, t):,}', cls='role-chip') for t in list(sch)[:6]],
                               Span(f'+{len(sch) - 6} more', cls='role-chip') if len(sch) > 6 else None,
                               cls='flex flex-wrap gap-1 mt-2'),
                           cls='chart-card'), href=Routes.db.format(db=k), cls='block'))
    return wrap(Div(H1('Dashboards', cls='m-0'),
                    P('Charts and tables inferred from whatever the database happens to contain.', cls='chart-why'),
                    cls='dash-head'),
                Div(*cards, cls='chart-grid'))

# ── /dash/{db} ────────────────────────────────────────────────────────────────

def tile(t):
    return Div(Div(t.label, cls='tile-label'), Div(t.value, cls='tile-value'),
               Div(t.sub, cls='tile-sub') if t.get('sub') else None,
               sparkline(t.spark) if t.get('spark') else None, cls='tile')

def chart_card(spec, wide=False):
    src = f'/dash/chart.json?{urlencode(spec.qs)}'
    return Div(Header(H3(spec.title), P(spec.why, cls='chart-why')),
               Div(Div('Loading…', cls='chart-skel'),
                   Canvas(data_chart_src=src), cls=f'chart-box{" tall" if spec.kind == "hbar" else ""}'),
               Div(Div(cls='chart-legend'), cls='chart-foot'),
               # the light-mode palette runs under 3:1 on three slots, so the numbers
               # are always reachable without reading a colour
               Details(Summary('Show data'), Div(cls='tbl-scroll')(Table(cls='dash-tbl')), cls='chart-data'),
               cls=f'chart-card{" wide" if wide else ""}')

def db_view(db):
    sch, specs = schema(db), specs_for_db(db)
    tiles = Div(*[tile(t) for t in headline(db)], cls='tile-grid')
    charts = Div(*[chart_card(s, wide=(s.kind == 'area' or s.kind == 'line')) for s in specs], cls='chart-grid')
    tbls = Div(cls='tbl-scroll')(Table(cls='dash-tbl')(
        Thead(Tr(Th('Table'), Th('Rows', cls='num'), Th('Columns'), Th('References'), Th('Referenced by'))),
        Tbody(*[Tr(Td(dlink(t, href=Routes.table.format(db=db, table=quote(t)))),
                   Td(f'{rowcount(db, t):,}', cls='num'), Td(str(len(sch[t].cols))),
                   Td(', '.join(f.ref_table for f in sch[t].fks) or '—'),
                   Td(', '.join(c.table for c in sch[t].children) or '—'))
                for t in sch])))
    return wrap(Div(crumbs(('Dashboards', Routes.index), (DBS[db].nm, None)), cls='dash-head'),
                H1(DBS[db].nm, cls='m-0'), P(DBS[db].about, cls='chart-why mb-4'),
                tiles, charts,
                H2('Tables', cls='mt-6 mb-2'), tbls)

# ── /dash/{db}/{table} ────────────────────────────────────────────────────────

def _col_row(db, tbl, name, s):
    bits = []
    if s.role in ('measure',):
        bits = [f'min {_n(s.lo)}', f'max {_n(s.hi)}', f'mean {_n(s.mean)}', f'σ {_n(s.sd)}']
    elif s.role == 'temporal': bits = [str(s.get('lo'))[:10], '→', str(s.get('hi'))[:10]]
    elif s.get('maxlen') is not None: bits = [f'max len {s.maxlen}']
    ref = dlink(f'{s.fk.ref_table}.{s.fk.ref_col}', href=Routes.table.format(db=db, table=quote(s.fk.ref_table))) if s.get('fk') else '—'
    return Tr(Td(Div(Span(name), Span(s.role, cls='role-chip'), cls='col-head')),
              Td(s.type), Td(f'{s.distinct:,}', cls='num'), Td(f'{s.nulls:,}', cls='num'),
              Td(ref), Td(' '.join(bits)))

def _n(v):
    if v is None: return '—'
    if isinstance(v, float): return f'{v:,.2f}'
    return f'{v:,}' if isinstance(v, int) else str(v)

def table_view(db, tbl, page=0):
    r, rl = reflect(db, tbl), roles(db, tbl)
    n = rowcount(db, tbl)
    rows = page_rows(db, tbl, page)
    kinds = {c.name: rl[c.name].kind for c in r.cols}
    pk = r.pk[0] if r.pk else None
    specs = specs_for_table(db, tbl, limit=4)
    body = []
    for row in rows:
        tds = []
        for c in r.cols:
            v, td = row[c.name], _fmt_cell(row[c.name], kinds[c.name])
            f = r.fk_by_col.get(c.name)
            if f and v is not None: td = Td(dlink(str(v), href=_pk_href(db, f.ref_table, v)), cls='num')
            elif c.name == pk and v is not None: td = Td(dlink(str(v), href=_pk_href(db, tbl, v)), cls='num')
            tds.append(td)
        body.append(Tr(*tds))
    pages = (n + cfg.rows_per_page - 1) // cfg.rows_per_page
    nav = Div(Span(f'Rows {page * cfg.rows_per_page + 1:,}–{min(n, (page + 1) * cfg.rows_per_page):,} of {n:,}'),
              Div(dlink('← Prev', href=f'?page={page - 1}', cls=f'{ButtonT.default} {ButtonT.xs}') if page else None,
                  dlink('Next →', href=f'?page={page + 1}', cls=f'{ButtonT.default} {ButtonT.xs}') if page + 1 < pages else None,
                  cls='flex gap-2'), cls='pager')
    cols_tbl = Div(cls='tbl-scroll')(Table(cls='dash-tbl')(
        Thead(Tr(Th('Column'), Th('Type'), Th('Distinct', cls='num'), Th('Nulls', cls='num'), Th('References'), Th('Profile'))),
        Tbody(*[_col_row(db, tbl, c.name, rl[c.name]) for c in r.cols])))
    return wrap(Div(crumbs(('Dashboards', Routes.index), (DBS[db].nm, Routes.db.format(db=db)), (tbl, None)), cls='dash-head'),
                H1(tbl, cls='m-0'), P(f'{n:,} rows · {len(r.cols)} columns · '
                                      f'{len(r.fks)} outbound, {len(schema(db)[tbl].children)} inbound references',
                                      cls='chart-why mb-4'),
                Div(*[chart_card(s) for s in specs], cls='chart-grid mb-6') if specs else None,
                H2('Columns', cls='mt-6 mb-2'), cols_tbl,
                H2('Rows', cls='mt-6 mb-2'),
                Div(cls='tbl-scroll')(Table(cls='dash-tbl')(
                    Thead(Tr(*[Th(c.name) for c in r.cols])), Tbody(*body))), nav)

# ── /dash/{db}/{table}/{pk} — the nested view ─────────────────────────────────

def _title_for(db, tbl, row):
    # strict: a row is titled by a real name column or not at all — heading an invoice
    # with its billing address because that was the first text column reads as a bug
    lab = label_col(db, tbl, strict=True)
    return str(row.get(lab) or '') if lab else ''

def row_view(db, tbl, pk, row):
    r, rl = reflect(db, tbl), roles(db, tbl)
    fields = []
    for c in r.cols:
        v = row[c.name]
        f = r.fk_by_col.get(c.name)
        if f and v is not None:
            parent = row_get(db, f.ref_table, v)
            lab = _title_for(db, f.ref_table, parent) if parent else None
            dd = dlink(lab or str(v), href=_pk_href(db, f.ref_table, v))
        else:
            dd = 'null' if v is None else str(v)
        fields.append(Div(Dt(c.name), Dd(dd), cls='field'))
    kids = schema(db)[tbl].children
    return wrap(Div(crumbs(('Dashboards', Routes.index), (DBS[db].nm, Routes.db.format(db=db)),
                           (tbl, Routes.table.format(db=db, table=quote(tbl))), (str(pk), None)), cls='dash-head'),
                H1(_title_for(db, tbl, row) or f'{tbl} {pk}', cls='m-0'),
                P(f'{tbl} · {r.pk[0] if r.pk else "row"} {pk}', cls='chart-why mb-4'),
                Dl(*fields, cls='field-grid'),
                H2('Related', cls='mt-6 mb-2') if kids else None,
                Div(*[_rel_node(db, tbl, pk, k, 0) for k in kids], cls='rel-tree') if kids else None)

def _rel_node(db, parent, pk, kid, depth):
    n = child_count(db, kid.table, kid.col, pk)
    url = Routes.rel.format(db=db, table=quote(parent), pk=quote(str(pk)), child=quote(kid.table)) + f'?col={quote(kid.col)}&depth={depth}'
    return Details(Summary(lc_icon('table-2', 14), Span(f'{kid.table}'),
                           Span(f'via {kid.col}', cls='role-chip'), Span(f'{n:,}', cls='rel-count')),
                   Div(Div('Loading…', cls='chart-skel'), cls='rel-body',
                       hx_get=url, hx_trigger='toggle once from:closest details', hx_swap='innerHTML'),
                   cls='rel-node')

def rel_view(db, child, col, val, depth=0):
    'One nesting level: the child rows, each able to open its own children.'
    r = reflect(db, child)
    rows = child_rows(db, child, col, val, limit=cfg.rel_preview)
    n = child_count(db, child, col, val)
    kinds = {c.name: k for c, k in [(c, profile(db, child)['cols'][c.name]['kind']) for c in r.cols]}
    pk = r.pk[0] if r.pk else None
    body = []
    for row in rows:
        tds = []
        for c in r.cols:
            v = row[c.name]
            f = r.fk_by_col.get(c.name)
            if f and v is not None: tds.append(Td(dlink(str(v), href=_pk_href(db, f.ref_table, v)), cls='num'))
            elif c.name == pk and v is not None: tds.append(Td(dlink(str(v), href=_pk_href(db, child, v)), cls='num'))
            else: tds.append(_fmt_cell(v, kinds[c.name]))
        body.append(Tr(*tds))
    tbl = Div(cls='tbl-scroll')(Table(cls='dash-tbl')(
        Thead(Tr(*[Th(c.name) for c in r.cols])), Tbody(*body)))
    more = None
    if n > len(rows):
        more = P(dlink(f'View all {n:,} in {child} →', href=Routes.table.format(db=db, table=quote(child))),
                 cls='chart-why mt-2')
    # one level of inline nesting, then the row page takes over — otherwise a deep
    # schema would try to open the whole database in one response
    deeper = None
    if depth < 2 and pk:
        kids = schema(db)[child].children
        if kids and rows:
            deeper = Div(P(f'Inside {child} {rows[0][pk]}', cls='chart-why mt-3'),
                         Div(*[_rel_node(db, child, rows[0][pk], k, depth + 1) for k in kids], cls='rel-tree'))
    return Div(tbl, more, deeper)
