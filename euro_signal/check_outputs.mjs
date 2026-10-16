// Contrôle des fichiers produits par le calcul du soir, avant leur publication sur le tableau de bord.
// Vérifie que chaque vue a de quoi s'afficher correctement (graphiques 1 an et 5 ans différents, plans d'entrée complets,
// convergence, journal, secteurs) et que rien d'absurde ne part en ligne. N'arrête jamais le calcul : écrit un rapport
// dans data/diagnostics/check-outputs.txt et sort en erreur seulement si un contrôle bloquant échoue.
//
//   node euro_signal/check_outputs.mjs            (après euro_signal/build.mjs)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DATA = path.join(ROOT, 'data');
const today = process.env.ES_TODAY || new Date().toISOString().slice(0, 10);
const lines = [];
let fails = 0, warns = 0;
const ok = (m) => lines.push('OK     ' + m);
const ko = (m) => { fails++; lines.push('ÉCHEC  ' + m); };
const warn = (m) => { warns++; lines.push('ALERTE ' + m); };
const check = (cond, m, soft) => (cond ? ok(m) : soft ? warn(m) : ko(m));
const read = (f) => { const p = path.join(DATA, f); if (!fs.existsSync(p)) return null; try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return { __error: e.message }; } };
const sizeMb = (f) => { const p = path.join(DATA, f); return fs.existsSync(p) ? fs.statSync(p).size / 1048576 : 0; };
const yearsBetween = (a, b) => (new Date(b) - new Date(a)) / (365.25 * 86400000);
const median = (a) => { if (!a.length) return null; const s = a.slice().sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };

// 1. Fichiers présents, lisibles, de taille raisonnable (GitHub refuse au-delà de 100 Mo)
const main = read('euro-signal.json');
check(main && !main.__error, 'euro-signal.json lisible' + (main && main.__error ? ' (' + main.__error + ')' : ''));
if (!main || main.__error) finish();
for (const f of ['euro-signal.json', 'euro-signal-long.json', 'euro-signal-state.json', 'sectors.json', 'societes-index.json']) {
  const mb = sizeMb(f);
  check(mb < 60, `${f} : ${mb.toFixed(1)} Mo (limite 60)`);
}
const raw = fs.readFileSync(path.join(DATA, 'euro-signal.json'), 'utf8');
check(!/\bNaN\b|\bInfinity\b/.test(raw), 'aucune valeur NaN ou Infinity dans euro-signal.json');
check(main.today === today || process.env.ES_TODAY == null, `date des données ${main.today} (aujourd'hui ${today})`, true);

