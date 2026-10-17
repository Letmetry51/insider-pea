// Euro Signal — calcul quotidien (exécuté par GitHub Actions après la collecte).
// Entrées : data/latest.json (collecteur AMF insider-pea), data/prices.json (cours Yahoo),
//           data/euro-signal-state.json (archive et journal des alertes), euro_signal/config.json.
// Sorties : data/euro-signal.json (tableau de bord), data/euro-signal-outbox.json (emails à envoyer),
//           data/euro-signal-state.json (mis à jour).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import zlib from 'node:zlib';

const require = createRequire(import.meta.url);
const ES = require('./core.js');
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const DATA = path.join(ROOT, 'data');
const F = {
  latest: path.join(DATA, 'latest.json'), eu: path.join(DATA, 'insiders-eu.json'), events: path.join(DATA, 'events.json'), shorts: path.join(DATA, 'shorts.json'), financials: path.join(DATA, 'financials.json'), prices: path.join(DATA, 'prices.json'), state: path.join(DATA, 'euro-signal-state.json'),
  history: path.join(DATA, 'history'), insiders: path.join(DATA, 'euro-signal-insiders.json'), societes: path.join(DATA, 'societes'),
  out: path.join(DATA, 'euro-signal.json'), sectors: path.join(DATA, 'sectors.json'), journal: path.join(DATA, 'history', 'journal.json.gz'), detail: path.join(DATA, 'euro-signal-detail.json'), long: path.join(DATA, 'euro-signal-long.json'), learning: path.join(DATA, 'euro-signal-learning.json'), outbox: path.join(DATA, 'euro-signal-outbox.json'), config: path.join(HERE, 'config.json')
};

// NaN / Infinity écrits par Python : remplacés seulement en position de valeur (jamais dans un texte)
const sanitize = (txt) => txt.replace(/([:\[,]\s*)-?(?:NaN|Infinity)(?=\s*[,\]}])/g, '$1null');
function readJSON(file, fallback) {
  try {
    const v = JSON.parse(sanitize(fs.readFileSync(file, 'utf8')));
    if ((v === null || typeof v !== 'object') && fallback !== undefined) return fallback; // « null », nombre, chaîne : inutilisable
    return v;
  } catch (e) { if (fallback === undefined) throw e; return fallback; }
}
/** Fichier indispensable : absent = valeur par défaut ; présent mais illisible = arrêt (jamais d'écrasement silencieux). */
function readRequired(file, fallback, label) {
  if (!fs.existsSync(file)) return fallback;
  try { return JSON.parse(sanitize(fs.readFileSync(file, 'utf8'))); }
  catch (e) {
    const bak = file + '.illisible-' + new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    try { fs.copyFileSync(file, bak); } catch (e2) { }
    throw new Error(label + ' illisible (' + e.message + ') : arrêt pour ne pas perdre le journal des alertes. Copie conservée : ' + bak);
  }
}
function writeJSON(file, obj, pretty, compact) {
  const tmp = file + '.tmp';
  // compact : nombres à 5 chiffres significatifs (le tableau de bord n'a pas besoin de plus)
  const rep = compact ? (k, v) => (typeof v === 'number' && !Number.isInteger(v) ? Number(v.toPrecision(5)) : v) : undefined;
  fs.writeFileSync(tmp, JSON.stringify(obj, rep, pretty ? 1 : 0));
  fs.renameSync(tmp, file); // écriture atomique : jamais de fichier à moitié écrit
}
function parisToday() {
  if (process.env.ES_TODAY) return process.env.ES_TODAY;
  return new Intl.DateTimeFormat('fr-CA', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

function mainRegistry(list) {
  const n = {};
  list.forEach((t) => { if (t.type !== 'instrument') n[t.registry] = (n[t.registry] || 0) + 1; });
  return Object.keys(n).sort((a, b) => n[b] - n[a])[0] || 'AMF';
}

/** Historique long des dirigeants (collecteur séparé, data/history) : déclarations normalisées, début par registre, résultats des achats. */
/** Cours hebdomadaires du module secteurs (CSV compressé : une colonne par symbole, en euros) → { dates, series } ; null si absent. */
function readWeeklyCsv(file, universe) {
  try {
    const lines = zlib.gunzipSync(fs.readFileSync(file)).toString('utf8').split(/\r?\n/).filter(Boolean);
    const head = lines[0].split(','), keep = [];
    head.forEach((h, k) => { if (k > 0 && universe && universe[h]) keep.push([k, h]); });
    const dates = [], series = {}; keep.forEach(([, h]) => { series[h] = []; });
    for (let r = 1; r < lines.length; r++) {
      const c = lines[r].split(','); dates.push(String(c[0]).slice(0, 10));
      keep.forEach(([k, h]) => { const v = parseFloat(c[k]); series[h].push(v > 0 ? v : null); });
    }
    return { dates, series };
  } catch (e) { return null; }
}
function readGz(file, fallback) { try { return JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString('utf8')); } catch (e) { return fallback; } }
function loadHistory(today, live) {
  const out = { tx: {}, cov: {}, outcomes: readGz(path.join(F.history, 'outcomes.json.gz'), {}), n: {}, from: {}, cut: {} };
  // début de l'archive du tableau de bord par registre : l'historique ne sert qu'avant (aucun doublon)
  Object.values(live).forEach((l) => (l || []).forEach((t) => { const d = ES.availDate(t); if (d && (!out.cut[t.registry] || d < out.cut[t.registry])) out.cut[t.registry] = d; }));
  [['AMF', 'amf.json.gz'], ['FI', 'fi.json.gz']].forEach(([reg, file]) => {
    const recs = readGz(path.join(F.history, file), []);
    let n = 0;
    (Array.isArray(recs) ? recs : []).forEach((r) => {
      if (!r || typeof r !== 'object' || Array.isArray(r)) return; // ligne illisible : ignorée, jamais bloquante
      let res; try { res = ES.fromCollectorRecord(r, { today }); } catch (e) { return; }
      if (!res.ok || res.rec.type === 'instrument') return;
      const t = res.rec, d = ES.availDate(t);
      if (out.cut[reg] && d >= out.cut[reg]) return;
      if (!ES.isEuropeanIsin(t.isin)) return;
      (out.tx[t.isin] = out.tx[t.isin] || []).push(t); n++;
      if (d && (!out.from[reg] || d < out.from[reg])) out.from[reg] = d;
    });
    out.n[reg] = n;
  });
  // couverture : première date de publication relevée pour chaque registre (historique long, sinon archive du tableau de bord).
  // Une déclaration tardive portant sur une vieille opération ne fait pas remonter la couverture.
  Object.keys(out.cut).forEach((reg) => { out.cov[reg] = out.cut[reg]; });
  Object.keys(out.from).forEach((reg) => { if (!out.cov[reg] || out.from[reg] < out.cov[reg]) out.cov[reg] = out.from[reg]; });
  return out;
}
/** Écart au STOXX 600 (fraction) d'un achat publié le jour d, à 20, 60 ou 120 séances (collecteur d'historique). */
const H_IDX = { 20: 1, 60: 2, 120: 3 };
const okRet = (v) => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) < 10; // rendement plausible (fraction)
function histOutcome(o, h) {
  const r0 = histOutcomeRaw(o, h);
  return r0 && okRet(r0.ret) && okRet(r0.excess) ? Object.assign(r0, { local: okRet(r0.local) ? r0.local : null }) : null;
}
function histOutcomeRaw(o, h) {
  if (!o || typeof o !== 'object' || !H_IDX[h]) return null;
  if (Array.isArray(o)) { const r = o[H_IDX[h]], b = o[H_IDX[h] + 3]; return r != null && b != null ? { ret: r, excess: r - b, local: null } : null; } // ancien format
  const k = H_IDX[h] - 1, r = o.r && o.r[k], b = o.b && o.b[k], lr = o.lr && o.lr[k], lb = o.lb && o.lb[k];
  return r != null && b != null ? { ret: r, excess: r - b, local: lr != null && lb != null ? lr - lb : null } : null;
}

