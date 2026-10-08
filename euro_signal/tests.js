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
const cfg = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });

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
  ok(/note \d+\/100/.test(m.subject) && m.text.indexOf(score.total + " points") > -1, m.subject);
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
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });
  const atp = { type: 'achat', person: 'ATP Holding GmbH', associated: true, issuer: 'Rheinmetall AG' };
  ok(ES.isVoluntaryBuy(atp, c2), 'holding du DG comptée');
  ok(!ES.isVoluntaryBuy(atp, ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { excludeLegalEntities: 'strict' } })), 'strict : exclue');
  ok(!ES.isVoluntaryBuy({ type: 'achat', person: 'BPIFRANCE INVESTISSEMENT', associated: false }, c2), 'investisseur exclu');
  const tx = [Object.assign({ id: 'BaFin:1', isin: 'DE0007030009', txDate: '2026-09-29', pubDate: '2026-09-29', status: 'active', price: 950, qty: 525, amount: 498750, currency: 'EUR', ceo: false, board: true, personKey: 'atp' }, atp)];
  const refs = { 'BaFin:1': { available: true, paidAdj: 950, atPurchase: { paidVsHigh52Pct: -52, paidPos52: 1, ex52: { high: 1972, highDate: '2025-10-06' }, full52: true } } };
  const sc = ES.score({ inst: { isin: 'DE0007030009', stats: { sessions: 300, sma50: 1080, sma200: 1336, lastCloseAdj: 953 } }, tx, events: {}, refs, cfg: c2, today: '2026-10-07' });
  eq(Math.round(sc.discount.pct), 52);
  ok(sc.families.insiders.items.some((x) => /52\s%\ssous le plus haut/.test(x.label) && x.points === c2.weights.insiders.discountBig));
  ok(sc.fallingKnife && sc.families.market.items.some((x) => /cours en repli/.test(x.label)));
});

t('Croisement MM50 / MM200 après un achat de dirigeant', () => {
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });
  const rows = []; let p = 100;
  for (let i = 0; i < 320; i++) { const d = ES.addDays('2025-01-01', i); p = i < 200 ? p * 0.998 : p * 1.01; rows.push([d, p, p, p, p, 1e5]); }
  const st = ES.computeStats(rows, [], rows[rows.length - 1][0], c2, 'EUR');
  ok(st.sma50 > st.sma200 && st.goldenCrossDate, 'croisement détecté');
  const tx = [{ id: 'x', isin: 'FR0000120271', type: 'achat', txDate: '2025-08-20', pubDate: '2025-08-21', status: 'active', person: 'Jean Martin', personKey: 'jm', price: 80, qty: 250, amount: 20000, currency: 'EUR' }];
  const sc = ES.score({ inst: { isin: 'FR0000120271', stats: st }, tx, events: {}, refs: {}, cfg: c2, today: rows[rows.length - 1][0] });
  ok(sc.goldenCrossAfterBuy && sc.families.market.items.some((x) => /après l'achat d'un dirigeant/.test(x.label) && x.points === c2.weights.market.goldenCrossAfterBuy));
  const sc2 = ES.score({ inst: { isin: 'FR0000120271', stats: st }, tx: [Object.assign({}, tx[0], { txDate: '2025-10-01', pubDate: '2025-10-02' })], events: {}, refs: {}, cfg: c2, today: rows[rows.length - 1][0] });
  ok(!sc2.goldenCrossAfterBuy && sc2.trendUp, 'croisement antérieur à l\'achat : tendance seulement');
});

t('Le tableau de bord embarque exactement le moteur testé (pas de version désynchronisée)', () => {
  const fs = require('fs'), path = require('path');
  const html = path.join(__dirname, '..', 'euro-signal.html');
  if (!fs.existsSync(html)) return;
  ok(fs.readFileSync(html, 'utf8').indexOf(fs.readFileSync(path.join(__dirname, 'core.js'), 'utf8')) > -1, 'euro-signal.html à reconstruire avec core.js');
});

