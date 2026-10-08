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
  latest: path.join(DATA, 'latest.json'), eu: path.join(DATA, 'insiders-eu.json'), events: path.join(DATA, 'events.json'), shorts: path.join(DATA, 'shorts.json'), prices: path.join(DATA, 'prices.json'), state: path.join(DATA, 'euro-signal-state.json'),
  out: path.join(DATA, 'euro-signal.json'), detail: path.join(DATA, 'euro-signal-detail.json'), learning: path.join(DATA, 'euro-signal-learning.json'), outbox: path.join(DATA, 'euro-signal-outbox.json'), config: path.join(HERE, 'config.json')
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

export function build(opts = {}) {
  const today = opts.today || parisToday();
  let cfg = ES.mergeConfig(ES.DEFAULT_CONFIG, readRequired(F.config, {}, 'euro_signal/config.json'));
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
    if (mkt && i.stats.ret6m1 != null && mkt.ret6m1 != null) i.stats.rel6m = i.stats.ret6m1 - mkt.ret6m1;
    if (mkt) { i.stats.marketAbove200 = mkt.above200; i.stats.marketIndex = mkt.ticker; }
    const er = (evRaw.items || {})[isin];
    state.fund = state.fund || {};
    if (er && er.fund) state.fund[isin] = er.fund; // conservées si la collecte du soir échoue
    i.fund = state.fund[isin] || null;
    if (i.fund && i.fund.sector) i.sector = i.fund.sector;
    i.nextEarnings = er && er.nextEarnings && er.nextEarnings > today ? er.nextEarnings : (state.nextEarnings || {})[isin] > today ? state.nextEarnings[isin] : null;
    if (i.nextEarnings) (state.nextEarnings = state.nextEarnings || {})[isin] = i.nextEarnings;
    if (!p) i.priceNote = (prices.unresolved || []).indexOf(isin) > -1 ? 'aucun ticker Yahoo trouvé pour cet ISIN' : 'cours non collectés';
    inst[isin] = i; tx[isin] = list;
  });
  // Valorisation par rapport aux pairs (même industrie, sinon même secteur) et positions vendeuses publiées
  const peers = ES.peerValuation(inst);
  const shortsRaw = readJSON(F.shorts, { items: {}, sources: {} });
  const shortsList = shortsRaw.items || {};
  Object.keys(inst).forEach((isin) => {
    if (peers[isin]) inst[isin].peer = peers[isin];
    const sh = ES.shortInfo(shortsList[isin], today);
    if (sh) inst[isin].shorts = sh;
  });
  // Mémoire des critères non historisés au moment où un achat devient public (valorisation, positions vendeuses)
  state.obsAtBuy = state.obsAtBuy || {};

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
    const R0 = refs[isin] || {};
    sigAll[isin] = ES.significantBuys(ES.activeTx(tx[isin]).filter((t) => ES.isVoluntaryBuy(t, cfg) && !(R0[t.id] && R0[t.id].belowMarket)), cfg).kept.map((t) => ES.availDate(t));
  });
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
  Object.keys(shortsRaw.sources || {}).forEach((cc) => { if (shortsRaw.sources[cc].status === 'ok' && !state.shortsSince[cc]) state.shortsSince[cc] = today; });
  const shortCovered = (isin, d) => { const cc = isin.slice(0, 2); return SHORT_HIST[cc] ? !!state.shortsSince[cc] : state.shortsSince[cc] ? d >= state.shortsSince[cc] : false; };
  const events = [], samples = [];
  const bAdj = prices.bench ? ES.adjustedSeries(ES.normalizeSeries(prices.bench.rows), []) : null;
  const bIdx = {}; if (bAdj) bAdj.forEach((r, k) => { bIdx[r[0]] = k; });
  const mAdj = mRef && mRef.rows ? ES.adjustedSeries(ES.normalizeSeries(mRef.rows), []) : null;
  const ret6m1At = (a, d) => { let k = -1; for (let q = a.length - 1; q >= 0; q--) if (a[q][0] <= d) { k = q; break; } return k >= 126 ? (a[k - 21][4] / a[k - 126][4] - 1) * 100 : null; };
  Object.keys(inst).forEach((isin) => {
    if (!pItems[isin]) return;
    const R = refs[isin] || {};
    const buys = ES.significantBuys(ES.activeTx(tx[isin]).filter((t) => ES.isVoluntaryBuy(t, cfg) && !(R[t.id] && R[t.id].belowMarket) && ES.daysBetween(t.txDate, ES.availDate(t)) <= cfg.insiders.maxFilingLagDays), cfg).kept.sort((a, b) => (ES.availDate(a) < ES.availDate(b) ? -1 : 1));
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
      let kk = -1; { let lo = 0, hi = adj.length - 1; while (lo <= hi) { const m = (lo + hi) >> 1; if (adj[m][0] <= d) { kk = m; lo = m + 1; } else hi = m - 1; } }
      const above = kk >= 199 ? (cum[kk + 1] - cum[kk - 49]) / 50 > (cum[kk + 1] - cum[kk - 199]) / 200 : null; // MM50 > MM200 à la date de publication
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
          peerCheap: state.obsAtBuy[t.id] && state.obsAtBuy[t.id].peerDisc != null ? state.obsAtBuy[t.id].peerDisc >= 20 : undefined,
          shorted: shortCovered(isin, d) ? !!ES.shortInfo(shortsList[isin], d) : undefined } });
      if (ES.daysBetween(d, today) <= 7 && !state.obsAtBuy[t.id]) state.obsAtBuy[t.id] = { at: today, peerDisc: inst[isin].peer ? inst[isin].peer.discountPct : null, shortPct: inst[isin].shorts ? inst[isin].shorts.totalPct : 0 };
      if (t.ceo || t.cfo) push('Achat DG ou DAF', d);
      const known = buys.filter((b) => ES.availDate(b) <= d && b.txDate >= ES.addDays(t.txDate, -(cfg.insiders.clusterWindowDays - 1)) && b.txDate <= t.txDate);
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
  const backtest = { results: ES.eventStudy(events, series, prices.bench ? { rows: prices.bench.rows, splits: [] } : null, { costRoundTripPct: cfg.backtest.costRoundTripPct, horizons: cfg.backtest.horizons, oosStart: oos }), bench: prices.bench ? prices.bench.ticker : null, oosStart: oos, cost: cfg.backtest.costRoundTripPct, horizons: cfg.backtest.horizons, events: events.length };

  /* 6a. Auto-apprentissage mensuel (appliqué à partir du passage suivant) */
  // Sans cours frais (panne Yahoo), on ne consomme pas le recalibrage du mois : il sera retenté le soir suivant.
  const canLearn = pFresh && samples.some((x) => x.excess != null);
  const learning = canLearn ? ES.calibrate(samples, ES.mergeConfig(cfg, {}), learnPrev, today)
    : Object.assign({ month: null, version: 0, weights: {}, log: [], stats: [] }, learnPrev || {}, { changed: [] });
  learning.mode = cfg.learning.mode; learning.samples = samples.length; learning.withOutcome = samples.filter((x) => x.excess != null).length; learning.baseVersion = baseVersion;
  if (learning.changed.length && cfg.learning.mode === 'auto') {
    const lines = learning.changed.map((e) => e.label + ' : ' + e.from + ' → ' + e.to + ' point(s) (écart mesuré ' + (e.effect >= 0 ? '+' : '') + e.effect + ' pt sur ' + e.nWith + ' cas, t = ' + e.t + ')');
    outbox.push({ id: 'apprentissage-' + learning.month, kind: 'info', isin: null, name: 'Barème', subject: '[Euro Signal] Barème ajusté automatiquement (' + learning.month + ')',
      text: 'Euro Signal a comparé ses signaux aux résultats réels et ajusté son barème :\n' + lines.join('\n') + '\n\nRègles : un pas au plus par mois, seulement si l\'écart est net sur au moins ' + cfg.learning.minCases + ' cas, entre 0 et 2 fois le poids d\'origine. Pour désactiver : "learning": {"mode": "off"} dans euro_signal/config.json.',
      html: '<div style="font-family:Arial,sans-serif;font-size:14px"><h2>Barème ajusté automatiquement</h2><p>Euro Signal a comparé ses signaux aux résultats réels (' + learning.withOutcome + ' achats suivis sur ' + cfg.learning.horizon + ' séances) :</p><ul>' + lines.map((l) => '<li>' + ES.esc(l) + '</li>').join('') + '</ul><p style="color:#55615c;font-size:12px">Un pas au plus par mois, seulement si l\'écart est net sur au moins ' + cfg.learning.minCases + ' cas, entre 0 et 2 fois le poids d\'origine. Désactivable dans euro_signal/config.json.</p>' + (dashUrl ? '<p><a href="' + ES.esc(dashUrl) + '">Voir l\'onglet Résultats passés</a></p>' : '') + '</div>',
      eventIds: ['learn:' + learning.month], score: null, version: cfg.scoringVersion });
  }

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
  state.selections = state.selections || {};
  const prevWeek = Object.keys(state.selections).filter((w) => w < week).sort().pop();
  if (prevWeek) { const was = new Set(state.selections[prevWeek].items.map((x) => x.isin)); selection.items.forEach((x) => { x.isNew = !was.has(x.isin); }); }
  // Suivi des sélections passées (tableau de bord et email) : performance depuis l'envoi, comparée au CAC 40
  const closeAt = (rows, splits, d) => { const a = ES.adjustedSeries(ES.normalizeSeries(rows), splits || []); let v = null; for (const r of a) { if (r[0] <= d) v = r[4]; else break; } return { at: v, last: a.length ? a[a.length - 1][4] : null }; };
  const selectionTrack = Object.keys(state.selections).filter((w) => w < week).sort().slice(-26).map((w) => {
    const S0 = state.selections[w], b = prices.bench ? closeAt(prices.bench.rows, [], S0.date) : null;
    const bench = b && b.at && b.last ? (b.last / b.at - 1) * 100 : null;
    return { week: w, date: S0.date, bench, items: S0.items.map((x) => { const p = pItems[x.isin]; const c = p ? closeAt(p.rows, p.splits, S0.date) : null; return { isin: x.isin, name: x.name, score: x.score, perf: c && c.at && c.last ? (c.last / c.at - 1) * 100 : null }; }) };
  });
  selection.track = ES.selectionTrackSummary(selectionTrack);
  // Repère historique : sélections rejouées chaque lundi passé, avec uniquement l'information connue ce jour-là
  const replay = [];
  {
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
        const txD = tx[isin].filter((t) => ES.availDate(t) <= D0), rf = {};
        txD.forEach((t) => { if (t.type === 'achat' || t.type === 'vente') rf[t.id] = ES.priceRefs(t, rows, splits, D0, p.currency || null); });
        const sc = ES.score({ inst: iD, tx: txD, events: evOut[isin] || { buybacks: [], results: [] }, refs: rf, cfg, today: D0 });
        if (!sc.buys.length || sc.ambiguousCount || sc.total < (selCfg.minScore || 0)) return;
        if (!sc.buys.some((t) => ES.availDate(t) >= from)) return;
        notes.push(ES.note(sc.total, cfg));
      });
      notes.sort((a, b) => b - a);
      replay.push({ week: ES.isoWeek(D0), date: D0, notes: notes.slice(0, selCfg.size || 5) });
    });
  }
  const histNotes = replay.flatMap((w) => w.notes), weekBest = replay.filter((w) => w.notes.length).map((w) => w.notes[0]);
  selection.items.forEach((x) => { x.note = ES.note(x.score, cfg); x.hist = ES.historicRank(x.note, histNotes); });
  selection.verdict = ES.weekVerdict(selection.items, histNotes, weekBest);
  selection.reference = { weeks: replay.length, withPicks: weekBest.length, from: replay.length ? replay[0].date : null, histNotes, weekBest };
  if (selCfg.enabled) {
    const id = 'selection-' + week, dow = (new Date(today + 'T12:00:00Z').getUTCDay() + 6) % 7 + 1; // 1 = lundi
    const prev = state.alerts[id];
    const done = prev && ['envoyee', 'incertain', 'en_cours'].concat(process.env.ES_MAIL_READY === 'oui' ? [] : ['simulee']).indexOf(prev.status) > -1;
    if (!done && dow >= (selCfg.weekday || 1) && dow <= 5 && pFresh) {
      const since = events.length ? events.map((e) => e.date).sort()[0] : null;
      const mail = ES.buildSelectionEmail(selection.items, week, cfg, dashUrl, today, ES.methodRationale(backtest.results, cfg, since ? since.split('-').reverse().join('/') : null), selection.track, selection.verdict);
      state.selections[week] = { date: today, items: selection.items.map((x) => ({ isin: x.isin, name: x.name, score: x.score })) };
      Object.keys(state.selections).sort().slice(0, -60).forEach((w) => { delete state.selections[w]; });
      outbox.push({ id, kind: 'selection', isin: null, name: 'Sélection ' + week, subject: mail.subject, text: mail.text, html: mail.html,
        eventIds: ['selection:' + week], score: null, version: cfg.scoringVersion });
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
    if (a) o.atPurchase = { drop10: a.drop10, rsi14: a.rsi14, paidVsHigh52Pct: a.paidVsHigh52Pct, paidVsLow52Pct: a.paidVsLow52Pct, paidPos52: a.paidPos52, paidVsHighAllPct: a.paidVsHighAllPct, paidVsLowAllPct: a.paidVsLowAllPct, paidPosAll: a.paidPosAll, full52: a.full52, ex52: a.ex52 ? { high: a.ex52.high, highDate: a.ex52.highDate, basis: a.ex52.basis, from: a.ex52.from } : null };
    if (t) o.today = { paidVsHigh52Pct: t.paidVsHigh52Pct, paidVsLow52Pct: t.paidVsLow52Pct, paidPos52: t.paidPos52, currentPos52: t.currentPos52, paidPosAll: t.paidPosAll, currentPosAll: t.currentPosAll, exAll: t.exAll ? { from: t.exAll.from, basis: t.exAll.basis } : null };
    return o;
  };
  const dashRefs = {};
  Object.keys(dashTx).forEach((isin) => { const r = refs[isin]; if (!r) return; dashRefs[isin] = {}; dashTx[isin].forEach((t) => { if (r[t.id]) dashRefs[isin][t.id] = slim(r[t.id]); }); });
  const winFrom = ES.addDays(ES.windowStart(today, cfg.insiders.windowMonths), -cfg.insiders.clusterWindowDays);
  const mainTx = {}, mainRefs = {};
  Object.keys(dashTx).forEach((isin) => {
    const l = dashTx[isin].filter((t) => ES.availDate(t) >= winFrom);
    if (!l.length) return;
    mainTx[isin] = l;
    if (dashRefs[isin]) { mainRefs[isin] = {}; l.forEach((t) => { if (dashRefs[isin][t.id]) mainRefs[isin][t.id] = dashRefs[isin][t.id]; }); }
  });
  const detail = { format: 'euro-signal-detail', generatedAt: new Date().toISOString(), today, tx: dashTx, refs: dashRefs, prices: dashPrices };
  const payload = {
    format: 'euro-signal-snapshot', formatVersion: 1, engine: ES.ENGINE_VERSION, generatedAt: new Date().toISOString(), today,
    // fichier principal léger (classement) : déclarations de la fenêtre seulement ; cours et historique dans le fichier « détail »
    cfg, inst, tx: mainTx, ev: evOut, src: state.src, alerts: alertsMap, refs: mainRefs, prices: {}, detailFile: 'data/euro-signal-detail.json', backtest,
    run: { rejects: rejects.slice(0, 200), merge: mergeStats, outbox: outbox.length, instruments: Object.keys(inst).length, unresolved: prices.unresolved || [] },
    mail: { ready: process.env.ES_MAIL_READY === 'oui' }, market: mkt, followups, selection, selectionTrack, shortsSrc: shortsRaw.sources || {},
    learning: { mode: learning.mode, month: learning.month, version: learning.version, samples: learning.samples, withOutcome: learning.withOutcome, stats: learning.stats, log: learning.log.slice(-24), baseVersion, observe: ES.observeStats(samples, cfg) }
  };
  Object.keys(state.obsAtBuy).forEach((k) => { if (ES.daysBetween(state.obsAtBuy[k].at, today) > 400) delete state.obsAtBuy[k]; });
  state.runs = [{ at: new Date().toISOString(), today, rows: rows.length, rejects: rejects.length, added: mergeStats.added, instruments: Object.keys(inst).length, outbox: outbox.length }].concat(state.runs || []).slice(0, 60);

  if (!opts.dryRun) {
    writeJSON(F.state, state);
    writeJSON(F.outbox, outbox, true);
    writeJSON(F.learning, { month: learning.month, version: learning.version, weights: learning.weights, log: learning.log, stats: learning.stats, updatedAt: new Date().toISOString() }, true);
    writeJSON(F.out, payload, false, true);
    writeJSON(F.detail, detail, false, true);
    const mb = fs.statSync(F.detail).size / 1e6;
    if (mb > 60) { // garde-fou : GitHub refuse les fichiers de plus de 100 Mo, ce qui empêcherait aussi d'enregistrer le journal
      detail.prices = {}; detail.trimmed = 'cours retirés (fichier de ' + mb.toFixed(0) + ' Mo)';
      writeJSON(F.detail, detail, false, true);
      console.warn('  ATTENTION : fichier détail allégé (' + mb.toFixed(0) + ' Mo sans allègement)');
    }
    console.log('  Tableau de bord : ' + (fs.statSync(F.out).size / 1e6).toFixed(1) + ' Mo (classement) + ' + (fs.statSync(F.detail).size / 1e6).toFixed(1) + ' Mo (fiches)');
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
