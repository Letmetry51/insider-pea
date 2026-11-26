/**
 * Verdict des comptes à chaque date, comme le calcul du soir (ES.accountsAnalysis, même règle que comptes_dates.js), pour les
 * comptes EODHD de survivant_comptes.py (26/11/2026) : 'good', 'mixed', 'bad', 'na' (pas encore lus ou de plus de 18 mois),
 * 'fin' (banque ou assurance). Comptes lus 120 jours après la clôture.
 *
 *   node comptes_dates_eodhd.js <entrée.json> <sortie.json>
 * Entrée : { symbole : { years: [...], currency, sector, industry } } (fichier temporaire, effacé par survivant_comptes.py).
 * Sortie : { symbole : [[date, verdict], …] } (changements seulement).
 */
const fs = require('fs');
const ES = require('../euro_signal/core.js');

const [, , inp, outp] = process.argv;
const fin = JSON.parse(fs.readFileSync(inp, 'utf8'));
const STALE = 548;
const out = {};
let n = 0,
  err = 0;
for (const [sym, f] of Object.entries(fin)) {
  if (!f || !Array.isArray(f.years) || !f.years.length) continue;
  const ys = f.years
    .map((y) => y && y.date)
    .filter((d) => typeof d === 'string')
    .sort();
  const ev = [...new Set(ys.flatMap((d) => [ES.addDays(d, 120), ES.addDays(d, STALE + 1)]))].sort();
  const pts = [];
  for (const d of ev) {
    let v = 'na';
    try {
      const a = ES.accountsAnalysis(f, { asOf: d, sector: f.sector, industry: f.industry });
      const last = a && a.years && a.years.length ? a.years[a.years.length - 1] : null;
      if (a && !(last && last.date && ES.daysBetween(String(last.date).slice(0, 10), d) > STALE)) {
        const isFin = !!(a.fscore && a.fscore.na && /banques/.test(a.fscore.reason || ''));
        v = isFin ? 'fin' : a.verdict ? a.verdict.key : 'na';
      }
    } catch (e) {
      v = 'na';
      err++;
    }
    if (!pts.length || pts[pts.length - 1][1] !== v) pts.push([d, v]);
  }
  out[sym] = pts;
  n++;
}
fs.writeFileSync(outp, JSON.stringify(out));
console.log(`verdicts des comptes : ${n} sociétés, ${err} erreur(s) de calcul`);