// 2. Cours 1 an (fichier détaillé) et 5 ans (fichier long) : présents et réellement différents
// fiches détaillées : réparties en petits fichiers (data/fiches/N.json), rassemblées ici pour les contrôles
const SH = main.detailShards || null;
let detail = null, shardBad = 0, shardMax = 0;
if (SH && SH.n > 0) {
  detail = { prices: {}, tx: {} };
  for (let k = 0; k < SH.n; k++) {
    const f = path.join(ROOT, SH.dir, k + '.json');
    let d = null; try { d = JSON.parse(fs.readFileSync(f, 'utf8')); shardMax = Math.max(shardMax, fs.statSync(f).size / 1048576); } catch (e) { shardBad++; continue; }
    Object.assign(detail.prices, d.prices || {}); Object.assign(detail.tx, d.tx || {});
    for (const i of Object.keys(d.prices || {})) if (ES_shard(i, SH.n) !== k) shardBad++;
  }
  check(shardBad === 0, `fiches réparties : ${SH.n} fichiers lisibles, chaque société dans le bon fichier`);
  check(shardMax < 3, `plus gros fichier de fiches : ${shardMax.toFixed(1)} Mo (3 au plus, pour un téléphone)`, true);
} else detail = read('euro-signal-detail.json');
function ES_shard(isin, n) { let h = 0; for (const ch of String(isin)) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h % n; }
const long = read('euro-signal-long.json');
check(detail && !detail.__error && Object.keys(detail.prices || {}).length > 0, 'cours journaliers (vue 1 an) publiés');
check(main.longFile === 'data/euro-signal-long.json', 'le tableau de bord pointe vers le fichier 5 ans (longFile)');
check(long && !long.__error && long.items, 'euro-signal-long.json lisible' + (long && long.__error ? ' (' + long.__error + ')' : ''));
if (detail && detail.prices && long && long.items) {
  const isins = Object.keys(detail.prices);
  const withLong = isins.filter((i) => long.items[i] && Array.isArray(long.items[i].w) && long.items[i].w.length >= 20);
  check(withLong.length >= 0.8 * isins.length, `vue 5 ans disponible pour ${withLong.length} titres sur ${isins.length} (80 % au moins)`);
  const spans = withLong.map((i) => yearsBetween(long.items[i].w[0][0], long.items[i].w[long.items[i].w.length - 1][0]));
  const spans1 = isins.map((i) => { const r = detail.prices[i].rows || []; return r.length ? yearsBetween(r[0][0], r[r.length - 1][0]) : 0; });
  const m5 = median(spans), m1 = median(spans1);
  check(m1 != null && m1 > 0.9 && m1 < 1.2, `vue 1 an : ${m1 == null ? 'n.d.' : m1.toFixed(2)} an de cours (médiane)`);
  check(m5 != null && m5 >= 4.5, `vue 5 ans : ${m5 == null ? 'n.d.' : m5.toFixed(2)} ans de cours (médiane, 4,5 au moins)`);
  const long4 = spans.filter((s) => s >= 4.5).length;
  check(long4 >= 0.7 * withLong.length, `${long4} titres sur ${withLong.length} ont au moins 4,5 ans de cours hebdomadaires`, true);
  // même titre : la vue 5 ans doit commencer bien avant la vue 1 an et finir au même cours (raccord)
  let same = 0, badJoin = 0;
  withLong.forEach((i) => {
    const w = long.items[i].w, r = detail.prices[i].rows;
    if (!r || !r.length) return;
    if (yearsBetween(w[0][0], r[0][0]) < 1.5) same++;
    const lastW = w[w.length - 1], k = r.findIndex((x) => x[0] >= lastW[0]);
    const ref = k >= 0 ? r[k][1] : r[r.length - 1][1];
    if (ref > 0 && lastW[1] > 0 && Math.abs(lastW[1] / ref - 1) > 0.15) badJoin++;
  });
  check(same <= 0.2 * withLong.length, `${same} titres dont la vue 5 ans ne remonte pas plus loin que la vue 1 an (20 % au plus)`);
  check(badJoin <= 0.05 * withLong.length, `${badJoin} titres dont les cours 1 an et 5 ans ne se raccordent pas (écart > 15 %, 5 % au plus)`, true);
  let jumps = 0;
  withLong.forEach((i) => { const w = long.items[i].w; for (let k = 1; k < w.length; k++) if (w[k - 1][1] > 0 && (w[k][1] / w[k - 1][1] > 3 || w[k][1] / w[k - 1][1] < 1 / 3)) { jumps++; break; } });
  check(jumps <= 0.06 * withLong.length, `${jumps} séries 5 ans avec un saut de cours de plus de ×3 en une semaine, signalé sur la fiche (6 % au plus ; souvent réel : augmentation de capital, regroupement, scission)`, true);
}

