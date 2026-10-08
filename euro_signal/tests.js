/* Tests du moteur Euro Signal — exécuter avec : node tests.js */
'use strict';
const ES = require('./core.js');
let pass = 0, fail = 0;
const results = [];
function t(name, fn) {
  try { fn(); pass++; results.push('OK   ' + name); }
  catch (e) { fail++; results.push('ÉCHEC ' + name + ' → ' + e.message); }
}
function eq(a, b, m) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error((m || '') + ' attendu ' + JSON.stringify(b) + ', obtenu ' + JSON.stringify(a)); }
function ok(v, m) { if (!v) throw new Error(m || 'condition fausse'); }
function near(a, b, eps, m) { if (Math.abs(a - b) > (eps || 1e-6)) throw new Error((m || '') + ' attendu ≈' + b + ', obtenu ' + a); }

const TODAY = '2026-10-07';
const cfg = ES.mergeConfig(ES.DEFAULT_CONFIG, {});

/* ---------- Dates ---------- */
t('fenêtre de 3 mois calendaires (pas 90 jours)', () => {
  eq(ES.addMonths('2026-10-07', -3), '2026-07-07');
  eq(ES.addMonths('2026-05-31', -3), '2026-02-28');
  eq(ES.addMonths('2028-05-31', -3), '2028-02-29', 'année bissextile');
  eq(ES.addMonths('2026-01-15', -3), '2025-10-15', 'changement d\'année');
  ok(ES.daysBetween(ES.addMonths('2026-05-31', -3), '2026-05-31') !== 90, '≠ 90 jours');
});
t('formats de dates européens et rejets', () => {
  eq(ES.parseDate('07/10/2026'), '2026-10-07');
  eq(ES.parseDate('07.10.2026'), '2026-10-07');
  eq(ES.parseDate('2026-10-07T18:01:00Z'), '2026-10-07');
  eq(ES.parseDate('20261007'), '2026-10-07');
  eq(ES.parseDate('31/02/2026'), null, '31 février');
  eq(ES.parseDate('demain'), null);
  eq(ES.parseDateTime('07/10/2026 18:05'), { date: '2026-10-07', time: '18:05', precision: 'minute' });
  eq(ES.parseDateTime('2026-10-07').precision, 'jour');
});
t('jours ouvrés', () => {
  eq(ES.businessDaysBetween('2026-10-02', '2026-10-07'), 3); // ven → mer : lun, mar, mer
  eq(ES.businessDaysBetween('2026-10-07', '2026-10-07'), 0);
});

/* ---------- Nombres ---------- */
t('nombres français, allemands, anglais et invalides', () => {
  eq(ES.parseNumber('1 234,56'), 1234.56);
  eq(ES.parseNumber('1.234,56'), 1234.56);
  eq(ES.parseNumber('1,234.56'), 1234.56);
  eq(ES.parseNumber('12,5'), 12.5);
  eq(ES.parseNumber('1.234.567'), 1234567);
  eq(ES.parseNumber('25,30 EUR'), 25.3);
  eq(ES.parseNumber('1.234', 'eu'), 1234, 'format allemand forcé');
  eq(ES.parseNumber('(12,5)'), -12.5);
  eq(ES.parseNumber('abc'), null);
  eq(ES.parseNumber('12abc'), null);
  eq(ES.parseNumber(''), null);
  eq(ES.parseNumber('n/a'), null);
  eq(ES.parseNumber(Infinity), null);
});

/* ---------- ISIN ---------- */
t('contrôle ISIN avec clé', () => {
  ok(ES.isValidIsin('FR0000120271'), 'TotalEnergies');
  ok(ES.isValidIsin('DE0007164600'), 'SAP');
  ok(ES.isValidIsin('NL0000235190'), 'Airbus');
  ok(!ES.isValidIsin('FR0000120272'), 'mauvaise clé');
  ok(!ES.isValidIsin('FR000012027'), 'trop court');
});

/* ---------- CSV / JSON ---------- */
t('CSV point-virgule, guillemets, BOM, ligne tronquée', () => {
  const r = ES.parseCSV('﻿ISIN;Déclarant;Prix\r\n"FR0000120271";"Dupont; Jean";"25,3"\r\nFR0000120271;X');
  eq(r.delimiter, ';');
  eq(r.rows.length, 1);
  eq(r.rows[0]['Déclarant'], 'Dupont; Jean');
  ok(r.truncated, 'ligne tronquée détectée');
});
t('JSON imbriqué aplati', () => {
  const r = ES.parseTable('{"data":[{"isin":"FR0000120271","insider":{"name":"A B"},"price":10}]}');
  eq(r.rows[0]['insider.name'], 'A B');
});
t('correspondance automatique des colonnes (FR et DE) et colonne ambiguë', () => {
  const fr = ES.autoMap('tx', ['ISIN', 'Nom du déclarant', 'Fonction', 'Nature de l\'opération', 'Date de l\'opération', 'Date de publication', 'Prix unitaire', 'Volume']).map;
  eq(fr.person, 'Nom du déclarant'); eq(fr.txDate, 'Date de l\'opération'); eq(fr.pubDate, 'Date de publication'); eq(fr.price, 'Prix unitaire');
  const am = ES.autoMap('tx', ['ISIN', 'Volume']);
  ok(!am.map.qty && !am.map.amount, '« Volume » jamais mappé automatiquement');
  ok(am.warnings.length === 1);
  const de = ES.autoMap('tx', ['Emittent', 'ISIN', 'Meldepflichtiger', 'Position / Status', 'Art des Geschäfts', 'Durchschnittspreis', 'Aggregiertes Volumen', 'Datum des Geschäfts', 'Mitteilungsdatum']).map;
  eq(de.issuer, 'Emittent'); eq(de.person, 'Meldepflichtiger'); eq(de.price, 'Durchschnittspreis'); eq(de.amount, 'Aggregiertes Volumen'); eq(de.txDate, 'Datum des Geschäfts'); eq(de.pubDate, 'Mitteilungsdatum');
  ok(!de.qty, 'pas de quantité inventée pour BaFin');
});