export function build(opts = {}) {
  const today = opts.today || parisToday();
  const cfgRaw = readRequired(F.config, {}, 'euro_signal/config.json');
  // config.json porte les règles en vigueur (DG/DAF, sociétés exclues, gel jusqu'à la revue) : absent ou tronqué, on le signale
  const cfgMissing = ['selection', 'rules', 'insiders', 'learning'].filter((k) => !cfgRaw || typeof cfgRaw[k] !== 'object');
  if (cfgMissing.length) console.warn('  ATTENTION : euro_signal/config.json incomplet (' + cfgMissing.join(', ') + ') : valeurs par défaut du moteur utilisées');
  let cfg = ES.mergeConfig(ES.DEFAULT_CONFIG, cfgRaw);
  // Auto-apprentissage : poids appris les mois précédents (fichier public, journalisé), appliqués si le mode est « auto »
  const learnPrev = readJSON(F.learning, null);
  const baseVersion = cfg.scoringVersion;
  if (cfg.learning.mode === 'auto' && learnPrev && learnPrev.weights && Object.keys(learnPrev.weights).length) {
    cfg = ES.mergeConfig(cfg, { weights: learnPrev.weights });
    if (learnPrev.version) cfg.scoringVersion = baseVersion + '+a' + learnPrev.version;
  }
  const errs = ES.validateConfig(cfg);
  if (errs.length) throw new Error('config.json invalide : ' + errs.join(' ; '));
  const latest = readJSON(F.latest, null);
  const prices = readJSON(F.prices, { items: {}, unresolved: [] });
  // Marché européen (STOXX Europe 600, sinon CAC 40) : tendance de fond et référence de force relative
  const mRef = prices.market || prices.bench || null;
  const mStats = mRef && Array.isArray(mRef.rows) && mRef.rows.length > 200 ? ES.computeStats(mRef.rows, [], today, ES.mergeConfig(ES.DEFAULT_CONFIG, {}), null) : null;
  const mkt = mStats ? { ticker: mRef.ticker, ret6m1: mStats.ret6m1, above200: mStats.sma200 ? mStats.lastCloseAdj > mStats.sma200 : null, lastDate: mStats.lastDate } : null;
  const state = readRequired(F.state, { txArchive: {}, alerts: {}, src: {}, runs: [] }, 'data/euro-signal-state.json');
  state.txArchive = state.txArchive || {}; state.alerts = state.alerts || {}; state.src = state.src || {};
  // Taux de change du soir (conservés d'un soir à l'autre si la collecte échoue) : montants et liquidité hors zone euro
  if (prices.fx && typeof prices.fx === 'object' && Object.keys(prices.fx).length) state.fx = prices.fx;
  ES.setFx(state.fx || {});
  if (!fs.existsSync(F.state)) { // journal disparu : on repart des alertes recopiées dans le tableau de bord, pour ne jamais renvoyer
    const prevDash = readJSON(F.out, null);
    if (prevDash && prevDash.alerts) { state.alerts = prevDash.alerts; console.warn('  Journal absent : ' + Object.keys(state.alerts).length + ' alerte(s) reprises du tableau de bord'); }
  }

  /* 1. Source AMF : absence de collecte ≠ absence de transaction */
  const amf = { name: 'AMF', via: 'transactions-amf.swaoo.com, republication de la base BDIF', countries: ['FR'], kind: 'déclarations' };
  const prevAmf = state.src.AMF || {};
  const genDate = latest && latest.generated_at ? String(latest.generated_at).slice(0, 10) : null;
  let rows = latest && Array.isArray(latest.transactions) ? latest.transactions.filter((t) => t && typeof t === 'object') : [];
  const amfFresh = genDate && ES.daysBetween(genDate, today) <= 3 && rows.length > 0;
  amf.status = amfFresh ? 'ok' : 'echec';
  amf.lastSuccess = amfFresh ? genDate : prevAmf.lastSuccess || null;
  amf.lastAttempt = today;
  amf.note = amfFresh ? null : !latest ? 'fichier data/latest.json absent ou illisible' : rows.length === 0 ? 'collecte vide' : 'collecte non mise à jour depuis le ' + genDate;

  /* 2. Conversion et fusion dans l'archive (corrections, doublons, première observation) */
  const rejects = [], incoming = {};
  let warnCount = 0;
  // ISIN mal saisi dans la déclaration : « O » à la place d'un zéro, ou chiffre manquant ou erroné. Réparé seulement quand c'est sûr :
  // correction O → 0 qui donne un ISIN valide, sinon même nom de société qu'un ISIN valide déjà déclaré.
  const normName = (n) => String(n || '').toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
  const isinByName = {};
  rows.forEach((t) => { const i = String(t.isin || '').toUpperCase().trim(); if (ES.isValidIsin(i) && t.company_name) isinByName[normName(t.company_name)] = i; });
  Object.keys(state.txArchive || {}).forEach((i) => { const l = state.txArchive[i] || []; const n = l.length && normName(l[l.length - 1].issuer); if (n && !isinByName[n] && ES.isValidIsin(i)) isinByName[n] = i; });
  let isinFixed = 0;
  rows = rows.map((t) => {
    const raw = String(t.isin || '').toUpperCase().replace(/\s+/g, '');
    if (!raw || ES.isValidIsin(raw)) return t;
    const o = raw.slice(0, 2) + raw.slice(2).replace(/O/g, '0');
    const fix = ES.isValidIsin(o) ? o : isinByName[normName(t.company_name)] || null;
    if (!fix) return t;
    isinFixed++;
    return Object.assign({}, t, { isin: fix, isinDeclared: raw });
  });
  if (isinFixed) console.log('  ISIN mal saisis réparés : ' + isinFixed);
  rows.forEach((t) => {
    const r = ES.fromAmfCollector(t, { today, via: amf.via });
    if (!r.ok) { rejects.push({ isin: t.isin, company: t.company_name, declaration: t.declaration_number, errors: r.errors }); return; }
    warnCount += r.warnings.length;
    (incoming[r.rec.isin] = incoming[r.rec.isin] || []).push(r.rec);
  });
  /* 2b. Registres hors France (FSMA, AFM…) : même traitement, statut propre à chaque source */
  const eu = readJSON(F.eu, { records: {}, sources: {} });
  eu.records = Object.fromEntries(Object.entries(eu.records && typeof eu.records === 'object' ? eu.records : {}).filter(([, v]) => v && typeof v === 'object'));
  eu.sources = eu.sources && typeof eu.sources === 'object' ? Object.fromEntries(Object.entries(eu.sources).filter(([, v]) => v && typeof v === 'object')) : {};
  const euSrc = {};
  const euRejects = {};
  const foreign = [];
  Object.values(eu.records || {}).filter((rec) => rec && typeof rec === 'object').forEach((rec) => {
    const r = ES.fromCollectorRecord(rec, { today });
    if (!r.ok) { (euRejects[rec.registry] = euRejects[rec.registry] || []).push({ isin: rec.isin, company: rec.issuer, declaration: rec.id, errors: r.errors }); return; }
    if (r.rec.type === 'instrument') return;
    if (!ES.isEuropeanIsin(r.rec.isin)) { foreign.push({ r, rec }); return; }
    (incoming[r.rec.isin] = incoming[r.rec.isin] || []).push(r.rec);
  });
  // ISIN hors Europe (ADR américain, ou société confondue par la source) : rattaché à la cotation européenne de même nom si elle existe, sinon écarté
  const nameKey = (n) => String(n || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\b(n\.?v|s\.?a|s\.?e|ag|s\.?p\.?a|plc|se|sa|nv|holding|holdings|group|inc|corp|corporation)\b\.?/g, ' ').replace(/[^a-z0-9]+/g, ' ').trim();
  const euByName = {};
  const addName = (n, isin) => { const k = nameKey(n); if (k.length >= 4 && ES.isEuropeanIsin(isin)) euByName[k] = euByName[k] || isin; };
  Object.keys(incoming).forEach((isin) => incoming[isin].forEach((t) => addName(t.issuer, isin)));
  Object.keys(state.txArchive).forEach((isin) => (state.txArchive[isin] || []).forEach((t) => addName(t.issuer, isin)));
  Object.keys(prices.items || {}).forEach((isin) => addName((prices.items[isin] || {}).name, isin));
  let remapped = 0;
  foreign.forEach(({ r, rec }) => {
    const to = euByName[nameKey(rec.issuer)];
    if (to) { r.rec.isin = to; r.rec.id = String(r.rec.id || '').replace(rec.isin, to) || r.rec.id; (incoming[to] = incoming[to] || []).push(r.rec); remapped++; return; }
    (euRejects[rec.registry] = euRejects[rec.registry] || []).push({ isin: rec.isin, company: rec.issuer, declaration: rec.id, errors: ['ISIN hors Europe sans cotation européenne connue : société confondue ou non éligible'] });
  });
  if (foreign.length) console.log(`  ISIN hors Europe : ${remapped} rattaché(s) à leur cotation européenne, ${foreign.length - remapped} écarté(s)`);
  Object.keys(eu.sources || {}).forEach((name) => {
    const s0 = eu.sources[name];
    const fresh = s0.lastSuccess && ES.daysBetween(s0.lastSuccess, today) <= 3;
    euSrc[name] = Object.assign({}, s0, { status: s0.status === 'ok' && !fresh ? 'echec' : s0.status, rejected: (euRejects[name] || []).length,
      note: s0.status === 'ok' && !fresh ? 'collecte non mise à jour depuis le ' + s0.lastSuccess : s0.note || null,
      log: [{ at: today, rows: s0.rows || 0, accepted: Object.values(eu.records || {}).filter((x) => x.registry === name).length - (euRejects[name] || []).length, rejected: (euRejects[name] || []).length, fetched: s0.fetched != null ? s0.fetched : null, backlog: s0.backlog || 0 }].concat(((state.src[name] || {}).log) || []).slice(0, 15) });
  });
  Object.values(euRejects).forEach((l) => rejects.push.apply(rejects, l.slice(0, 50)));
  const mergeStats = { added: 0, duplicates: 0, corrected: 0, cancelled: 0, crossSource: 0 };
  Object.keys(incoming).forEach((isin) => {
    const m = ES.mergeTransactions(state.txArchive[isin] || [], incoming[isin], today);
    Object.keys(mergeStats).forEach((k) => { mergeStats[k] += m.stats[k]; });
    state.txArchive[isin] = m.list;
  });
  // Textes déjà archivés avec des entités HTML (« &amp; » publié par certaines sources) : nettoyés
  Object.values(state.txArchive).forEach((l) => (l || []).forEach((t) => { ['person', 'role', 'issuer', 'natureText', 'linkedTo'].forEach((k) => { if (typeof t[k] === 'string') t[k] = ES.unescapeHtml(t[k]); }); }));
  const keepFrom = ES.addMonths(today, -36);
  Object.keys(state.txArchive).forEach((isin) => { if (!ES.isEuropeanIsin(isin)) delete state.txArchive[isin]; }); // confusions de société déjà archivées
  Object.keys(state.txArchive).forEach((isin) => {
    state.txArchive[isin] = state.txArchive[isin].filter((t) => t.txDate >= keepFrom);
    if (!state.txArchive[isin].length) delete state.txArchive[isin];
  });
  const pubs = rows.map((t) => ES.parseDate(t.date_published)).filter(Boolean).sort();
  Object.assign(amf, { coveredFrom: pubs[0] || null, coveredTo: pubs[pubs.length - 1] || null, totalRows: rows.length, rejected: rejects.length, warnings: warnCount });
  amf.log = [{ at: today, rows: rows.length, accepted: rows.length - rejects.length, rejected: rejects.length, added: mergeStats.added, duplicates: mergeStats.duplicates, corrected: mergeStats.corrected, cancelled: mergeStats.cancelled }].concat(prevAmf.log || []).slice(0, 15);

  /* 3. Source cours */
  const pItems = prices.items || {};
  // Dividendes intégrés aux ajustements (comme des divisions) : sans cela, un dividende exceptionnel passe pour un krach
  Object.keys(pItems).forEach((isin) => {
    const p = pItems[isin];
    if (!p || !Array.isArray(p.rows)) return;
    p.splits = (Array.isArray(p.splits) ? p.splits.filter((x) => !x.dividend) : []).concat(ES.dividendSplits(p.rows, p.dividends));
  });
  const pDate = prices.generated_at ? String(prices.generated_at).slice(0, 10) : null;
  const pFresh = pDate && ES.daysBetween(pDate, today) <= 3 && Object.keys(pItems).length > 0;
  const prevY = state.src['Yahoo Finance'] || {};
  const yahoo = { name: 'Yahoo Finance', kind: 'cours', via: 'yfinance (GitHub Actions)', status: pFresh ? 'ok' : 'echec', lastSuccess: pFresh ? pDate : prevY.lastSuccess || null, lastAttempt: today, countries: [], note: pFresh ? (prices.unresolved && prices.unresolved.length ? prices.unresolved.length + ' émetteur(s) sans ticker Yahoo' : null) : 'cours non mis à jour' };
  yahoo.log = [{ at: today, accepted: Object.keys(pItems).length, rejected: (prices.unresolved || []).length }].concat(prevY.log || []).slice(0, 15);
  /* 3b. Événements Yahoo (résultats, communiqués, révisions) : conservés d'un jour à l'autre */
  const evRaw = readJSON(F.events, { items: {} });
  const eDate = evRaw.generated_at ? String(evRaw.generated_at).slice(0, 10) : null;
  const eFresh = eDate && ES.daysBetween(eDate, today) <= 3 && Object.keys(evRaw.items || {}).length > 0;
  const prevE = state.src['Yahoo Finance (événements)'] || {};
  // Communiqués : Yahoo ne les sert plus depuis GitHub (aucun titre, sur tous les onglets) → rachats et prévisions des communiqués non détectés
  const pressN = Object.values(evRaw.items || {}).reduce((s, v) => s + ((v && v.press) || []).length, 0);
  const noPress = eFresh && Object.keys(evRaw.items || {}).length >= 50 && pressN === 0;
  const yev = { name: 'Yahoo Finance (événements)', kind: 'résultats, communiqués, révisions', via: 'yfinance (GitHub Actions)', status: eFresh ? (noPress ? 'partiel' : 'ok') : 'echec', lastSuccess: eFresh ? eDate : prevE.lastSuccess || null, lastAttempt: today, countries: [], note: eFresh ? (noPress ? 'résultats et révisions à jour ; communiqués indisponibles chez Yahoo (rachats d\'actions et prévisions des communiqués non détectés, nombre d\'actions suivi à la place)' + (evRaw.partial ? ' ; collecte partielle faute de temps' : '') : evRaw.partial ? 'collecte partielle faute de temps : ' + Object.keys(evRaw.items || {}).length + ' titres sur ' + (evRaw.total || '?') + ' relus ce soir, les autres gardent leurs données précédentes' : null) : 'événements non mis à jour (familles R et E figées à la dernière collecte)' };
  yev.log = [{ at: today, accepted: Object.keys(evRaw.items || {}).length, rejected: evRaw.errors || 0 }].concat(prevE.log || []).slice(0, 15);
  state.events = state.events || {};
  const revisions = {};
  Object.keys(evRaw.items || {}).forEach((isin) => {
    const e = ES.eventsFromYahoo(evRaw.items[isin], today);
    const prev = state.events[isin] || { buybacks: [], results: [] };
    const byId = (list) => { const m = {}; list.forEach((x) => { m[x.id] = x; }); return m; };
    const bb = Object.assign(byId(prev.buybacks || []), byId(e.buybacks)), rs = Object.assign(byId(prev.results || []), byId(e.results));
    const keep = ES.addMonths(today, -30);
    state.events[isin] = { buybacks: Object.values(bb).filter((x) => x.date >= keep).sort((a, b) => (a.date < b.date ? -1 : 1)), results: Object.values(rs).filter((x) => x.pubDate >= keep).sort((a, b) => (a.pubDate < b.pubDate ? -1 : 1)) };
    if (e.revision30d != null) revisions[isin] = e.revision30d;
  });
  state.src = Object.assign({ AMF: amf }, euSrc, { 'Yahoo Finance': yahoo, 'Yahoo Finance (événements)': yev });

  /* 4. Univers : émetteurs ayant au moins une déclaration portant sur des actions */
  const inst = {}, tx = {}, refs = {}, computed = {};
  const names = {};
  rows.forEach((t) => { if (t.isin && t.company_name) names[String(t.isin).toUpperCase()] = t.company_name; });
  Object.values(eu.records || {}).forEach((r) => { const k = String(r.isin || '').toUpperCase(); if (k && r.issuer && !names[k]) names[k] = r.issuer; });
  Object.keys(state.txArchive).forEach((isin) => {
    let list = state.txArchive[isin];
    if (!list.some((t) => t.type !== 'instrument') || !ES.isValidIsin(isin)) return;
    const p = pItems[isin];
    const i = {
      isin, name: (p && p.name) || names[isin] || list[0].issuer || isin, ticker: p ? p.ticker : null,
      venue: p ? p.exchange || null : null, currency: p ? p.currency || null : null,
      country: /^[A-Z]{2}/.test(isin) ? isin.slice(0, 2) : null, countrySource: 'préfixe ISIN (non vérifié)',
      registry: mainRegistry(list), shareType: 'ordinaire', isReference: true, sector: null, revision30d: revisions[isin] != null ? revisions[isin] : null,
      peaStatus: 'a_verifier', peaSource: null, peaDate: null, auto: true
    };
    i.stats = p && p.rows && p.rows.length ? ES.computeStats(p.rows, p.splits || [], today, cfg, i.currency) : { sessions: 0, empty: true };
    if (mkt && i.stats.ret6m1 != null && mkt.ret6m1 != null) i.stats.rel6m = i.stats.ret6m1 - mkt.ret6m1;
    if (mkt) { i.stats.marketAbove200 = mkt.above200; i.stats.marketIndex = mkt.ticker; }
    const er = (evRaw.items || {})[isin];
    state.fund = state.fund || {};
    if (er && er.fund) state.fund[isin] = er.fund; // conservées si la collecte du soir échoue
    // Nombre d'actions sur un an (relu une fois par semaine) : baisse nette = rachats, hausse = émission d'actions (dilution)
    state.shares = state.shares || {};
    if (er && er.shares && er.shares.n0 > 0 && er.shares.n1 > 0) state.shares[isin] = Object.assign({ asOf: today }, er.shares);
    if (state.shares[isin] && ES.daysBetween(state.shares[isin].asOf || today, today) > 45) delete state.shares[isin];
    const shr = state.shares[isin];
    i.sharesChange = shr && ES.daysBetween(shr.from, shr.to) >= 180 ? { pct: +((shr.n1 / shr.n0 - 1) * 100).toFixed(2), from: shr.from, to: shr.to } : null;
    // variation énorme (÷2 ou ×2 et plus) : regroupement ou division d'actions, pas des rachats ni une émission
    if (i.sharesChange && (shr.n1 / shr.n0 <= 0.5 || shr.n1 / shr.n0 >= 2)) i.sharesChange.corporate = true;
    i.fund = state.fund[isin] || null;
    // Prévisionnels des analystes (consensus du jour) : conservés si la collecte du soir échoue, abandonnés après 30 jours
    state.forecast = state.forecast || {};
    if (er && er.forecast) state.forecast[isin] = er.forecast;
    if (state.forecast[isin] && ES.daysBetween(state.forecast[isin].asOf || today, today) > 30) delete state.forecast[isin];
    i.forecast = state.forecast[isin] || null;
    if (i.fund && i.fund.sector) i.sector = i.fund.sector;
    // Foncières cotées (SIIC, SOCIMI, SIR, REIT) : régime fiscal exonéré, exclues du PEA (loi de finances 2011 pour les SIIC)
    if (i.fund && /^REIT\b/i.test(String(i.fund.industry || ''))) { i.peaStatus = 'non_eligible'; i.peaSource = 'foncière cotée (SIIC, SOCIMI, REIT) : exclue du PEA'; i.peaDate = today; }
    // PEA : siège dans l'Union européenne ou l'Espace économique européen exigé ; Royaume-Uni, Suisse, îles anglo-normandes… exclus
    if (/^(GB|CH|JE|GG|IM|GI|FO|MC)/.test(isin)) { i.peaStatus = 'non_eligible'; i.peaSource = 'siège hors Union européenne et Espace économique européen (code ISIN ' + isin.slice(0, 2) + ')'; i.peaDate = today; }
    // Probable : action d'une société immatriculée dans l'UE ou l'EEE (code ISIN), qui n'est pas une foncière cotée. Affichage seulement :
    // le statut « éligible » confirmé (mode strict, qualité des données) reste réservé à une vérification documentée.
    if (i.peaStatus === 'a_verifier' && ES.EEA.indexOf(isin.slice(0, 2)) > -1 && i.fund && i.fund.industry) { i.peaStatus = 'probable'; i.peaSource = 'siège dans l\'UE ou l\'EEE (code ISIN ' + isin.slice(0, 2) + '), pas une foncière cotée'; i.peaDate = today; }
    i.nextEarnings = er && er.nextEarnings && er.nextEarnings > today ? er.nextEarnings : (state.nextEarnings || {})[isin] > today ? state.nextEarnings[isin] : null;
    if (i.nextEarnings) (state.nextEarnings = state.nextEarnings || {})[isin] = i.nextEarnings;
    if (!p) i.priceNote = (prices.unresolved || []).indexOf(isin) > -1 ? 'aucun ticker Yahoo trouvé pour cet ISIN' : 'cours non collectés';
    // DG et DAF reconnus aussi par la liste des dirigeants publiée (déclarations allemandes : « membre du directoire » sans plus de détail)
    const off = i.fund && Array.isArray(i.fund.officers) ? i.fund.officers : null;
    // Déclaration en double avec prix et quantité inversés (ex. Interparfums : 52 124 € « payés » pour 24,702 actions) : écartée
    {
      const lastClose = p && p.rows && p.rows.length ? p.rows[p.rows.length - 1][4] : null, seenSw = {};
      list.forEach((t) => { if (t.price > 0 && t.qty > 0) seenSw[[t.person, t.txDate, Math.round(t.amount || t.price * t.qty)].join('|')] = (seenSw[[t.person, t.txDate, Math.round(t.amount || t.price * t.qty)].join('|')] || 0) + 1; });
      list = list.filter((t) => {
        if (!(t.price > 0 && t.qty > 0) || !lastClose) return true;
        const k = [t.person, t.txDate, Math.round(t.amount || t.price * t.qty)].join('|');
        if (seenSw[k] < 2) return true;
        const far = (v) => Math.abs(Math.log(v / lastClose));
        return !(far(t.price) > Math.log(5) && far(t.qty) < Math.log(2)); // c'est la quantité qui ressemble au cours : champs inversés
      });
    }
    inst[isin] = i; tx[isin] = off ? list.map((t) => {
      if (t.ceo || t.cfo || t.associated || (t.type !== 'achat' && t.type !== 'vente') || ES.isLegalEntity(t.person, t.issuer)) return t;
      const r = ES.officerMatch(t.person, off);
      return r ? Object.assign({}, t, { ceo: r === 'ceo', cfo: r === 'cfo', roleSource: 'liste des dirigeants Yahoo' }) : t;
    }) : list;
  });
  // Valorisation par rapport aux pairs (même industrie, sinon même secteur) et positions vendeuses publiées
  // Deux ISIN pour la même cotation (ancien et nouveau code après une opération sur titres) : un seul dossier, le plus récent
  const byTicker = {};
  Object.keys(inst).forEach((isin) => { const t = inst[isin].ticker; if (t) (byTicker[t] = byTicker[t] || []).push(isin); });
  // les déclarations de l'autre ISIN rejoignent le dossier gardé (une seule fiche, avec son graphique) ; l'ancien ISIN reste
  // joignable (lien d'un email, favori) par la table des alias
  const aliases = {}, finEarly = (readJSON(F.financials, { items: {} }).items) || {};
  Object.values(byTicker).filter((l) => l.length > 1).forEach((l) => {
    const last = (isin) => (tx[isin] || []).map((t) => ES.availDate(t)).sort().pop() || '';
    const hasFin = (isin) => !!(finEarly[isin] && Array.isArray(finEarly[isin].years) && finEarly[isin].years.length);
    // dossier gardé : celui qui a des comptes annuels, puis la déclaration la plus récente
    const keep = l.slice().sort((a, b) => (hasFin(b) - hasFin(a)) || (last(a) < last(b) ? 1 : last(a) > last(b) ? -1 : 0))[0];
    l.filter((x) => x !== keep).forEach((x) => {
      const seen = new Set((tx[keep] || []).map((t) => t.id)), sig = new Set((tx[keep] || []).map((t) => [t.person, t.txDate, t.price, t.qty].join('|')));
      (tx[x] || []).forEach((t) => {
        const k = [t.person, t.txDate, t.price, t.qty].join('|');
        if (seen.has(t.id) || sig.has(k)) return; // même déclaration publiée sous les deux ISIN
        tx[keep].push(Object.assign({}, t, { isin: keep, isinDeclared: x }));
      });
      tx[keep].sort((a, b) => (ES.availDate(a) < ES.availDate(b) ? -1 : 1));
      aliases[x] = keep; delete inst[x]; delete tx[x];
    });
  });
  // ISIN sans cours dont le nom est celui d'une société suivie avec cours (Studsvik : options et droits d'un programme) :
  // ligne secondaire, signalée et retirée des listes (la fiche renvoie vers la ligne principale)
  {
    const nk = (n) => String(n || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[(),.&'’-]/g, ' ')
      .split(/\s+/).filter((w) => w.length > 1 && !/^(sa|se|ag|nv|spa|ab|publ|plc|oyj|abp|asa|as|sca|gmbh|kgaa|co|holding|holdings|group|groupe|ser|the|aktiebolag|aktiebolaget)$/.test(w)).join(' ');
    const priced = {};
    Object.keys(inst).forEach((i) => { const p = pItems[i]; if (p && p.rows && p.rows.length && inst[i].name) { const k = nk(inst[i].name); if (k && !priced[k]) priced[k] = i; } });
    Object.keys(inst).forEach((i) => {
      const p = pItems[i]; if (p && p.rows && p.rows.length) return;
      const main = priced[nk(inst[i].name)];
      if (main && main !== i) { inst[i].secondary = main; inst[i].shareType = 'ligne secondaire sans cours (options, droits ou actions nouvelles de ' + main + ')'; }
    });
  }
  // Informations croisées : jamais bloquantes (une donnée mal formée est ignorée, le calcul continue)
  const shortsRaw = readJSON(F.shorts, { items: {}, sources: {} });
  const isObj = (o) => o && typeof o === 'object' && !Array.isArray(o);
  const shortsSrc = {};
  Object.keys(isObj(shortsRaw.sources) ? shortsRaw.sources : {}).forEach((cc) => { const x = shortsRaw.sources[cc]; if (isObj(x)) shortsSrc[cc] = { name: String(x.name || cc), status: x.status === 'ok' ? 'ok' : 'echec', open: Number.isFinite(+x.open) ? +x.open : null, note: x.note ? String(x.note).slice(0, 160) : null }; });
  const shortsList = {};
  Object.keys(isObj(shortsRaw.items) ? shortsRaw.items : {}).forEach((isin) => {
    const l = shortsRaw.items[isin];
    if (!Array.isArray(l)) return;
    const ok = l.filter((p) => isObj(p) && Number.isFinite(+p.pct)).map((p) => ({ holder: String(p.holder || '?').slice(0, 80), pct: +p.pct, from: typeof p.from === 'string' ? p.from : null, to: typeof p.to === 'string' ? p.to : null, country: String(p.country || '') }));
    if (ok.length) shortsList[isin] = ok;
  });
  let peers = {}, positions = {};
  try { peers = ES.peerValuation(inst); } catch (e) { console.warn('  Valorisation vs pairs ignorée : ' + e.message); }
  try { positions = ES.marketPosition(inst); } catch (e) { console.warn('  Position concurrentielle ignorée : ' + e.message); }
  // Comptes annuels (4 exercices) : analyse et F-score de Piotroski, avec les seuls comptes publiés à ce jour
  const finRaw = readJSON(F.financials, { items: {} });
  const finList = isObj(finRaw.items) ? finRaw.items : {};
  const accAt = (isin, d) => { try { const i = inst[isin]; return ES.accountsAnalysis(finList[isin], { asOf: d, sector: i.sector || (i.fund && i.fund.sector), industry: i.fund && i.fund.industry }); } catch (e) { return null; } };
  // Valeur comptable et valeur intrinsèque : cours brut du jour d (non ajusté des dividendes) et comptes publiés à cette date
  const rawCache = {};
  const rawCloseAt = (isin, d) => {
    const p = pItems[isin]; if (!p || !p.rows) return null;
    const a = rawCache[isin] || (rawCache[isin] = ES.normalizeSeries(p.rows));
    let lo = 0, hi = a.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (a[m][0] <= d) { k = m; lo = m + 1; } else hi = m - 1; }
    return k >= 0 && ES.daysBetween(a[k][0], d) <= 10 ? { date: a[k][0], close: a[k][4] } : null;
  };
  const valueAt = (isin, d) => {
    const i = inst[isin], fin = finList[isin]; if (!i || !fin) return null;
    const f = i.fund || {}, px = rawCloseAt(isin, d); if (!px || !(px.close > 0)) return null;
    if (/PREF|-PR?\.|\bPFD\b/i.test(i.ticker || '')) return null; // action de préférence : les comptes ne sont pas les siens
    const capEur = +f.marketCap > 0 ? (i.currency === 'EUR' ? +f.marketCap : ES.FX[i.currency] > 0 ? f.marketCap / ES.FX[i.currency] : null) : null;
    try {
      const v = ES.intrinsicValue(fin, { asOf: d, price: px.close, priceDate: px.date, currency: i.currency || f.currency, splits: ((pItems[isin] && pItems[isin].splits) || []).filter((s) => !s.dividend),
        sharesNow: f.sharesOut, marketCap: d === today && (!f.currency || f.currency === i.currency) ? f.marketCap : null, capEur, sector: f.sector || i.sector, industry: f.industry, pbYahoo: d === today ? f.priceToBook : null });
      if (!v) return null;
      v.price = px.close;
      if (v.methods) v.methods = v.methods.map((m) => ({ k: m.k, v: m.v })); // libellés côté page
      if (!v.notes.length) delete v.notes;
      return v;
    } catch (e) { return null; }
  };
  Object.keys(inst).forEach((isin) => {
    const a = finList[isin] ? accAt(isin, today) : null;
    if (a) {
      try { a.plain = ES.accountsPlain(a, inst[isin].fund, { nextEarnings: inst[isin].nextEarnings }); } catch (e) { a.plain = null; }
      // Une seule conclusion par fiche : la lecture complète (pertes, société en développement, trésorerie) prime sur le seul F-score
      if (a.plain && a.plain.tone === 'bad' && a.verdict && a.verdict.key === 'good') a.verdict = Object.assign({}, a.verdict, { key: 'mixed', text: a.verdict.text.replace('Comptes solides et en amélioration', 'Comptes mitigés') });
      inst[isin].accounts = a;
    }
    const v = valueAt(isin, today);
    if (v) inst[isin].value = v;
    if (peers[isin]) inst[isin].peer = peers[isin];
    if (positions[isin]) inst[isin].position = positions[isin];
    const sh = ES.shortInfo(shortsList[isin], today);
    if (sh) inst[isin].shorts = sh;
  });
  // Mémoire des critères non historisés au moment où un achat devient public (valorisation, positions vendeuses)
  state.obsAtBuy = isObj(state.obsAtBuy) ? state.obsAtBuy : {};
  Object.keys(state.obsAtBuy).forEach((k) => { if (!isObj(state.obsAtBuy[k]) || typeof state.obsAtBuy[k].at !== 'string') delete state.obsAtBuy[k]; });

  /* 5. Comparaisons, score, qualité, surchauffe, décision d'alerte */
  const sentIds = {};
  Object.values(state.alerts).forEach((a) => {
    // une alerte simulée (Gmail pas encore configuré) n'empêche pas l'envoi réel ensuite
    const counted = ['envoyee', 'brouillon', 'incertain', 'en_cours'].concat(process.env.ES_MAIL_READY === 'oui' ? [] : ['simulee']);
    if (counted.indexOf(a.status) > -1) (a.eventIds || []).forEach((id) => { (sentIds[a.isin] = sentIds[a.isin] || {})[id] = 1; });
  });
  const outbox = [];
  const cands = [];
  const evOut = {};
  const dashUrl = cfg.dashboardUrl || null;
  Object.keys(inst).forEach((isin) => {
    const i = inst[isin], p = pItems[isin];
    refs[isin] = {};
    if (p) tx[isin].forEach((t) => { if (t.type === 'achat' || t.type === 'vente') refs[isin][t.id] = ES.priceRefs(t, p.rows, p.splits || [], today, p.currency || null); });
    const se = state.events[isin] || { buybacks: [], results: [] };
    const ev = { buybacks: se.buybacks, results: se.results, splits: (p && p.splits) || [] };
    evOut[isin] = ev;
    const uni = ES.universeStatus(i, cfg);
    const score = ES.score({ inst: i, tx: tx[isin], events: ev, refs: refs[isin], cfg, today });
    const quality = ES.quality({ inst: i, score, sources: state.src, events: ev, cfg, today });
    const overheat = ES.overheat(i, cfg);
    const decision = ES.alertDecision({ inst: i, score, quality, overheat, universe: uni, cfg, today, sentEventIds: sentIds[isin] || {} });
    cands.push({ isin, inst: i, score, quality, universe: uni });
    computed[isin] = { score: score.total, quality: quality.total, overheat: overheat.total, send: decision.send, blocking: decision.blocking.length };
    if (decision.send && cfg.alerts.buyEmails !== false) { // alertes d'achat séparées (désactivables : la sélection du lundi les reprend)
      const health = ES.financialHealth(i.fund);
      const warn = uni.reasons.concat(['Éligibilité PEA non confirmée automatiquement : à vérifier avant tout achat.']);
      if (health.status === 'inconnu') warn.push('Solidité financière non vérifiable (données indisponibles) : regarder l\'endettement et la trésorerie avant d\'acheter.');
      else warn.push('Solidité financière : ' + health.status + (health.notes.length ? ' (' + health.notes.join(', ') + ')' : ''));
      if (i.nextEarnings && ES.daysBetween(today, i.nextEarnings) <= cfg.alerts.earningsWarnDays) warn.push('Résultats prévus le ' + i.nextEarnings + ' (dans ' + ES.daysBetween(today, i.nextEarnings) + ' jours) : acheter juste avant revient à parier sur leur contenu.');
      if (score.marketDown) warn.push('Marché européen sous sa moyenne 200 séances : environnement baissier.');
      const mail = ES.buildEmail({ inst: i, score, quality, overheat, decision, refs: refs[isin], events: ev, today, universeWarnings: warn, cfg });
      if (dashUrl) {
        const link = dashUrl + '#' + isin; // ouvre directement la fiche de la société
        const btn = '<p style="margin:10px 0 14px"><a href="' + ES.esc(link) + '" style="display:inline-block;background:#0D6A56;color:#ffffff;text-decoration:none;font-weight:bold;padding:10px 16px;border-radius:6px">Voir la fiche dans Euro Signal</a></p>';
        mail.html = mail.html.replace('</h2>', '</h2>' + btn).replace(/<\/div>\s*$/, '<p><a href="' + ES.esc(dashUrl) + '">Ouvrir le tableau de bord complet</a></p></div>');
        mail.text = 'Fiche : ' + link + '\n\n' + mail.text + '\nTableau de bord : ' + dashUrl;
      }
      const cluster = score.families.insiders.items.some((x) => /^cluster/.test(x.label));
      const discTrend = !!(score.discount && score.discount.pct >= cfg.weights.insiders.discountMediumPct && score.trendUp);
      const profile = cluster ? 'Cluster ≥ ' + cfg.insiders.clusterMinBuyers + ' dirigeants' : discTrend ? 'Décote ≥ ' + cfg.weights.insiders.discountMediumPct + ' % + MM50 > MM200' : score.panicBuy ? 'Achat dans la panique' : score.buys.some((t) => t.ceo || t.cfo) ? 'Achat DG ou DAF' : 'Achat volontaire';
      outbox.push({ id: isin + '-' + decision.fingerprint, isin, name: i.name, subject: mail.subject, html: mail.html, text: mail.text, eventIds: decision.eventIds, score: score.total, version: cfg.scoringVersion, profile });
    }
  });

  /* 6. Étude d'événements (validation) sur l'archive accumulée */
  // Pré-calculs pour les critères en observation : séries ajustées, achats significatifs par société, rendement 6 mois
  const adjAll = {}, sigAll = {};
  Object.keys(inst).forEach((isin) => {
    if (pItems[isin]) adjAll[isin] = ES.adjustedSeries(ES.normalizeSeries(pItems[isin].rows), pItems[isin].splits || []);
    // Supports et résistances sur un an (affichés dans les fiches et la sélection ; information, hors note)
    if (adjAll[isin]) { try { const sr = ES.supportResistance(adjAll[isin]); if (sr) inst[isin].levels = sr; } catch (e) { /* niveaux non calculables */ } }
    // Plan d'entrée (rebond sur support ou cassure de résistance) : information, hors note ; le cône est recalculé par le tableau de bord
    if (adjAll[isin] && inst[isin].levels) {
      try { const pl = ES.entryPlan(adjAll[isin], { levels: inst[isin].levels, riskPct: (cfg.plan && cfg.plan.riskPct) || 1, maxWeightPct: (cfg.plan && cfg.plan.maxWeightPct) || 25 }); if (pl) { delete pl.cone; inst[isin].plan = pl; } } catch (e) { /* plan non calculable */ }
    }
    const R0 = refs[isin] || {};
    sigAll[isin] = ES.countedBuys(tx[isin], R0, cfg).map((t) => ES.availDate(t));
  });
  // Profil des acheteurs : historique de chaque dirigeant (toutes sociétés), résultat 60 séances après chaque achat
  const bAdj0 = prices.bench ? ES.adjustedSeries(ES.normalizeSeries(prices.bench.rows), []) : null;
  const bIdx0 = {}; if (bAdj0) bAdj0.forEach((r, k) => { bIdx0[r[0]] = k; });
  const archiveFrom = Object.values(tx).flat().map((t) => t.txDate).filter(Boolean).sort()[0] || null;
  // Historique long (France depuis 2021, Suède depuis 2016) ajouté à l'archive : profil habituel / inhabituel, palmarès, fiche dirigeant
  let hist;
  try { hist = loadHistory(today, tx); } catch (e) { console.warn('  Historique long illisible : ' + e.message); hist = { tx: {}, cov: {}, outcomes: {}, n: {}, from: {}, cut: {} }; }
  if (!isObj(hist.outcomes)) hist.outcomes = {};
  const allTx = {};
  new Set(Object.keys(hist.tx).concat(Object.keys(tx))).forEach((isin) => { allTx[isin] = (hist.tx[isin] || []).concat(tx[isin] || []); });
  const covOf = (t) => hist.cov[t.registry] || archiveFrom;
  const buyerHist = {}, buyerTrades = {}, sigBuys = {};
  const fwdRet = (a, d, h) => { if (!a) return null; let i = 0; while (i < a.length && a[i][0] <= d) i++; if (i + h >= a.length) return null; const e = a[i][1] != null ? a[i][1] : a[i][4]; return a[i + h][4] / e - 1; };
  const hz = cfg.learning.horizon;
  Object.keys(allTx).forEach((isin) => {
    const R0 = refs[isin] || {}, act = ES.activeTx(allTx[isin]);
    sigBuys[isin] = ES.countedBuys(allTx[isin], R0, cfg); // même règle que la note
    sigBuys[isin].forEach((t) => {
      const key = ES.buyerKey(t) || t.personKey; if (!key) return;
      const d = ES.availDate(t), a = adjAll[isin], o = hist.outcomes[isin + '|' + d], ho = histOutcome(o, H_IDX[hz] ? hz : 60);
      // résultat : collecteur d'historique (STOXX 600, en euros) sinon cours du soir (CAC 40)
      (buyerHist[key] = buyerHist[key] || []).push({ isin, id: t.id, date: d, eur: ES.toEur(t.amount, t.currency) || 0,
        ret: ho ? ho.ret : fwdRet(a, d, hz), excess: ho ? ho.excess : a && bAdj0 ? ES.forwardExcess(a, bAdj0, bIdx0, d, hz, 0) : null });
    });
    // ordres volontaires (achats et ventes) : base du classement de Cohen, Malloy et Pomorski
    act.forEach((t) => { if ((t.type === 'achat' || t.type === 'vente') && !ES.excludedEntity(t, cfg)) { const key = ES.buyerKey(t) || t.personKey; if (key) (buyerTrades[key] = buyerTrades[key] || []).push({ date: t.txDate }); } });
  });
  const profileOf = (t) => { const key = ES.buyerKey(t) || t.personKey; if (!key) return null; return ES.buyerProfile(buyerHist[key], { date: ES.availDate(t), eur: ES.toEur(t.amount, t.currency) || 0 }, covOf(t), buyerTrades[key]); };
  // Étude sur l'historique long : chaque achat jugé avec ce qu'on savait ce jour-là, résultat à 3 et 6 mois contre le STOXX 600
  const histEvents = [], seenEv = {};
  Object.keys(sigBuys).forEach((isin) => sigBuys[isin].forEach((t) => {
    const key = ES.buyerKey(t) || t.personKey, d = ES.availDate(t); if (!key || !d) return;
    const k = isin + '|' + key + '|' + d; if (seenEv[k]) return; seenEv[k] = 1;
    const o = hist.outcomes[isin + '|' + d], a60 = histOutcome(o, 60), a120 = histOutcome(o, 120); if (!a60 && !a120) return;
    const pf = profileOf(t) || {}, tr = pf.track && pf.track.n >= 2 ? pf.track.beat / pf.track.n : null;
    histEvents.push({ x60: a60 ? a60.excess : null, x120: a120 ? a120.excess : null, l60: a60 ? a60.local : null, l120: a120 ? a120.local : null,
      f: { dg: !!(t.ceo || t.cfo), cohen: pf.cohen, routine: pf.routine, trackGood: tr != null ? tr >= 2 / 3 : undefined, trackPoor: tr != null ? tr < 0.5 : undefined, record: pf.record === true, country: t.registryCountry || null } });
  }));
  // Humeur du marché (psychologie) : aujourd'hui et à chaque date d'achat
  // Profils des acheteurs de la fenêtre actuelle (affichés dans la fiche, utilisés par l'avis croisé)
  cands.forEach((c) => {
    const bp = {};
    (c.score.buys || []).forEach((t) => { const key = ES.buyerKey(t) || t.personKey; if (!key) return; const pf = profileOf(t); if (!pf) return;
      const prev = bp[key]; if (!prev || ES.availDate(t) > prev.date) bp[key] = Object.assign({ name: t.associated && t.linkedTo ? t.linkedTo : t.person, date: ES.availDate(t), ceo: !!(t.ceo || t.cfo) }, pf); });
    if (Object.keys(bp).length) inst[c.isin].buyerProfiles = bp;
  });
  const moodCache = {};
  const moodAt = (d) => { if (!(d in moodCache)) { try { moodCache[d] = ES.marketMood(mAdj0, d); } catch (e) { moodCache[d] = null; } } return moodCache[d]; };
  const r6 = (a, d) => { if (!a) return null; let lo = 0, hi = a.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (a[m][0] <= d) { k = m; lo = m + 1; } else hi = m - 1; } return k >= 126 ? (a[k - 21][4] / a[k - 126][4] - 1) * 100 : null; };
  const mAdj0 = mRef && mRef.rows ? ES.adjustedSeries(ES.normalizeSeries(mRef.rows), []) : null;
  const secCache = {};
  const sectorStrongAt = (sec, d) => {
    if (!sec || !mAdj0) return undefined;
    const key = sec + '|' + d; if (key in secCache) return secCache[key];
    const m = r6(mAdj0, d), vals = Object.keys(inst).filter((j) => inst[j].sector === sec && adjAll[j]).map((j) => r6(adjAll[j], d)).filter((x) => x != null).sort((a, b) => a - b);
    return (secCache[key] = m == null || vals.length < 5 ? undefined : vals[Math.floor(vals.length / 2)] > m);
  };
  const breadthAt = (sec, d) => {
    if (!sec) return undefined;
    const from = ES.addDays(d, -30);
    return Object.keys(inst).filter((j) => inst[j].sector === sec && sigAll[j].some((x) => x >= from && x <= d)).length >= 3;
  };
  const SHORT_HIST = { FR: 1, IT: 1, ES: 1, NL: 1, BE: 1 }; // régulateurs publiant l'historique ; Allemagne : à partir de la première collecte
  state.shortsSince = state.shortsSince || {};
  Object.keys(shortsSrc).forEach((cc) => { if (shortsSrc[cc].status === 'ok' && !state.shortsSince[cc]) state.shortsSince[cc] = today; });
  const shortOk = (cc) => shortsSrc[cc] && shortsSrc[cc].status === 'ok';
  const shortCovered = (isin, d) => {
    const own = (shortsList[isin] || []).map((p) => p.country).filter(Boolean), cc = isin.slice(0, 2);
    const ccs = own.length ? own : [cc]; // titre déclaré auprès d'un autre régulateur (ex. Airbus, ISIN NL, à l'AMF)
    return ccs.some((c) => shortOk(c) && (SHORT_HIST[c] || (state.shortsSince[c] && d >= state.shortsSince[c])));
  };
  const events = [], samples = [];
  const bAdj = prices.bench ? ES.adjustedSeries(ES.normalizeSeries(prices.bench.rows), []) : null;
  const bIdx = {}; if (bAdj) bAdj.forEach((r, k) => { bIdx[r[0]] = k; });
  const mAdj = mAdj0, ret6m1At = r6;
  Object.keys(inst).forEach((isin) => {
    if (!pItems[isin]) return;
    const R = refs[isin] || {};
    const buys = ES.countedBuys(tx[isin], R, cfg).sort((a, b) => (ES.availDate(a) < ES.availDate(b) ? -1 : 1));
    // moyennes 50 / 200 connues à la date de publication (aucune donnée postérieure)
    const adj = ES.adjustedSeries(ES.normalizeSeries(pItems[isin].rows), pItems[isin].splits || []);
    const cum = [0]; adj.forEach((r) => cum.push(cum[cum.length - 1] + r[4]));
    const trendAt = (d) => { let lo = 0, hi = adj.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (adj[m][0] <= d) { k = m; lo = m + 1; } else hi = m - 1; } if (k < 199) return null; return (cum[k + 1] - cum[k - 49]) / 50 > (cum[k + 1] - cum[k - 199]) / 200; };
    const W = cfg.weights.insiders;
    const fund = inst[isin].fund || {}, cap = fund.marketCap && (!fund.currency || fund.currency === 'EUR' || inst[isin].currency === 'EUR') ? fund.marketCap : null;
    let lastCluster = null;
    const lastBy = {}; // regroupement : un même groupe ne compte qu'une fois par société sur la fenêtre du cluster
    const push = (g, d) => { if (lastBy[g] && ES.daysBetween(lastBy[g], d) < cfg.insiders.clusterWindowDays) return false; lastBy[g] = d; events.push({ isin, date: d, group: g }); return true; };
    const raw = [];
    buys.forEach((t) => {
      const d = ES.availDate(t);
      push('Achat volontaire', d);
      const a = R[t.id] && !R[t.id].outOfRange ? R[t.id].atPurchase : null;
      if (a && a.paidVsHigh52Pct != null && -a.paidVsHigh52Pct >= W.discountMediumPct) {
        push('Décote ≥ ' + W.discountMediumPct + ' %', d);
        if (trendAt(d)) push('Décote ≥ ' + W.discountMediumPct + ' % + MM50 > MM200', d);
      }
      if (a && ES.isPanic(a, W)) push('Achat dans la panique', d);
      // composantes connues à la date de publication, et résultat réel 60 séances plus tard
      const disc = a && a.paidVsHigh52Pct != null ? -a.paidVsHigh52Pct : null;
      const above = trendAt(d); // MM50 > MM200 à la date de publication
      const rs = mAdj ? (() => { const x = ret6m1At(adj, d), y = ret6m1At(mAdj, d); return x != null && y != null ? x - y : null; })() : null;
      const known2 = buys.filter((b) => ES.availDate(b) <= d && b.txDate >= ES.addDays(t.txDate, -(cfg.insiders.clusterWindowDays - 1)) && b.txDate <= t.txDate);
      raw.push({ isin, date: d, excess: bAdj ? ES.forwardExcess(adj, bAdj, bIdx, d, cfg.learning.horizon, cfg.backtest.costRoundTripPct / 100) : null,
        f: { discountBig: disc != null ? disc >= W.discountBigPct : undefined, discountMedium: disc != null ? disc >= W.discountMediumPct && disc < W.discountBigPct : undefined,
          panic: a ? ES.isPanic(a, W) : undefined, ceo: !!(t.ceo || t.cfo),
          cluster: ES.clusterInfo(known2, cfg.insiders.clusterWindowDays).count >= cfg.insiders.clusterMinBuyers, trend: above == null ? undefined : above, relStrong: rs == null ? undefined : rs >= cfg.weights.market.relStrengthPts,
          // critères en observation (sans poids dans le score)
          sectorStrong: sectorStrongAt(inst[isin].sector, d), sectorBreadth: breadthAt(inst[isin].sector, d),
          smallMid: cap ? cap < 2e9 : undefined,
          bigVsCap: cap ? known2.filter((b) => (b.personKey || b.person) === (t.personKey || t.person)).reduce((a, b) => a + (ES.toEur(b.amount, b.currency) || 0), 0) / cap >= 0.0005 : undefined,
          peerCheap: state.obsAtBuy[t.id] && state.obsAtBuy[t.id].peerDisc != null ? state.obsAtBuy[t.id].peerDisc >= cfg.valuation.cheapPct : undefined,
          // Révisions des analystes : relevées le soir de l'achat (pas d'historique gratuit), les cas s'accumulent au fil des mois
          revisionUp: state.obsAtBuy[t.id] && state.obsAtBuy[t.id].rev30 != null ? state.obsAtBuy[t.id].rev30 >= 1 : undefined,
          revisionDown: state.obsAtBuy[t.id] && state.obsAtBuy[t.id].rev30 != null ? state.obsAtBuy[t.id].rev30 <= -1 : undefined,
          ...(() => { const f = state.obsAtBuy[t.id] && state.obsAtBuy[t.id].fc; if (!f) return {};
            return { fcGrowth: f.n >= 3 ? f.tone === 'good' && f.epsG1 != null && f.epsG1 >= 10 : undefined, fcBad: f.n >= 3 ? f.tone === 'bad' : undefined, fcUpside: f.upside != null ? f.upside >= 20 : undefined }; })(),
          // Actionnariat : données du moment (l'actionnariat change lentement)
          controlled: ES.ownership(inst[isin].fund).controlled, lowFloat: ES.ownership(inst[isin].fund).lowFloat,
          shorted: shortCovered(isin, d) ? !!ES.shortInfo(shortsList[isin], d) : undefined,
          ...(() => { const a = finList[isin] ? accAt(isin, d) : null; return { fscoreHigh: a && a.fscore && !a.fscore.na ? a.fscore.f9 >= cfg.accounts.fscoreGood : undefined,
            altmanDistress: a && a.altman && !a.altman.na ? a.altman.zone === 'distress' : undefined, beneishFlag: a && a.beneish && !a.beneish.na ? a.beneish.flag : undefined }; })(),
          // Valeur comptable et intrinsèque avec le cours et les comptes publiés à la date de l'achat
          ...(() => { const v = valueAt(isin, d); return v && !v.na && !v.negEquity && v.pb != null ? { belowBook: v.pb < 1, ivDiscount: v.marginPct != null ? ES.valueCheap(v) : undefined } : {}; })(),
          // Situation technique à la date de publication (support proche, cassure récente) : cours connus ce jour-là seulement
          ...(() => { const st = ES.setupAt(adj, d); return st ? { nearSupport: st.nearSupport, breakout: st.breakout } : {}; })(),
          ...(() => { const o = ES.oscillatorsAt(adj, d); return o ? { rsiLow: o.rsi < 30, macdBull: o.above } : {}; })(),
          ...(() => { const pf = profileOf(t), m = moodAt(d); return { opportunistic: !pf || pf.routine === 'inconnu' ? undefined : pf.routine === 'inhabituel', trackGood: pf && pf.track && pf.track.n >= 2 ? pf.track.beat / pf.track.n >= 2 / 3 : undefined, personalRecord: pf && pf.record != null ? pf.record : undefined, marketFear: m ? m.key === 'fear' : undefined }; })() } });
      if (ES.daysBetween(d, today) <= 7 && !state.obsAtBuy[t.id]) {
        const fv = inst[isin].forecast ? ES.forecastView(inst[isin].forecast, inst[isin].fund) : null;
        state.obsAtBuy[t.id] = { at: today, peerDisc: inst[isin].peer ? inst[isin].peer.discountPct : null, rev30: Number.isFinite(+inst[isin].revision30d) && inst[isin].revision30d !== null ? +inst[isin].revision30d : null,
          // prévisionnels figés le soir de l'achat (Yahoo n'en garde pas l'historique)
          fc: fv && !fv.na ? { tone: fv.tone, n: fv.n, epsG1: fv.epsG1 != null ? +fv.epsG1.toFixed(1) : null, rev90: fv.rev90 != null ? +fv.rev90.toFixed(1) : null, upside: fv.upside != null ? +fv.upside.toFixed(1) : null } : null };
      }
      if (t.ceo || t.cfo) push('Achat DG ou DAF', d);
      const known = known2;
      if (ES.clusterInfo(known, cfg.insiders.clusterWindowDays).count >= cfg.insiders.clusterMinBuyers && (!lastCluster || ES.daysBetween(lastCluster, d) > 30)) { events.push({ isin, date: d, group: 'Cluster ≥ ' + cfg.insiders.clusterMinBuyers + ' dirigeants' }); lastCluster = d; }
    });
    // Un cluster (ou une série d'achats rapprochés) = un seul cas : fenêtre ouverte au premier achat, close après clusterWindowDays
    let win = null;
    const flush = () => { if (!win) return; const last = win.items[win.items.length - 1]; const f = {};
      win.items.forEach((x) => Object.keys(x.f).forEach((k) => { if (x.f[k] === true) f[k] = true; else if (x.f[k] === false && f[k] !== true) f[k] = false; }));
      samples.push({ isin, date: last.date, f, excess: bAdj ? ES.forwardExcess(adj, bAdj, bIdx, last.date, cfg.learning.horizon, cfg.backtest.costRoundTripPct / 100) : null, n: win.items.length }); win = null; };
    raw.forEach((x) => { if (win && ES.daysBetween(win.start, x.date) >= cfg.insiders.clusterWindowDays) flush(); if (!win) win = { start: x.date, items: [] }; win.items.push(x); });
    flush();
  });
  const series = {};
  Object.keys(pItems).forEach((isin) => { series[isin] = { rows: pItems[isin].rows, splits: pItems[isin].splits || [] }; });
  const oos = cfg.backtest.oosStart || ES.addMonths(today, -6);
  // Rendement médian des autres sociétés liquides du même secteur sur la même période : sépare le talent du dirigeant de l'effet secteur
  const secMembers = {}, dateIdx = {};
  Object.keys(inst).forEach((isin) => { const sc = inst[isin].sector; if (!sc || !adjAll[isin] || inst[isin].benchmark) return; (secMembers[sc] = secMembers[sc] || []).push(isin); });
  const idxOf = (isin) => { if (!dateIdx[isin]) { const m = {}; adjAll[isin].forEach((r, k) => { m[r[0]] = k; }); dateIdx[isin] = m; } return dateIdx[isin]; };
  const secRetCache = {};
  const sectorRet = (isin, d0, d1) => {
    const sc = inst[isin] && inst[isin].sector, key = isin + '|' + d0 + '|' + d1;
    if (!sc || !secMembers[sc]) return null;
    if (!(key in secRetCache)) {
      const v = secMembers[sc].filter((o) => o !== isin).map((o) => { const a = adjAll[o], I = idxOf(o); if (I[d0] == null || I[d1] == null) return null; const x0 = a[I[d0]], x1 = a[I[d1]]; const e = x0[1] != null ? x0[1] : x0[4]; return e > 0 ? x1[4] / e - 1 : null; }).filter((x) => x != null && isFinite(x) && Math.abs(x) < 3).sort((x, y) => x - y);
      secRetCache[key] = v.length >= 5 ? v[Math.floor(v.length / 2)] : null;
    }
    return secRetCache[key];
  };
  const backtest = { results: ES.eventStudy(events, series, prices.bench ? { rows: prices.bench.rows, splits: [] } : null, { costRoundTripPct: cfg.backtest.costRoundTripPct, horizons: cfg.backtest.horizons, oosStart: oos, bench2: prices.market && prices.market.ticker !== (prices.bench && prices.bench.ticker) ? { rows: prices.market.rows, splits: [] } : null, sectorRet }), bench: prices.bench ? prices.bench.ticker : null, bench2: prices.market ? prices.market.ticker : null, oosStart: oos, cost: cfg.backtest.costRoundTripPct, horizons: cfg.backtest.horizons, events: events.length };

  /* 6a. Auto-apprentissage mensuel (appliqué à partir du passage suivant) */
  // Sans cours frais (panne Yahoo), on ne consomme pas le recalibrage du mois : il sera retenté le soir suivant.
  const canLearn = pFresh && samples.some((x) => x.excess != null);
  // Garde-fou : l'historique long (France et Suède, plusieurs milliers d'achats) fixe le sens admis quand il l'établit nettement
  const histStudy = ES.historyStudy(histEvents, { costRoundTripPct: cfg.backtest.costRoundTripPct, horizons: [60, 120] });
  const priors = {};
  { const g = (k) => (histStudy.find((r) => r.key === k) || {}).h60, a = g('dg'), b = g('other');
    if (a && b && a.n >= 100 && b.n >= 100 && a.ci && b.ci && (a.ci[0] > b.ci[1] || b.ci[0] > a.ci[1])) priors.ceo = { sign: a.mean > b.mean ? 1 : -1, text: 'achats DG/DAF ' + (a.mean > b.mean ? 'meilleurs' : 'moins bons') + ' que les autres sur ' + a.n + ' cas' }; }
  const learning = canLearn ? ES.calibrate(samples, ES.mergeConfig(cfg, {}), learnPrev, today, { priors })
    : Object.assign({ month: null, version: 0, weights: {}, log: [], stats: [] }, learnPrev || {}, { changed: [] });
  learning.mode = cfg.learning.mode; learning.samples = samples.length; learning.withOutcome = samples.filter((x) => x.excess != null).length; learning.baseVersion = baseVersion;
  // Règles figées jusqu'à la revue (protection contre le sur-ajustement sur peu de cas) : les mesures continuent, le barème ne bouge pas
  const frozen = !!(cfg.rules && cfg.rules.frozenUntil && today <= cfg.rules.frozenUntil);
  learning.frozenUntil = frozen ? cfg.rules.frozenUntil : null;
  if (frozen && learning.changed.length) { learning.changed = []; learning.weights = (learnPrev && learnPrev.weights) || {}; learning.version = (learnPrev && learnPrev.version) || 0; }
  if (learning.changed.length && cfg.learning.mode === 'auto') {
    state.pendingInfo = state.pendingInfo || {};
    const lines = learning.changed.map((e) => e.label + ' : ' + e.from + ' → ' + e.to + ' point(s) (écart mesuré ' + (e.effect >= 0 ? '+' : '') + e.effect + ' pt sur ' + e.nWith + ' cas, t = ' + e.t + ')');
    state.pendingInfo['apprentissage-' + learning.month] = ({ id: 'apprentissage-' + learning.month, kind: 'info', isin: null, name: 'Barème', subject: '[Euro Signal] Barème ajusté automatiquement (' + learning.month + ')',
      text: 'Euro Signal a comparé ses signaux aux résultats réels et ajusté son barème :\n' + lines.join('\n') + '\n\nRègles : un pas au plus par mois, seulement si l\'écart est net sur au moins ' + cfg.learning.minCases + ' cas, entre 0 et 2 fois le poids d\'origine. Pour désactiver : "learning": {"mode": "off"} dans euro_signal/config.json.',
      html: '<div style="font-family:Arial,sans-serif;font-size:14px"><h2>Barème ajusté automatiquement</h2><p>Euro Signal a comparé ses signaux aux résultats réels (' + learning.withOutcome + ' achats suivis sur ' + cfg.learning.horizon + ' séances) :</p><ul>' + lines.map((l) => '<li>' + ES.esc(l) + '</li>').join('') + '</ul><p style="color:#55615c;font-size:12px">Un pas au plus par mois, seulement si l\'écart est net sur au moins ' + cfg.learning.minCases + ' cas, entre 0 et 2 fois le poids d\'origine. Désactivable dans euro_signal/config.json.</p>' + (dashUrl ? '<p><a href="' + ES.esc(dashUrl) + '">Voir l\'onglet Résultats passés</a></p>' : '') + '</div>',
      eventIds: ['learn:' + learning.month], score: null, version: cfg.scoringVersion });
  }  // Emails d'information en attente (barème) : renvoyés chaque soir jusqu'à un envoi confirmé ou incertain, jamais deux fois
  Object.keys(state.pendingInfo || {}).forEach((id) => {
    const a = state.alerts[id], sent = a && ['envoyee', 'incertain', 'en_cours'].concat(process.env.ES_MAIL_READY === 'oui' ? [] : ['simulee']).indexOf(a.status) > -1;
    if (sent) delete state.pendingInfo[id]; else outbox.push(state.pendingInfo[id]);
  });


  /* 6c. Suivi des alertes envoyées et signaux de sortie */
  const followups = [];
  if (cfg.exits.enabled) {
    const tracked = Object.values(state.alerts).filter((a) => a.isin && !a.kind && ['envoyee', 'incertain', 'simulee'].indexOf(a.status) > -1);
    const latestByIsin = {}; tracked.forEach((a) => { if (!latestByIsin[a.isin] || a.createdAt > latestByIsin[a.isin].createdAt) latestByIsin[a.isin] = a; });
    Object.values(latestByIsin).forEach((a) => {
      const d0 = String(a.createdAt || '').slice(0, 10), p = pItems[a.isin], i = inst[a.isin];
      if (!d0 || !p || !i || ES.daysBetween(d0, today) > cfg.exits.followDays) return;
      const adj = ES.adjustedSeries(ES.normalizeSeries(p.rows), p.splits || []);
      const after = adj.filter((r) => r[0] >= d0);
      if (!after.length) return;
      const p0 = after[0][4], last = after[after.length - 1][4], peak = Math.max(...after.map((r) => r[4]));
      let benchPct = null;
      if (bAdj) { const b = bAdj.filter((r) => r[0] >= d0); if (b.length) benchPct = (b[b.length - 1][4] / b[0][4] - 1) * 100; }
      const R = refs[a.isin] || {};
      const paid = (a.eventIds || []).filter((e) => /^tx:/.test(e)).map((e) => R[e.slice(3)] && !R[e.slice(3)].outOfRange ? R[e.slice(3)].paidAdj : null).filter((x) => x != null);
      const minPaid = paid.length ? Math.min(...paid) : null;
      const sells = ES.activeTx(tx[a.isin]).filter((t) => t.type === 'vente' && ES.availDate(t) > d0 && !ES.isLegalEntity(t.person, t.issuer));
      const signals = [];
      if (sells.length) signals.push({ type: 'vente', label: 'un dirigeant a vendu depuis l\'alerte (' + sells.map((t) => (t.person || '?') + ' le ' + t.txDate).slice(0, 3).join(', ') + ')' });
      if (i.stats.deathCrossDate && i.stats.deathCrossDate > d0) signals.push({ type: 'tendance', label: 'la MM50 est repassée sous la MM200 le ' + i.stats.deathCrossDate });
      if (minPaid && last < minPaid * (1 - cfg.exits.belowInsiderPricePct / 100)) signals.push({ type: 'prix_dirigeant', label: 'le cours (' + last.toFixed(2) + ') est plus de ' + cfg.exits.belowInsiderPricePct + ' % sous le prix payé par les dirigeants (' + minPaid.toFixed(2) + ')' });
      if (last / peak - 1 <= -cfg.exits.drawdownFromPeakPct / 100) signals.push({ type: 'repli', label: 'le cours a reculé de ' + Math.round((1 - last / peak) * 100) + ' % depuis son plus haut atteint après l\'alerte' });
      const perf = (last / p0 - 1) * 100;
      followups.push({ alertId: a.id, isin: a.isin, name: i.name, sentAt: d0, status: a.status, priceAtAlert: p0, last, perfPct: perf, benchPct, fromPeakPct: (last / peak - 1) * 100, signals: signals.map((x) => x.label) });
      if (a.status === 'simulee') return; // pas d'email de sortie pour une alerte jamais envoyée
      signals.forEach((sg) => {
        const id = a.id + '-sortie-' + sg.type;
        if (state.alerts[id] && ['envoyee', 'incertain', 'en_cours'].indexOf(state.alerts[id].status) > -1) return;
        const body = 'Signal de sortie sur ' + i.name + ' : ' + sg.label + '. Depuis l\'alerte du ' + d0 + ' : ' + ES.fmtPct(perf) + (benchPct != null ? ' (CAC 40 : ' + ES.fmtPct(benchPct) + ')' : '') + '.';
        outbox.push({ id, kind: 'sortie', isin: a.isin, name: i.name, subject: '[Euro Signal] Signal de sortie — ' + i.name,
          text: body + '\nCe n\'est pas un ordre de vente : à examiner selon votre propre stratégie.' + (dashUrl ? '\nFiche : ' + dashUrl + '#' + a.isin : ''),
          html: '<div style="font-family:Arial,sans-serif;font-size:14px;max-width:680px"><h2 style="margin:0 0 6px">Signal de sortie — ' + ES.esc(i.name) + '</h2>' + (dashUrl ? '<p><a href="' + ES.esc(dashUrl + '#' + a.isin) + '" style="display:inline-block;background:#0D6A56;color:#fff;text-decoration:none;font-weight:bold;padding:10px 16px;border-radius:6px">Voir la fiche</a></p>' : '') + '<p>' + ES.esc(body) + '</p><p style="color:#55615c;font-size:12px">Ce n\'est pas un ordre de vente : à examiner selon votre propre stratégie. Un même signal n\'est envoyé qu\'une fois.</p></div>',
          eventIds: ['exit:' + id], score: null, version: cfg.scoringVersion });
      });
    });
  }

  /* 6d. Sélection de la semaine : les meilleurs dossiers du moment, un email par semaine (premier soir à partir du jour prévu) */
  const selCfg = cfg.selection || {};
  const week = ES.isoWeek(today);
  const selection = { week, items: ES.weeklySelection(cands, cfg, today) };
  // « Nouveau » : absent de la sélection précédente
  state.selections = isObj(state.selections) ? state.selections : {};
  Object.keys(state.selections).forEach((w) => { const v = state.selections[w]; if (!isObj(v) || !Array.isArray(v.items) || typeof v.date !== 'string') delete state.selections[w]; });
  const prevWeek = Object.keys(state.selections).filter((w) => w < week).sort().pop();
  if (prevWeek) { const was = new Set(state.selections[prevWeek].items.map((x) => x.isin)); selection.items.forEach((x) => { x.isNew = !was.has(x.isin); }); }
  // Suivi des sélections passées (tableau de bord et email) : performance depuis l'envoi, comparée au CAC 40
  const closeAt = (rows, splits, d) => { const a = ES.adjustedSeries(ES.normalizeSeries(rows), splits || []); const nx = a.find((r) => r[0] > d); return { at: nx ? nx[1] || nx[4] : null, last: a.length ? a[a.length - 1][4] : null }; }; // ouverture de la séance suivant l'envoi
  const selectionTrack = Object.keys(state.selections).filter((w) => w < week).sort().slice(-26).map((w) => {
    const S0 = state.selections[w], b = prices.bench ? closeAt(prices.bench.rows, [], S0.date) : null;
    const bench = b && b.at && b.last ? (b.last / b.at - 1) * 100 : null;
    return { week: w, date: S0.date, bench, items: S0.items.map((x) => { const p = pItems[x.isin]; const c = p ? closeAt(p.rows, p.splits, S0.date) : null; return { isin: x.isin, name: x.name, score: x.score, perf: c && c.at && c.last ? (c.last / c.at - 1) * 100 : null }; }) };
  });
  selection.track = ES.selectionTrackSummary(selectionTrack);
  // Repère historique : sélections rejouées chaque lundi passé, avec uniquement l'information connue ce jour-là
  const replay = [];
  try {
    const firstAvail = Object.values(sigAll).flat().sort()[0];
    const monday = (d) => { const x = new Date(d + 'T12:00:00Z'); x.setUTCDate(x.getUTCDate() - ((x.getUTCDay() + 6) % 7)); return x.toISOString().slice(0, 10); };
    let D = firstAvail ? monday(ES.addDays(firstAvail, 7)) : null;
    const stopAt = monday(today), weeks = [];
    while (D && D < stopAt) { weeks.push(D); D = ES.addDays(D, 7); }
    const recentDays = selCfg.recentDays || 30;
    weeks.slice(-52).forEach((D0) => {
      const mRows = mRef && mRef.rows ? mRef.rows.filter((r) => r && r[0] <= D0) : [];
      const mS = mRows.length > 200 ? ES.computeStats(mRows, [], D0, ES.mergeConfig(ES.DEFAULT_CONFIG, {}), null) : null;
      const from = ES.addDays(D0, -recentDays), notes = [];
      Object.keys(inst).forEach((isin) => {
        if (!pItems[isin] || !sigAll[isin].some((x) => x >= from && x <= D0)) return;
        const i = inst[isin], p = pItems[isin], rows = p.rows.filter((r) => r && r[0] <= D0);
        if (rows.length < 200) return;
        const splits = (p.splits || []).filter((x) => x.date <= D0);
        const st = ES.computeStats(rows, splits, D0, cfg, i.currency);
        if (mS && st.ret6m1 != null && mS.ret6m1 != null) st.rel6m = st.ret6m1 - mS.ret6m1;
        if (mS) st.marketAbove200 = mS.sma200 ? mS.lastCloseAdj > mS.sma200 : null;
        const iD = Object.assign({}, i, { stats: st });
        if (ES.universeStatus(iD, cfg).status !== 'retenu' || ES.financialHealth(i.fund).status === 'fragile') return;
        if (selCfg.peaOnly !== false && i.peaStatus === 'non_eligible') return; // mêmes filtres que la sélection réelle (revue du 2026-10-12)
        const txD = tx[isin].filter((t) => ES.availDate(t) <= D0), rf = {};
        txD.forEach((t) => { if (t.type === 'achat' || t.type === 'vente') rf[t.id] = ES.priceRefs(t, rows, splits, D0, p.currency || null); });
        const sc = ES.score({ inst: iD, tx: txD, events: evOut[isin] || { buybacks: [], results: [] }, refs: rf, cfg, today: D0 });
        if (!sc.buys.length || sc.ambiguousCount || sc.total < (selCfg.minScore || 0)) return;
        if (!sc.buys.some((t) => ES.availDate(t) >= from)) return;
        if (sc.sellEur > sc.buyEur && sc.sellEur > 0) return;
        const acD = finList[isin] ? accAt(isin, D0) : null; // comptes publiés à cette date seulement
        if (acD && acD.fscore && !acD.fscore.na && acD.fscore.f9 <= 1) return; // comptes en forte dégradation : écartés comme dans la sélection réelle
        notes.push({ isin, total: sc.total, disc: sc.discount ? sc.discount.pct : 0, note: ES.note(sc.total, cfg), dg: sc.buys.some((t) => (t.ceo || t.cfo) && ES.availDate(t) >= from), cl: !!(sc.cluster && sc.cluster.count >= cfg.insiders.clusterMinBuyers), fs: acD && acD.fscore && !acD.fscore.na ? acD.fscore.f9 : null });
      });
      notes.sort((a, b) => b.total - a.total || b.disc - a.disc); // même ordre que la sélection réelle : note, puis décote
      replay.push({ week: ES.isoWeek(D0), date: D0, picks: notes.filter((x) => !selCfg.requireCeoCfo || x.dg).slice(0, selCfg.size || 5), cands: notes });
    });
  } catch (e) { console.warn('  Repère historique indisponible : ' + e.message); replay.length = 0; }
  // Une société retenue plusieurs lundis de suite = un seul dossier (sa meilleure note). Les dossiers de la sélection actuelle
  // encore « en cours » (retenus jusqu'à la dernière semaine rejouée) sont écartés du repère : on ne se compare pas à soi-même.
  const cur = new Set(selection.items.map((x) => x.isin)), lastK = replay.length - 1, streak = {};
  cur.forEach((isin) => { let k = lastK; while (k >= 0 && replay[k].picks.some((x) => x.isin === isin)) k--; if (k < lastK) streak[isin] = k + 1; });
  const ongoing = (isin, k) => streak[isin] != null && k >= streak[isin];
  const episodes = {}, histNotes = [];
  replay.forEach((w, k) => w.picks.forEach((x) => {
    if (ongoing(x.isin, k)) return;
    const e = episodes[x.isin];
    if (e && e.last === k - 1) { e.note = Math.max(e.note, x.note); e.last = k; } else { if (e) histNotes.push(e.note); episodes[x.isin] = { note: x.note, last: k }; }
  }));
  Object.keys(episodes).forEach((i) => histNotes.push(episodes[i].note));
  const weekBest = replay.map((w, k) => w.picks.filter((x) => !ongoing(x.isin, k))).filter((p) => p.length).map((p) => p[0].note);
  const candBy = {}; cands.forEach((c) => { candBy[c.isin] = c; });
  selection.items.forEach((x) => {
    x.note = ES.note(x.score, cfg); x.hist = ES.historicRank(x.note, histNotes);
    const c = candBy[x.isin];
    if (c) { const a = ES.advice(c.inst, c.score, cfg, { histKey: x.hist.key, today, universe: c.universe, mood: moodAt(today) }); x.advice = { key: a.key, icon: a.icon, label: a.label, why: a.why, signals: a.signals.map((g) => ({ k: g.k, icon: g.icon, text: g.text, tone: g.tone })) }; try { const z = ES.positionSize(c.inst, c.score, a, cfg); x.size = { pct: z.pct, stopPct: z.stopPct, staged: z.staged }; } catch (e) { /* taille non calculable */ } }
  });
  selection.verdict = ES.weekVerdict(selection.items, weekBest);
  selection.reference = { weeks: replay.length, withPicks: weekBest.length, from: replay.length ? replay[0].date : null, histNotes, weekBest };
  // Fiabilité mesurée : ce que sont devenues les sélections rejouées, 60 séances (≈ 3 mois) plus tard, frais de 0,5 % déduits.
  // Une société retenue plusieurs lundis de suite ne compte qu'une fois (à sa première semaine).
  try {
    const H = cfg.learning.horizon, cost = cfg.backtest.costRoundTripPct / 100, N = selCfg.size || 5;
    const outsOf = (pick, h) => {
      const hh = h || H, outs = [], lastSeen = {};
      replay.forEach((w, k) => pick(w).forEach((x) => {
        const cont = lastSeen[x.isin] === k - 1; lastSeen[x.isin] = k;
        if (cont) return;
        const a = adjAll[x.isin], r = fwdRet(a, w.date, hh);
        if (r == null) return;
        outs.push({ isin: x.isin, date: w.date, note: x.note, ret: r - cost, excess: a && bAdj0 ? ES.forwardExcess(a, bAdj0, bIdx0, w.date, hh, cost) : null });
      }));
      return outs;
    };
    const outs = outsOf((w) => w.picks);
    // Variantes de règle, rejouées de la même façon : ne garder que les achats du DG ou du DAF, ou aussi les clusters
    const variant = (f) => { const o = outsOf((w) => (w.cands || []).filter(f).slice(0, N)); const st = ES.outcomeStats(o); if (st) st.perWeek = Math.round(replay.reduce((a, w) => a + Math.min(N, (w.cands || []).filter(f).length), 0) / Math.max(1, replay.length) * 10) / 10; return st; };
    const G = cfg.accounts.fscoreGood;
    const variants = { current: variant(() => true), dg: variant((x) => x.dg), dgCluster: variant((x) => x.dg || x.cl), cluster: variant((x) => x.cl),
      f7: variant((x) => x.fs != null && x.fs >= G), dgF7: variant((x) => x.dg && x.fs != null && x.fs >= G) };
    const band = (lo, hi) => ES.outcomeStats(outs.filter((o) => o.note >= lo && o.note < hi));
    selection.replayStats = { horizon: H, all: ES.outcomeStats(outs), top: band(ES.note(cfg.alerts.minScore, cfg), 101), strong: band(ES.note(cfg.selection.minScore, cfg), ES.note(cfg.alerts.minScore, cfg)),
      from: outs.length ? outs.map((o) => o.date).sort()[0] : null, to: outs.length ? outs.map((o) => o.date).sort().pop() : null, variants,
      // Même mesure à 6 mois (120 séances) : l'avantage des achats de dirigeants se mesure surtout entre 6 et 12 mois
      h120: { all: ES.outcomeStats(outsOf((w) => w.picks, 120)), current: ES.outcomeStats(outsOf((w) => (w.cands || []).slice(0, N), 120)), dg: ES.outcomeStats(outsOf((w) => (w.cands || []).filter((x) => x.dg).slice(0, N), 120)) } };
  } catch (e) { console.warn('  Fiabilité rejouée indisponible : ' + e.message); }
  // F-score seul (stratégie de Piotroski, sans achat de dirigeant) sur les sociétés liquides suivies : chaque exercice,
  // signal 120 jours après la clôture (comptes publiés), résultat 60 séances plus tard, comparé au CAC 40, frais déduits
  try {
    const H = cfg.learning.horizon, cost = cfg.backtest.costRoundTripPct / 100, pts = [];
    Object.keys(inst).forEach((isin) => {
      const a = adjAll[isin], i = inst[isin];
      if (!a || !finList[isin] || i.benchmark || ES.universeStatus(i, cfg).status !== 'retenu') return;
      const full = accAt(isin, today);
      if (!full || !full.fscoreHistory) return;
      full.fscoreHistory.forEach((h) => {
        const row = (full.years || []).find((y) => y.year === h.year);
        if (h.na || h.f9 == null || !row) return;
        const d = ES.addDays(row.date, 120), r = fwdRet(a, d, H);
        if (r == null || d < a[0][0]) return;
        const ins = (sigAll[isin] || []).some((x) => x <= d && x >= ES.addDays(d, -180)); // achat de dirigeant dans les 6 mois précédant le signal
        const r6 = fwdRet(a, d, 120);
        pts.push({ isin, date: d, f9: h.f9, ins, ret: r - cost, excess: bAdj0 ? ES.forwardExcess(a, bAdj0, bIdx0, d, H, cost) : null, ret120: r6 == null ? null : r6 - cost, excess120: r6 != null && bAdj0 ? ES.forwardExcess(a, bAdj0, bIdx0, d, 120, cost) : null });
      });
    });
    const st = (f, k) => ES.outcomeStats(pts.filter(f).map((p) => k ? Object.assign({}, p, { ret: p.ret120, excess: p.excess120 }) : p));
    selection.piotroski = { horizon: H, n: pts.length, low: st((p) => p.f9 <= 3), mid: st((p) => p.f9 >= 4 && p.f9 <= 6), high: st((p) => p.f9 >= 7), top: st((p) => p.f9 >= 8),
      highIns: st((p) => p.f9 >= 7 && p.ins), highNoIns: st((p) => p.f9 >= 7 && !p.ins), from: pts.length ? pts.map((p) => p.date).sort()[0] : null,
      h120: { low: st((p) => p.f9 <= 3, 1), mid: st((p) => p.f9 >= 4 && p.f9 <= 6, 1), high: st((p) => p.f9 >= 7, 1), top: st((p) => p.f9 >= 8, 1) } };
  } catch (e) { console.warn('  Test du F-score seul indisponible : ' + e.message); }
  // Coût d'attendre le lundi (mesure seulement, la règle ne change pas avant la revue)
  try {
    const seen = {}, evOf = (g) => events.filter((e) => e.group === g).filter((e) => { const k = g + e.isin + e.date; if (seen[k]) return false; seen[k] = 1; return true; });
    selection.waitCost = { dg: ES.waitCost(evOf('Achat DG ou DAF'), adjAll, mAdj0), all: ES.waitCost(evOf('Achat volontaire'), adjAll, mAdj0) };
  } catch (e) { console.warn('  Coût d\'attente indisponible : ' + e.message); }
  // Portefeuille simulé : toutes les règles appliquées jour après jour aux sélections du lundi rejouées (aucune donnée future)
  try {
    const sells = {};
    Object.keys(tx).forEach((isin) => { const l = ES.activeTx(tx[isin]).filter((t) => t.type === 'vente' && (t.ceo || t.cfo)).map((t) => ES.availDate(t)); if (l.length) sells[isin] = l; });
    const N = selCfg.size || 5, run = (pick, core) => ES.paperPortfolio({ weeks: replay.map((w) => ({ date: w.date, picks: pick(w).map((x) => x.isin) })), series: adjAll, bench: mAdj0, sells, cfg, today, core });
    const named = (r) => { if (r) { const nm = (i) => (inst[i] && inst[i].name) || i; r.list.forEach((t) => { t.name = nm(t.isin); }); r.open.forEach((t) => { t.name = nm(t.isin); }); } return r; };
    const coreRule = run((w) => w.picks, true);
    selection.paper = { rule: named(run((w) => w.picks)), all: named(run((w) => (w.cands || []).slice(0, N))), bench: mRef ? mRef.ticker : null,
      // Cœur indiciel + satellite Euro Signal : la question qui compte pour un épargnant (faire mieux que l'indice seul ?)
      core: coreRule ? { ret: coreRule.ret, bench: coreRule.bench, maxDD: coreRule.maxDD, benchMaxDD: coreRule.benchMaxDD, curve: coreRule.curve.map((p) => [p[0], p[1]]), coreAll: (() => { const r = run((w) => (w.cands || []).slice(0, N), true); return r ? { ret: r.ret, maxDD: r.maxDD, curve: r.curve.map((p) => [p[0], p[1]]) } : null; })() } : null };
  } catch (e) { console.warn('  Portefeuille simulé indisponible : ' + e.message); }
  /* 6e. Classement principal (barème 3.0) : tendance + comptes sur toutes les sociétés liquides du catalogue, dirigeants en bonus */
  let rank = null;
  try {
    const t0 = Date.now(), R = cfg.rank, co = {};
    let wDates = [], dDates = [], coDate = null;
    if (fs.existsSync(F.societes)) fs.readdirSync(F.societes).filter((f) => /^\d+\.json$/.test(f)).forEach((f) => {
      const sh = readJSON(path.join(F.societes, f), null); if (!sh || !isObj(sh.items)) return;
      if (Array.isArray(sh.wDates) && sh.wDates.length > wDates.length) wDates = sh.wDates;
      if (Array.isArray(sh.dDates) && sh.dDates.length > dDates.length) dDates = sh.dDates;
      const g = String(sh.generatedAt || '').slice(0, 10); if (g && (!coDate || g > coDate)) coDate = g;
      Object.assign(co, sh.items);
    });
    const isinOfSym = {}; Object.keys(inst).forEach((isin) => { const t = inst[isin].ticker; if (t && !isinOfSym[t]) isinOfSym[t] = isin; });
    const histTk = readJSON(path.join(F.history, 'tickers.json'), {});
    const symOfIsin = {}; Object.keys(isObj(histTk) ? histTk : {}).forEach((i) => { const t = histTk[i] && histTk[i].ticker; if (t && co[t]) symOfIsin[i] = t; });
    Object.keys(isinOfSym).forEach((t) => { if (co[t]) symOfIsin[isinOfSym[t]] = t; });
    const accSummary = (a) => {
      if (!a) return null;
      const last = a.years && a.years.length ? a.years[a.years.length - 1] : null;
      return { key: a.verdict ? a.verdict.key : 'na', f9: a.fscore && !a.fscore.na ? a.fscore.f9 : null, loss: !!(last && last.netIncome != null && last.netIncome < 0),
        alt: a.altman && !a.altman.na ? a.altman.zone : null, fin: !!(a.fscore && a.fscore.na && /banques/.test(a.fscore.reason || '')) };
    };
    const coAcc = (sym, x, d) => { const fin = finList['@' + sym]; if (!fin || !Array.isArray(fin.years) || !fin.years.length) return null; try { return ES.accountsAnalysis(fin, { asOf: d, sector: x.sector, industry: x.industry }); } catch (e) { return null; } };
    const scoreOf = {}; cands.forEach((c) => { scoreOf[c.isin] = c.score; });
    const winFrom = ES.windowStart(today, cfg.insiders.windowMonths);
    const items = Object.keys(co).map((sym) => {
      const x = co[sym], isin = isinOfSym[sym] || null, i = isin ? inst[isin] : null;
      const acc = i ? accSummary(i.accounts) : accSummary(coAcc(sym, x, today));
      const sc = isin ? scoreOf[isin] : null;
      const ins = sc ? { buys: sc.buys.length, ceo: sc.buys.some((t) => t.ceo || t.cfo), multi: sc.cluster && sc.cluster.count >= 2 ? sc.cluster.count : 0,
        netSeller: sc.sellEur > sc.buyEur && sc.sellEur > 0, ceoSale: ES.activeTx(tx[isin] || []).some((t) => t.type === 'vente' && (t.ceo || t.cfo) && ES.availDate(t) >= winFrom && ES.availDate(t) <= today) } : null;
      return { key: isin || sym, isin, sym, name: (i && i.name) || x.name || sym, country: x.country || (i && i.country) || null, sector: ES.sectorFr(x.sector) || null,
        turnoverEur: x.turnoverEur, pea: (i && i.peaStatus === 'non_eligible') || /^REIT\b/i.test(String(x.industry || '')) ? false : x.pea, f: ES.rankFeatures(x.d, x.w, x.wv), acc, ins, nextEarnings: i ? i.nextEarnings || null : null };
    });
    const rows = ES.rankUniverse(items, cfg);
    const nextE = {}; items.forEach((x) => { if (x.nextEarnings) nextE[x.key] = x.nextEarnings; });
    // Étude de contrôle sur 4 ans de cours hebdomadaires (même méthode que l'étude qui a fondé le barème)
    let study = null, breadth = null;
    try {
      const series = {}, insM = {}, accM = {};
      Object.keys(co).forEach((sym) => { if (Array.isArray(co[sym].w) && co[sym].w.length === wDates.length) series[sym] = co[sym].w; });
      Object.keys(sigBuys).forEach((isin) => { const sym = symOfIsin[isin]; if (!sym || !series[sym]) return; (insM[sym] = insM[sym] || []).push(...sigBuys[isin].map((t) => ES.availDate(t))); });
      Object.keys(insM).forEach((k) => insM[k].sort());
      Object.keys(series).forEach((sym) => {
        const isin = isinOfSym[sym], fin = isin ? finList[isin] : finList['@' + sym]; if (!fin || !Array.isArray(fin.years) || fin.years.length < 2) return;
        const x = co[sym], ds = [...new Set(fin.years.map((y) => y && y.date ? ES.addDays(y.date, 120) : null).filter(Boolean))].sort();
        accM[sym] = ds.map((d) => { let a = null; try { a = ES.accountsAnalysis(fin, { asOf: d, sector: x.sector, industry: x.industry }); } catch (e) { a = null; } const sm = accSummary(a); return sm ? Object.assign({ from: d }, sm) : null; }).filter(Boolean);
      });
      // Historique long (8 ans, sociétés de plus de 500 M€, module secteurs) quand il est disponible : étude plus exigeante,
      // qui couvre le krach de 2020 et la baisse de 2022 ; sinon les 5 ans du catalogue
      const long = readWeeklyCsv(path.join(DATA, 'sectors', 'weekly.csv.gz'), readJSON(path.join(DATA, 'sectors', 'universe.json'), {}).items || {});
      const useLong = long && long.dates.length >= 300 && Object.keys(long.series).length >= 300;
      const SD = useLong ? long.dates : wDates, SS = useLong ? long.series : series;
      study = ES.factorStudy(SD, SS, { cfg, insiders: insM, accounts: accM });
      study.source = useLong ? 'sociétés de plus de 500 M€, 8 ans' : 'toutes les sociétés cotées, 5 ans';
      try { const t1 = Date.now(); breadth = ES.marketBreadth(SD, SS); if (breadth) breadth.source = study.source; if (breadth) breadth.ms = Date.now() - t1; } catch (e) { console.warn('  Psychologie du marché indisponible : ' + e.message); }
      study.withAccounts = Object.keys(accM).length; study.withInsiders = Object.keys(insM).length;
    } catch (e) { console.warn('  Étude de contrôle du classement indisponible : ' + e.message); }
    // Sélection de la semaine : les premières sociétés non écartées au-dessus du seuil ; suivi depuis l'envoi
    state.rankSelections = isObj(state.rankSelections) ? state.rankSelections : {};
    const week = ES.isoWeek(today), mkLink = (r) => dashUrl ? dashUrl + '#' + (r.isin || 'co=' + r.sym) : null;
    const lastOf = {}; rows.forEach((r) => { lastOf[r.key] = r.last; });
    const mRows = mRef && Array.isArray(mRef.rows) ? ES.normalizeSeries(mRef.rows) : [], mLast = mRows.length ? mRows[mRows.length - 1][4] : null;
    const prevW = Object.keys(state.rankSelections).filter((w) => w < week).sort().pop(), was = new Set(prevW ? state.rankSelections[prevW].items.map((x) => x.key) : []);
    const sel = ES.rankSelection(rows, cfg).map((r) => Object.assign({}, r, { isNew: !!prevW && !was.has(r.key), link: mkLink(r), nextEarnings: nextE[r.key] || null }));
    const track = Object.keys(state.rankSelections).filter((w) => w < week).sort().slice(-26).map((w) => {
      const S0 = state.rankSelections[w];
      return { week: w, date: S0.date, bench: S0.b0 && mLast ? (mLast / S0.b0 - 1) * 100 : null,
        items: S0.items.map((x) => ({ key: x.key, name: x.name, note: x.note, perf: x.p0 > 0 && lastOf[x.key] > 0 ? (lastOf[x.key] / x.p0 - 1) * 100 : null })) };
    });
    const perfs = [], benches = []; track.forEach((w) => w.items.forEach((x) => { if (x.perf != null) { perfs.push(x.perf); if (w.bench != null) benches.push(w.bench); } }));
    const trackSum = perfs.length ? { n: perfs.length, avg: perfs.reduce((a, b) => a + b, 0) / perfs.length, bench: benches.length ? benches.reduce((a, b) => a + b, 0) / benches.length : null, beat: track.reduce((a, w) => a + w.items.filter((x) => x.perf != null && w.bench != null && x.perf > w.bench).length, 0) } : null;
    const slimRow = (r) => ({ key: r.key, isin: r.isin, sym: r.sym, name: r.name, country: r.country, sector: r.sector, note: r.note, parts: r.parts, v: r.verdict.key, out: r.out, why: r.why, warn: r.warn,
      mom: r.mom != null ? +(r.mom * 100).toFixed(1) : null, momPct: r.momPct != null ? Math.round(r.momPct * 100) : null, ratio: r.ratio != null ? +(r.ratio * 100).toFixed(1) : null, trend: r.trend,
      ret6m: r.ret6m != null ? +(r.ret6m * 100).toFixed(1) : null, liq: r.turnoverEur != null ? Math.round(r.turnoverEur) : null, pos: r.pos || null, acc: r.acc,
      slope6: r.slope != null ? Math.round((Math.sqrt(1 + r.slope) - 1) * 100) : null, sc: r.slopeCls || null, brk: r.brk != null ? r.brk : undefined, vx: r.volx != null ? r.volx : undefined,
      plan: r.plan || null, pw: r.pw || undefined, tmpl: r.tmpl, sec: r.sec || null, secEn: r.secEn || null, f9: r.f9 != null ? r.f9 : null, pb: r.pb != null ? r.pb : null, iv: r.iv || undefined });
    // Liste publiée : sociétés liquides (classées ou écartées pour une raison de fond) ; les autres sont trouvables par la recherche du catalogue
    const shown = rows.filter((r) => (r.turnoverEur || 0) >= cfg.rank.minTurnoverEur || r.isin);
    // Repères des filtres (mêmes que l'ancien classement) : plan d'entrée et figure, secteur, cycle, valeur, F-score
    const accF9 = {}; items.forEach((x) => { if (x.acc && x.acc.f9 != null) accF9[x.key] = x.acc.f9; });
    shown.forEach((r) => {
      const x = co[r.sym] || {}, i = r.isin ? inst[r.isin] : null;
      let pl = i && i.plan ? i.plan : null;
      if (!pl && Array.isArray(x.d) && dDates.length === x.d.length) {
        try { const a = ES.normalizeSeries(x.d.map((v, k) => [dDates[k], null, null, null, v, null]).filter((q) => q[0] && q[4] > 0)); if (a.length >= 120) pl = ES.entryPlan(a.slice(-260)); } catch (e) { pl = null; }
      }
      if (pl && pl.verdict) r.plan = { v: pl.verdict, f: ES.figureKey(pl.wedge) || null, t: ES.timingKeys(pl) };
      // repères du plan pour les alertes « Me prévenir pour ce plan » des sociétés sans dossier Euro Signal (lus par positions.py)
      if (pl && pl.verdict && !r.isin) {
        const rd = (v) => (v != null && isFinite(v) ? +(+v).toPrecision(6) : null), pr = pl.primary || {};
        r.pw = { v: pl.verdict, label: pl.label || null, p: { key: pr.key || null, trigger: rd(pr.trigger), entry: rd(pr.entry), level: rd(pr.level), stop: rd(pr.stop), zoneLo: rd(pr.zoneLo), zoneHi: rd(pr.zoneHi) },
          w: pl.wedge ? { type: pl.wedge.type || null, upperNow: rd(pl.wedge.upperNow) } : null };
      }
      r.sec = x.groupTrending ? 't' : x.groupEmerging ? 'e' : null; r.secEn = x.sector || (i && i.fund && i.fund.sector) || null;
      r.f9 = accF9[r.key] != null ? accF9[r.key] : null;
      const pb = i && i.value && i.value.pb != null ? i.value.pb : x.pb; r.pb = pb != null && isFinite(pb) ? +(+pb).toFixed(2) : null;
      r.iv = !!(i && ES.valueCheap(i.value));
      if (Array.isArray(x.d)) { const tt = ES.trendTemplate(x.d); if (tt) r.tmpl = tt.ok ? 1 : 0; }
    });
    rank = { version: R.version, since: R.since, today, coDate, coFresh: !!(coDate && ES.daysBetween(coDate, today) <= 3), generatedAt: new Date().toISOString(), counts: { catalogue: rows.length, liquid: rows.filter((r) => (r.turnoverEur || 0) >= R.minTurnoverEur).length, ranked: rows.filter((r) => !r.out.length).length, top: rows.filter((r) => r.verdict.key === 'top').length },
      bench: mRef ? mRef.ticker : null, selection: { week, items: sel.map(slimRow).map((r, k) => Object.assign(r, { isNew: sel[k].isNew })), track: trackSum, weeks: track }, rows: shown.map(slimRow), study, breadth };
    rank.ms = Date.now() - t0;
    console.log('  Classement tendance + comptes : ' + rank.counts.ranked + ' sociétés classées sur ' + rank.counts.liquid + ' liquides (' + rank.counts.catalogue + ' au catalogue), ' + rank.counts.top + ' en tête ; sélection : ' + sel.length + ' (' + (rank.ms / 1000).toFixed(0) + ' s)');
    rank._sel = sel; rank._b0 = mLast;
  } catch (e) { console.warn('  Classement tendance + comptes indisponible : ' + e.message); rank = null; }
  if (selCfg.enabled) {
    // Renvoi demandé à la main (bouton « Run workflow ») : un nouvel identifiant, donc un seul email de plus, jamais en boucle
    const resend = String(process.env.ES_RESEND_SELECTION || '').toLowerCase() === 'true';
    const id = 'selection-' + week + (resend ? '-renvoi-' + new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '') : ''), dow = (new Date(today + 'T12:00:00Z').getUTCDay() + 6) % 7 + 1; // 1 = lundi
    const prev = state.alerts[id];
    const done = prev && ['envoyee', 'incertain', 'en_cours'].concat(process.env.ES_MAIL_READY === 'oui' ? [] : ['simulee']).indexOf(prev.status) > -1;
    const insBad = Object.keys(state.src).filter((n) => state.src[n].kind === 'déclarations' || /^(AMF|BaFin|CNMV|CONSOB|FSMA|AFM|FI)$/.test(n)).filter((n) => state.src[n].status === 'echec');
    selection.sourcesDown = insBad;
    if (insBad.length && selection.verdict) selection.verdict = { key: 'na', icon: '⚠️', text: 'Données incomplètes : ' + insBad.join(', ') + ' en panne. Les sociétés concernées peuvent manquer à la sélection.' };
    // la sélection vient du classement tendance + comptes : on attend des cours du catalogue à jour, au plus tard le vendredi
    const coOk = !!(rank && rank.coFresh), wait = !coOk && dow < 5;
    if ((resend && coOk) || (!done && !wait && dow >= (selCfg.weekday || 1) && dow <= 5 && coOk)) {
      // Depuis le barème 3.0 : la sélection envoyée est celle du classement tendance + comptes (l'ancienne, fondée sur les dirigeants,
      // reste calculée et affichée pour comparaison jusqu'à la revue du 31/01/2027)
      const mail = rank ? ES.buildRankEmail(rank._sel, week, cfg, dashUrl, today, rank.selection.track) : null;
      if (!mail) { console.warn('  Sélection de la semaine non envoyée : classement indisponible'); }
      if (rank) state.rankSelections[week] = { date: today, b0: rank._b0, items: rank._sel.map((x) => ({ key: x.key, name: x.name, note: x.note, p0: x.last })) };
      Object.keys(state.rankSelections || {}).sort().slice(0, -60).forEach((w) => { delete state.rankSelections[w]; });
      state.selections[week] = { date: today, items: selection.items.map((x) => ({ isin: x.isin, name: x.name, score: x.score })) };
      Object.keys(state.selections).sort().slice(0, -60).forEach((w) => { delete state.selections[w]; });
      if (mail) outbox.push({ id, kind: 'selection', isin: null, name: 'Sélection ' + week, subject: mail.subject, text: mail.text, html: mail.html,
        eventIds: ['selection:' + week], score: null, version: cfg.rank.version });
    }
  }

  /* 6b. Argumentaire chiffré en tête de chaque email (profil de signal le plus proche, mesuré sur nos données) */
  outbox.forEach((m) => {
    if (m.kind) return; // emails de sortie et d'information : pas d'argumentaire
    const r = ES.emailRationale(backtest.results, m.profile, 60);
    const anchor = m.html.indexOf('Voir la fiche dans Euro Signal</a></p>') > -1 ? 'Voir la fiche dans Euro Signal</a></p>' : '</h2>';
    m.html = m.html.replace(anchor, anchor + r.html);
    m.text = r.text + '\n\n' + m.text;
  });

  /* 7. Tableau de bord : cours allégés (clôtures, 260 séances) pour tous les titres suivis : une fiche ouverte depuis la
     recherche ou « Tous les titres » (sans achat récent) a aussi son graphique et son plan d'entrée */
  const dashPrices = {};
  Object.keys(inst).forEach((isin) => {
    const p = pItems[isin];
    if (!p || !Array.isArray(p.rows) || !p.rows.length) return;
    dashPrices[isin] = { rows: ES.normalizeSeries(p.rows).slice(-260).map((r) => [r[0], +r[4].toFixed(4)]), closesOnly: true, splits: p.splits || [], source: 'Yahoo Finance', updatedAt: prices.generated_at }; // [date, clôture] : format compact, développé par le tableau de bord
  });
  // Historique 5 ans (une clôture par semaine) et achats des dirigeants sur la période avec leur résultat à 6 mois :
  // fichier séparé, lu seulement quand l'utilisateur choisit la vue « 5 ans » d'une fiche
  const longItems = {};
  Object.keys(dashPrices).forEach((isin) => {
    const p = pItems[isin];
    if (!p || !Array.isArray(p.weekly) || p.weekly.length < 20) return;
    try {
      const wRows = ES.normalizeSeries(p.weekly.map((r) => [r[0], null, null, null, r[1], null]));
      const d0 = p.rows && p.rows.length ? ES.normalizeSeries(p.rows)[0][0] : today;
      // dividendes : mêmes facteurs que les cours journaliers sur leur période, calculés sur les clôtures hebdomadaires avant
      const sp = (p.splits || []).concat(ES.dividendSplits(wRows, (p.dividends || []).filter((x) => x && x.date < d0)));
      const w = ES.adjustedSeries(wRows, sp).map((r) => [r[0], r[4]]);
      const near = (d) => { let k = w.length - 1; while (k > 0 && w[k][0] > d) k--; return w[k][1]; };
      const R0 = refs[isin] || {}, seen = {};
      const list = ((hist.tx && hist.tx[isin]) || []).concat(tx[isin] || []);
      const buys = ES.countedBuys(list, R0, cfg).filter((t) => t.txDate >= w[0][0]).map((t) => {
        const k = (t.personKey || t.person || '') + '|' + t.txDate; if (seen[k]) return null; seen[k] = 1;
        let paid = R0[t.id] && R0[t.id].available ? R0[t.id].paidAdj : null;
        if (paid == null && t.price > 0 && (!t.currency || !p.currency || String(t.currency).toUpperCase() === String(p.currency).toUpperCase())) paid = t.price / ES.splitFactor(sp, t.txDate);
        if (!(paid > 0)) return null;
        const ref = near(t.txDate); if (!(ref > 0) || paid / ref < 0.6 || paid / ref > 1.6) return null; // unité ou devise incohérente : écarté
        const o = histOutcome(hist.outcomes[isin + '|' + ES.availDate(t)], 120);
        return [t.txDate, +paid.toPrecision(5), String(t.person || '').slice(0, 40), o ? +((o.local != null ? o.local : o.excess) * 100).toFixed(1) : null, (t.ceo || t.cfo) ? 1 : 0];
      }).filter(Boolean).sort((a, b) => (a[0] < b[0] ? -1 : 1));
      longItems[isin] = { w, buys };
    } catch (e) { /* série longue illisible : vue 1 an seulement */ }
  });
  const dashTx = {};
  const dashFrom = ES.addMonths(today, -13);
  Object.keys(tx).forEach((isin) => { if (inst[isin]) dashTx[isin] = tx[isin].filter((t) => t.txDate >= dashFrom).map((t) => { const o = Object.assign({}, t); delete o.dedupKey; return o; }); });
  const recentAlerts = Object.values(state.alerts).sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)).slice(0, 300);
  const alertsMap = {}; recentAlerts.forEach((a) => { alertsMap[a.id] = a; });

  const slim = (r) => {
    if (!r) return r;
    const o = { available: r.available, notes: r.notes, paidAdj: r.paidAdj, lastDate: r.lastDate, currentVsPaidPct: r.currentVsPaidPct, outOfRange: r.outOfRange, belowMarket: r.belowMarket, currencyMismatch: r.currencyMismatch };
    const a = r.atPurchase, t = r.today;
    if (a) o.atPurchase = { drop10: a.drop10, rsi14: a.rsi14, paidVsHigh52Pct: a.paidVsHigh52Pct, paidVsLow52Pct: a.paidVsLow52Pct, paidPos52: a.paidPos52, paidVsHighAllPct: a.paidVsHighAllPct, paidVsLowAllPct: a.paidVsLowAllPct, paidPosAll: a.paidPosAll, full52: a.full52, ex52: a.ex52 ? { high: a.ex52.high, highDate: a.ex52.highDate, basis: a.ex52.basis, from: a.ex52.from } : null };
    if (t) o.today = { paidVsHigh52Pct: t.paidVsHigh52Pct, paidVsLow52Pct: t.paidVsLow52Pct, paidPos52: t.paidPos52, currentPos52: t.currentPos52, paidPosAll: t.paidPosAll, currentPosAll: t.currentPosAll, exAll: t.exAll ? { from: t.exAll.from, basis: t.exAll.basis } : null };
    return o;
  };
  const dashRefs = {};
  Object.keys(dashTx).forEach((isin) => { const r = refs[isin]; if (!r) return; dashRefs[isin] = {}; dashTx[isin].forEach((t) => { if (r[t.id]) dashRefs[isin][t.id] = slim(r[t.id]); }); });
  const winFrom = ES.addDays(ES.windowStart(today, cfg.insiders.windowMonths), -cfg.insiders.clusterWindowDays);
  const mainTx = {}, mainRefs = {};
  Object.keys(dashTx).forEach((isin) => {
    // Fichier principal allégé : opérations utiles au classement seulement (achats, ventes, cas ambigus), champs nécessaires au calcul ;
    // le détail complet (attributions, options, liens vers les sources…) est lu à l'ouverture d'une fiche
    const KEEP = ['id', 'isin', 'issuer', 'registry', 'person', 'personKey', 'role', 'ceo', 'cfo', 'board', 'associated', 'linkedTo', 'type', 'status', 'txDate', 'pubDate', 'qty', 'price', 'currency', 'amount', 'planned', 'version'];
    const l = dashTx[isin].filter((t) => ES.availDate(t) >= winFrom && (t.type === 'achat' || t.type === 'vente' || t.type === 'autre')).map((t) => { const o = {}; KEEP.forEach((k) => { if (t[k] != null && t[k] !== false) o[k] = t[k]; }); if (t.sourceUrl) o.hasSource = 1; return o; });
    if (!l.length) return;
    mainTx[isin] = l;
    if (dashRefs[isin]) { mainRefs[isin] = {}; l.forEach((t) => { if (dashRefs[isin][t.id]) mainRefs[isin][t.id] = dashRefs[isin][t.id]; }); }
  });
  // Comptes : détail (exercices, critères) dans le fichier des fiches ; le classement ne garde que le verdict et le F-score
  const accountsFull = {};
  Object.keys(inst).forEach((isin) => {
    const a = inst[isin].accounts; if (!a) return;
    accountsFull[isin] = a;
    // Fichier principal allégé : le texte complet de la lecture des comptes n'est lu qu'à l'ouverture d'une fiche (fichier détail)
    inst[isin].accounts = { fscore: a.fscore ? (a.fscore.na ? { na: true, reason: a.fscore.reason } : { f9: a.fscore.f9, score: a.fscore.score, avail: a.fscore.avail, year: a.fscore.year }) : null, verdict: a.verdict, n: a.n, plain: a.plain ? { tone: a.plain.tone, label: a.plain.label } : null, fscoreHistory: a.fscoreHistory || null, fscoreTrend: a.fscoreTrend || null,
      altman: a.altman && !a.altman.na ? { z: a.altman.z, zone: a.altman.zone } : null, beneish: a.beneish && !a.beneish.na ? { m: a.beneish.m, flag: a.beneish.flag } : null, summary: true };
  });
  // Liste des dirigeants (Yahoo) : sert seulement au calcul (DG et DAF), pas au tableau de bord
  Object.keys(inst).forEach((isin) => { const f = inst[isin].fund; if (f && f.officers) { const c = Object.assign({}, f); delete c.officers; inst[isin].fund = c; } });
  const detail = { format: 'euro-signal-detail', generatedAt: new Date().toISOString(), today, tx: dashTx, refs: dashRefs, prices: dashPrices, accounts: accountsFull };
  const payload = {
    format: 'euro-signal-snapshot', formatVersion: 1, engine: ES.ENGINE_VERSION, generatedAt: new Date().toISOString(), today,
    // fichier principal léger (classement) : déclarations de la fenêtre seulement ; cours et historique dans le fichier « détail »
    cfg, inst, aliases, tx: mainTx, ev: evOut, src: state.src, alerts: alertsMap, refs: mainRefs, prices: {}, detailFile: null, detailShards: { dir: 'data/fiches', n: ES.DETAIL_SHARDS }, longFile: 'data/euro-signal-long.json', backtest,
    run: { rejects: rejects.slice(0, 200), merge: mergeStats, outbox: outbox.length, instruments: Object.keys(inst).length, unresolved: prices.unresolved || [] },
    fx: ES.FX, mail: { ready: process.env.ES_MAIL_READY === 'oui' }, market: Object.assign({}, mkt, { mood: moodAt(today) }), followups, selection, selectionTrack, shortsSrc,
    learning: { mode: learning.mode, frozenUntil: learning.frozenUntil || null, month: learning.month, version: learning.version, samples: learning.samples, withOutcome: learning.withOutcome, stats: learning.stats, log: learning.log.slice(-24), baseVersion, observe: ES.observeStats(samples, cfg) }
  };
  // Fiche dirigeant (lue à la demande) : tout l'historique connu des personnes qui ont acheté depuis un an, avec le résultat de chaque achat
  const recentFrom = ES.addDays(today, -365), persons = {}, issuers = {};
  Object.keys(tx).forEach((isin) => (tx[isin] || []).forEach((t) => { if (t.type === 'achat' && ES.availDate(t) >= recentFrom) { const k = ES.buyerKey(t) || t.personKey; if (k) persons[k] = persons[k] || { rows: [], name: null, role: null, dg: false, reg: {} }; } }));
  Object.keys(allTx).forEach((isin) => ES.activeTx(allTx[isin]).forEach((t) => {
    if (t.type !== 'achat' && t.type !== 'vente') return;
    const k = ES.buyerKey(t) || t.personKey, p = k && persons[k]; if (!p) return;
    const d = ES.availDate(t), o = t.type === 'achat' ? hist.outcomes[isin + '|' + d] : null, a60 = histOutcome(o, 60), a120 = histOutcome(o, 120);
    const eur = ES.toEur(t.amount, t.currency);
    p.rows.push([d, t.txDate, isin, t.type === 'achat' ? 'A' : 'V', t.qty, t.price, t.currency, eur != null ? Math.round(eur) : null,
      a60 ? +(a60.excess * 100).toFixed(1) : null, a120 ? +(a120.excess * 100).toFixed(1) : null, t.registry, t.associated ? (t.person || 1) : 0, ES.excludedEntity(t, cfg) ? 1 : 0]);
    if (!t.associated && (!p.name || d >= p.lastDirect)) { p.name = t.person; p.role = t.role; p.lastDirect = d; }
    if (!p.name && t.linkedTo) p.name = t.linkedTo;
    p.dg = p.dg || !!(t.ceo || t.cfo); p.reg[t.registry] = 1;
    issuers[isin] = t.issuer || issuers[isin] || null;
  }));
  Object.keys(persons).forEach((k) => {
    const p = persons[k]; p.rows.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    if (p.rows.length > 400) { p.trimmed = p.rows.length; p.rows = p.rows.slice(-400); } // acheteurs en série : 400 dernières opérations
    const regs = Object.keys(p.reg), cov = regs.map((r) => hist.cov[r]).filter(Boolean).sort()[0] || archiveFrom;
    const pf = ES.buyerProfile(buyerHist[k], { date: today, eur: 0 }, cov, buyerTrades[k]);
    p.profile = { cohen: pf.cohen, routine: pf.routine, track: pf.track, pastBuys: pf.pastBuys };
    p.cov = cov; p.reg = regs; delete p.lastDirect;
  });
  const insidersOut = { format: 'euro-signal-insiders', generatedAt: new Date().toISOString(), today, cov: hist.cov,
    cols: ['date', 'txDate', 'isin', 'type', 'qty', 'price', 'currency', 'eur', 'x60', 'x120', 'registry', 'via', 'excluded'], issuers, persons };
  // Contrôle de cohérence de la chaîne de décision (ordre des filtres, priorité, tailles), publié dans le fichier du soir
  const audit = [];
  try {
    const S = cfg.selection, items = selection.items, byIsin = {}; cands.forEach((c) => { byIsin[c.isin] = c; });
    const passing = cands.filter((c) => !ES.selectionBlockers(c, cfg, today).length).sort((a, b) => b.score.total - a.score.total || ((b.score.discount || {}).pct || 0) - ((a.score.discount || {}).pct || 0));
    const want = passing.slice(0, S.size || 5).map((c) => c.isin).join(','), got = items.map((x) => x.isin).join(',');
    if (want !== got) audit.push('sélection différente du classement attendu : ' + got + ' au lieu de ' + want);
    items.forEach((x, k) => {
      const c = byIsin[x.isin];
      if (!c) { audit.push(x.name + ' : candidat introuvable'); return; }
      const bl = ES.selectionBlockers(c, cfg, today); if (bl.length) audit.push(x.name + ' : retenu malgré « ' + bl[0] + ' »');
      if (k && items[k - 1].score < x.score) audit.push(x.name + ' : ordre de la sélection non décroissant');
      if (x.advice && x.advice.key === 'avoid') audit.push(x.name + ' : retenu avec l\'avis « Éviter »');
      if (S.requireCeoCfo && !x.ceo) audit.push(x.name + ' : retenu sans achat du DG ou du DAF');
      if (c.inst.peaStatus === 'non_eligible' && S.peaOnly !== false) audit.push(x.name + ' : hors PEA');
      if (!x.size || !(x.size.pct > 0) || x.size.pct > cfg.sizing.maxPct) audit.push(x.name + ' : taille de position absente ou hors bornes (' + (x.size ? x.size.pct : 'n.d.') + ')');
      if (x.size && (x.size.stopPct < cfg.sizing.stopMinPct || x.size.stopPct > cfg.sizing.stopMaxPct)) audit.push(x.name + ' : seuil de protection hors bornes');
    });
    // Les avis « Éviter » doivent toujours correspondre à un motif bloquant de la sélection (jamais l'inverse : un blocage n'implique pas « Éviter »)
    cands.forEach((c) => { if (!c.score || !c.score.buys.length) return; const a = ES.advice(c.inst, c.score, cfg, { today, universe: c.universe }); if (a.key === 'avoid' && !ES.selectionBlockers(c, cfg, today).length) audit.push((c.inst.name || c.isin) + ' : avis « Éviter » sans motif bloquant'); });
    const rp = replay.length ? replay[replay.length - 1] : null;
    if (rp && rp.picks.some((x) => inst[x.isin] && inst[x.isin].peaStatus === 'non_eligible' && S.peaOnly !== false)) audit.push('rejeu : société hors PEA retenue le ' + rp.date);
  } catch (e) { audit.push('contrôle impossible : ' + e.message); }
  if (cfgMissing.length) audit.unshift('configuration incomplète (' + cfgMissing.join(', ') + ') : règles par défaut du moteur appliquées');
  payload.run.audit = { at: today, checked: cands.length, issues: audit.slice(0, 50) };
  console.log('  Contrôle de la chaîne de décision : ' + (audit.length ? audit.length + ' anomalie(s) — ' + audit.slice(0, 3).join(' ; ') : 'aucune anomalie'));
  /* Convergence, journal de bord et étude historique du plan d'entrée */
  try {
    const secRaw = readJSON(F.sectors, null), gByKey = {};
    ((secRaw && secRaw.groups) || []).forEach((g) => { gByKey[g.key] = g; });
    const nG = Object.keys(gByKey).length, from30 = ES.addDays(today, -(((cfg.selection || {}).recentDays) || 30));
    Object.keys(inst).forEach((isin) => {
      const x = inst[isin], f = x.fund || {};
      const g = nG ? gByKey[f.industry] || gByKey['Autres : ' + (f.sector || x.sector)] : null;
      if (g) x.sectorTrend = { key: g.key, rank: g.rank, of: nG, trending: !!g.trending, emerging: !!g.emerging };
      const buys = ES.countedBuys(tx[isin], refs[isin] || {}, cfg);
      const cv = ES.convergence({ dgRecent: buys.some((t) => (t.ceo || t.cfo) && ES.availDate(t) >= from30), sectorTrend: x.sectorTrend || null,
        revision30d: Number.isFinite(+x.revision30d) && x.revision30d !== null ? +x.revision30d : null, plan: x.plan || null });
      x.convergence = { n: cv.n, known: cv.known }; // détail recalculé par le tableau de bord (fichier léger)
    });
  } catch (e) { console.warn('  Convergence non calculée : ' + e.message); }
  // Étude historique : plan recalculé chaque semaine sur 2 ans de cours (sans regard vers le futur), comparé à l'indice européen
  let planStudy = null;
  try {
    if (mAdj0) { const t0 = Date.now(); planStudy = ES.planStudy(adjAll, mAdj0, { step: 5, horizons: [20, 60], costPct: cfg.backtest.costRoundTripPct }); planStudy.ms = Date.now() - t0; }
  } catch (e) { console.warn('  Étude du plan d\'entrée impossible : ' + e.message); }
  // Journal de bord : relevé du soir (verdict, figure, convergence) et résultats 20 et 60 séances plus tard
  let journal = null;
  try {
    const J = readGz(F.journal, { entries: [] });
    // un relevé par semaine (le premier soir de la semaine) : historique léger, résultats comparables
    const wk = (d) => { const t = new Date(d + 'T12:00:00Z'), day = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - day); return t.toISOString().slice(0, 10); };
    const entries = (J.entries || []).filter((e) => e && e.d && e.d >= ES.addMonths(today, -26));
    const weekDone = entries.some((e) => wk(e.d) === wk(today));
    if (!weekDone) Object.keys(inst).forEach((isin) => { const x = inst[isin]; if (x.plan && adjAll[isin] && adjAll[isin].length) entries.push({ d: today, i: isin, p: +adjAll[isin][adjAll[isin].length - 1][4].toPrecision(6), v: x.plan.verdict, f: ES.figureKey(x.plan.wedge) || 'none', c: x.convergence ? x.convergence.n : null, k: x.convergence ? x.convergence.known : null }); });
    J.entries = entries; J.since = J.since || today;
    const mIdx = {}; if (mAdj0) mAdj0.forEach((r, k) => { mIdx[r[0]] = k; });
    const res = { since: J.since, days: new Set(entries.map((e) => e.d)).size, entries: entries.length, byConv: {} };
    [20, 60].forEach((h) => {
      const acc = {};
      entries.forEach((e) => {
        const a = adjAll[e.i]; if (!a || !mAdj0) return;
        let k = -1; for (let q = a.length - 1; q >= 0; q--) if (a[q][0] <= e.d) { k = q; break; }
        const mk = mIdx[a[k] && a[k][0]]; if (k < 0 || mk == null || k + h >= a.length || mk + h >= mAdj0.length) return;
        const x = Math.max(-0.6, Math.min(1.5, a[k + h][4] / a[k][4] - 1)) - (mAdj0[mk + h][4] / mAdj0[mk][4] - 1);
        const g = e.c == null ? 'n.d.' : e.c >= 3 ? '3 et plus' : String(e.c);
        (acc[g] = acc[g] || []).push(x);
      });
      Object.keys(acc).forEach((g) => { const v = acc[g]; (res.byConv[g] = res.byConv[g] || {})['h' + h] = { n: v.length, mean: +(v.reduce((s2, y) => s2 + y, 0) / v.length * 100).toFixed(2), beatPct: Math.round(v.filter((y) => y > 0).length / v.length * 100) }; });
    });
    journal = res;
    if (!opts.dryRun) { fs.mkdirSync(path.dirname(F.journal), { recursive: true }); fs.writeFileSync(F.journal, zlib.gzipSync(JSON.stringify(J))); }
  } catch (e) { console.warn('  Journal de bord indisponible : ' + e.message); }
  payload.planStudy = planStudy; payload.journal = journal;
  if (planStudy) console.log('  Plan d\'entrée reconstitué : ' + planStudy.obs + ' relevés du ' + planStudy.from + ' au ' + planStudy.to + ' (' + (planStudy.ms / 1000).toFixed(0) + ' s)');
  if (rank) { const r = Object.assign({}, rank); delete r._sel; delete r._b0; payload.rank = r; }
  payload.history = { cov: hist.cov, n: hist.n, cut: hist.cut, outcomes: Object.keys(hist.outcomes).length, events: histEvents.length, persons: Object.keys(persons).length,
    study: histStudy, insidersFile: 'data/euro-signal-insiders.json' };
  Object.keys(state.obsAtBuy).forEach((k) => { if (ES.daysBetween(state.obsAtBuy[k].at, today) > 400) delete state.obsAtBuy[k]; });
  state.runs = [{ at: new Date().toISOString(), today, rows: rows.length, rejects: rejects.length, added: mergeStats.added, instruments: Object.keys(inst).length, outbox: outbox.length }].concat(state.runs || []).slice(0, 60);

  if (!opts.dryRun) {
    writeJSON(F.state, state);
    writeJSON(F.outbox, outbox, true);
    writeJSON(F.learning, { month: learning.month, version: learning.version, weights: learning.weights, log: learning.log, stats: learning.stats, updatedAt: new Date().toISOString() }, true);
    writeJSON(F.out, payload, false, true);
    writeJSON(F.insiders, insidersOut, false, true);
    // fiches détaillées : 32 petits fichiers (une fiche ouverte sur téléphone n'en télécharge qu'un, environ 600 Ko au lieu de 20 Mo)
    const shardDir = path.join(DATA, 'fiches'), shards = [];
    for (let k = 0; k < ES.DETAIL_SHARDS; k++) shards.push({ format: 'euro-signal-detail', generatedAt: detail.generatedAt, today, shard: k, tx: {}, refs: {}, prices: {}, accounts: {} });
    ['tx', 'refs', 'prices', 'accounts'].forEach((key) => Object.keys(detail[key] || {}).forEach((isin) => { shards[ES.shardOf(isin)][key][isin] = detail[key][isin]; }));
    fs.mkdirSync(shardDir, { recursive: true });
    shards.forEach((sh, k) => writeJSON(path.join(shardDir, k + '.json'), sh, false, true));
    fs.readdirSync(shardDir).forEach((f) => { const m = /^(\d+)\.json$/.exec(f); if (!m || +m[1] >= ES.DETAIL_SHARDS) fs.rmSync(path.join(shardDir, f), { force: true }); });
    if (fs.existsSync(F.detail)) fs.rmSync(F.detail); // ancien fichier unique, remplacé par les fiches réparties
    if (Object.keys(longItems).length) writeJSON(F.long, { format: 'euro-signal-long', generatedAt: new Date().toISOString(), today, items: longItems }, false, true);
    const shardMb = fs.readdirSync(shardDir).reduce((s, f) => s + fs.statSync(path.join(shardDir, f)).size, 0) / 1e6;
    console.log('  Tableau de bord : ' + (fs.statSync(F.out).size / 1e6).toFixed(1) + ' Mo (classement) + ' + shardMb.toFixed(1) + ' Mo (fiches, en ' + ES.DETAIL_SHARDS + ' fichiers) + ' + (fs.statSync(F.insiders).size / 1e6).toFixed(1) + ' Mo (dirigeants)');
    console.log('  Historique long : ' + Object.keys(hist.n).map((r) => r + ' ' + hist.n[r] + ' déclarations depuis le ' + (hist.from[r] || '?')).join(', ') + ' ; ' + histEvents.length + ' achats avec résultat');
  }
  return { payload, outbox, state, rejects, mergeStats, computed };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const r = build();
  const ready = Object.values(r.computed).filter((c) => c.send).length;
  console.log('Euro Signal ' + ES.ENGINE_VERSION + ' — ' + r.payload.today);
  console.log('  Déclarations lues : ' + (r.payload.src.AMF.totalRows || 0) + ' (' + r.rejects.length + ' refusées), nouvelles : ' + r.mergeStats.added + ', corrections : ' + r.mergeStats.corrected);
  console.log('  Source AMF : ' + r.payload.src.AMF.status + (r.payload.src.AMF.note ? ' (' + r.payload.src.AMF.note + ')' : ''));
  Object.keys(r.payload.src).filter((n) => n !== 'AMF' && n !== 'Yahoo Finance').forEach((n) => console.log('  Source ' + n + ' : ' + r.payload.src[n].status + (r.payload.src[n].note ? ' (' + r.payload.src[n].note + ')' : '')));
  console.log('  Source cours : ' + r.payload.src['Yahoo Finance'].status + (r.payload.src['Yahoo Finance'].note ? ' (' + r.payload.src['Yahoo Finance'].note + ')' : ''));
  console.log('  Émetteurs suivis : ' + Object.keys(r.payload.inst).length + ', alertes à envoyer : ' + ready);
}
