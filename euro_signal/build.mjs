// Euro Signal — calcul quotidien (exécuté par GitHub Actions après la collecte).
// Entrées : data/latest.json (collecteur AMF insider-pea), data/prices.json (cours Yahoo),
//           data/euro-signal-state.json (archive et journal des alertes), euro_signal/config.json.
// Sorties : data/euro-signal.json (tableau de bord), data/euro-signal-outbox.json (emails à envoyer),
//           data/euro-signal-state.json (mis à jour).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ES = require('./core.js');
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const DATA = path.join(ROOT, 'data');
const F = {
  latest: path.join(DATA, 'latest.json'), eu: path.join(DATA, 'insiders-eu.json'), events: path.join(DATA, 'events.json'), prices: path.join(DATA, 'prices.json'), state: path.join(DATA, 'euro-signal-state.json'),
  out: path.join(DATA, 'euro-signal.json'), outbox: path.join(DATA, 'euro-signal-outbox.json'), config: path.join(HERE, 'config.json')
};

// NaN / Infinity écrits par Python : remplacés seulement en position de valeur (jamais dans un texte)
const sanitize = (txt) => txt.replace(/([:\[,]\s*)-?(?:NaN|Infinity)(?=\s*[,\]}])/g, '$1null');
function readJSON(file, fallback) {
  try { return JSON.parse(sanitize(fs.readFileSync(file, 'utf8'))); }
  catch (e) { if (fallback === undefined) throw e; return fallback; }
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
  // compact : nombres à 7 chiffres significatifs (le tableau de bord n'a pas besoin de plus)
  const rep = compact ? (k, v) => (typeof v === 'number' && !Number.isInteger(v) ? Number(v.toPrecision(7)) : v) : undefined;
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

export function build(opts = {}) {
  const today = opts.today || parisToday();
  const cfg = ES.mergeConfig(ES.DEFAULT_CONFIG, readRequired(F.config, {}, 'euro_signal/config.json'));
  const errs = ES.validateConfig(cfg);
  if (errs.length) throw new Error('config.json invalide : ' + errs.join(' ; '));
  const latest = readJSON(F.latest, null);
  const prices = readJSON(F.prices, { items: {}, unresolved: [] });
  const state = readRequired(F.state, { txArchive: {}, alerts: {}, src: {}, runs: [] }, 'data/euro-signal-state.json');
  state.txArchive = state.txArchive || {}; state.alerts = state.alerts || {}; state.src = state.src || {};
  if (!fs.existsSync(F.state)) { // journal disparu : on repart des alertes recopiées dans le tableau de bord, pour ne jamais renvoyer
    const prevDash = readJSON(F.out, null);
    if (prevDash && prevDash.alerts) { state.alerts = prevDash.alerts; console.warn('  Journal absent : ' + Object.keys(state.alerts).length + ' alerte(s) reprises du tableau de bord'); }
  }

  /* 1. Source AMF : absence de collecte ≠ absence de transaction */
  const amf = { name: 'AMF', via: 'transactions-amf.swaoo.com (republication de la base BDIF)', countries: ['FR'], kind: 'déclarations' };
  const prevAmf = state.src.AMF || {};
  const genDate = latest && latest.generated_at ? String(latest.generated_at).slice(0, 10) : null;
  const rows = latest && Array.isArray(latest.transactions) ? latest.transactions.filter((t) => t && typeof t === 'object') : [];
  const amfFresh = genDate && ES.daysBetween(genDate, today) <= 3 && rows.length > 0;
  amf.status = amfFresh ? 'ok' : 'echec';
  amf.lastSuccess = amfFresh ? genDate : prevAmf.lastSuccess || null;
  amf.lastAttempt = today;
  amf.note = amfFresh ? null : !latest ? 'fichier data/latest.json absent' : rows.length === 0 ? 'collecte vide' : 'collecte non mise à jour depuis le ' + genDate;

  /* 2. Conversion et fusion dans l'archive (corrections, doublons, première observation) */
  const rejects = [], incoming = {};
  let warnCount = 0;
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
  Object.values(eu.records || {}).filter((rec) => rec && typeof rec === 'object').forEach((rec) => {
    const r = ES.fromCollectorRecord(rec, { today });
    if (!r.ok) { (euRejects[rec.registry] = euRejects[rec.registry] || []).push({ isin: rec.isin, company: rec.issuer, declaration: rec.id, errors: r.errors }); return; }
    if (r.rec.type === 'instrument') return;
    (incoming[r.rec.isin] = incoming[r.rec.isin] || []).push(r.rec);
  });
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
  const keepFrom = ES.addMonths(today, -36);
  Object.keys(state.txArchive).forEach((isin) => {
    state.txArchive[isin] = state.txArchive[isin].filter((t) => t.txDate >= keepFrom);
    if (!state.txArchive[isin].length) delete state.txArchive[isin];
  });
  const pubs = rows.map((t) => ES.parseDate(t.date_published)).filter(Boolean).sort();
  Object.assign(amf, { coveredFrom: pubs[0] || null, coveredTo: pubs[pubs.length - 1] || null, totalRows: rows.length, rejected: rejects.length, warnings: warnCount });
  amf.log = [{ at: today, rows: rows.length, accepted: rows.length - rejects.length, rejected: rejects.length, added: mergeStats.added, duplicates: mergeStats.duplicates, corrected: mergeStats.corrected, cancelled: mergeStats.cancelled }].concat(prevAmf.log || []).slice(0, 15);

  /* 3. Source cours */
  const pItems = prices.items || {};
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
  const yev = { name: 'Yahoo Finance (événements)', kind: 'résultats, communiqués, révisions', via: 'yfinance (GitHub Actions)', status: eFresh ? 'ok' : 'echec', lastSuccess: eFresh ? eDate : prevE.lastSuccess || null, lastAttempt: today, countries: [], note: eFresh ? null : 'événements non mis à jour (familles R et E figées à la dernière collecte)' };
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
    const list = state.txArchive[isin];
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
    if (!p) i.priceNote = (prices.unresolved || []).indexOf(isin) > -1 ? 'aucun ticker Yahoo trouvé pour cet ISIN' : 'cours non collectés';
    inst[isin] = i; tx[isin] = list;
  });

  /* 5. Comparaisons, score, qualité, surchauffe, décision d'alerte */
  const sentIds = {};
  Object.values(state.alerts).forEach((a) => {
    // une alerte simulée (Gmail pas encore configuré) n'empêche pas l'envoi réel ensuite
    const counted = ['envoyee', 'brouillon', 'incertain', 'en_cours'].concat(process.env.ES_MAIL_READY === 'oui' ? [] : ['simulee']);
    if (counted.indexOf(a.status) > -1) (a.eventIds || []).forEach((id) => { (sentIds[a.isin] = sentIds[a.isin] || {})[id] = 1; });
  });
  const outbox = [];
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
    computed[isin] = { score: score.total, quality: quality.total, overheat: overheat.total, send: decision.send, blocking: decision.blocking.length };
    if (decision.send) {
      const mail = ES.buildEmail({ inst: i, score, quality, overheat, decision, refs: refs[isin], events: ev, today, universeWarnings: uni.reasons.concat(['Éligibilité PEA non confirmée automatiquement : à vérifier avant tout achat.']) });
      if (dashUrl) {
        const link = dashUrl + '#' + isin; // ouvre directement la fiche de la société
        const btn = '<p style="margin:10px 0 14px"><a href="' + ES.esc(link) + '" style="display:inline-block;background:#0D6A56;color:#ffffff;text-decoration:none;font-weight:bold;padding:10px 16px;border-radius:6px">Voir la fiche dans Euro Signal</a></p>';
        mail.html = mail.html.replace('</h2>', '</h2>' + btn).replace(/<\/div>\s*$/, '<p><a href="' + ES.esc(dashUrl) + '">Ouvrir le tableau de bord complet</a></p></div>');
        mail.text = 'Fiche : ' + link + '\n\n' + mail.text + '\nTableau de bord : ' + dashUrl;
      }
      outbox.push({ id: isin + '-' + decision.fingerprint, isin, name: i.name, subject: mail.subject, html: mail.html, text: mail.text, eventIds: decision.eventIds, score: score.total, version: cfg.scoringVersion });
    }
  });

  /* 6. Étude d'événements (validation) sur l'archive accumulée */
  const events = [];
  Object.keys(inst).forEach((isin) => {
    if (!pItems[isin]) return;
    const buys = ES.activeTx(tx[isin]).filter((t) => ES.isVoluntaryBuy(t, cfg)).sort((a, b) => (ES.availDate(a) < ES.availDate(b) ? -1 : 1));
    let lastCluster = null;
    buys.forEach((t) => {
      const d = ES.availDate(t);
      events.push({ isin, date: d, group: 'Achat volontaire' });
      if (t.ceo || t.cfo) events.push({ isin, date: d, group: 'Achat DG ou DAF' });
      const known = buys.filter((b) => ES.availDate(b) <= d && b.txDate >= ES.addDays(t.txDate, -(cfg.insiders.clusterWindowDays - 1)) && b.txDate <= t.txDate);
      if (ES.clusterInfo(known, cfg.insiders.clusterWindowDays).count >= cfg.insiders.clusterMinBuyers && (!lastCluster || ES.daysBetween(lastCluster, d) > 30)) { events.push({ isin, date: d, group: 'Cluster ≥ ' + cfg.insiders.clusterMinBuyers + ' dirigeants' }); lastCluster = d; }
    });
  });
  const series = {};
  Object.keys(pItems).forEach((isin) => { series[isin] = { rows: pItems[isin].rows, splits: pItems[isin].splits || [] }; });
  const oos = cfg.backtest.oosStart || ES.addMonths(today, -6);
  const backtest = { results: ES.eventStudy(events, series, prices.bench ? { rows: prices.bench.rows, splits: [] } : null, { costRoundTripPct: cfg.backtest.costRoundTripPct, horizons: cfg.backtest.horizons, oosStart: oos }), bench: prices.bench ? prices.bench.ticker : null, oosStart: oos, cost: cfg.backtest.costRoundTripPct, horizons: cfg.backtest.horizons, events: events.length };

  /* 7. Tableau de bord : cours allégés (clôtures, 260 séances) pour les titres actifs dans la fenêtre */
  const from = ES.windowStart(today, cfg.insiders.windowMonths);
  const dashPrices = {};
  Object.keys(inst).forEach((isin) => {
    const p = pItems[isin];
    if (!p || !tx[isin].some((t) => ES.availDate(t) >= from)) return;
    dashPrices[isin] = { rows: ES.normalizeSeries(p.rows).slice(-260).map((r) => [r[0], +r[4].toFixed(4)]), closesOnly: true, splits: p.splits || [], source: 'Yahoo Finance', updatedAt: prices.generated_at }; // [date, clôture] : format compact, développé par le tableau de bord
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
    if (a) o.atPurchase = { paidVsHigh52Pct: a.paidVsHigh52Pct, paidVsLow52Pct: a.paidVsLow52Pct, paidPos52: a.paidPos52, paidVsHighAllPct: a.paidVsHighAllPct, paidVsLowAllPct: a.paidVsLowAllPct, paidPosAll: a.paidPosAll, full52: a.full52, ex52: a.ex52 ? { high: a.ex52.high, highDate: a.ex52.highDate, basis: a.ex52.basis, from: a.ex52.from } : null };
    if (t) o.today = { paidVsHigh52Pct: t.paidVsHigh52Pct, paidVsLow52Pct: t.paidVsLow52Pct, paidPos52: t.paidPos52, currentPos52: t.currentPos52, paidPosAll: t.paidPosAll, currentPosAll: t.currentPosAll, exAll: t.exAll ? { from: t.exAll.from, basis: t.exAll.basis } : null };
    return o;
  };
  const dashRefs = {};
  Object.keys(dashTx).forEach((isin) => { const r = refs[isin]; if (!r) return; dashRefs[isin] = {}; dashTx[isin].forEach((t) => { if (r[t.id]) dashRefs[isin][t.id] = slim(r[t.id]); }); });
  const payload = {
    format: 'euro-signal-snapshot', formatVersion: 1, engine: ES.ENGINE_VERSION, generatedAt: new Date().toISOString(), today,
    cfg, inst, tx: dashTx, ev: evOut, src: state.src, alerts: alertsMap, refs: dashRefs, prices: dashPrices, backtest,
    run: { rejects: rejects.slice(0, 200), merge: mergeStats, outbox: outbox.length, instruments: Object.keys(inst).length, unresolved: prices.unresolved || [] },
    mail: { ready: process.env.ES_MAIL_READY === 'oui' }
  };
  state.runs = [{ at: new Date().toISOString(), today, rows: rows.length, rejects: rejects.length, added: mergeStats.added, instruments: Object.keys(inst).length, outbox: outbox.length }].concat(state.runs || []).slice(0, 60);

  if (!opts.dryRun) {
    writeJSON(F.state, state);
    writeJSON(F.outbox, outbox, true);
    writeJSON(F.out, payload, false, true);
    const mb = fs.statSync(F.out).size / 1e6;
    if (mb > 60) { // garde-fou : GitHub refuse les fichiers de plus de 100 Mo, ce qui empêcherait aussi d'enregistrer le journal
      payload.prices = {}; payload.run.trimmed = 'cours retirés du tableau de bord (fichier de ' + mb.toFixed(0) + ' Mo)';
      writeJSON(F.out, payload, false, true);
      console.warn('  ATTENTION : tableau de bord allégé (' + mb.toFixed(0) + ' Mo sans allègement)');
    }
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