/* ---------- Classification ---------- */
t('nature des opérations', () => {
  eq(ES.classifyType('Acquisition'), 'achat');
  eq(ES.classifyType('Kauf'), 'achat');
  eq(ES.classifyType('Verkauf'), 'vente');
  eq(ES.classifyType('Cession'), 'vente');
  eq(ES.classifyType('Exercice de stock-options'), 'option');
  eq(ES.classifyType('Attribution gratuite d\'actions de performance'), 'attribution');
  eq(ES.classifyType('Acquisition définitive d\'actions gratuites'), 'attribution');
  eq(ES.classifyType('Souscription à une augmentation de capital'), 'souscription');
  eq(ES.classifyType('Donation'), 'don');
  eq(ES.classifyType('Nantissement'), 'nantissement');
  eq(ES.classifyType(''), 'inconnu');
  eq(ES.classifyType('Autre type'), 'autre');
});
t('fonctions et personnes liées', () => {
  ok(ES.classifyRole('Président-Directeur Général').ceo);
  ok(ES.classifyRole('Directeur financier').cfo);
  ok(ES.classifyRole('Finanzvorstand').cfo);
  ok(ES.classifyRole('Personne étroitement liée à M. Martin').associated);
  ok(!ES.classifyRole('Administrateur').ceo);
});

/* ---------- Normalisation ---------- */
const MAP = { isin: 'isin', person: 'p', role: 'r', nature: 'n', txDate: 'd', pubDate: 'pd', qty: 'q', price: 'px', amount: 'm', currency: 'c', registryId: 'id', version: 'v', status: 's', sourceUrl: 'u', linkedTo: 'lt' };
function row(o) { return Object.assign({ isin: 'FR0000120271', p: 'Jean Dupont', r: 'Directeur général', n: 'Acquisition', d: '2026-09-20', pd: '2026-09-22 17:45', q: '1000', px: '50', m: '', c: 'EUR', id: 'A1', v: '1', s: '', u: 'https://example.org/a1', lt: '' }, o); }
const opts = { map: MAP, registry: 'AMF', country: 'FR', today: TODAY, locale: 'auto' };
t('déclaration valide normalisée', () => {
  const r = ES.normalizeTx(row({}), opts);
  ok(r.ok, r.errors.join());
  eq(r.rec.amount, 50000); ok(r.rec.amountComputed); eq(r.rec.pubTime, '17:45'); ok(r.rec.ceo); eq(r.rec.id, 'AMF:A1');
});
t('rejets : date future, nombres invalides, ISIN, publication avant transaction', () => {
  ok(!ES.normalizeTx(row({ d: '2026-12-01' }), opts).ok, 'date future');
  ok(!ES.normalizeTx(row({ pd: '2027-01-01' }), opts).ok, 'publication future');
  ok(!ES.normalizeTx(row({ px: 'douze' }), opts).ok, 'prix invalide');
  ok(!ES.normalizeTx(row({ q: '-5' }), opts).ok, 'quantité négative');
  ok(!ES.normalizeTx(row({ isin: 'FR0000120272' }), opts).ok, 'ISIN invalide');
  ok(!ES.normalizeTx(row({ pd: '2026-09-10' }), opts).ok, 'publication avant transaction');
});
t('aucune quantité inventée à partir du montant', () => {
  const r = ES.normalizeTx(row({ q: '', m: '50000' }), opts);
  ok(r.ok); eq(r.rec.qty, null); eq(r.rec.amount, 50000); ok(!r.rec.amountComputed);
  ok(r.warnings.some(w => /non déduite/.test(w)));
});
t('devise absente non supposée EUR', () => {
  const r = ES.normalizeTx(row({ c: '' }), opts);
  eq(r.rec.currency, null);
  eq(ES.toEur(r.rec.amount, r.rec.currency), null);
});

/* ---------- Fusion, corrections, doublons ---------- */
t('doublons, corrections, annulations et doublons inter-fournisseurs', () => {
  const a = ES.normalizeTx(row({}), opts).rec;
  let m = ES.mergeTransactions([], [a], TODAY);
  eq(m.stats.added, 1);
  m = ES.mergeTransactions(m.list, [a], TODAY); eq(m.stats.duplicates, 1, 'pagination répétée');
  const corr = ES.normalizeTx(row({ v: '2', px: '51', s: 'Rectificatif' }), opts).rec;
  m = ES.mergeTransactions(m.list, [corr], TODAY);
  eq(m.stats.corrected, 1); eq(m.list.length, 1); eq(m.list[0].price, 51); eq(m.list[0].history.length, 1); eq(m.list[0].history[0].snapshot.price, 50);
  const canc = ES.normalizeTx(row({ v: '3', px: '51', s: 'Annulation' }), opts).rec;
  m = ES.mergeTransactions(m.list, [canc], TODAY);
  eq(m.stats.cancelled, 1); eq(m.list[0].status, 'annulee');
  eq(ES.activeTx(m.list).length, 0, 'annulée exclue');
  // même opération vue par un agrégateur puis par le registre officiel
  const agg = ES.normalizeTx(row({ id: 'IS-9', px: '50' }), Object.assign({}, opts, { registry: 'Insider Screener' })).rec;
  const off = ES.normalizeTx(row({ id: 'B7', px: '50' }), Object.assign({}, opts, { registry: 'AMF' })).rec;
  let m2 = ES.mergeTransactions([], [agg], TODAY);
  m2 = ES.mergeTransactions(m2.list, [off], TODAY);
  eq(m2.list.length, 1); eq(m2.list[0].registry, 'AMF'); eq(m2.list[0].alsoSeenIn[0].registry, 'Insider Screener'); eq(m2.stats.crossSource, 1);
});

