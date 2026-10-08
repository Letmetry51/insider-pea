/* Euro Signal : réseau d'abord (toujours les données du soir), copie locale si pas de connexion ou réseau trop lent. */
const CACHE = 'euro-signal-v2';
const TIMEOUT_MS = 8000;
self.addEventListener('install', () => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin) return; // polices et autres sites : non gérés
  const key = e.request.url.split('?')[0].split('#')[0];
  const net = new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('délai')), TIMEOUT_MS);
    fetch(e.request).then((r) => { clearTimeout(t); resolve(r); }, (err) => { clearTimeout(t); reject(err); });
  });
  e.respondWith(net.then((r) => {
    if (r.ok) { const c = r.clone(); e.waitUntil(caches.open(CACHE).then((ca) => ca.put(key, c))); }
    return r;
  }).catch(() => caches.match(key).then((m) => m || fetch(e.request))));
});
