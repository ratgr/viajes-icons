const CACHE = 'viajes-17858634';
const FILES = ['./index.html', './japon.html'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(FILES.map(function (u) {
    return fetch(new Request(u, { cache: 'reload' })).then(function (r) { return c.put(u, r); });
  }))));
});
self.addEventListener('message', e => { if (e.data === 'skip') self.skipWaiting(); });
const FCACHE = 'viajes-fotos';
// Modo ahorro (bandera que escribe la pagina): true => cero peticiones a la red.
const ahorro = () => caches.match('cfg-ahorro').then(r => r ? r.text() : '0').then(v => v === '1').catch(() => false);
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE && k !== FCACHE && k !== 'viajes-cfg').map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('viajes-icons')) {
    e.respondWith(caches.open(FCACHE).then(c => c.match(e.request).then(m =>
      m || ahorro().then(save => save ? Response.error()
        : fetch(e.request).then(r => { if (r.ok) c.put(e.request, r.clone()); return r; })))));
    return;
  }
  // App (HTML): responde YA desde cache y revalida en segundo plano.
  // En modo ahorro NO toca la red (ni revalida la pagina de ~1.2MB).
  // Asi la app abre al instante y NO depende del gist en cada apertura
  // (se acaban los reloads y la reautenticacion de gist).
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(cached =>
    ahorro().then(save => {
      if (cached && save) return cached;
      const net = fetch(e.request).then(r => {
        if (r && r.ok) caches.open(CACHE).then(c => c.put(e.request, r.clone()));
        return r;
      }).catch(() => cached || caches.match('./index.html'));
      return cached || net;
    })
  ));
});