/* ---------- Séries, splits, extrêmes ---------- */
function makeSeries(n, startPrice, opts2) {
  opts2 = opts2 || {};
  const rows = []; let d = opts2.start || '2025-06-02', p = startPrice;
  if (opts2.end) { let k = 0; d = opts2.end; while (k < n - 1) { d = ES.addDays(d, -1); const w = new Date(d + 'T00:00:00Z').getUTCDay(); if (w !== 0 && w !== 6) k++; } }
  for (let i = 0; i < n; i++) {
    const w = new Date(d + 'T00:00:00Z').getUTCDay();
    if (w === 0 || w === 6) { d = ES.addDays(d, 1); i--; continue; }
    if (opts2.splitOn && d === opts2.splitOn) p = p / 2;
    p = p * (1 + (opts2.drift || 0));
    rows.push([d, p, p * 1.01, p * 0.99, p, opts2.vol != null ? opts2.vol : 100000]);
    d = ES.addDays(d, 1);
  }
  return rows;
}
t('split : prix d\'initié ajusté et pas de fausse anomalie après déclaration du split', () => {
  const rows = makeSeries(300, 100, { splitOn: '2026-03-02' });
  const splits = [{ date: '2026-03-02', ratio: 2 }];
  const s = ES.computeStats(rows, splits, rows[rows.length - 1][0], cfg, 'EUR');
  eq(s.anomalies.length, 0, 'split déclaré');
  const s2 = ES.computeStats(rows, [], rows[rows.length - 1][0], cfg, 'EUR');
  ok(s2.anomalies.length === 1 && s2.anomalies[0].possibleSplit, 'split non déclaré détecté');
  const r = ES.priceRefs({ txDate: '2026-01-15', price: 100 }, rows, splits, rows[rows.length - 1][0]);
  near(r.paidAdj, 50, 1e-9, 'prix ajusté');
  near(r.currentVsPaidPct, 0, 1e-9, 'cours plat après split');
});
t('extrêmes : base intrajournalière vs clôtures et historique incomplet signalé', () => {
  const rows = makeSeries(120, 10);
  const r = ES.priceRefs({ txDate: rows[100][0], price: 10 }, rows, [], rows[119][0]);
  eq(r.atPurchase.ex52.basis, 'intrajournalier');
  ok(!r.atPurchase.full52, '52 semaines incomplètes');
  ok(r.notes.some(n => /incomplète/.test(n)));
  const closesOnly = rows.map(x => [x[0], null, null, null, x[4], x[5]]);
  eq(ES.priceRefs({ txDate: rows[100][0], price: 10 }, closesOnly, [], rows[119][0]).atPurchase.ex52.basis, 'clôtures');
  const before = ES.priceRefs({ txDate: '2025-01-01', price: 10 }, rows, [], rows[119][0]);
  eq(before.atPurchase, null, 'achat antérieur à l\'historique');
});
t('références à la date d\'achat sans données postérieures', () => {
  const rows = makeSeries(300, 100, { drift: 0.002 });
  const tx = rows[150][0];
  const r = ES.priceRefs({ txDate: tx, price: rows[150][4] }, rows, [], rows[299][0]);
  ok(r.atPurchase.ex52.to === tx, 'aucune donnée postérieure à l\'achat');
  near(r.atPurchase.paidVsHigh52Pct, (rows[150][4] / rows[150][2] - 1) * 100, 1e-9, 'plus haut 52 sem. = plus haut intrajournalier du jour');
  ok(r.today.currentPos52 > 90, 'tendance haussière : cours en haut d\'intervalle');
});

/* ---------- Univers ---------- */
t('univers : retenu, rejeté (liquidité), à examiner (historique, périmé, devise)', () => {
  const rows = makeSeries(260, 50, { vol: 50000 }); // 2,5 M€/jour
  const last = rows[rows.length - 1][0];
  const inst = { isin: 'FR0000120271', shareType: 'ordinaire', stats: ES.computeStats(rows, [], last, cfg, 'EUR') };
  eq(ES.universeStatus(inst, cfg).status, 'retenu');
  const illiquid = { shareType: 'ordinaire', stats: ES.computeStats(makeSeries(260, 5, { vol: 1000 }), [], last, cfg, 'EUR') };
  eq(ES.universeStatus(illiquid, cfg).status, 'rejete');
  const short = { shareType: 'ordinaire', stats: ES.computeStats(makeSeries(80, 50), [], ES.addDays('2025-06-02', 115), cfg, 'EUR') };
  eq(ES.universeStatus(short, cfg).status, 'a_examiner');
  const stale = { shareType: 'ordinaire', stats: ES.computeStats(rows, [], ES.addDays(last, 14), cfg, 'EUR') };
  ok(ES.universeStatus(stale, cfg).reasons.some(r => /périmé/.test(r)));
  const gbp = { shareType: 'ordinaire', stats: ES.computeStats(rows, [], last, cfg, 'GBP') };
  eq(ES.universeStatus(gbp, cfg).status, 'a_examiner');
  eq(ES.universeStatus({ shareType: 'préférentielle', stats: inst.stats }, cfg).status, 'rejete');
  eq(ES.universeStatus({ shareType: 'ordinaire', isReference: false, stats: inst.stats }, cfg).status, 'rejete', 'double cotation');
  const susp = { shareType: 'ordinaire', stats: ES.computeStats(rows.map((r, i) => i > 252 ? [r[0], r[1], r[2], r[3], r[4], 0] : r), [], last, cfg, 'EUR') };
  ok(ES.universeStatus(susp, cfg).reasons.some(r => /suspension/.test(r)));
});

