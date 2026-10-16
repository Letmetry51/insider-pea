// Contrôle du tableau de bord comme un lecteur sur téléphone, chaque soir après le calcul : toutes les fiches ouvertes,
// panneaux dépliés ; textes illisibles (null, NaN, undefined…), débordements de l'écran, erreurs JavaScript, fiches vides ;
// onglets ; échantillon de fiches du catalogue. N'arrête jamais le calcul : écrit data/diagnostics/ui-check.json et .txt.
//
//   node euro_signal/ui_check.mjs            (après euro_signal/build.mjs ; Playwright et Chromium nécessaires)
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'data', 'diagnostics');
const W = 390, H = 844, PAGES = 4;
const BAD = /\bNaN\b|\bundefined\b|\[object Object\]|\bInfinity\b|\bnull\b/;
const report = { date: new Date().toISOString().slice(0, 10), at: new Date().toISOString(), fiches: 0, catalogue: 0, views: 0, problems: [], jsErrors: [] };

let chromium;
try { ({ chromium } = await import('playwright')); } catch (e) {
  try { ({ chromium } = await import('/opt/node-tools/node_modules/playwright/index.mjs')); } catch (e2) { finish('Playwright indisponible : contrôle des fiches non fait'); }
}

// petit serveur de fichiers (la page lit ses données en relatif)
const TYPES = { '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.js': 'text/javascript', '.png': 'image/png', '.webmanifest': 'application/manifest+json' };
const server = http.createServer((req, res) => {
  const p = path.join(ROOT, decodeURIComponent(req.url.split('?')[0].split('#')[0]));
  if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(p)] || 'application/octet-stream' }); fs.createReadStream(p).pipe(res);
});
await new Promise((r) => server.listen(0, r));
const URL0 = 'http://localhost:' + server.address().port + '/euro-signal.html';

const main = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'euro-signal.json'), 'utf8'));
const isins = Object.keys(main.inst || {});
const browser = await chromium.launch();
const problem = (kind, where, detail) => { if (report.problems.length < 400) report.problems.push({ kind, where, detail: String(detail || '').slice(0, 160) }); };
const jsErr = (where, m) => { if (report.jsErrors.length < 100) report.jsErrors.push({ where, message: String(m).slice(0, 200) }); };

async function newPage() {
  const p = await browser.newPage({ viewport: { width: W, height: H } });
  p.on('pageerror', (e) => jsErr(p.__where || 'page', e.message));
  p.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource|net::ERR|favicon|sw\.js|service worker/i.test(m.text())) jsErr(p.__where || 'page', m.text()); });
  await p.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await p.goto(URL0); await p.waitForTimeout(4000);
  return p;
}
async function inspect(p, where) {
  return p.evaluate(() => {
    document.querySelectorAll('details').forEach((d) => { d.open = true; });
    const t = document.body.innerText;
    return { t, sw: document.documentElement.scrollWidth, title: (document.querySelector('.fhead h2') || {}).textContent || '' };
  });
}
function judge(r, where, needTitle) {
  const m = r.t.match(BAD);
  if (m) problem('texte illisible', where, r.t.slice(Math.max(0, m.index - 70), m.index + 30).replace(/\s+/g, ' '));
  if (r.sw > W + 2) problem('débordement de l\'écran', where, r.sw + ' px pour ' + W);
  if (needTitle && !r.title) problem('fiche vide', where, '');
  if (/Fiche indisponible|HTTP \d{3}/.test(r.t)) problem('fiche indisponible', where, (r.t.match(/[^\n]*(Fiche indisponible|HTTP \d{3})[^\n]*/) || [''])[0]);
}

// 1. toutes les fiches, sur plusieurs onglets de navigateur en parallèle
process.on('unhandledRejection', (e) => { problem('contrôle interrompu', 'script', e && e.message); finish('Contrôle interrompu : ' + (e && e.message || e)); });
const queue = isins.slice();
await Promise.all(Array.from({ length: PAGES }, async () => {
  const p = await newPage();
  while (queue.length) {
    const i = queue.shift(); p.__where = i;
    await p.evaluate((i) => { location.hash = '#' + i; }, i);
    try { await p.waitForFunction(() => document.querySelector('.fhead') && !/Chargement (des cours|de la fiche)/.test(document.body.innerText), null, { timeout: 6000 }); } catch (e) { /* jugé quand même */ }
    await p.waitForTimeout(120);
    judge(await inspect(p, i), i + ' ' + ((main.inst[i] || {}).name || ''), true);
    report.fiches++;
  }
  await p.close();
}));

