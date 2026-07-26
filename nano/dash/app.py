from fasthtml.common import JSONResponse
from fastcore.xml import Div
from nano.core import base, not_found, RouteOverrides
from .cfg import Routes, cfg
from .data import DBS, table_names, reflect
from .charts import payload, row_get
from .ui import dash_head, index_view, db_view, table_view, row_view, rel_view

__all__ = ['connect', 'Routes']

def _page(content, auth, title):
    return (*base(content, auth, title=title), *dash_head())

def _known(db, tbl=None):
    if db not in DBS: return False
    return tbl is None or tbl in table_names(db)

def dash_index(req, auth=None): return _page(index_view(), auth, 'Dashboards')

def dash_db(req, db: str, auth=None):
    if not _known(db): return not_found()
    return _page(db_view(db), auth, f'{DBS[db].nm} · Dashboards')

def dash_table(req, db: str, table: str, page: int = 0, auth=None):
    if not _known(db, table): return not_found()
    return _page(table_view(db, table, max(0, page)), auth, f'{table} · {DBS[db].nm}')

def dash_row(req, db: str, table: str, pk: str, auth=None):
    if not _known(db, table): return not_found()
    row = row_get(db, table, pk)
    if row is None: return not_found()
    return _page(row_view(db, table, pk, row), auth, f'{table} {pk}')

def dash_rel(req, db: str, table: str, pk: str, child: str, col: str = '', depth: int = 0, auth=None):
    'htmx partial: one level of children, loaded when the reader opens the section.'
    if not _known(db, child): return not_found()
    if col not in reflect(db, child).fk_by_col: return Div('Not a foreign key', cls='chart-why')
    return rel_view(db, child, col, pk, depth=min(int(depth), 2))

def dash_chart(req):
    try: return JSONResponse(payload(dict(req.query_params)))
    except (ValueError, KeyError) as e: return JSONResponse({'error': str(e)}, status_code=400)

def connect(app):
    if cfg.public: RouteOverrides.skip += Routes.skip
    RouteOverrides.nav = RouteOverrides.nav + [('Dashboards', Routes.index)]
    app.get(Routes.chart)(dash_chart)   # before /dash/{db}, which would otherwise swallow it
    app.get(Routes.index)(dash_index)
    app.get(Routes.db)(dash_db)
    app.get(Routes.table)(dash_table)
    app.get(Routes.row)(dash_row)
    app.get(Routes.rel)(dash_rel)