/* ---------- Clusters et score ---------- */
function tx(o) { return Object.assign({ id: 'x' + Math.random(), isin: 'FR0000120271', type: 'achat', status: 'active', txDate: '2026-09-20', pubDate: '2026-09-22', price: 50, qty: 1000, amount: 50000, currency: 'EUR', person: 'A', personKey: 'a', sourceUrl: 'u', registry: 'AMF' }, o); }
t('cluster : 3 dirigeants distincts sur 14 jours ; personnes liées non comptées en double', () => {
  const buys = [tx({ personKey: 'a', txDate: '2026-09-01' }), tx({ personKey: 'b', txDate: '2026-09-05' }), tx({ personKey: 'c', txDate: '2026-09-14' })];
  eq(ES.clusterInfo(buys, 14).count, 3);
  eq(ES.clusterInfo([buys[0], buys[1], tx({ personKey: 'c', txDate: '2026-09-15' })], 14).count, 2, '15e jour hors fenêtre');
  const linked = [tx({ personKey: 'a' }), tx({ personKey: 'epouse a', associated: true, linkedTo: 'A' }), tx({ personKey: 'b' })];
  eq(ES.clusterInfo(linked, 14).count, 2, 'personne liée rattachée au même dirigeant');
  const orphan = [tx({ personKey: 'a' }), tx({ personKey: 'holding x', associated: true, linkedTo: null }), tx({ personKey: 'b' })];
  eq(ES.clusterInfo(orphan, 14).count, 2, 'personne liée sans rattachement non comptée');
});
const baseInst = () => {
  const rows = makeSeries(300, 40, { drift: 0.001, vol: 200000, end: TODAY });
  return { isin: 'FR0000120271', name: 'Test', country: 'FR', shareType: 'ordinaire', peaStatus: 'eligible', peaSource: 'Euronext', peaDate: '2026-09-01', stats: ES.computeStats(rows, [], TODAY, cfg, 'EUR'), rows };
};
t('score : familles plafonnées, pas de double comptage, achats hors fenêtre ignorés', () => {
  const inst = baseInst();
  const many = [];
  for (let i = 0; i < 6; i++) many.push(tx({ personKey: 'p' + i, txDate: '2026-09-1' + i, pubDate: '2026-09-2' + i, amount: 2e6, ceo: i === 0 }));
  many.push(tx({ personKey: 'p0', txDate: '2026-09-25', pubDate: '2026-09-26' }));
  many.push(tx({ personKey: 'old', txDate: '2026-06-01', pubDate: '2026-06-03' }));
  const s = ES.score({ inst, tx: many, events: {}, refs: {}, cfg, today: TODAY });
  eq(s.families.insiders.points, 40, 'plafond de famille');
  ok(s.families.insiders.capped);
  eq(s.buys.length, 7, 'achat du 3 juin hors fenêtre de 3 mois (depuis le 7 juillet)');
  ok(s.total <= 100);
});
t('score : attribution et option ignorées ; ventes pénalisantes ; annulée exclue', () => {
  const inst = baseInst();
  const s = ES.score({ inst, tx: [tx({ type: 'attribution' }), tx({ type: 'option' }), tx({ status: 'annulee' })], events: {}, refs: {}, cfg, today: TODAY });
  eq(s.families.insiders.points, 0);
  const s2 = ES.score({ inst, tx: [tx({ amount: 10000 }), tx({ type: 'vente', amount: 900000, cfo: true, personKey: 'z' })], events: {}, refs: {}, cfg, today: TODAY });
  eq(s2.families.insiders.raw, 10 - 10 - 5);
  eq(s2.families.insiders.points, -5, 'plancher -10, valeur -5');
});
t('score : consensus postérieur à la publication refusé', () => {
  const inst = baseInst();
  const bad = { id: 'r1', pubDate: '2026-09-30', consensusDate: '2026-10-01', comparable: true, epsActual: 2, epsConsensus: 1 };
  eq(ES.score({ inst, tx: [], events: { results: [bad] }, refs: {}, cfg, today: TODAY }).families.results.points, 0);
  const good = Object.assign({}, bad, { consensusDate: '2026-09-20', guidance: 'relevee' });
  eq(ES.score({ inst, tx: [], events: { results: [good] }, refs: {}, cfg, today: TODAY }).families.results.points, 18);
  const notComp = Object.assign({}, good, { comparable: false, guidance: null });
  eq(ES.score({ inst, tx: [], events: { results: [notComp] }, refs: {}, cfg, today: TODAY }).families.results.points, 0, 'périodes non comparables');
});
t('rachats : candidat non confirmé = 0 ; autorisation seule = 0 ; annonce confirmée comptée', () => {
  const inst = baseInst();
  const ev = b => ES.score({ inst, tx: [], events: { buybacks: b }, refs: {}, cfg, today: TODAY }).families.buyback.points;
  eq(ev([{ id: 'b1', stage: 'annonce', date: '2026-09-15', confirmed: false }]), 0);
  eq(ev([{ id: 'b1', stage: 'autorisation_ag', date: '2026-09-15', confirmed: true }]), 0);
  eq(ev([{ id: 'b1', stage: 'annonce', date: '2026-09-15', confirmed: true, pctCapital: 3 }]), 11);
});

