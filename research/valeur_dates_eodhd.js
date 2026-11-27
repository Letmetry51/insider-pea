/**
 * 💎 Valeur sur 25 ans (27/11/2026, survivant_valeur.py) : à chaque date où des comptes annuels EODHD deviennent connus, lecture
 * du calcul du soir (ES.accountsAnalysis) : verdict, F-score de Piotroski, dernier exercice en perte, zone d'Altman, banque ou
 * assurance, et clôture de l'exercice lu (pour le cours / fonds propres et le nombre d'actions).
 * Mode « lag120 » : comptes connus 120 jours après la clôture, comme le calcul du soir et comptes_dates_eodhd.js.
 * Mode « depot » : comptes connus à la date de dépôt donnée par EODHD quand elle tombe plus tard (contrôle).
 * Au-delà de 18 mois sans nouveaux comptes : « pas lus ».
 *
 *   node valeur_dates_eodhd.js <entrée.json> <sortie.json> [lag120|depot]
 * Entrée : { symbole : { years: [... avec « filed » éventuel], currency, sector, industry } } (fichier temporaire, effacé par
 * survivant_valeur.py). Sortie : { symbole : [[date, verdict, f9, perte, altman, banque, clôture lue], …] } (changements seulement).
 */
const fs = require('fs');
const ES = require('../euro_signal/core.js');

const [, , inp, outp, mode = 'lag120'] = process.argv;
const fin = JSON.parse(fs.readFileSync(inp, 'utf8'));
const STALE = 548;
const avail = (y) => {
  const d0 = ES.addDays(y.date, 120);
  if (mode !== 'depot' || typeof y.filed !== 'string' || y.filed.length < 10) return d0;
  const f = y.filed.slice(0, 10);
  return f > d0 ? f : d0;
};
const out = {};
let n = 0,
  err = 0;
for (const [sym, f] of Object.entries(fin)) {
  if (!f || !Array.isArray(f.years) || !f.years.length) continue;
  const ys = f.years.filter((y) => y && typeof y.date === 'string').sort((a, b) => (a.date < b.date ? -1 : 1));
  const ev = [...new Set(ys.flatMap((y) => [avail(y), ES.addDays(y.date, STALE + 1)]))].sort();
  const pts = [];
  let prev = '';
  for (const d of ev) {
    let row = [d, 'na', null, 0, '', 0, ''];
    try {
      const known = ys.filter((y) => avail(y) <= d);
      if (known.length) {
        const a = ES.accountsAnalysis(Object.assign({}, f, { years: known }), {
          asOf: d,
          sector: f.sector,
          industry: f.industry,
        });
        const last = a && a.years && a.years.length ? a.years[a.years.length - 1] : null;
        if (a && last && last.date && ES.daysBetween(String(last.date).slice(0, 10), d) <= STALE) {
          const isFin = !!(a.fscore && a.fscore.na && /banques/.test(a.fscore.reason || ''));
          row = [
            d,
            isFin ? 'fin' : a.verdict ? a.verdict.key : 'na',
            a.fscore && !a.fscore.na ? a.fscore.f9 : null,
            last.netIncome != null && last.netIncome < 0 ? 1 : 0,
            a.altman && !a.altman.na ? a.altman.zone || '' : '',
            isFin ? 1 : 0,
            String(last.date).slice(0, 10),
          ];
        }
      }
    } catch (e) {
      err++;
    }
    const key = JSON.stringify(row.slice(1));
    if (key !== prev) {
      pts.push(row);
      prev = key;
    }
  }
  out[sym] = pts;
  n++;
}
fs.writeFileSync(outp, JSON.stringify(out));
console.log(`lectures des comptes (${mode}) : ${n} sociétés, ${err} erreur(s) de calcul`);
