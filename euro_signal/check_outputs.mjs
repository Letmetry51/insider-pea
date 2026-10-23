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
let fails = 0,
  warns = 0;
const ok = (m) => lines.push('OK     ' + m);
const ko = (m) => {
  fails++;
  lines.push('ÉCHEC  ' + m);
};
const warn = (m) => {
  warns++;
  lines.push('ALERTE ' + m);
};
const check = (cond, m, soft) => (cond ? ok(m) : soft ? warn(m) : ko(m));
const read = (f) => {
  const p = path.join(DATA, f);
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch (e) {
    return { __error: e.message };
  }
};
const sizeMb = (f) => {
  const p = path.join(DATA, f);
  return fs.existsSync(p) ? fs.statSync(p).size / 1048576 : 0;
};
const yearsBetween = (a, b) => (new Date(b) - new Date(a)) / (365.25 * 86400000);
const median = (a) => {
  if (!a.length) return null;
  const s = a.slice().sort((x, y) => x - y);
  return s[Math.floor(s.length / 2)];
};

// 1. Fichiers présents, lisibles, de taille raisonnable (GitHub refuse au-delà de 100 Mo)
const main = read('euro-signal.json');
check(main && !main.__error, 'euro-signal.json lisible' + (main && main.__error ? ' (' + main.__error + ')' : ''));
if (!main || main.__error) finish();
for (const f of [
  'euro-signal.json',
  'euro-signal-long.json',
  'euro-signal-state.json',
  'sectors.json',
  'societes-index.json',
]) {
  const mb = sizeMb(f);
  check(mb < 60, `${f} : ${mb.toFixed(1)} Mo (limite 60)`);
}
const raw = fs.readFileSync(path.join(DATA, 'euro-signal.json'), 'utf8');
check(!/\bNaN\b|\bInfinity\b/.test(raw), 'aucune valeur NaN ou Infinity dans euro-signal.json');
check(
  main.today === today || process.env.ES_TODAY == null,
  `date des données ${main.today} (aujourd'hui ${today})`,
  true
);

// 2. Cours 1 an (fichier détaillé) et 5 ans (fichier long) : présents et réellement différents
// fiches détaillées : réparties en petits fichiers (data/fiches/N.json), rassemblées ici pour les contrôles
const SH = main.detailShards || null;
let detail = null,
  shardBad = 0,
  shardMax = 0;