/* ---------- Qualité, couverture, alertes ---------- */
const sources = { AMF: { status: 'ok', lastSuccess: '2026-10-06', countries: ['FR'] } };
function decide(inst, txs, ev, sent, srcs, cfg2) {
  cfg2 = cfg2 || cfg;
  const score = ES.score({ inst, tx: txs, events: ev || {}, refs: {}, cfg: cfg2, today: TODAY });
  const quality = ES.quality({ inst, score, sources: srcs || sources, events: ev || {}, cfg: cfg2, today: TODAY });
  return ES.alertDecision({ inst, score, quality, overheat: ES.overheat(inst, cfg2), universe: ES.universeStatus(inst, cfg2), cfg: cfg2, today: TODAY, sentEventIds: sent || {} });
}
const strongCase = () => {
  const inst = baseInst();
  const txs = [tx({ id: 't1', personKey: 'a', txDate: '2026-09-28', pubDate: '2026-09-30', ceo: true, amount: 600000 }), tx({ id: 't2', personKey: 'b', txDate: '2026-09-29', pubDate: '2026-10-01' }), tx({ id: 't3', personKey: 'c', txDate: '2026-10-01', pubDate: '2026-10-02' })];
  const ev = { results: [{ id: 'r1', pubDate: '2026-09-25', consensusDate: '2026-09-10', comparable: true, epsActual: 1.2, epsConsensus: 1, revActual: 105, revConsensus: 100, guidance: 'relevee' }] };
  return { inst, txs, ev };
};
t('alerte envoyée quand toutes les conditions sont remplies', () => {
  const { inst, txs, ev } = strongCase();
  const d = decide(inst, txs, ev);
  ok(d.send, d.blocking.join(' | '));
});
t('pas d\'email : doublon (événements déjà signalés)', () => {
  const { inst, txs, ev } = strongCase();
  const d = decide(inst, txs, ev);
  const sent = {}; d.eventIds.forEach(id => sent[id] = 1);
  ok(!decide(inst, txs, ev, sent).send);
});
t('pas d\'email : PEA inconnu en mode strict', () => {
  const { inst, txs, ev } = strongCase(); inst.peaStatus = 'a_verifier';
  ok(!decide(inst, txs, ev).send);
});
t('pas d\'email : source en panne ≠ absence de transaction', () => {
  const { inst, txs, ev } = strongCase();
  const d = decide(inst, txs, ev, {}, { AMF: { status: 'echec', lastSuccess: '2026-10-06', countries: ['FR'] } });
  ok(!d.send && d.blocking.some(b => /Couverture/.test(b)));
  const old = decide(inst, txs, ev, {}, { AMF: { status: 'ok', lastSuccess: '2026-09-01', countries: ['FR'] } });
  ok(!old.send, 'collecte trop ancienne');
});
t('pas d\'email : prix périmé, déclaration ambiguë, aucun événement récent', () => {
  const { inst, txs, ev } = strongCase();
  const stale = Object.assign({}, inst, { stats: ES.computeStats(inst.rows.slice(0, 280), [], TODAY, cfg, 'EUR') });
  ok(!decide(stale, txs, ev).send, 'prix périmé');
  ok(!decide(inst, txs.concat([tx({ type: 'inconnu', personKey: 'q' })]), ev).send, 'ambiguë');
  const oldTx = txs.map(x => Object.assign({}, x, { txDate: '2026-08-01', pubDate: '2026-08-03' }));
  ok(!decide(inst, oldTx, { results: [] }).send, 'événement ancien');
});
t('configuration : validation et somme des plafonds', () => {
  eq(ES.validateConfig(cfg), []);
  const bad = ES.mergeConfig(cfg, { alerts: { mode: 'auto', recipient: 'x' }, weights: { market: { cap: 30 } } });
  eq(ES.validateConfig(bad).length, 3);
});

/* ---------- Étude d'événements ---------- */
t('étude d\'événements : entrée après publication, coûts déduits, hors échantillon séparé', () => {
  const rows = makeSeries(200, 100, { drift: 0.001 });
  const evs = [{ isin: 'X', date: rows[10][0], group: 'achat' }, { isin: 'X', date: rows[150][0], group: 'achat' }];
  const r = ES.eventStudy(evs, { X: { rows, splits: [] } }, { rows, splits: [] }, { costRoundTripPct: 0.5, horizons: [20], oosStart: rows[100][0] });
  eq(r.length, 2);
  const ins = r.find(x => x.sample === 'échantillon');
  const exp = (rows[31][4] / rows[11][1] - 1) * 100 - 0.5;
  near(ins.mean, exp, 1e-9, 'entrée à l\'ouverture de la séance suivante');
  near(ins.meanExcess, -0.5, 1e-9, 'excès vs indice = coûts');
});