// 3. Plans d'entrée, figures, oscillateurs, convergence
const I = Object.keys(main.inst || {});
const plans = I.map((i) => main.inst[i].plan).filter(Boolean);
check(plans.length >= 0.5 * I.length, `plans d'entrée calculés : ${plans.length} sur ${I.length} titres`);
const full = plans.filter((p) => p.verdict && p.primary && p.wedge && p.osc);
check(full.length >= 0.95 * plans.length, `plans complets (verdict, scénario, figure, RSI/MACD) : ${full.length} sur ${plans.length}`);
const badPlan = plans.filter((p) => p.primary && p.primary.rr != null && !(p.primary.rr > -50 && p.primary.rr < 50)).length;
check(badPlan === 0, `${badPlan} plan(s) avec un rapport gain / risque absurde`);
const verdicts = {}; plans.forEach((p) => { verdicts[p.verdict] = (verdicts[p.verdict] || 0) + 1; });
check(Object.keys(verdicts).length >= 2, 'répartition des verdicts : ' + Object.entries(verdicts).map(([k, v]) => k + ' ' + v).join(', '), true);
const conv = I.map((i) => main.inst[i].convergence).filter(Boolean);
check(conv.length >= 0.5 * I.length && conv.every((c) => c.n >= 0 && c.n <= 5), `convergence notée pour ${conv.length} titres`);
const nAcc = I.filter((i) => main.inst[i].accounts).length, nVal = I.filter((i) => main.inst[i].value).length;
check(nAcc >= 0.5 * I.length, `comptes annuels (F-score, Beneish, analyse des comptes) pour ${nAcc} titres sur ${I.length} (50 % au moins)`);
check(nVal >= 0.5 * I.length, `valeur comptable et intrinsèque pour ${nVal} titres sur ${I.length} (50 % au moins)`, true);
const secT = I.filter((i) => main.inst[i].sectorTrend).length;
check(secT >= 0.3 * I.length, `tendance du secteur rattachée pour ${secT} titres`, true);
check(main.planStudy && main.planStudy.obs > 1000, `étude historique du plan : ${main.planStudy ? main.planStudy.obs : 0} relevés`, true);
check(main.journal && main.journal.entries > 0, `journal de bord : ${main.journal ? main.journal.entries : 0} relevés`, true);

// 4. Toutes les sociétés cotées (recherche et fiches)
const CI = read('societes-index.json');
check(CI && !CI.__error && CI.rows && CI.rows.length >= 1500, `toutes les sociétés cotées : ${CI && CI.rows ? CI.rows.length : 0} dans la liste de recherche (1 500 au moins)`, true);
if (CI && CI.rows) {
  const want = ['TTE.PA', 'MC.PA', 'SAN.PA', 'ASML.AS', 'SAP.DE', 'VU.PA'];
  const have = new Set(CI.rows.map((r) => r[0]));
  check(want.every((w) => have.has(w)), 'grandes valeurs présentes (TotalEnergies, LVMH, Sanofi, ASML, SAP, Vusion) : ' + want.filter((w) => !have.has(w)).join(', ') || 'toutes');
  let bad = 0;
  for (let k = 0; k < (CI.shards || 32); k++) { try { JSON.parse(fs.readFileSync(path.join(DATA, 'societes', k + '.json'), 'utf8')); } catch (e) { bad++; } }
  check(bad === 0, `fiches des sociétés : ${CI.shards || 32} fichiers lisibles`);
}

// 5. Secteurs
const sec = read('sectors.json');
check(sec && !sec.__error && sec.format === 'euro-signal-sectors' && (sec.groups || []).length >= 20, `secteurs : ${sec && sec.groups ? sec.groups.length : 0} groupes classés`);
if (sec && sec.generatedAt) check(yearsBetween(sec.generatedAt.slice(0, 10), today) * 365 <= 4, `secteurs à jour (${sec.generatedAt.slice(0, 10)})`, true);

finish();

function finish() {
  lines.push('', `${fails} échec(s), ${warns} alerte(s)`);
  const txt = `Contrôle des fichiers du ${today}\n\n` + lines.join('\n') + '\n';
  fs.mkdirSync(path.join(DATA, 'diagnostics'), { recursive: true });
  fs.writeFileSync(path.join(DATA, 'diagnostics', 'check-outputs.txt'), txt);
  console.log(txt);
  process.exit(fails ? 1 : 0);
}