t('Stress test : devise, prix incohérents, liens, corrections, doublons entre registres', () => {
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });
  const rows = []; for (let i = 0; i < 30; i++) rows.push([ES.addDays('2026-09-01', i), 250, 260, 240, 250, 1e5]);
  eq(ES.priceRefs({ txDate: '2026-09-10', price: 2.5, currency: 'GBP' }, rows, [], '2026-10-01', 'GBp').paidAdj, 250, 'GBP payé vs GBp coté');
  ok(!ES.priceRefs({ txDate: '2026-09-10', price: 2.5, currency: 'EUR' }, rows, [], '2026-10-01', 'GBp').available, 'EUR vs GBp : comparaison refusée');
  ok(ES.priceRefs({ txDate: '2026-09-10', price: 20, currency: 'EUR' }, rows, [], '2026-10-01', 'EUR').belowMarket, 'prix très sous le marché');
  eq(ES.safeUrl('javascript:alert(1)'), ''); eq(ES.safeUrl('https://bdif.amf-france.org/x.pdf'), 'https://bdif.amf-france.org/x.pdf');
  eq(ES.cleanCurrency('<img src=x>'), null); eq(ES.cleanCurrency('eur'), 'EUR');
  eq(ES.normalizeSeries([['2026-01-01', 1, 1, 1, Infinity, 1], ['2026-01-02', 1, 1, 1, '5', 1], ['2026-01-03', 1, 1, 1, 5, 1]]).length, 1);
  const amf = ES.fromAmfCollector({ isin: 'FR0000120271', date: '2026-09-01', date_published: '2026-09-02', company_name: 'X', insider: 'Jean Martin', role: 'Directeur général', nature: 'Acquisition', instrument: 'Action', price: 0, quantity: 1000, amount: 0, currency: 'EUR', declaration_number: '2026DD1', reference_url: 'https://bdif.amf-france.org/a.pdf' }, { today: '2026-10-01' });
  eq(amf.rec.type, 'autre_nv', 'AMF prix nul');
  const base = { isin: 'IT0001234567', txDate: '2026-09-01', pubDate: '2026-09-02', type: 'achat', price: 10, qty: 100, amount: 1000, currency: 'EUR', status: 'active', version: 1 };
  const a1 = Object.assign({}, base, { id: 'AMF:1', registry: 'AMF', person: 'Mario Rossi', personKey: 'mr' }); a1.dedupKey = ES.dedupKey(a1);
  const b1 = Object.assign({}, base, { id: 'CONSOB:1', registry: 'CONSOB', person: 'L6A4 SRL', personKey: 'l6' }); b1.dedupKey = ES.dedupKey(b1);
  const m = ES.mergeTransactions([a1], [b1], '2026-10-01');
  eq(m.list.length, 1, 'même opération dans deux registres'); eq(m.stats.crossSource, 1);
  const c1 = Object.assign({}, base, { id: 'CNMV:1', registry: 'CNMV', person: 'Ana Ruiz', personKey: 'ar', price: 19.05 }); c1.dedupKey = ES.dedupKey(c1);
  const c2r = Object.assign({}, c1, { id: 'CNMV:2', price: 18.05, status: 'corrigee' }); c2r.dedupKey = ES.dedupKey(c2r);
  const m2 = ES.mergeTransactions([c1], [c2r], '2026-10-01');
  eq(m2.list.filter((x) => x.status === 'active').length, 1, 'correction sous un nouvel identifiant remplace l\'originale'); eq(m2.list[0].price, 18.05);
  const m3 = ES.mergeTransactions(m2.list, [c2r], '2026-10-02');
  eq(m3.stats.corrected, 0, 'idempotent'); eq(m3.list.length, 1);
  const inst = { isin: 'DE0007030009', country: 'DE', registry: 'AMF' };
  ok(!ES.coverage(inst, { AMF: { status: 'ok', lastSuccess: '2026-10-01' }, BaFin: { status: 'echec' } }, c2, '2026-10-01').ok, 'registre du pays de domiciliation aussi exigé');
  ok(ES.coverage(inst, { AMF: { status: 'ok', lastSuccess: '2026-10-01' }, BaFin: { status: 'ok', lastSuccess: '2026-10-01', countries: ['DE'] } }, c2, '2026-10-01').ok);
});

