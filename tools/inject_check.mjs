// Contrôle de sécurité de la page sur des données piégées (tools/poison.py) : aucun texte venu des sources (noms, titres de
// presse, descriptions…) ne doit pouvoir devenir du code. Échec si une balise injectée apparaît, si un lien « javascript: » ou
// un attribut d'événement (onerror, onclick…) est créé, ou si le code piégé s'exécute.
//
//   python tools/poison.py data && node tools/inject_check.mjs        (sur une copie des données ; Playwright et Chromium)
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch (e) {
  ({ chromium } = await import('/opt/node-tools/node_modules/playwright/index.mjs'));
}
const TY = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
};
const srv = http.createServer((q, r) => {
  const p = path.join(ROOT, decodeURIComponent(q.url.split('?')[0].split('#')[0]));
  if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) {
    r.writeHead(404);
    r.end();
    return;
  }
  r.writeHead(200, { 'Content-Type': TY[path.extname(p)] || 'application/octet-stream' });
  fs.createReadStream(p).pipe(r);
});
await new Promise((r) => srv.listen(0, r));
const URL0 = 'http://localhost:' + srv.address().port + '/euro-signal.html';
const main = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'euro-signal.json'), 'utf8'));
const browser = await chromium.launch();
const found = new Map(),
  errs = [];
let pages = 0;
async function open() {
  const p = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await p.addInitScript(() => {
    window.__hits = [];
    window.__xss = (n) => window.__hits.push(n);
  });
  await p.route(/fonts\./, (r) => r.abort());
  p.on('pageerror', (e) => errs.push(String(e.message).slice(0, 160)));
  await p.goto(URL0);
  await p
    .waitForFunction(
      () => window.__ES_STATE && window.__ES_STATE.mode !== 'chargement' && !window.__ES_STATE.busy,
      null,
      {
        timeout: 20000,
      }
    )
    .catch(() => {});
  return p;
}
async function scan(p, where) {
  pages++;
  const bad = await p.evaluate(() => {
    document.querySelectorAll('details').forEach((d) => {
      d.open = true;
    });
    const out = [];
    document
      .querySelectorAll('img[src="x"]')
      .forEach((e) => out.push('balise injectée : ' + e.outerHTML.slice(0, 120)));
    document.querySelectorAll('a[href]').forEach((a) => {
      if (/^\s*javascript:/i.test(a.getAttribute('href'))) out.push('lien javascript: ' + a.outerHTML.slice(0, 120));
    });
    document.querySelectorAll('*').forEach((e) => {
      for (const at of e.attributes)
        if (/^on/i.test(at.name)) out.push('attribut ' + at.name + ' : ' + e.outerHTML.slice(0, 120));
    });
    return out;
  });
  await p.waitForTimeout(150);
  const hits = await p.evaluate(() => window.__hits.slice());
  bad.forEach((x) => found.set(x, where));
  if (hits.length) found.set('code piégé exécuté (' + hits.join(',') + ')', where);
}
{
  const p = await open();
  await scan(p, 'tableau de bord');
  for (const v of ['classement', 'secteurs', 'inities', 'alertes', 'aide']) {
    const t = p.locator(`nav [data-v="${v}"]`).first();
    if (await t.count()) {
      await t.click().catch(() => {});
      await p.waitForTimeout(600);
      await scan(p, 'onglet ' + v);
    }
  }
  await p.goto(URL0);
  await p.waitForTimeout(1500);
  for (const a of ['psyOpen', 'pick3', 'valueOpen', 'weekBrk', 'rankWhy']) {
    const t = p.locator(`[data-a="${a}"]`).first();
    if (await t.count()) {
      await t.click().catch(() => {});
      await p.waitForTimeout(500);
      await scan(p, 'action ' + a);
    }
  }
  await p.close();
}
const keys = new Set();
((main.rank || {}).rows || [])
  .filter((r) => !(r.out || []).length)
  .slice(0, 20)
  .forEach((r) => keys.add(r.isin ? '#' + r.isin : '#co=' + encodeURIComponent(r.sym)));
Object.keys(main.inst || {})
  .filter((_, k) => k % 25 === 0)
  .forEach((i) => keys.add('#' + i));
const Q = [...keys];
await Promise.all(
  Array.from({ length: 3 }, async () => {
    const p = await open();
    while (Q.length) {
      const h = Q.shift();
      await p.evaluate((h) => {
        location.hash = h;
      }, h);
      await p
        .waitForFunction(() => document.querySelector('.fhead') && !/Chargement/.test(document.body.innerText), null, {
          timeout: 6000,
        })
        .catch(() => {});
      await scan(p, 'fiche ' + h);
    }
    await p.close();
  })
);
await browser.close();
srv.close();
console.log(`Données piégées : ${pages} vues examinées, ${found.size} faille(s), ${errs.length} erreur(s) JavaScript`);
for (const [k, w] of found) console.log('- ' + w + ' · ' + k);
[...new Set(errs)].slice(0, 5).forEach((e) => console.log('  erreur JavaScript : ' + e));
process.exit(found.size || pages < 10 ? 1 : 0);