if (SH && SH.n > 0) {
  detail = { prices: {}, tx: {} };
  for (let k = 0; k < SH.n; k++) {
    const f = path.join(ROOT, SH.dir, k + '.json');
    let d = null;
    try {
      d = JSON.parse(fs.readFileSync(f, 'utf8'));
      shardMax = Math.max(shardMax, fs.statSync(f).size / 1048576);
    } catch (e) {
      shardBad++;
      continue;
    }
    Object.assign(detail.prices, d.prices || {});
    Object.assign(detail.tx, d.tx || {});
    for (const i of Object.keys(d.prices || {})) if (ES_shard(i, SH.n) !== k) shardBad++;
  }
  check(shardBad === 0, `fiches réparties : ${SH.n} fichiers lisibles, chaque société dans le bon fichier`);
  check(shardMax < 3, `plus gros fichier de fiches : ${shardMax.toFixed(1)} Mo (3 au plus, pour un téléphone)`, true);
} else detail = read('euro-signal-detail.json');
function ES_shard(isin, n) {
  let h = 0;
  for (const ch of String(isin)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % n;
}
const long = read('euro-signal-long.json');
check(detail && !detail.__error && Object.keys(detail.prices || {}).length > 0, 'cours journaliers (vue 1 an) publiés');
check(main.longFile === 'data/euro-signal-long.json', 'le tableau de bord pointe vers le fichier 5 ans (longFile)');
check(
  long && !long.__error && long.items,
  'euro-signal-long.json lisible' + (long && long.__error ? ' (' + long.__error + ')' : '')
);
if (detail && detail.prices && long && long.items) {
  const isins = Object.keys(detail.prices);
  const withLong = isins.filter((i) => long.items[i] && Array.isArray(long.items[i].w) && long.items[i].w.length >= 20);
  check(
    withLong.length >= 0.8 * isins.length,
    `vue 5 ans disponible pour ${withLong.length} titres sur ${isins.length} (80 % au moins)`
  );
  const spans = withLong.map((i) =>
    yearsBetween(long.items[i].w[0][0], long.items[i].w[long.items[i].w.length - 1][0])
  );
  const spans1 = isins.map((i) => {
    const r = detail.prices[i].rows || [];
    return r.length ? yearsBetween(r[0][0], r[r.length - 1][0]) : 0;
  });
  const m5 = median(spans),
    m1 = median(spans1);
  check(m1 != null && m1 > 0.9 && m1 < 1.2, `vue 1 an : ${m1 == null ? 'n.d.' : m1.toFixed(2)} an de cours (médiane)`);
  check(
    m5 != null && m5 >= 4.5,
    `vue 5 ans : ${m5 == null ? 'n.d.' : m5.toFixed(2)} ans de cours (médiane, 4,5 au moins)`
  );
  const long4 = spans.filter((s) => s >= 4.5).length;
  check(
    long4 >= 0.7 * withLong.length,
    `${long4} titres sur ${withLong.length} ont au moins 4,5 ans de cours hebdomadaires`,
    true
  );
  // même titre : la vue 5 ans doit commencer bien avant la vue 1 an et finir au même cours (raccord)
  let same = 0,
    badJoin = 0;
  withLong.forEach((i) => {
    const w = long.items[i].w,
      r = detail.prices[i].rows;
    if (!r || !r.length) return;
    if (yearsBetween(w[0][0], r[0][0]) < 1.5) same++;
    const lastW = w[w.length - 1],
      k = r.findIndex((x) => x[0] >= lastW[0]);
    const ref = k >= 0 ? r[k][1] : r[r.length - 1][1];
    if (ref > 0 && lastW[1] > 0 && Math.abs(lastW[1] / ref - 1) > 0.15) badJoin++;
  });
  check(
    same <= 0.2 * withLong.length,
    `${same} titres dont la vue 5 ans ne remonte pas plus loin que la vue 1 an (20 % au plus)`
  );
  check(
    badJoin <= 0.05 * withLong.length,
    `${badJoin} titres dont les cours 1 an et 5 ans ne se raccordent pas (écart > 15 %, 5 % au plus)`,
    true
  );
  let jumps = 0;
  withLong.forEach((i) => {
    const w = long.items[i].w;
    for (let k = 1; k < w.length; k++)
      if (w[k - 1][1] > 0 && (w[k][1] / w[k - 1][1] > 3 || w[k][1] / w[k - 1][1] < 1 / 3)) {
        jumps++;
        break;
      }
  });
  check(
    jumps <= 0.06 * withLong.length,
    `${jumps} séries 5 ans avec un saut de cours de plus de ×3 en une semaine, signalé sur la fiche (6 % au plus ; souvent réel : augmentation de capital, regroupement, scission)`,
    true
  );
}

// 3. Plans d'entrée, figures, oscillateurs, convergence
const I = Object.keys(main.inst || {});
const plans = I.map((i) => main.inst[i].plan).filter(Boolean);
check(plans.length >= 0.5 * I.length, `plans d'entrée calculés : ${plans.length} sur ${I.length} titres`);
const full = plans.filter((p) => p.verdict && p.primary && p.wedge && p.osc);
check(
  full.length >= 0.95 * plans.length,
  `plans complets (verdict, scénario, figure, RSI/MACD) : ${full.length} sur ${plans.length}`
);
const badPlan = plans.filter(
  (p) => p.primary && p.primary.rr != null && !(p.primary.rr > -50 && p.primary.rr < 50)
).length;
check(badPlan === 0, `${badPlan} plan(s) avec un rapport gain / risque absurde`);
const verdicts = {};
plans.forEach((p) => {
  verdicts[p.verdict] = (verdicts[p.verdict] || 0) + 1;
});
check(
  Object.keys(verdicts).length >= 2,
  'répartition des verdicts : ' +
    Object.entries(verdicts)
      .map(([k, v]) => k + ' ' + v)
      .join(', '),
  true
);
const conv = I.map((i) => main.inst[i].convergence).filter(Boolean);
check(
  conv.length >= 0.5 * I.length && conv.every((c) => c.n >= 0 && c.n <= 5),
  `convergence notée pour ${conv.length} titres`
);
const nAcc = I.filter((i) => main.inst[i].accounts).length,
  nVal = I.filter((i) => main.inst[i].value).length;
check(
  nAcc >= 0.5 * I.length,
  `comptes annuels (F-score, Beneish, analyse des comptes) pour ${nAcc} titres sur ${I.length} (50 % au moins)`
);
check(
  nVal >= 0.5 * I.length,
  `valeur comptable et intrinsèque pour ${nVal} titres sur ${I.length} (50 % au moins)`,
  true
);
const secT = I.filter((i) => main.inst[i].sectorTrend).length;
check(secT >= 0.3 * I.length, `tendance du secteur rattachée pour ${secT} titres`, true);
check(
  main.planStudy && main.planStudy.obs > 1000,
  `étude historique du plan : ${main.planStudy ? main.planStudy.obs : 0} relevés`,
  true
);
check(
  main.journal && main.journal.entries > 0,
  `journal de bord : ${main.journal ? main.journal.entries : 0} relevés`,
  true
);

// 4. Toutes les sociétés cotées (recherche et fiches)
const CI = read('societes-index.json');
check(
  CI && !CI.__error && CI.rows && CI.rows.length >= 1500,
  `toutes les sociétés cotées : ${CI && CI.rows ? CI.rows.length : 0} dans la liste de recherche (1 500 au moins)`,
  true
);
if (CI && CI.rows) {
  const want = ['TTE.PA', 'MC.PA', 'SAN.PA', 'ASML.AS', 'SAP.DE', 'VU.PA'];
  const have = new Set(CI.rows.map((r) => r[0]));
  check(
    want.every((w) => have.has(w)),
    'grandes valeurs présentes (TotalEnergies, LVMH, Sanofi, ASML, SAP, Vusion) : ' +
      (want.filter((w) => !have.has(w)).join(', ') || 'toutes')
  );
  // cotation principale (et non une ligne secondaire de Vienne ou de Francfort) : absentes du filtre Yahoo jusqu'au 23/10/2026
  const homes = {
    'ALV.DE': 'Allianz',
    'SIE.DE': 'Siemens',
    'PUB.PA': 'Publicis',
    'ALO.PA': 'Alstom',
    'KBC.BR': 'KBC',
    'ISP.MI': 'Intesa Sanpaolo',
    'SAN.MC': 'Santander',
    'NOVO-B.CO': 'Novo Nordisk',
    'ASSA-B.ST': 'Assa Abloy',
    'INVE-B.ST': 'Investor',
  };
  // une autre classe d'actions de la même société suffit (Investor A tant que la ligne B n'a pas remplacé la A dans l'univers)
  const clsOf = (t) => String(t).replace(/-[A-Z0-9]{1,2}(?=\.)/, ''),
    haveClass = new Set([...have].map(clsOf));
  const noHome = Object.keys(homes).filter((w) => !have.has(w) && !haveClass.has(clsOf(w)));
  check(
    !noHome.length,
    'cotations principales des grandes sociétés : ' +
      (noHome.length ? 'absentes : ' + noHome.map((w) => homes[w] + ' (' + w + ')').join(', ') : 'toutes présentes'),
    true
  );
  // dossiers suivis très échangés (5 M€ par jour ou plus) dont la cotation manque à la liste des sociétés : jamais classés
  // (une autre classe d'actions de la même société, Atlas Copco A au lieu de B, suffit : la plus échangée la représente)
  const lost = Object.keys(main.inst || {})
    .map((i) => main.inst[i])
    .filter((x) => x && x.ticker && !x.secondary && (x.stats || {}).adv20Eur >= 5e6 && !haveClass.has(clsOf(x.ticker)));
  check(
    !lost.length,
    `dossiers très échangés présents dans la liste des sociétés (classement)` +
      (lost.length
        ? ' : absents ' +
          lost
            .slice(0, 8)
            .map((x) => x.name + ' (' + x.ticker + ')')
            .join(', ') +
          (lost.length > 8 ? '…' : '')
        : ''),
    true
  );
  let bad = 0;
  for (let k = 0; k < (CI.shards || 32); k++) {
    try {
      JSON.parse(fs.readFileSync(path.join(DATA, 'societes', k + '.json'), 'utf8'));
    } catch (e) {
      bad++;
    }
  }
  check(bad === 0, `fiches des sociétés : ${CI.shards || 32} fichiers lisibles`);
  // chaque fichier de cours du catalogue doit contenir des sociétés : un fichier vide réduit le classement sans autre signe
  const thin = [];
  for (let k = 0; k < (CI.shards || 32); k++) {
    try {
      const d = JSON.parse(fs.readFileSync(path.join(DATA, 'societes', k + '.json'), 'utf8'));
      if (Object.keys(d.items || {}).length < 20) thin.push(k);
    } catch (e) {}
  }
  check(
    !thin.length,
    `cours du catalogue : chaque fichier contient des sociétés${thin.length ? ' (vides : ' + thin.join(', ') + ')' : ''}`
  );
}
// 4b. Ventes à découvert (🐻 : exclusion à Paris) et actualité : fichiers présents et récents
const SHS = read('shorts.json'),
  NWS = read('news.json'),
  genOf = (x) => (x && (x.generatedAt || x.generated_at)) || null,
  ageD = (x) => (genOf(x) ? yearsBetween(String(genOf(x)).slice(0, 10), today) * 365 : 99);
check(
  SHS && !SHS.__error && Object.keys(SHS.items || {}).length >= 300 && ageD(SHS) <= 4,
  `ventes à découvert : ${SHS && SHS.items ? Object.keys(SHS.items).length : 0} sociétés, données du ${genOf(SHS) ? String(genOf(SHS)).slice(0, 10) : '?'}`,
  true
);
// « en panne » : fichier illisible, positions de la veille gardées ; « non mis à jour » : fichier lu, mais le régulateur ne publie
// plus (dernière notification trop ancienne) ; dans les deux cas l'exclusion 🐻 de Paris tourne sur des positions anciennes
const ssrc = main.shortsSrc || {},
  ssBad = Object.keys(ssrc).filter((c) => ssrc[c] && ssrc[c].status !== 'ok'),
  ssDown = ssBad.filter((c) => ssrc[c].status !== 'perime'),
  ssOld = ssBad.filter((c) => ssrc[c].status === 'perime');
check(
  Object.keys(ssrc).length >= 5 && !ssBad.length,
  `régulateurs des ventes à découvert : ${Object.keys(ssrc).length - ssBad.length}/${Object.keys(ssrc).length} à jour` +
    (ssDown.length ? ' (en panne : ' + ssDown.map((c) => ssrc[c].name || c).join(', ') + ')' : '') +
    (ssOld.length
      ? ' (non mis à jour par le régulateur : ' +
        ssOld
          .map((c) => {
            const d = ssrc[c].lastNotification;
            return (
              (ssrc[c].name || c) + (d ? ', dernière notification le ' + d.slice(8, 10) + '/' + d.slice(5, 7) : '')
            );
          })
          .join(' ; ') +
        ')'
      : ''),
  true
);
check(
  NWS && !NWS.__error && ageD(NWS) <= 4,
  `actualité des sociétés : données du ${genOf(NWS) ? String(genOf(NWS)).slice(0, 10) : '?'}`,
  true
);

// 5. Secteurs
const sec = read('sectors.json');
check(
  sec && !sec.__error && sec.format === 'euro-signal-sectors' && (sec.groups || []).length >= 20,
  `secteurs : ${sec && sec.groups ? sec.groups.length : 0} groupes classés`
);
if (sec && sec.generatedAt)
  check(
    yearsBetween(sec.generatedAt.slice(0, 10), today) * 365 <= 4,
    `secteurs à jour (${sec.generatedAt.slice(0, 10)})`,
    true
  );

// 5b. Classement principal (tendance + comptes) et sélection du lundi
const RK = main.rank;
check(
  RK && RK.counts && RK.counts.ranked >= 200,
  `classement tendance + comptes : ${RK && RK.counts ? RK.counts.ranked : 0} sociétés classées (200 au moins)`
);
if (RK) {
  check(RK.coFresh, `cours du catalogue à jour pour le classement (${RK.coDate || '?'})`, true);
  check(
    RK.study && RK.study.weeks >= 100,
    `étude de contrôle du classement : ${RK.study ? RK.study.weeks : 0} semaines`,
    true
  );
  const nAccR = (RK.rows || []).filter((r) => !r.out.length && r.acc && r.acc !== 'na').length;
  check(
    nAccR >= 0.5 * (RK.counts.ranked || 1),
    `comptes lus pour ${nAccR} des ${RK.counts.ranked} sociétés classées (50 % au moins)`,
    true
  );
  // cohérence : note = somme des points, email du lundi PEA seulement et dans les règles du bouton 🎯
  const rowsOk = (RK.rows || []).filter((r) => !r.out.length);
  const badSum = rowsOk.filter(
    (r) =>
      r.note !==
      Math.max(
        0,
        Math.min(
          100,
          Object.values(r.parts || {}).reduce((a, b) => a + b, 0)
        )
      )
  ).length;
  check(badSum === 0, `classement : note égale à la somme des points (${badSum} écart)`);
  const selRows = ((RK.selection && RK.selection.items) || [])
    .map((x) => (RK.rows || []).find((r) => r.key === x.key))
    .filter(Boolean);
  check(
    selRows.every((r) => r.pea !== false && r.acc === 'good' && (r.sc === 'strong' || r.sc === 'mid') && r.mom <= 200),
    `sélection du lundi dans les règles (PEA, comptes solides, pente, hausse ≤ +200 %) : ${selRows.map((r) => r.name).join(', ') || 'aucune'}`
  );
  check(
    RK.rows.every((r) => r.note >= 0 && r.note <= 100 && r.name),
    'notes du classement entre 0 et 100, chaque société nommée'
  );
  // garde-fous des données Yahoo : devises sans taux de change, cours figés, variations d'un jour à vérifier
  const fxm = main.fx || {},
    noFx = [...new Set((RK.rows || []).map((r) => r.cur).filter((c) => c && c !== 'EUR' && !(fxm[c] > 0)))];
  check(
    !noFx.length,
    `taux de change disponibles pour toutes les devises du classement${noFx.length ? ' (manquent : ' + noFx.join(', ') + ')' : ''}`
  );
  const stale = (RK.rows || []).filter((r) => (r.out || []).some((t) => /cours figé/.test(t))).length,
    djn = (RK.rows || []).filter((r) => r.dj != null).length;
  check(stale <= 20, `cours figés écartés : ${stale}`, true);
  check(
    djn <= 15,
    `variations de plus de 40 % sur la dernière séance (à vérifier, jamais proposées par 🎯) : ${djn}`,
    true
  );
}

// 5b bis. Double calcul (euro_signal/twin_check.py) : le classement et la sélection refaits à part, en Python, sur les mêmes cours
const TW = read('diagnostics/twin.json');
if (!TW || TW.__error)
  warn('double calcul : pas de rapport ce soir (diagnostics/twin.json) : classement non recalculé à part');
else if (TW.error) warn(`double calcul impossible ce soir : ${TW.error}`);
else if (TW.engineAt !== main.generatedAt)
  warn(
    `double calcul fait sur un autre calcul (${TW.engineAt || '?'}) que celui de ce soir (${main.generatedAt || '?'})`
  );
else {
  const names = (l) => (l && l.length ? l.join(', ') : 'aucune');
  check(
    TW.selection && TW.selection.same,
    TW.selection && TW.selection.same
      ? `double calcul : même sélection des 5 (${names(TW.selection.engine)})`
      : `double calcul : la sélection des 5 diffère (moteur : ${names(TW.selection && TW.selection.engine)} ; recalcul à part : ${names(TW.selection && TW.selection.twin)}), à vérifier avant d'acheter`
  );
  check(
    TW.pick10 && TW.pick10.same,
    TW.pick10 && TW.pick10.same
      ? 'double calcul : mêmes 10 🎯'
      : `double calcul : les 10 🎯 diffèrent (moteur : ${names(TW.pick10 && TW.pick10.engine)} ; recalcul à part : ${names(TW.pick10 && TW.pick10.twin)})`,
    true
  );
  const val = (v) =>
    v == null
      ? 'rien'
      : typeof v === 'number'
        ? String(v).replace('.', ',')
        : typeof v === 'object'
          ? JSON.stringify(v)
          : String(v);
  const ex = (TW.examples || [])
    .slice(0, 3)
    .map((e) => `${e.name}, ${e.label || e.field} : ${val(e.engine)} pour le moteur, ${val(e.twin)} recalculé`)
    .join(' ; ');
  check(
    !TW.diffs,
    TW.diffs
      ? `double calcul : ${TW.diffs} écart(s) sur ${TW.rows} sociétés (${Object.entries(TW.byLabel || TW.byField || {})
          .map(([k, v]) => k + ' : ' + v)
          .join(', ')}), par exemple ${ex}`
      : `double calcul : ${TW.rows} sociétés recalculées à part, mêmes chiffres (hausse sur 12 mois, plus haut, tendance, pente, volumes, bond, volatilité, points, note, place)`,
    true
  );
  if ((TW.gaps || []).length)
    warn(
      `cours hebdomadaires incomplets sur l'année pour ${TW.gaps.join(', ')} (sélection) : hausse sur 12 mois à vérifier`
    );
}

// 5c. Lien avec Yahoo Finance : titres demandés, reçus, récupérés en 2e passe, repris de la veille (scrapers/yahoo.py)
const YH = read('diagnostics/yahoo.json'),
  YM = {};
// part de titres manquants comparée au calcul précédent : les émetteurs sans cotation Yahoo manquent chaque soir (part stable),
// seule une hausse est une alerte (sinon l'email de contrôle partait chaque soir pour le même constat)
const ymPrev = (() => {
  try {
    const h = JSON.parse(fs.readFileSync(path.join(DATA, 'diagnostics', 'coverage-history.json'), 'utf8'));
    return (Array.isArray(h) ? h.filter((x) => x && x.ym) : []).slice(-1)[0] || null;
  } catch (e) {
    return null;
  }
})();
if (YH && YH.sections) {
  Object.keys(YH.sections).forEach((k) => {
    const s = YH.sections[k],
      req = s.requested || 0,
      miss = s.missing || 0,
      pctMiss = req ? miss / req : 0;
    if (!req && !s.carried) return;
    YM[k] = +pctMiss.toFixed(4);
    check(
      pctMiss <= 0.3,
      `Yahoo (${k}) : ${req - miss}/${req} reçus, ${s.recovered || 0} récupérés en 2e passe, ${s.carried || 0} repris de la veille, ${s.errors || 0} erreurs passagères`,
      pctMiss <= 0.3 ? undefined : false
    );
    const was = ymPrev && ymPrev.ym[k] != null ? ymPrev.ym[k] : null,
      worse = was == null ? pctMiss > 0.15 : pctMiss - was > 0.02;
    if (pctMiss > 0.05 && pctMiss <= 0.3 && worse)
      warn(
        `Yahoo (${k}) : ${Math.round(pctMiss * 100)} % des titres manquants ce soir` +
          (was != null ? ` (${Math.round(was * 100)} % au calcul précédent)` : '')
      );
  });
} else warn('Yahoo : compteurs du soir absents (diagnostics/yahoo.json)');

// 5d. Cours de secours (scrapers/backup_prices.py) : clôtures prises chez Euronext et Nasdaq Nordic quand Yahoo ne les a pas
const BK = read('diagnostics/backup.json');
if (BK && !BK.__error && BK.date === today) {
  const c = BK.catalogue || {},
    p = BK.prices || {},
    mk = Object.entries(c.byMarket || {})
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => k + ' ' + v)
      .join(', ');
  const left = (c.needed || 0) - (c.filled || 0);
  if (BK.euronext && BK.euronext.error) {
    // Euronext muet : séance prise dans le calendrier, secours nordique quand même (21/10/2026) ; reste-t-il des trous ?
    const m =
      `cours de secours : liste Euronext injoignable (${BK.euronext.error}), séance du ${BK.session || '?'}` +
      (BK.sessionSource === 'calendrier' ? " d'après le calendrier" : '') +
      ` ; ${c.filled || 0} fiches complétées par Nasdaq Nordic sur ${c.needed || 0} sans clôture Yahoo`;
    if (left >= 200) ko(m);
    else if (left > 0) warn(m);
    else ok(m);
  } else
    ok(
      `cours de secours (séance du ${BK.session || '?'}) : ${c.filled || 0} fiches complétées sur ${c.needed || 0} sans clôture Yahoo` +
        (mk ? ` (${mk})` : '') +
        `, ${p.filled || 0} cours Euro Signal complétés, ${(c.rejected || 0) + (p.rejected || 0)} clôtures écartées`
    );
} else warn('cours de secours : pas de compteurs ce soir (diagnostics/backup.json)');