t('Force relative 6 mois et tendance du marché européen', () => {
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });
  const tx = [{ id: 'x', isin: 'FR0000120271', type: 'achat', txDate: '2026-09-20', pubDate: '2026-09-21', status: 'active', person: 'Jean Martin', personKey: 'jm', price: 80, qty: 250, amount: 20000, currency: 'EUR' }];
  const st = { sessions: 300, sma50: 90, sma200: 85, lastCloseAdj: 95, rel6m: 14, marketAbove200: false };
  const sc = ES.score({ inst: { isin: 'FR0000120271', stats: st }, tx, events: {}, refs: {}, cfg: c2, today: '2026-10-07' });
  ok(sc.families.market.items.some((x) => /plus fort que le marché/.test(x.label) && x.points === c2.weights.market.relStrength));
  ok(sc.marketDown && sc.families.market.items.some((x) => /marché européen sous sa moyenne/.test(x.label) && x.points === 0));
  const rows = []; let p = 100; for (let i = 0; i < 200; i++) { p *= 1.002; rows.push([ES.addDays('2026-01-01', i), p, p, p, p, 1e5]); }
  const s2 = ES.computeStats(rows, [], rows[199][0], c2, 'EUR');
  ok(Math.abs(s2.ret6m1 - (Math.pow(1.002, 105) - 1) * 100) < 1e-6, 'momentum 6 mois hors dernier mois');
});

t('Psychologie : achat pendant une vente panique ; argumentaire chiffré des emails', () => {
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });
  const rows = []; let p = 100;
  for (let i = 0; i < 60; i++) { p = i < 45 ? p * 1.001 : p * 0.975; rows.push([ES.addDays('2026-07-01', i), p, p, p, p, 1e5]); }
  const r = ES.priceRefs({ txDate: rows[59][0], price: rows[59][4], currency: 'EUR' }, rows, [], rows[59][0], 'EUR');
  ok(r.atPurchase.drop10 <= -15 && r.atPurchase.rsi14 < 30, 'chute et survente mesurées à la date d\'achat');
  const tx = [{ id: 'x', isin: 'FR0000120271', type: 'achat', txDate: rows[59][0], pubDate: rows[59][0], status: 'active', person: 'Jean Martin', personKey: 'jm', price: rows[59][4], qty: 100, amount: 20000, currency: 'EUR' }];
  const sc = ES.score({ inst: { isin: 'FR0000120271', stats: {} }, tx, events: {}, refs: { x: r }, cfg: c2, today: rows[59][0] });
  ok(sc.panicBuy && sc.families.insiders.items.some((x) => /vente panique/.test(x.label) && x.points === 2));
  const res = [{ group: 'Achat volontaire', horizon: 60, nExcess: 40, hitExcess: 55, meanExcess: 1.5 }, { group: 'Achat volontaire', horizon: 60, nExcess: 60, hitExcess: 45, meanExcess: -1 }];
  const ra = ES.emailRationale(res, 'Achat volontaire', 60);
  ok(/100 cas/.test(ra.text) && /49 %/.test(ra.text) && /\+0,0|0,0/.test(ra.text), ra.text);
  ok(/trop petit/.test(ES.emailRationale([{ group: 'G', horizon: 60, nExcess: 5, hitExcess: 60, meanExcess: 3 }], 'G', 60).text));
  ok(ra.html.indexOf('<script') < 0);
});

