from fasthtml.common import *
from fasthtml.common import Meta, Favicon, Socials, Link, serve, Script, JSONResponse, Div, P
from .core import *
from nano import auth as a, blog as b

__all__ = ['launch', 'nano']

f = ['Libre+Baskerville', 'Fira+Code', 'Playfair+Display']
fonts = ('&'.join(map(lambda x: 'family=%s:wght@300;400;500;600;700' % x, f)) + '&display=swap')

hdrs = [
    Meta(charset='UTF-8'),
    Meta(name='description', content=cfg.site_description),
    Meta(name='author', content=cfg.site_author),
    Meta(name='keywords', content=cfg.site_keywords),
    Meta(name='robots', content='index, follow'),
    Meta(name='theme-color', content='#FCA847'),
    Meta(name='apple-mobile-web-app-capable', content='yes'),
    Meta(name='apple-mobile-web-app-status-bar-style', content='default'),
    Meta(name='mobile-web-app-capable', content='yes'),
    Meta(name='mobile-web-app-status-bar-style', content='default'),
    *Favicon('/static/favicon.ico', '/static/favicon-dark.ico'),
    Link(rel='icon', type='image/svg+xml', href='/static/favicon.svg'),
    Link(rel='stylesheet', href='https://fonts.googleapis.com/css2?%s' % fonts, defer=True),
    *Socials(title=cfg.app_nm, description=cfg.site_description, site_name=cfg.domain, image='/static/favicon.svg',
             url=cfg.domain), *themes()]

def nf(req, exc): return not_found()
kw,exh = {'class': 'hidden', 'hx-ext': 'preload', 'hx-boost': 'true'}, {404: nf, 500: nf, 403: nf}
nano, rt = fast_app(hdrs=hdrs, bodykw=kw, live=not_prod(), title=cfg.app_nm, exts='preload', pico=False, exception_handlers=exh)

# connect your blocks
b.connect(nano)
a.connect(nano) # auth needs to be the last to connect. it reads RouteOverrides skip list to skip auth

def showcase(auth):
    if auth: return home()
    txt = Div(
        P('Welcome to Lego', cls='text-xl font-bold align-center'),
        P('make coding fun again', cls='text-xs font-bold mb-4 align-center'),
        P('Write code one block at a time. Use syntactic sugars like multi process locking, backups, caching and more. Modify, hack and refactor anything.', cls='mb-2'),
        P('Lego uses functional, succinct code. So no ruff, pep or linters. Its optimised for reading on mobiles.',cls='mb-2'),
        cls='mx-auto mt-4')
    td_get, td_tgt, bj_get, bj_tgt = '/', '#main-content', f'{a.Routes.auth_modal}?step={a.Step.login}', '#showcase'
    btns = Div(cls='flex justify-center space-x-4 mt-4')(
        Button('Test Drive', hx_get=td_get, hx_target=td_tgt, cls=[ButtonT.default, TextT.sm]),
        Button('Begin Journey', hx_get=bj_get, hx_target=bj_tgt, cls=[ButtonT.primary, TextT.sm]))
    c = Div(txt, btns, id='showcase', cls='max-w-xs align-center mx-auto')
    return landing(c)

# add default routes. the blocks can override these. the first in line wins.
nano.get('/')(showcase)
nano.get('/health')(lambda req: JSONResponse({'status': 'ok'}))

def launch(): serve('nano', 'nano', port=cfg.port)
if __name__ == '__main__': launch()
