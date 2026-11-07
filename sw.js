/* Euro Signal : fichiers à empreinte (?v=…) servis par la copie du téléphone tant qu'ils ne changent pas ; page, liste des
   empreintes et le reste : réseau d'abord (toujours la dernière version et les données du soir, sans attendre le cache de GitHub
   Pages), copie locale si pas de connexion ou réseau trop lent. */
const CACHE = 'euro-signal-v5'; // v5 : page découpée en fichiers (app/, euro_signal/core.js)
const TIMEOUT_MS = 8000;
const VERSIONED = /[?&]v=[0-9a-f]{6,40}(&|$)/; // scripts (tools/stamp.mjs) et données (data/version.json, écrit à la publication)
self.addEventListener('install', () => {
  self.skipWaiting();
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
// copie d'un fichier à empreinte : gardée sous son adresse exacte et sous l'adresse simple (secours hors connexion) ; les copies
// des versions précédentes du même fichier sont effacées (le cache ne grossit pas d'un soir à l'autre)
function keep(ca, req, key, r) {
  return ca
    .keys()
    .then((ks) =>
      Promise.all(
        ks
          .filter((k) => k.url !== req.url && k.url.split('?')[0] === key && VERSIONED.test(k.url))
          .map((k) => ca.delete(k))
      )
    )
    .then(() => Promise.all([ca.put(req.url, r.clone()), ca.put(key, r.clone())]));
}
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin) return; // polices et autres sites : non gérés
  const key = e.request.url.split('?')[0].split('#')[0];
  if (VERSIONED.test(u.search)) {
    // contenu fixé par son empreinte : la copie locale est forcément la bonne
    e.respondWith(
      caches.open(CACHE).then((ca) =>
        ca.match(e.request.url).then(
          (m) =>
            m ||
            fetch(e.request).then(
              (r) => {
                if (r.ok) e.waitUntil(keep(ca, e.request, key, r.clone()));
                return r;
              },
              () => ca.match(key).then((m2) => m2 || Response.error())
            )
        )
      )
    );
    return;
  }
  const net = new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('délai')), TIMEOUT_MS);
    // page et données : adresse rendue unique pour passer le cache de GitHub Pages (jusqu'à 10 minutes de retard sinon)
    const fresh = /\.(html|json|js|css)$/.test(u.pathname) || u.pathname.endsWith('/'); // la page et ses scripts toujours de la même version
    const req = fresh
      ? new Request(key + (key.indexOf('?') > -1 ? '&' : '?') + '_=' + Date.now(), { credentials: 'same-origin' })
      : e.request;
    fetch(req, { cache: 'no-store' }).then(
      (r) => {
        clearTimeout(t);
        resolve(r);
      },
      (err) => {
        clearTimeout(t);
        reject(err);
      }
    );
  });
  e.respondWith(
    net
      .then((r) => {
        if (r.ok) {
          const c = r.clone();
          e.waitUntil(caches.open(CACHE).then((ca) => ca.put(key, c)));
        }
        return r;
      })
      .catch(() => caches.match(key).then((m) => m || fetch(e.request)))
  );
});