t('Solidité financière : fragile, solide, inconnu ; alerte bloquée si fragile', () => {
  eq(ES.financialHealth(null).status, 'inconnu');
  const fr = ES.financialHealth({ totalDebt: 900, totalCash: 100, ebitda: 150, profitMargins: 0.02, freeCashflow: 10, operatingCashflow: 40 });
  eq(fr.status, 'fragile'); ok(/5,3 fois/.test(fr.reasons[0]), fr.reasons[0]);
  eq(ES.financialHealth({ totalDebt: 100, totalCash: 300, ebitda: 80, profitMargins: 0.12, freeCashflow: 50 }).status, 'solide');
  eq(ES.financialHealth({ totalDebt: 1e12, totalCash: 1e9, ebitda: 1e8, profitMargins: 0.2, sector: 'Financial Services' }).status, 'solide', 'banque : dette non comparable');
  eq(ES.financialHealth({ profitMargins: -0.4, freeCashflow: -5, operatingCashflow: -3 }).status, 'fragile');
  eq(ES.financialHealth({ totalDebt: 10e9, totalCash: 0.6e9, ebitda: 1e9, profitMargins: 0.5, sector: 'Real Estate' }).status, 'solide', 'foncière');
  eq(ES.financialHealth({ totalDebt: 72e9, totalCash: 21e9, ebitda: 6.2e9, profitMargins: 0.02, sector: 'Consumer Cyclical', industry: 'Auto Manufacturers' }).status, 'solide', 'constructeur auto');
  eq(ES.financialHealth({ totalDebt: 9.3e6, totalCash: 21.5e6, ebitda: -18.9e6, profitMargins: 0, freeCashflow: -16.9e6 }).status, 'fragile', 'trésorerie qui s\'épuise (Circus)');
  eq(ES.financialHealth({ totalDebt: 33.8e9, totalCash: 9.5e9, ebitda: 5.77e9, profitMargins: 0.03, sector: 'Industrials', industry: 'Waste Management' }).status, 'solide', 'Veolia : 4,2 fois, normal pour le secteur');
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });
  const d = ES.alertDecision({ inst: { isin: 'FR0000120271', fund: { totalDebt: 900, totalCash: 0, ebitda: 100 } }, score: { total: 80, independentFamilies: 3, eventFamilies: 2, contributing: [{ id: 'a', date: '2026-10-06' }], lastEventDate: '2026-10-06', ambiguousCount: 0 }, quality: { total: 90, coverage: { ok: true } }, overheat: { total: 0 }, universe: { status: 'retenu', reasons: [] }, cfg: c2, today: '2026-10-07', sentEventIds: {} });
  ok(!d.send && d.blocking.some((b) => /Solidité financière/.test(b)));
});

t('Auto-apprentissage : ajustement borné, significatif, une fois par mois', () => {
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 0 } });
  const samples = [];
  for (let i = 0; i < 200; i++) samples.push({ excess: (i % 2 ? 0.08 : 0.06) + (i % 7) * 0.001, f: { panic: true, ceo: i % 3 === 0 } });
  for (let i = 0; i < 200; i++) samples.push({ excess: (i % 2 ? -0.01 : 0.01) + (i % 5) * 0.001, f: { panic: false, ceo: i % 3 === 0 } });
  const r = ES.calibrate(samples, c2, null, '2026-11-02');
  eq(r.weights.insiders.panicBuy, c2.weights.insiders.panicBuy + 1, 'hausse d\'un pas');
  ok(!(r.weights.insiders && r.weights.insiders.ceoCfo != null), 'composante sans effet net : inchangée');
  eq(r.version, 1); eq(r.changed.length, 1);
  const again = ES.calibrate(samples, ES.mergeConfig(c2, { weights: r.weights }), r, '2026-11-20');
  eq(again.changed.length, 0, 'pas deux fois dans le mois');
  let w = r;
  for (let m = 1; m <= 9; m++) w = ES.calibrate(samples, ES.mergeConfig(c2, { weights: w.weights }), w, '2027-0' + m + '-02');
  eq(w.weights.insiders.panicBuy, 2 * c2.weights.insiders.panicBuy, 'plafond : 2 fois le poids d\'origine');
  const few = ES.calibrate(samples.slice(0, 50).concat(samples.slice(200, 250)), c2, null, '2026-11-02');
  eq(few.changed.length, 0, 'pas assez de cas');
});