// 2. onglets et quelques fiches du catalogue (par la recherche, comme un lecteur)
{
  const p = await newPage();
  // chaque onglet doit montrer son contenu (une erreur rattrapée par la page laisserait sinon un onglet vide sans bruit)
  const EXPECT = { classement: 'tr.rowlink', secteurs: '#sec-q', inities: 'table.ops tr.rowlink', alertes: 'h2', aide: '[data-k="aide-guide"]' };
  for (const v of ['classement', 'secteurs', 'inities', 'alertes', 'aide']) {
    p.__where = 'onglet ' + v;
    await p.goto(URL0); await p.waitForTimeout(2500);
    try {
      const b = p.locator(`nav [data-v="${v}"]`).first(); if (await b.count()) { await b.click({ timeout: 5000 }); await p.waitForTimeout(1500); }
      if (!(await p.locator(EXPECT[v]).count())) problem('onglet sans contenu', v, 'élément attendu absent : ' + EXPECT[v]);
      judge(await inspect(p, 'onglet ' + v), 'onglet ' + v, false); report.views++;
      // polices un peu plus larges (celles du téléphone, chargées depuis Google, varient selon les appareils) : pas de débordement
      await p.addStyleTag({ content: '*{letter-spacing:.05em !important}' }); await p.waitForTimeout(200);
      const sw = await p.evaluate(() => document.documentElement.scrollWidth);
      if (sw > W + 2) problem('débordement avec une police plus large', 'onglet ' + v, sw + ' px pour ' + W);
    } catch (e) { problem('onglet impossible à ouvrir', v, e.message.split('\n')[0]); }
  }
  // classement principal : ancien classement (dirigeants) et fiches ouvertes depuis le classement tendance + comptes
  try {
    p.__where = 'ancien classement';
    await p.goto(URL0); await p.waitForTimeout(2500);
    const b = p.locator('[data-a="rankMode"][data-v="ins"]').first();
    if (await b.count()) {
      await b.click({ timeout: 5000 }); await p.waitForTimeout(800);
      if (!(await p.locator('tr.rowlink').count())) problem('onglet sans contenu', 'ancien classement', 'aucune ligne');
      judge(await inspect(p, 'ancien classement'), 'ancien classement', false); report.views++;
      await p.locator('[data-a="rankMode"][data-v="rank"]').first().click({ timeout: 5000 }); await p.waitForTimeout(500);
    } else if (main.rank) problem('onglet sans contenu', 'classement', 'bouton « ancien classement » absent');
  } catch (e) { problem('onglet impossible à ouvrir', 'ancien classement', e.message.split('\n')[0]); }
  const rk = (main.rank && main.rank.rows) || [];
  if (main.rank && !rk.filter((r) => !r.out.length).length) problem('classement vide', 'classement tendance + comptes', 'aucune société classée');
  for (const r of rk.filter((x) => !x.out.length).slice(0, 30)) {
    p.__where = 'classement ' + r.key;
    try {
      await p.evaluate((h) => { location.hash = h; }, r.isin ? '#' + r.isin : '#co=' + encodeURIComponent(r.sym));
      try { await p.waitForFunction(() => document.querySelector('.fhead') && !/Chargement( de la fiche)?…/.test(document.body.innerText), null, { timeout: 6000 }); } catch (e) { }
      await p.waitForTimeout(150);
      const res = await inspect(p, 'classement ' + r.key);
      judge(res, 'classement ' + r.key + ' ' + (r.name || ''), true);
      if (!(await p.locator('.rcard').count())) problem('fiche sans note du classement', r.key + ' ' + (r.name || ''), '');
      report.ranked = (report.ranked || 0) + 1;
    } catch (e) { problem('classement : fiche impossible à ouvrir', r.key, e.message.split('\n')[0]); }
  }
  await p.evaluate(() => { location.hash = ''; });
  let rows = []; try { rows = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'societes-index.json'), 'utf8')).rows || []; } catch (e) { problem('catalogue illisible', 'societes-index.json', e.message); }
  const sample = rows.filter((_, k) => k % Math.max(1, Math.floor(rows.length / 40)) === 0).slice(0, 40);
  await p.goto(URL0); await p.waitForTimeout(2500);
  for (const r of sample) {
    p.__where = 'catalogue ' + r[0];
    try {
      await p.locator('nav [data-v="secteurs"]').first().click({ timeout: 5000 }); await p.waitForTimeout(500);
      await p.fill('#sec-q', r[0], { timeout: 5000 }); await p.waitForTimeout(600);
      const btn = p.locator(`[data-a="secCo"][data-v="${r[0]}"]`).first();
      if (!(await btn.count())) { problem('catalogue : société introuvable par la recherche', r[0], r[1]); continue; }
      await btn.click({ timeout: 5000 });
      try { await p.waitForFunction(() => !/Chargement de la fiche/.test(document.body.innerText), null, { timeout: 6000 }); } catch (e) { }
      judge(await inspect(p, 'catalogue ' + r[0]), 'catalogue ' + r[0] + ' ' + (r[1] || ''), false); report.catalogue++;
    } catch (e) { problem('catalogue : fiche impossible à ouvrir', r[0] + ' ' + (r[1] || ''), e.message.split('\n')[0]); if (report.problems.filter((x) => x.kind === 'catalogue : fiche impossible à ouvrir').length >= 5) break; }
  }
  await p.close();
}
await browser.close(); server.close();
finish();

function finish(note) {
  if (note) report.note = note;
  const by = {}; report.problems.forEach((x) => { by[x.kind] = (by[x.kind] || 0) + 1; });
  report.summary = by;
  const L = ['Contrôle du tableau de bord du ' + report.date + ' (téléphone ' + W + ' px, panneaux dépliés)', '',
    (note ? note + '\n' : '') + report.fiches + ' fiches, ' + (report.ranked || 0) + ' fiches du classement, ' + report.catalogue + ' fiches du catalogue, ' + report.views + ' onglets ouverts',
    report.problems.length + ' problème(s) d\'affichage, ' + report.jsErrors.length + ' erreur(s) JavaScript', ''];
  Object.entries(by).forEach(([k, n]) => L.push('  ' + k + ' : ' + n));
  report.problems.slice(0, 60).forEach((x) => L.push('- ' + x.kind + ' · ' + x.where + (x.detail ? ' · ' + x.detail : '')));
  report.jsErrors.slice(0, 20).forEach((x) => L.push('- erreur JavaScript · ' + x.where + ' · ' + x.message));
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'ui-check.json'), JSON.stringify(report));
  fs.writeFileSync(path.join(OUT, 'ui-check.txt'), L.join('\n') + '\n');
  console.log(L.slice(0, 30).join('\n'));
  process.exit(0);
}