// 5e. Trous : chaque étape a-t-elle produit ses données ce soir, chaque place a-t-elle sa dernière clôture ? (19/10/2026 : tous
// les contrôles étaient verts alors que 97 % des fiches n'avaient pas la clôture du jour : ils vérifiaient les dates, pas les cours)
const PLACE = {
    PA: 'Paris',
    AS: 'Amsterdam',
    BR: 'Bruxelles',
    MI: 'Milan',
    LS: 'Lisbonne',
    IR: 'Dublin',
    OL: 'Oslo',
    ST: 'Stockholm',
    HE: 'Helsinki',
    CO: 'Copenhague',
    DE: 'Francfort',
    MC: 'Madrid',
    VI: 'Vienne',
    SW: 'Zurich',
    L: 'Londres',
  },
  dm = (d) => (d ? d.slice(8, 10) + '/' + d.slice(5, 7) : '?'),
  bdays = (a, b) => {
    let n = 0;
    for (let t = Date.parse(a + 'T12:00:00Z') + 864e5; t <= Date.parse(b + 'T12:00:00Z'); t += 864e5) {
      const w = new Date(t).getUTCDay();
      if (w && w < 6) n++;
    }
    return n;
  };
if (BK && !BK.__error && BK.date === today && BK.complete && BK.complete.catalogue) {
  const C = BK.complete;
  [
    ['catalogue', 'liquid', 'sociétés liquides des fiches'],
    ['prices', 'n', 'dossiers Euro Signal'],
  ].forEach(([kind, tot, label]) => {
    const o = C[kind] || {},
      big = Object.keys(o)
        .filter((k) => o[k][tot] >= 10)
        .sort((a, b) => o[b][tot] - o[a][tot]),
      bad = big.filter((k) => o[k].ok < 0.9 * o[k][tot]);
    if (!big.length) return; // rien à contrôler (fichier absent : signalé par le contrôle des étapes ci-dessous)
    if (!bad.length)
      ok(
        `dernière clôture présente partout (${label} : ${big.map((k) => k + ' ' + o[k].ok + '/' + o[k][tot]).join(', ')})`
      );
    else if (bad.length >= 4)
      // panne générale (Yahoo, calcul trop tardif) : une seule ligne, lisible dans l'email
      warn(
        `clôture du ${dm(o[bad[0]].expected)} manquante dans ${bad.length} places (${label} sans la clôture / total) : ` +
          bad.map((k) => (PLACE[k] || k) + ' ' + (o[k][tot] - o[k].ok) + '/' + o[k][tot]).join(', ')
      );
    else
      bad.forEach((k) =>
        warn(
          `clôture du ${dm(o[k].expected)} manquante à ${PLACE[k] || k} : ${o[k][tot] - o[k].ok} ${label} sur ${o[k][tot]}` +
            ((o[k].missing || []).length ? ` (par exemple ${o[k].missing.slice(0, 3).join(', ')})` : '')
        )
      );
  });
  if (!C.calendar)
    warn(
      'calendriers des bourses indisponibles (exchange_calendars) : un jour férié peut passer pour une clôture manquante'
    );
  const cr = BK.corrections || {},
    ex = [...((cr.catalogue || {}).examples || []), ...((cr.prices || {}).examples || [])],
    nc = ((cr.catalogue || {}).corrected || 0) + ((cr.prices || {}).corrected || 0);
  if (nc)
    ok(
      `clôtures Yahoo aberrantes remplacées par la clôture officielle de la bourse : ${nc} (` +
        ex
          .slice(0, 4)
          .map((e) => e[0] + ' ' + e[1] + ' → ' + e[2])
          .join(', ') +
        ')'
    );
  // indice européen : tendance du marché, force relative et alerte de krach du momentum ; repli muet sur le CAC 40 jusqu'au 23/10/2026
  const mk = main.market || {},
    eP = (C.catalogue.PA || {}).expected;
  if (eP)
    check(
      mk.ticker === '^STOXX' && mk.lastDate >= eP,
      mk.lastDate
        ? `indice européen (${mk.ticker === '^STOXX' ? 'STOXX Europe 600' : (mk.ticker || '?') + ' à la place du STOXX Europe 600, indisponible'}) : dernière séance du ${dm(mk.lastDate)}`
        : 'indice européen (STOXX Europe 600) indisponible : tendance du marché et alerte de krach non calculées',
      true
    );
} else if (BK && BK.complete && BK.complete.error) warn(`contrôle des clôtures impossible : ${BK.complete.error}`);
// chaque étape du soir réécrit son fichier : un fichier ancien veut dire une étape en échec (données précédentes gardées)
{
  const hoursAgo = (x) => {
      const g = genOf(x);
      if (!g) return null;
      const t = Date.parse(/(Z|[+-]\d\d:\d\d)$/.test(String(g)) ? g : g + 'Z');
      return isFinite(t) ? (Date.now() - t) / 3600000 : null;
    },
    STEPS = [
      ['latest.json', 'déclarations AMF (étape 1)'],
      ['insiders-eu.json', 'déclarations FSMA, AFM et FI (étape 2)'],
      ['shorts.json', 'ventes à découvert (étape 2c)'],
      ['prices.json', 'cours Euro Signal (étape 3)'],
      ['sectors.json', 'secteurs (étape 3b)'],
      ['societes-index.json', 'fiches sociétés (étape 3b)'],
      ['financials.json', 'comptes annuels (étape 4b)'],
      ['news.json', 'actualité (étape 4c)'],
      ['euro-signal.json', 'calcul Euro Signal (étape 5b)'],
    ],
    old = STEPS.filter(([f]) => {
      const h = hoursAgo(f === 'euro-signal.json' ? main : read(f));
      return h == null || h > 8;
    });
  old.forEach(([f, label]) => {
    const g = genOf(f === 'euro-signal.json' ? main : read(f));
    warn(
      `${label} : rien de nouveau ce soir (${f} ${g ? 'du ' + dm(String(g).slice(0, 10)) : 'absent'}), données précédentes gardées`
    );
  });
  if (!old.length) ok(`chaque étape du soir a produit ses données (${STEPS.length} fichiers de moins de 8 heures)`);
  // fichiers hebdomadaires et mensuels (workflow « Historique », chaque nuit) : leur âge dit si la mise à jour périodique tourne
  const WEEKLY = [
    ['sectors/universe.json', 'univers des secteurs', 8],
    ['sectors/catalog.json', 'catalogue des sociétés cotées', 8],
    ['seasonality.json', 'saisonnalité des indices', 35],
  ];
  WEEKLY.forEach(([f, label, max]) => {
    const h = hoursAgo(read(f));
    check(
      h != null && h <= max * 24,
      `${label} : mis à jour il y a ${h == null ? '?' : Math.floor(h / 24)} jours (${max} au plus)`,
      true
    );
  });
  if (sec && sec.estimatesAt)
    check(
      yearsBetween(String(sec.estimatesAt).slice(0, 10), today) * 365 <= 8,
      `prévisions des analystes : relevé du ${dm(String(sec.estimatesAt).slice(0, 10))} (chaque semaine)`,
      true
    );
  const amf = (main.src || {}).AMF;
  if (amf && amf.coveredTo)
    check(
      bdays(amf.coveredTo, today) <= 3,
      `déclarations AMF publiées jusqu'au ${dm(amf.coveredTo)} (${bdays(amf.coveredTo, today)} jours ouvrés de décalage, 3 au plus)`,
      true
    );
  // registres de déclarations de dirigeants : une collecte en échec ou interrompue (AMF, FSMA, FI) n'avait aucune ligne de contrôle
  // (l'AFM, « partielle » en permanence : export public sans ISIN ni prix, n'est pas signalée chaque soir)
  const src = main.src || {},
    decl = Object.keys(src).filter((n) => src[n] && src[n].kind === 'déclarations'),
    dDown = decl.filter((n) => src[n].status === 'echec'),
    dPart = decl.filter((n) => src[n].status === 'partiel' && n !== 'AFM'),
    why = (n) => n + (src[n].note ? ' : ' + String(src[n].note).slice(0, 120) : '');
  if (decl.length)
    check(
      !dDown.length && !dPart.length,
      `registres de déclarations de dirigeants : ${decl.length - dDown.length}/${decl.length} lus ce soir` +
        (dDown.length ? ' (en panne : ' + dDown.map(why).join(' ; ') + ')' : '') +
        (dPart.length ? ' (partiels : ' + dPart.map(why).join(' ; ') + ')' : ''),
      true
    );
}