t('Cluster regroupé, programme collectif repéré, seuil de 10 000 € par dirigeant', () => {
  const c2 = ES.mergeConfig(ES.DEFAULT_CONFIG, { insiders: { minBuyerEur: 10000 } });
  const mk = (id, person, d, eur, extra) => Object.assign({ id, isin: 'FR0000133308', type: 'achat', txDate: d, pubDate: d, status: 'active', person, personKey: person.toLowerCase(), role: 'Membre du comité exécutif', price: 10, qty: eur / 10, amount: eur, currency: 'EUR' }, extra || {});
  const tx = [mk('a', 'Anne Durand', '2026-09-29', 20000), mk('b', 'Bruno Petit', '2026-09-29', 21000), mk('c', 'Carla Roux', '2026-09-30', 20500), mk('d', 'Denis Morel', '2026-09-30', 19800),
    mk('e', 'SCI Durand', '2026-09-30', 15000, { associated: true, linkedTo: 'Anne Durand' }), mk('f', 'Eric Blanc', '2026-09-30', 2000)];
  const sc = ES.score({ inst: { isin: 'FR0000133308', stats: {} }, tx, events: {}, refs: {}, cfg: c2, today: '2026-10-07' });
  eq(sc.cluster.count, 4, 'proche rattaché, petit achat ignoré'); eq(sc.cluster.buyers.length, 4);
  eq(sc.cluster.buyers.find((b) => b.name === 'Anne Durand').eur, 35000, 'achat du proche ajouté à son dirigeant');
  ok(sc.cluster.coordinated, 'même jour, montants proches');
  ok(sc.families.insiders.items.some((x) => /petit\(s\) achat\(s\)/.test(x.label)));
  ok(sc.families.insiders.items.some((x) => /programme collectif/.test(x.label) && x.points < 0));
  const sig = ES.significantBuys([mk('g', 'Gilles Noir', '2026-09-01', 6000), mk('h', 'Gilles Noir', '2026-09-05', 6000)], c2);
  eq(sig.kept.length, 1, 'cumul sur 14 jours : le 2e achat franchit le seuil'); eq(sig.small.length, 1);
});

t('Seuil par défaut : 100 000 € investis par le dirigeant', () => {
  const c = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  eq(c.insiders.minBuyerEur, 100000);
  const mk = (id, eur, d) => ({ id, type: 'achat', txDate: d, pubDate: d, person: 'Jean Martin', personKey: 'jm', amount: eur, currency: 'EUR', status: 'active' });
  eq(ES.significantBuys([mk('a', 60000, '2026-09-01')], c).kept.length, 0);
  eq(ES.significantBuys([mk('a', 60000, '2026-09-01'), mk('b', 50000, '2026-09-08')], c).kept.length, 1, 'cumul 110 k€ en 8 jours');
  eq(ES.significantBuys([mk('a', 250000, '2026-09-01')], c).kept.length, 1);
});

