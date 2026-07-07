const htmlElement = document.documentElement;
const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
const lego = '__NANO__';
let __NANO__ = JSON.parse(localStorage.getItem(lego) || '{{__state__}}');
function storeState(key, value) {__NANO__[key] = value; localStorage.setItem(lego, JSON.stringify(__NANO__));}
function getState(key){return __NANO__[key];}
function removeState(key) {delete  __NANO__[key]; localStorage.setItem(key, JSON.stringify(__NANO__)); }
function setTheme(color,fn=null, ...args) {
    if (color === null || color === undefined) {return;}
    htmlElement.classList.remove(__NANO__.theme);
    htmlElement.classList.add(color);
    storeState('theme', color);
    if (typeof fn === 'function') {fn(...args);}
}
function setMode(mode,fn=null, ...args) {
    if (mode === null || mode === undefined) {return;}
    if (mode === 'dark') {
        htmlElement.classList.remove('light');
        htmlElement.classList.remove('auto');
        htmlElement.classList.add('dark');
        storeState('mode', mode);
    } if (mode === 'light') {
        htmlElement.classList.remove('dark');
        htmlElement.classList.remove('auto');
        htmlElement.classList.add('light');
        storeState('mode', mode);
    } if (mode === 'auto') {
        let isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (isDark) {
            htmlElement.classList.remove('light');
            htmlElement.classList.add('dark');
        } else {
            htmlElement.classList.remove('dark');
            htmlElement.classList.add('light');
        }
        htmlElement.classList.add('auto');
        storeState('mode', mode);
    }
    if (typeof fn === 'function') {fn(...args);}
}
function setRadii(radii,fn=null, ...args) {
    if (radii === null || radii === undefined) {return;}
    htmlElement.classList.remove(__NANO__.radii);
    htmlElement.classList.add(radii);
    storeState('radii', radii);
    if (typeof fn === 'function') {fn(...args);}
}
function setShadows(shadows,fn=null, ...args) {
    if (shadows === null || shadows === undefined) {return;}
    htmlElement.classList.remove(__NANO__.shadows);
    htmlElement.classList.add(shadows);
    storeState('shadows', shadows);
    if (typeof fn === 'function') {fn(...args);}
}
function setFont(font,fn=null, ...args) {
    if (font === null || font === undefined) {return;}
    htmlElement.classList.remove(__NANO__.font);
    htmlElement.classList.add(font);
    storeState('font', font);
    if (typeof fn === 'function') {fn(...args);}
}
function setup() {
    setTheme('{{__theme__}}');
    setMode(__NANO__.mode);
    setRadii(__NANO__.radii);
    setShadows(__NANO__.shadows);
    setFont(__NANO__.font);}

mediaQuery.addEventListener('change', (event) => {if (!htmlElement.classList.contains('auto')) return;setMode('auto');});
document.addEventListener('uk-theme-switcher:change', (e) => {
    _.each(e.detail.value, (v,k) => {
    if (k === 'theme') setTheme(v);if (k === 'radii') setRadii(v);
    if (k === 'shadows') setShadows(v); if (k === 'font') setFont(v);});
});
_.defer(setup);
function* cycle(...items) {
  while(true)
    yield* items;
}