// 6. Couverture rubrique par rubrique, comparée au calcul précédent : une baisse brutale (Yahoo qui répond vide, fichier
// abîmé) est signalée le soir même, avant qu'un lecteur ne la découvre
const COV = {};
{
  const ids = I.filter((i) => !main.inst[i].secondary),
    has = (f) => ids.filter(f).length;
  COV['sociétés suivies'] = ids.length;
  COV['cours'] = has((i) => (main.inst[i].stats || {}).lastClose > 0);
  COV['graphiques (cours 1 an)'] =
    detail && detail.prices ? has((i) => detail.prices[i] && (detail.prices[i].rows || []).length > 0) : 0;
  COV['comptes annuels'] = has((i) => main.inst[i].accounts);
  COV['valeur comptable'] = has((i) => main.inst[i].value && main.inst[i].value.bvps != null);
  COV['secteur'] = has((i) => main.inst[i].fund && main.inst[i].fund.sector);
  COV['liquidité'] = has((i) => (main.inst[i].stats || {}).adv20Eur != null);
  COV["plan d'entrée"] = has((i) => main.inst[i].plan);
  // événements Yahoo (étape 4) : statut « ok » même quand Yahoo répond vide ; la baisse se voit ici
  COV['prévisions des analystes'] = has((i) => {
    const f = main.inst[i].forecast;
    return f && (f.eps != null || f.target != null);
  });
  COV['résultats publiés'] = has((i) => ((main.ev || {})[i] || {}).results && main.ev[i].results.length > 0);
  COV['déclarations (3 mois)'] = Object.values(main.tx || {}).reduce((s, l) => s + (l || []).length, 0);
  COV['sources à jour'] = Object.values(main.src || {}).filter((x) => x && x.status === 'ok').length;
  if (CI && CI.rows) COV['catalogue des sociétés cotées'] = CI.rows.length;
  if (RK && RK.counts) {
    COV['classement (sociétés classées)'] = RK.counts.ranked;
    COV['classement (comptes lus)'] = (RK.rows || []).filter((r) => r.acc && r.acc !== 'na').length;
  }
}
// Changement de périmètre voulu : comparaison avec les calculs antérieurs suspendue (17/10/2026 : arrêt d'Insider Screener,
// les sociétés allemandes, espagnoles, italiennes et néerlandaises quittent les dossiers suivis ; nouveau classement principal)
const REBASE = '2026-10-16T22:00'; // premier calcul du soir avec le nouveau périmètre
const HIST = path.join(DATA, 'diagnostics', 'coverage-history.json');
let hist = [];
try {
  hist = JSON.parse(fs.readFileSync(HIST, 'utf8'));
  if (!Array.isArray(hist)) hist = [];
} catch (e) {
  hist = [];
}
const prev = hist.filter((h) => h && h.at && h.at < new Date().toISOString() && h.at >= REBASE).slice(-1)[0] || null;
const delta = {};
Object.keys(COV).forEach((k) => {
  const now = COV[k],
    was = prev && prev.cov ? prev.cov[k] : null;
  delta[k] = [now, was];
  if (was == null || !(was > 0)) return;
  const drop = (was - now) / was;
  // moins de sociétés classées parce que plus de comptes ont été lus (celles en perte ou en détresse sortent alors) : normal
  const kAcc = 'classement (comptes lus)',
    moreAcc = prev.cov[kAcc] != null && COV[kAcc] != null ? COV[kAcc] - prev.cov[kAcc] : 0;
  if (k === 'classement (sociétés classées)' && now < was && moreAcc >= was - now)
    ok(`${k} : ${now} (${now - was} depuis le calcul précédent, expliqué par ${moreAcc} comptes lus de plus)`);
  else if (drop > 0.1 && was - now >= 20)
    ko(`baisse anormale : ${k} ${was} → ${now} (−${Math.round(drop * 100)} %) depuis le calcul précédent`);
  else if (drop > 0.03 && was - now >= 10)
    warn(`baisse : ${k} ${was} → ${now} (−${Math.round(drop * 100)} %) depuis le calcul précédent`);
  else ok(`${k} : ${now}` + (now !== was ? ` (${now > was ? '+' : ''}${now - was} depuis le calcul précédent)` : ''));
});
hist.push({ at: new Date().toISOString(), date: today, cov: COV, ym: YM });
fs.mkdirSync(path.join(DATA, 'diagnostics'), { recursive: true });
fs.writeFileSync(HIST, JSON.stringify(hist.slice(-60)));
globalThis.__COV = { cov: delta, prevAt: prev ? prev.at : null };

finish();

function finish() {
  lines.push('', `${fails} échec(s), ${warns} alerte(s)`);
  const txt = `Contrôle des fichiers du ${today}\n\n` + lines.join('\n') + '\n';
  fs.mkdirSync(path.join(DATA, 'diagnostics'), { recursive: true });
  fs.writeFileSync(path.join(DATA, 'diagnostics', 'check-outputs.txt'), txt);
  // synthèse lisible par la page (Aide → État des données) et par l'email de contrôle
  const bad = lines
    .filter((l) => /^(ÉCHEC|ALERTE)/.test(l))
    .map((l) => l.replace(/^(ÉCHEC|ALERTE)\s+/, (m, k) => (k === 'ÉCHEC' ? '✖ ' : '⚠ ')));
  fs.writeFileSync(
    path.join(DATA, 'diagnostics', 'quality.json'),
    JSON.stringify(
      Object.assign(
        { date: today, at: new Date().toISOString(), fails, warns, issues: bad.filter(Boolean) },
        globalThis.__COV || {}
      )
    )
  );
  console.log(txt);
  process.exit(fails ? 1 : 0);
}