/* ---------- Email ---------- */
t('email : contenu obligatoire et mention non probabiliste', () => {
  const { inst, txs, ev } = strongCase();
  const score = ES.score({ inst, tx: txs, events: ev, refs: {}, cfg, today: TODAY });
  const quality = ES.quality({ inst, score, sources, events: ev, cfg, today: TODAY });
  const overheat = ES.overheat(inst, cfg);
  const decision = ES.alertDecision({ inst, score, quality, overheat, universe: ES.universeStatus(inst, cfg), cfg, today: TODAY, sentEventIds: {} });
  const m = ES.buildEmail({ inst, score, quality, overheat, decision, refs: {}, events: ev, today: TODAY });
  ok(/score 8\d|score 9\d|score 7\d|score 6\d/.test(m.subject), m.subject);
  ok(/pas une probabilité/.test(m.html)); ok(/Opérations d'initiés/.test(m.html)); ok(/Risques/.test(m.html)); ok(/https?:|u/.test(m.html));
  ok(m.text.indexOf('<') === -1, 'version texte sans HTML');
});

/* ---------- Collecteur AMF (format réel insider-pea) ---------- */
t('collecteur AMF : natures tronquées, FCPE, montant 0, personnes liées, ISIN mal formé', () => {
  const base = { source: 'AMF/swaoo', declaration_number: '2026DD1141455', isin: 'FR0013230612', date: '2026-09-30', date_published: '2026-10-01', company_name: 'TIKEHAU CAPITAL', insider: 'Antoine  FLAMARION', role: 'Président de AF&CoManagement', nature: 'Acquisition', instrument: 'Action', price: 16.44, quantity: 2740, amount: 45045.6, currency: 'EUR', reference_url: 'https://bdif.amf-france.org/x.pdf' };
  const o = { today: TODAY };
  const a = ES.fromAmfCollector(base, o); ok(a.ok); eq(a.rec.type, 'achat'); eq(a.rec.id, 'AMF:2026DD1141455'); eq(a.rec.person, 'Antoine FLAMARION');
  eq(ES.fromAmfCollector(Object.assign({}, base, { nature: 'ATTRIBUTION GRA...' }), o).rec.type, 'attribution');
  eq(ES.fromAmfCollector(Object.assign({}, base, { nature: "Livraison d'act..." }), o).rec.type, 'attribution');
  eq(ES.fromAmfCollector(Object.assign({}, base, { nature: "Acquisition d'a..." }), o).rec.type, 'autre', 'tronqué = ambigu');
  eq(ES.fromAmfCollector(Object.assign({}, base, { nature: 'Souscription', instrument: 'FIE - TOTALENER...', isin: 'QS0009061084' }), o).rec.type, 'instrument');
  const z = ES.fromAmfCollector(Object.assign({}, base, { amount: 0, price: 0 }), o); eq(z.rec.amount, null); eq(z.rec.price, null, '0 = inconnu');
  const l = ES.fromAmfCollector(Object.assign({}, base, { insider: 'JEAN FOLTZER personne liée à Christian Mary', role: 'PDG' }), o).rec;
  ok(l.associated); eq(l.linkedTo, 'Christian Mary'); ok(!l.ceo, 'proche du PDG ≠ PDG'); eq(ES.buyerKey(l), ES.personKey('Christian Mary'));
  const pm = ES.fromAmfCollector(Object.assign({}, base, { insider: 'DFR INVESTMENT SARL', role: "PERSONNE MORALE LIEE A MR ROMOLO BARDIN ET MRGIOVANNI GIALLOMBARDO  MEMBRES DU CONSEIL D'ADMINISTRATION" }), o).rec;
  const pm2 = ES.fromAmfCollector(Object.assign({}, base, { insider: 'ATERNO SARL', role: "PERSONNE MORALE LIEE A M. ROMOLO BARDIN ET M.GIOVANNI GIALLOMBARDO, MEMBRES DU CONSEIL" }), o).rec;
  eq(ES.buyerKey(pm), ES.buyerKey(pm2), 'deux holdings des mêmes dirigeants = un seul acheteur');
  ok(!ES.fromAmfCollector(Object.assign({}, base, { isin: 'FR0014OOU4P9' }), o).ok, 'ISIN mal formé dans la source');
  ok(!ES.classifyRole("Directeur général d'une filiale").ceo); ok(!ES.classifyRole('DIRECTEUR GENERAL ADJOINT DIVISION CONSTRUCTION').ceo); ok(ES.classifyRole('Président Directeur Général').ceo);
});

t('prix payé hors fourchette du jour signalé', () => {
  const rows = makeSeries(300, 100);
  const d = rows[200][0];
  ok(ES.priceRefs({ txDate: d, price: rows[200][4] }, rows, [], rows[299][0]).outOfRange !== true);
  ok(ES.priceRefs({ txDate: d, price: rows[200][4] * 2 }, rows, [], rows[299][0]).outOfRange === true, 'split manquant ou erreur');
});

t('communiqués : rachats et perspectives détectés dans 6 langues', () => {
  const C = (s) => JSON.stringify(ES.classifyPressTitle(s));
  eq(C('Vusion: Launch of a share buyback program of up to 10% of share capital'), '{"kind":"buyback","value":"annonce"}');
  eq(ES.pctFromTitle('Launch of a share buyback program of up to 10% of share capital'), 10);
  eq(C('TotalEnergies : Déclaration des transactions sur actions propres réalisées du 29 septembre au 3 octobre'), '{"kind":"buyback","value":"execution"}');
  eq(C('SAP SE: Zwischenmeldung Aktienrückkauf – 3. Woche'), '{"kind":"buyback","value":"execution"}');
  eq(C('ASML reports transactions under its current share buyback program'), '{"kind":"buyback","value":"execution"}');
  eq(C('Enel: avvio del programma di acquisto di azioni proprie'), '{"kind":"buyback","value":"annonce"}');
  eq(C('Iberdrola lanza un programa de recompra de acciones'), '{"kind":"buyback","value":"annonce"}');
  eq(C('Prosus: inkoop eigen aandelen'), '{"kind":"buyback","value":"execution"}');
  eq(C('Kering abaisse ses perspectives annuelles'), '{"kind":"guidance","value":"abaissee"}');
  eq(C('Siemens hebt Prognose für Geschäftsjahr an'), '{"kind":"guidance","value":"relevee"}');
  eq(C('Company X raises full-year guidance after strong Q3'), '{"kind":"guidance","value":"relevee"}');
  eq(C('Air Liquide confirme ses objectifs 2026'), '{"kind":"guidance","value":"maintenue"}');
  eq(ES.classifyPressTitle('Recticel announces half-year results'), null, 'pas de conclusion sans motif clair');
});
t('événements Yahoo : surprise BPA, perspectives rattachées, consensus antérieur', () => {
  const raw = { ticker: 'X.PA', earnings: [{ date: '2026-09-25', epsEstimate: 1.0, epsActual: 1.2 }, { date: '2026-11-20', epsEstimate: 1.1, epsActual: null }],
    press: [{ title: 'X relève ses objectifs annuels', date: '2026-09-25', provider: 'GlobeNewswire', url: 'https://ex/1' }, { title: 'X : lancement d\'un programme de rachat d\'actions', date: '2026-09-30', provider: 'Business Wire', url: 'https://ex/2' }, { title: 'Rumeur', date: '2026-12-01' }],
    epsTrend: { current: 4.2, d30: 4.0 } };
  const ev = ES.eventsFromYahoo(raw, TODAY);
  eq(ev.results.length, 1, 'trimestre non publié ignoré'); eq(ev.results[0].guidance, 'relevee'); ok(ev.results[0].consensusDate < ev.results[0].pubDate);
  eq(ev.buybacks.length, 1); eq(ev.buybacks[0].stage, 'annonce'); ok(ev.buybacks[0].confirmed);
  near(ev.revision30d, 5, 1e-9);
  const inst = baseInst();
  const s = ES.score({ inst, tx: [], events: ev, refs: {}, cfg, today: TODAY });
  eq(s.families.results.points, 18, 'BPA +20 % (8) + perspectives relevées (10)'); eq(s.families.buyback.points, 8);
});
t('registre FSMA : nombres au format belge, personne liée', () => {
  const r = ES.fromCollectorRecord({ registry: 'FSMA', country: 'BE', id: '76', url: 'https://www.fsma.be/en/manager-transaction/recticel-76', published: '06/10/2026', issuer: 'RECTICEL', isin: 'BE0003656676', person: 'CORAL & WALLACE', role: 'Senior executive', nature: 'Purchase / Acquisition', instrument: 'Share', txDate: '05/10/2026', currency: 'EUR', quantity: '13.430', price: '12,73', amount: '170.981,36', place: 'Euronext Brussels', numberLocale: 'eu' }, { today: TODAY });
  ok(r.ok, r.errors.join()); eq(r.rec.type, 'achat'); eq(r.rec.qty, 13430); eq(r.rec.price, 12.73); eq(r.rec.amount, 170981.36); eq(r.rec.id, 'FSMA:76'); eq(r.rec.pubDate, '2026-10-06');
  eq(ES.fromCollectorRecord({ registry: 'FSMA', isin: 'BE0003656676', nature: 'Sale / Disposal', instrument: 'Share', txDate: '05/10/2026', numberLocale: 'eu' }, { today: TODAY }).rec.type, 'vente');
  eq(ES.fromCollectorRecord({ registry: 'AFM', isin: 'NL0010273215', nature: 'Aankoop', instrument: 'Aandelen', txDate: '2026-10-01' }, { today: TODAY }).rec.type, 'achat');
  eq(ES.fromCollectorRecord({ registry: 'FSMA', isin: 'BE0003656676', nature: 'Exercise of options', instrument: 'Option', txDate: '05/10/2026' }, { today: TODAY }).rec.type, 'instrument');
  const l = ES.fromCollectorRecord({ registry: 'FSMA', isin: 'BE0003656676', person: 'Holding SA', role: 'Person closely associated', linkedTo: 'Jan Peeters', nature: 'Purchase', instrument: 'Share', txDate: '05/10/2026' }, { today: TODAY }).rec;
  ok(l.associated); eq(ES.buyerKey(l), ES.personKey('Jan Peeters'));
});

t('Insider Screener : codes BUY/SELL/OO, libellé d\'origine prioritaire, source non configurée', () => {
  const base = { registry: 'BaFin', country: 'DE', id: 'tx_1', isin: 'DE0007164600', issuer: 'SAP SE', person: 'Christian Klein', role: 'CEO', instrument: 'Share', txDate: '2026-10-01', published: '2026-10-02', price: '210.5', quantity: '1000', currency: 'EUR', numberLocale: 'en' };
  const b = ES.fromCollectorRecord(Object.assign({}, base, { nature: 'BUY', natureCode: 'BUY' }), { today: TODAY }).rec;
  eq(b.type, 'achat'); ok(b.ceo); eq(b.amount, 210500); eq(b.id, 'BaFin:tx_1');
  eq(ES.fromCollectorRecord(Object.assign({}, base, { nature: 'SELL', natureCode: 'SELL' }), { today: TODAY }).rec.type, 'vente');
  eq(ES.fromCollectorRecord(Object.assign({}, base, { nature: 'OO', natureCode: 'OO' }), { today: TODAY }).rec.type, 'autre_nv', 'autre opération : ni comptée ni ambiguë');
  eq(ES.fromCollectorRecord(Object.assign({}, base, { nature: 'Ausübung von Optionen', natureCode: 'BUY' }), { today: TODAY }).rec.type, 'option', 'le libellé d\'origine prime');
  const inst = { isin: 'DE0007164600', country: 'DE', registry: 'BaFin', stats: {} };
  ok(!ES.coverage(inst, { BaFin: { status: 'absent', note: 'clé absente' } }, cfg, TODAY).ok);
  ok(ES.coverage(inst, { BaFin: { status: 'ok', lastSuccess: '2026-10-06' } }, cfg, TODAY).ok);
});

t('Opérations non volontaires : attribution gratuite, sell-to-cover, prix nul (FSMA, Consob)', () => {
  const base = { registry: 'FSMA', country: 'BE', id: 'x-0', isin: 'BE0003839561', issuer: 'VAN DE VELDE', person: 'VALSEBA', role: 'Member of administrative management or supervisory body', instrument: 'Share', txDate: '2026-10-01', published: '2026-10-02', currency: 'EUR', numberLocale: 'eu' };
  eq(ES.fromCollectorRecord(Object.assign({}, base, { nature: 'Purchase / Acquisition — Free allocation', price: '0,00', quantity: '230' }), { today: TODAY }).rec.type, 'autre_nv');
  eq(ES.fromCollectorRecord(Object.assign({}, base, { nature: 'Purchase / Acquisition', price: '0,00', quantity: '230' }), { today: TODAY }).rec.type, 'autre_nv', 'prix nul');
  eq(ES.fromCollectorRecord(Object.assign({}, base, { nature: 'Altro / Other - VENDITA ... A COPERTURA DEGLI ONERI FISCALI ("SELL-TO-COVER")', natureCode: 'SELL', price: '68.91', numberLocale: 'en' }), { today: TODAY }).rec.type, 'autre_nv');
  eq(ES.fromCollectorRecord(Object.assign({}, base, { nature: 'Purchase / Acquisition', price: '12,73', quantity: '13.430' }), { today: TODAY }).rec.type, 'achat', 'achat ordinaire inchangé');
});

t('Achats par une société (holding, SRL, GmbH, fondation…) exclus si excludeLegalEntities', () => {
  ['MBB Capital Management GmbH', 'HACIA S.A.', 'Giacomelli Holding SRL', 'Inversiones Río Arnoia, S.L.', 'KPS Stiftung', 'VALSEBA', 'Icecat International B.V.', 'Aktieselskabet af 1.2.2017']
    .forEach((n) => ok(ES.isLegalEntity(n), n));
  ['Abend, Robert', 'JEAN PIERRE SBRAIRE', 'Sole S.', 'Marc de Garidel', 'FRANCISCO LUCIANO GONZALEZ ANTUÑA', 'Sterley, Dr. Nadine', 'Anne-Sophie Le Lay']
    .forEach((n) => ok(!ES.isLegalEntity(n), n));
  ok(ES.isLegalEntity('Interparfums', 'INTERPARFUMS'), 'émetteur déclarant');
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { excludeLegalEntities: true } });
  ok(!ES.isVoluntaryBuy({ type: 'achat', person: 'DM Holding S.r.l.' }, c2));
  ok(ES.isVoluntaryBuy({ type: 'achat', person: 'Alberto Donati' }, c2));
  ok(ES.isVoluntaryBuy({ type: 'achat', person: 'DM Holding S.r.l.' }, ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { excludeLegalEntities: false } })), 'désactivable');
});

