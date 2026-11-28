/**
 * Achats et ventes de dirigeants de l'historique long (data/history/amf.json.gz, fi.json.gz), lus comme le calcul du soir
 * (ES.fromCollectorRecord, ES.isVoluntaryBuy, ES.significantBuys, déclaration à 30 jours au plus) pour survivant_restes.py
 * (28/11/2026).
 *
 *   node inities_eodhd.js <sortie.json>
 * Sortie : { isin : [[date de publication, date de l'opération, « a » achat retenu | « v » vente, DG ou DAF (0/1),
 *            clé de l'acheteur, montant en euros ou null], …] } (fichier temporaire, effacé par survivant_restes.py).
 */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const ES = require('../euro_signal/core.js');

const [, , outp] = process.argv;
const root = path.join(__dirname, '..');
const read = (p, d) => {
  try {
    const b = fs.readFileSync(p);
    return JSON.parse(p.endsWith('.gz') ? zlib.gunzipSync(b).toString('utf8') : b.toString('utf8'));
  } catch (e) {
    return d;
  }
};
const cfg = ES.mergeConfig(ES.DEFAULT_CONFIG, read(path.join(root, 'euro_signal', 'config.json'), {}));
const site = read(path.join(root, 'data', 'euro-signal.json'), {});
const fx = (site && site.fx && (site.fx.rates || site.fx)) || {};
ES.setFx(Object.assign({ SEK: 11.0, NOK: 11.7, DKK: 7.46 }, typeof fx === 'object' ? fx : {}));
const today = new Date().toISOString().slice(0, 10);
const per = {};
const stat = {};
for (const [reg, file] of [
  ['AMF', 'amf.json.gz'],
  ['FI', 'fi.json.gz'],
]) {
  const recs = read(path.join(root, 'data', 'history', file), []);
  const st = (stat[reg] = { lus: 0, achats: 0, ventes: 0, tardifs: 0 });
  for (const r of Array.isArray(recs) ? recs : []) {
    if (!r || typeof r !== 'object' || Array.isArray(r)) continue;
    let res;
    try {
      res = ES.fromCollectorRecord(r, { today });
    } catch (e) {
      continue;
    }
    if (!res.ok || res.rec.type === 'instrument') continue;
    const t = res.rec;
    if (!ES.isEuropeanIsin(t.isin) || t.status === 'annulee' || t.status === 'remplacee') continue;
    st.lus++;
    const late = t.pubDate && t.txDate ? ES.daysBetween(t.txDate, t.pubDate) > cfg.insiders.maxFilingLagDays : false;
    const x = (per[t.isin] = per[t.isin] || { buys: [], sells: [] });
    if (ES.isVoluntaryBuy(t, cfg)) {
      if (late) st.tardifs++;
      else x.buys.push(t);
    } else if (t.type === 'vente') x.sells.push(t);
  }
}
const out = {};
for (const [isin, x] of Object.entries(per)) {
  const kept = ES.significantBuys(x.buys, cfg).kept;
  const rows = [];
  for (const t of kept)
    rows.push([ES.availDate(t), t.txDate, 'a', t.ceo || t.cfo ? 1 : 0, ES.buyerKey(t) || t.personKey || '', ES.toEur(t.amount, t.currency)]);
  for (const t of x.sells)
    rows.push([ES.availDate(t), t.txDate, 'v', t.ceo || t.cfo ? 1 : 0, t.personKey || '', ES.toEur(t.amount, t.currency)]);
  if (rows.length) out[isin] = rows.filter((r) => typeof r[0] === 'string' && r[0].length >= 10);
  const reg = isin.slice(0, 2) === 'FR' ? 'AMF' : 'FI';
  if (stat[reg]) {
    stat[reg].achats += kept.length;
    stat[reg].ventes += x.sells.length;
  }
}
fs.writeFileSync(outp, JSON.stringify(out));
console.log(
  'dirigeants : ' +
    Object.entries(stat)
      .map(
        ([k, s]) =>
          `${k} ${s.lus} déclarations lues, ${s.achats} achats retenus, ${s.tardifs} achats déclarés à plus de 30 jours écartés, ${s.ventes} ventes`
      )
      .join(' ; ') +
    ` ; ${Object.keys(out).length} sociétés`
);
