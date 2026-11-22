/**
 * Verdict des comptes de chaque société à chaque date, comme le calcul du soir (ES.accountsAnalysis puis accSummary de
 * euro_signal/build.mjs) : 'good' (comptes solides), 'mixed', 'bad', 'na' (pas encore lus ou trop anciens), 'fin' (banque ou
 * assurance, F-score sans objet). Comptes Yahoo de data/financials.json (4 exercices, 2022-2026).
 *
 * Délai de lecture : 120 jours après la clôture dans l'outil ; 90 et 60 jours pour comparer (asOf décalé d'autant).
 * Sortie : out/comptes_dates.json = { symbole Yahoo : { "120": [[date, verdict], …], "90": …, "60": … } } (changements seulement).
 *
 *   node comptes_dates.js        (dans research/, données de la veille dans ../data : tools/donnees.sh)
 */
const fs = require('fs');
const path = require('path');
const ES = require('../euro_signal/core.js');

const DATA = path.join(__dirname, '..', 'data');
const read = (f) => JSON.parse(fs.readFileSync(path.join(DATA, f), 'utf8'));
const fin = read('financials.json').items || {};
const inst = read('euro-signal.json').inst || {};
const cat = {};
for (const f of fs.readdirSync(path.join(DATA, 'societes'))) {
  if (f.endsWith('.json')) Object.assign(cat, read(path.join('societes', f)).items || {});
}

const LAGS = [120, 90, 60];
const STALE = 548; // comme accSummary : derniers comptes complets de plus de 18 mois → non lus
const out = {};
let n = 0;
for (const [k, f] of Object.entries(fin)) {
  const isin = k.startsWith('@') ? null : k;
  const i = (isin && inst[isin]) || {};
  const sym = f.ticker || i.ticker || (k.startsWith('@') ? k.slice(1) : null);
  if (!sym || !Array.isArray(f.years) || !f.years.length) continue;
  const c = cat[sym] || {};
  const sector = i.sector || (i.fund && i.fund.sector) || c.sector;
  const industry = (i.fund && i.fund.industry) || c.industry;
  const ys = f.years.map((y) => y && y.date).filter((d) => typeof d === 'string').sort();
  const res = {};
  for (const L of LAGS) {
    const ev = [...new Set(ys.flatMap((d) => [ES.addDays(d, L), ES.addDays(d, STALE + 1)]))].sort();
    const pts = [];
    for (const d of ev) {
      let v = 'na';
      try {
        const a = ES.accountsAnalysis(f, { asOf: ES.addDays(d, 120 - L), sector, industry });
        const last = a && a.years && a.years.length ? a.years[a.years.length - 1] : null;
        if (a && !(last && last.date && ES.daysBetween(String(last.date).slice(0, 10), d) > STALE)) {
          const isFin = !!(a.fscore && a.fscore.na && /banques/.test(a.fscore.reason || ''));
          v = isFin ? 'fin' : a.verdict ? a.verdict.key : 'na';
        }
      } catch (e) {
        v = 'na';
      }
      if (!pts.length || pts[pts.length - 1][1] !== v) pts.push([d, v]);
    }
    res[L] = pts;
  }
  out[sym] = res;
  n++;
}
fs.mkdirSync(path.join(__dirname, 'out'), { recursive: true });
fs.writeFileSync(path.join(__dirname, 'out', 'comptes_dates.json'), JSON.stringify(out));
console.log(`comptes_dates : ${n} sociétés`);
