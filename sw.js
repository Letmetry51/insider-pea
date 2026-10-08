/* Euro Signal : réseau d'abord (toujours les données du soir), copie locale si pas de connexion. */
const CACHE = 'euro-signal-v1';
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin) return; // polices et autres sites : non gérés
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const c = r.clone(); caches.open(CACHE).then((ca) => ca.put(e.request.url.split('?')[0], c)); }
    return r;
  }).catch(() => caches.match(e.request.url.split('?')[0]).then((m) => m || Response.error())));
});