t('Sélection de la semaine : filtres durs, tri, 5 au plus, email échappé', () => {
  const c = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  eq(ES.isoWeek('2026-10-08'), '2026-W41'); eq(ES.isoWeek('2027-01-01'), '2026-W53'); eq(ES.isoWeek('2026-01-01'), '2026-W01');
  const q = { total: 90, coverage: { ok: true } };
  const mkc = (k, total, extra) => Object.assign({ isin: 'FR000000000' + k, inst: { name: 'Soc ' + k, country: 'FR', fund: null },
    score: { total, buys: [{ txDate: '2026-10-01', pubDate: '2026-10-01', person: 'X' }], ambiguousCount: 0, discount: { pct: 10 + k, person: 'X', date: '2026-10-01' }, buyEur: 200000, cluster: null },
    quality: q, universe: { status: 'retenu' } }, extra || {});
  const cands = [mkc(1, 50), mkc(2, 40), mkc(3, 40), mkc(4, 35), mkc(5, 31), mkc(6, 33), mkc(7, 20),
    mkc(8, 60, { universe: { status: 'rejete' } }), mkc(9, 60, { quality: { total: 40, coverage: { ok: true } } })];
  cands.push(Object.assign(mkc(0, 70), { inst: { name: 'Fragile', fund: { totalDebt: 1e10, totalCash: 0, ebitda: -1e8, freeCashflow: -5e8, operatingCashflow: -4e8, sector: 'Technology' } } }));
  const old = mkc(10, 80); old.score.buys = [{ txDate: '2026-07-01', pubDate: '2026-07-01' }]; cands.push(old);
  const sel = ES.weeklySelection(cands, c, '2026-10-08');
  eq(sel.length, 5, '5 au plus'); eq(sel[0].score, 50);
  eq(sel.map((x) => x.isin.slice(-1)).join(''), '13246', 'score puis décote, sous le score minimum exclu');
  ok(!sel.some((x) => x.name === 'Fragile'), 'société fragile exclue');
  ok(!sel.some((x) => /0$/.test(x.isin) && x.score === 80), 'achat de plus de 30 jours exclu');
  const evil = [Object.assign({}, sel[0], { name: '<img src=x onerror=alert(1)>' })];
  const m = ES.buildSelectionEmail(evil, '2026-W41', c, 'https://ex.org/es.html', '2026-10-08');
  ok(m.html.indexOf('<img') < 0 && m.html.indexOf('&lt;img') > -1, 'nom échappé');
  ok(/Sélection de la semaine \(2026-W41\) : 1 dossier à étudier/.test(m.subject));
  ok(/#FR0000000001/.test(m.text), 'lien direct vers la fiche');
  ok(/Aucune société/.test(ES.buildSelectionEmail([], '2026-W41', c, null, '2026-10-08').text), 'semaine sans dossier');
});

t('Secteur en français et argumentaire de méthode honnête', () => {
  const c = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  eq(ES.sectorFr('Industrials'), 'Industrie'); eq(ES.sectorFr('Inconnu'), 'Inconnu'); eq(ES.sectorFr(null), null);
  const res = [{ group: 'Achat volontaire', horizon: 60, sample: 'échantillon', n: 50, mean: 2, hit: 50, nExcess: 50, meanExcess: 1, hitExcess: 46 },
    { group: 'Achat volontaire', horizon: 60, sample: 'hors échantillon', n: 50, mean: 0, hit: 42, nExcess: 50, meanExcess: -0.4, hitExcess: 46 }];
  const o = ES.groupOutcome(res, 'Achat volontaire', 60); eq(o.n, 100); eq(Math.round(o.up), 46); eq(Math.round(o.beat), 46);
  const r = ES.methodRationale(res, c, '01/06/2026');
  ok(/plus haut 60 séances plus tard \(environ 3 mois\) dans 46 % des cas/.test(r.text), 'chiffre mesuré');
  ok(/pas d'avantage net/.test(r.text), 'pas d\'avantage affiché quand il n\'existe pas');
  ok(/100 k€/.test(r.text), 'seuil cité');
  const good = res.map((x) => Object.assign({}, x, { n: 200, nExcess: 200, hitExcess: 62 }));
  ok(/se confirme/.test(ES.methodRationale(good, c, null).text));
  ok(/Pas encore assez de recul/.test(ES.methodRationale([], c, null).text));
  const m = ES.buildSelectionEmail([{ isin: 'DE0006305006', name: 'DEUTZ', country: 'DE', sector: 'Industrie', score: 50, discountPct: 22, ceo: false, buyers: 4, buyEur: 2e6, trendUp: true }], '2026-W41', c, 'https://x.org/es.html', '2026-10-08', r);
  ok(/Secteur : Industrie/.test(m.html) && /DEUTZ \(Industrie\)/.test(m.text) && /Pourquoi cette méthode/.test(m.html));
});

t('Sélection : nouveautés, bilan des sélections passées, alertes d\'achat désactivables', () => {
  const c = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  eq(c.alerts.buyEmails, true, 'par défaut (compatibilité)');
  const tr = [{ week: '2026-W41', bench: 2, items: [{ perf: 5 }, { perf: -1 }, { perf: null }] }, { week: '2026-W42', bench: 0, items: [{ perf: 3 }] }];
  const s = ES.selectionTrackSummary(tr);
  eq(s.n, 3); eq(s.weeks, 2); eq(Math.round(s.avg * 100) / 100, 2.33); eq(Math.round(s.beatPct), 67, '5>2 et 3>0, pas -1');
  eq(ES.selectionTrackSummary([]), null);
  const x = { isin: 'FR0000000001', name: 'Soc', score: 40, discountPct: 30, ceo: true, buyers: 1, isNew: true };
  const m = ES.buildSelectionEmail([x], '2026-W42', c, null, '2026-10-12', null, s);
  ok(/\[NOUVEAU\] Soc/.test(m.text) && />NOUVEAU</.test(m.html), 'nouveauté signalée');
  ok(/Suivi des sélections précédentes \(2 semaines, 3 dossiers\) : \+2,3 %/.test(m.text), 'bilan en tête');
  ok(/fort/.test(m.text), 'libellé du score');
});

t('Note /100 : points bruts rapportés au maximum réaliste (60), plafonnée', () => {
  const c = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  eq(ES.note(50, c), 83); eq(ES.note(45, c), 75); eq(ES.note(30, c), 50); eq(ES.note(33, c), 55); eq(ES.note(80, c), 100); eq(ES.note(-5, c), 0);
  eq(ES.scoreLabel(45, c).hint, 'note 75 et plus');
  eq(ES.note(30, ES.mergeConfig(c, { display: { scoreCeiling: 100 } })), 30, 'réglable');
});

t('Pairs, positions vendeuses, critères en observation, repère historique', () => {
  const c = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  const mk = (isin, ev, ind, sec) => ({ isin, fund: { evToEbitda: ev, industry: ind || 'Specialty Industrial Machinery', sector: sec || 'Industrials' } });
  const inst = {}; [['FR0000000001', 5], ['FR0000000002', 10], ['FR0000000003', 11], ['FR0000000004', 9], ['FR0000000005', 12], ['FR0000000006', 10]].forEach((x) => { inst[x[0]] = mk(x[0], x[1]); });
  inst.FR0000000007 = { isin: 'FR0000000007', fund: { priceToBook: 0.8, sector: 'Financial Services', industry: 'Banks' } };
  const pv = ES.peerValuation(inst);
  eq(pv.FR0000000001.peers, 5); eq(pv.FR0000000001.peerMedian, 10); eq(pv.FR0000000001.discountPct, 50, '5 contre 10 : 50 % sous les pairs');
  eq(pv.FR0000000001.level, 'industrie'); ok(!pv.FR0000000007, 'banque sans pairs comparables : rien');
  const sh = ES.shortInfo([{ holder: 'A', pct: 0.7, from: '2026-09-01', to: null }, { holder: 'B', pct: 0.6, from: '2026-01-01', to: '2026-05-01' }, { holder: 'A', pct: 0.6, from: '2026-08-01', to: '2026-09-01' }], '2026-10-08');
  eq(sh.holders, 1); eq(sh.totalPct, 0.7); eq(ES.shortInfo([{ holder: 'B', pct: 0.6, from: '2026-01-01', to: '2026-05-01' }], '2026-10-08'), null, 'position close');
  ok(ES.shortInfo([{ holder: 'B', pct: 0.6, from: '2026-01-01', to: '2026-05-01' }], '2026-03-01'), 'en vigueur à la date passée');
  const smp = []; for (let k = 0; k < 70; k++) { smp.push({ f: { smallMid: true }, excess: 0.05 + (k % 7) * 0.001 }); smp.push({ f: { smallMid: false }, excess: -0.01 + (k % 5) * 0.001 }); }
  const ob = ES.observeStats(smp, c); const sm = ob.find((o) => o.feature === 'smallMid');
  eq(sm.nWith, 70); ok(/candidat/.test(sm.action), sm.action); ok(/en observation/.test(ob.find((o) => o.feature === 'shorted').action));
  const hist = [40, 45, 50, 52, 55, 58, 60, 62, 65, 70, 72, 75];
  eq(ES.historicRank(80, hist).key, 'rare'); eq(ES.historicRank(66, hist).key, 'good'); eq(ES.historicRank(45, hist).key, 'wait'); eq(ES.historicRank(80, [1, 2]).key, 'na');
  const items = [{ note: 83, hist: ES.historicRank(83, hist) }];
  eq(ES.weekVerdict(items, [50, 55, 60, 65, 70, 75]).key, 'strong');
  eq(ES.weekVerdict([{ note: 52 }], [50, 55, 60, 65, 70, 75]).key, 'weak');
  eq(ES.weekVerdict([], []).key, 'empty'); eq(ES.weekVerdict([{ note: 70 }], [60]).key, 'na');
  const x = { isin: 'FR0000000001', name: 'Soc', score: 50, discountPct: 30, ceo: true, buyers: 1, hist: ES.historicRank(83, hist), peer: pv.FR0000000001, shorts: { totalPct: 0.7, holders: 1 } };
  const m = ES.buildSelectionEmail([x], '2026-W41', c, null, '2026-10-08', null, null, ES.weekVerdict([{ note: 83, hist: x.hist }], [50, 55, 60, 65, 70, 75]));
  ok(/Semaine exceptionnelle/.test(m.text) && /Semaine exceptionnelle<\/b>/.test(m.html), 'verdict en tête');
  ok(/remarquable/.test(m.text) && /50 % sous ses pairs/.test(m.text) && /1 fonds parie à la baisse/.test(m.text), m.text.slice(0, 400));
});

t('Leader / challenger, étoiles, données mal formées tolérées', () => {
  const c = ES.mergeConfig(ES.DEFAULT_CONFIG, {});
  const mk = (rev, cur, ind) => ({ fund: { revenue: rev, currency: cur, industry: ind || 'Auto Parts' } });
  const inst = { A: mk(9e9, 'EUR'), B: mk(5e9, 'EUR'), B2: mk(5e9, 'EUR'), C: mk(3e9, 'GBP'), D: mk(1e9, 'EUR'), E: mk(2e7, 'EUR'), F: mk(4e9, null), G: mk('x', 'EUR') };
  const mp = ES.marketPosition(inst);
  eq(mp.A.key, 'leader'); eq(mp.A.of, 5, 'classe d\'actions en double, devise inconnue et valeur invalide écartées');
  eq(mp.B.key, 'challenger'); ok(!mp.B2 && !mp.F && !mp.G); eq(mp.E.key, 'niche');
  eq(Object.keys(ES.marketPosition({ A: mk(1, 'EUR'), B: mk(2, 'EUR') })).length, 0, 'moins de 5 sociétés : pas de classement');
  eq(ES.stars(50, c, 'rare').n, 5); eq(ES.stars(50, c, 'good').n, 4); eq(ES.stars(30, c).n, 3); eq(ES.stars(15, c).n, 2); eq(ES.stars(2, c).n, 1);
  eq(ES.shortInfo({ holder: 'x', pct: 1 }, '2026-10-08'), null, 'liste attendue');
  eq(ES.shortInfo([{ holder: 'x', pct: '1.5', from: '2026-01-01' }], '2026-10-08').totalPct, 1.5, 'pourcentage en texte converti');
  eq(ES.shortInfo([{ holder: 'x', pct: 40, from: '2026-01-01' }], '2026-10-08'), null, 'valeur aberrante ignorée');
  const pv = ES.peerValuation({ A: { fund: { evToEbitda: '12', industry: 'X', sector: 'Y' } } }); eq(Object.keys(pv).length, 0);
});

console.log(results.join('\n'));
console.log('\n' + pass + ' réussis, ' + fail + ' échoués');
process.exit(fail ? 1 : 0);