t('Holding personnelle d\'un dirigeant comptée (cas Rheinmetall), mode strict, décote vs plus haut 52 semaines', () => {
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  const atp = { type: 'achat', person: 'ATP Holding GmbH', associated: true, issuer: 'Rheinmetall AG' };
  ok(ES.isVoluntaryBuy(atp, c2), 'holding du DG comptée');
  ok(!ES.isVoluntaryBuy(atp, ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { excludeLegalEntities: 'strict' } })), 'strict : exclue');
  ok(!ES.isVoluntaryBuy({ type: 'achat', person: 'BPIFRANCE INVESTISSEMENT', associated: false }, c2), 'investisseur exclu');
  const tx = [Object.assign({ id: 'BaFin:1', isin: 'DE0007030009', txDate: '2026-09-29', pubDate: '2026-09-29', status: 'active', price: 950, qty: 525, amount: 498750, currency: 'EUR', ceo: false, board: true, personKey: 'atp' }, atp)];
  const refs = { 'BaFin:1': { available: true, paidAdj: 950, atPurchase: { paidVsHigh52Pct: -52, paidPos52: 1, ex52: { high: 1972, highDate: '2025-10-06' }, full52: true } } };
  const sc = ES.score({ inst: { isin: 'DE0007030009', stats: { sessions: 300, sma50: 1080, sma200: 1336, lastCloseAdj: 953 } }, tx, events: {}, refs, cfg: c2, today: '2026-10-07' });
  eq(Math.round(sc.discount.pct), 52);
  ok(sc.families.insiders.items.some((x) => /52 % sous le plus haut/.test(x.label) && x.points === c2.weights.insiders.discountBig));
  ok(sc.fallingKnife && sc.families.market.items.some((x) => /tendance baissière/.test(x.label)));
});

console.log(results.join('\n'));
console.log('\n' + pass + ' réussis, ' + fail + ' échoués');
process.exit(fail ? 1 : 0);
