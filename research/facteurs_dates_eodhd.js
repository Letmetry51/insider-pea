/**
 * Facteurs des comptes sur 25 ans (28/11/2026, survivant_facteurs.py) : comme valeur_dates_eodhd.js (comptes EODHD connus
 * 120 jours après la clôture, lus par ES.accountsAnalysis du calcul du soir), avec en plus le point d'alerte Beneish de la page.
 * Au-delà de 18 mois sans nouveaux comptes : « pas lus ».
 *
 *   node facteurs_dates_eodhd.js <entrée.json> <sortie.json>
 * Entrée : { symbole : { years, currency, sector, industry } } (fichier temporaire, effacé par survivant_facteurs.py).
 * Sortie : { symbole : [[date, verdict, f9, perte, zone d'Altman, banque, clôture lue, Beneish], …] } (changements seulement) ;
 * zone d'Altman : « safe », « grey », « distress » (après la confirmation de la page) ou vide ; Beneish : 1 profil signalé
 * par la page (M > −1,78), 0 non, −1 inconnu.
 */
const fs = require('fs');
const ES = require('../euro_signal/core.js');

const [, , inp, outp] = process.argv;
const fin = JSON.parse(fs.readFileSync(inp, 'utf8'));
const STALE = 548;
const avail = (y) => ES.addDays(y.date, 120);
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
    let row = [d, 'na', null, 0, '', 0, '', -1];
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
            a.beneish && !a.beneish.na ? (a.beneish.flag ? 1 : 0) : -1,
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
console.log(`lectures des comptes : ${n} sociétés, ${err} erreur(s) de calcul`);
