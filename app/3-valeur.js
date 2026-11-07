/* Euro Signal — interface : valeur comptable et valeur intrinsèque (lecture d'analyste).
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
/* ----- Valeur comptable et valeur intrinsèque (lecture d'analyste, sans poids dans la note) ----- */
var IV_LABEL = {
  riFade: [
    "Revenu résiduel, avantage qui s'efface",
    "Fonds propres + ce que la société gagne au-delà du rendement exigé, cet excédent disparaissant en 10 ans sous l'effet de la concurrence.",
  ],
  riLast: [
    'Revenu résiduel, avantage durable',
    'Fonds propres × rentabilité ÷ rendement exigé : la société garde durablement sa rentabilité actuelle, sans croissance.',
  ],
  nav: [
    'Actif net réévalué (ANR)',
    "Pour une foncière : capitaux propres, les immeubles étant au bilan à leur valeur d'expertise (normes IFRS). C'est la référence du métier ; le résultat, qui comprend les variations de valeur des immeubles, et la trésorerie disponible ne le sont pas.",
  ],
  fcf: [
    'Trésorerie disponible capitalisée, moins les dettes',
    "Trésorerie disponible moyenne ÷ rendement exigé (ce que vaut l'argent réellement dégagé chaque année, sans croissance), moins l'endettement net, qui revient d'abord aux prêteurs.",
  ],
};
function curOf(x) {
  var c = (x && x.currency) || 'EUR';
  return c === 'EUR' ? '€' : c === 'GBp' ? 'p' : c;
}
function ivNum(v) {
  return fmtN(v, v >= 1000 ? 0 : v >= 100 ? 1 : 2);
}
/** Règle de valeur : fourchette de valeur intrinsèque (bande verte), valeur comptable (trait bleu), cours (rond). */
function valueBar(v, cur) {
  var pts = [v.price, v.bvps, v.high, v.tbvps].filter(function (t) {
      return t != null && t > 0;
    }),
    mx = Math.max.apply(null, pts) * 1.12;
  var x = function (t) {
    return Math.max(0, Math.min(100, (t / mx) * 100));
  };
  var h =
    '<div class="vbar" role="img" aria-label="' +
    esc(
      'Cours ' +
        ivNum(v.price) +
        ', valeur comptable ' +
        ivNum(v.bvps) +
        (v.mid != null ? ', valeur intrinsèque ' + ivNum(v.low) + ' à ' + ivNum(v.high) : '')
    ) +
    '"><div class="vb-track">';
  if (v.mid != null)
    h +=
      '<i class="vb-band" style="left:' +
      x(v.low) +
      '%;width:' +
      Math.max(1, x(v.high) - x(v.low)) +
      '%"></i><i class="vb-mid" style="left:' +
      x(v.mid) +
      '%"></i>';
  if (v.tbvps != null && v.tbvps > 0 && v.tbvps < v.bvps * 0.97)
    h += '<i class="vb-tb" style="left:' + x(v.tbvps) + '%"></i>';
  h +=
    '<i class="vb-bv" style="left:' +
    x(v.bvps) +
    '%"></i><b class="vb-px" style="left:' +
    x(v.price) +
    '%"></b></div><div class="vb-ax"><span style="left:0;transform:none">0</span><span style="left:100%;transform:translateX(-100%)">' +
    ivNum(mx) +
    ' ' +
    esc(cur) +
    '</span></div></div>';
  h +=
    '<ul class="vb-leg"><li><b class="k-px"></b>Cours <b>' +
    ivNum(v.price) +
    ' ' +
    esc(cur) +
    '</b></li>' +
    (v.mid != null
      ? v.kind === 'property'
        ? '<li><b class="k-iv"></b>Actif net réévalué <b>' +
          ivNum(v.mid) +
          ' ' +
          esc(cur) +
          '</b> <span class="muted">(référence d\'une foncière)</span></li>'
        : '<li><b class="k-iv"></b>Valeur intrinsèque <b>' +
          ivNum(v.mid) +
          ' ' +
          esc(cur) +
          '</b> <span class="muted">(' +
          (v.high / v.low <= 1.05 ? 'méthodes concordantes' : ivNum(v.low) + ' à ' + ivNum(v.high)) +
          ')</span></li>'
      : '') +
    '<li><b class="k-bv"></b>Valeur comptable <b>' +
    ivNum(v.bvps) +
    ' ' +
    esc(cur) +
    '</b>' +
    (v.tbvps != null
      ? ' <span class="muted">(hors écarts d\'acquisition et incorporels : ' + ivNum(v.tbvps) + ')</span>'
      : '') +
    '</li></ul>';
  return h;
}
function valueSection(i) {
  var x = S.inst[i] || {},
    v = x.value,
    cur = curOf(x);
  if (!v)
    return (
      '<p class="muted">' +
      (x.accounts
        ? "Valeur non calculable : cours ou nombre d'actions manquant."
        : 'Comptes annuels pas encore collectés pour cette société (complétés au fil des soirs).') +
      '</p>'
    );
  var vv = ES.valueView(v) || { tone: 'na', text: '' },
    TI = { good: '🟢', mixed: '🟡', bad: '🔴', na: '⚪' };
  var below = v.mid != null && (v.zone === 'below' || v.marginPct >= 20),
    why = v.stale
      ? 'comptes anciens'
      : v.irregular
        ? 'rentabilité irrégulière'
        : 'rentabilité faible, piège de valeur possible';
  var head =
    vv.tone === 'good'
      ? 'Cours sous la valeur estimée'
      : vv.tone === 'bad'
        ? v.negEquity
          ? 'Fonds propres négatifs'
          : v.lossMaking
            ? 'Société en pertes'
            : 'Cours très au-dessus de la valeur estimée'
        : vv.tone === 'na'
          ? 'Valeur non estimable'
          : below
            ? 'Décote à confirmer (' + why + ')'
            : v.zone === 'above'
              ? 'Cours au-dessus de la valeur estimée'
              : 'Cours proche de la valeur estimée';
  var h =
    '<div class="kidline kid-' +
    esc(vv.tone) +
    '"><p class="kidh">' +
    (TI[vv.tone] || '⚪') +
    ' <b>' +
    esc(head) +
    '</b></p><p>' +
    esc(vv.text) +
    '</p></div>';
  if (v.na || v.negEquity) return h + '<p class="foot">Comptes de l\'exercice ' + esc(v.year) + '.</p>';
  h += valueBar(v, cur);
  var crits = [];
  if (v.mid != null) {
    var ratio = v.price / v.mid;
    var cheap = ES.valueCheap(v);
    crits.push(
      critBox(
        '💎',
        'Marge de sécurité',
        v.marginPct >= 0 ? '+' + v.marginPct + ' %' : '×' + fmtN(ratio, 1),
        cheap ? 'good' : v.marginPct >= 20 ? 'mid' : v.marginPct >= 0 ? 'neu' : ratio > 2 ? 'bad' : 'mid',
        v.marginPct >= 20 && !cheap
          ? 'Décote à confirmer : ' + why
          : v.marginPct >= 30
            ? 'Large décote sur la valeur estimée'
            : v.marginPct >= 20
              ? 'Décote nette'
              : v.marginPct >= 0
                ? 'Cours proche de la valeur estimée'
                : 'Aucune : le cours vaut ' + fmtN(ratio, 1) + ' fois la valeur estimée',
        scaleLine(
          Math.min(ratio, 3),
          0,
          3,
          [
            [0, 0.8, 'good'],
            [0.8, 1.2, 'neu'],
            [1.2, 2, 'mid'],
            [2, 3, 'bad'],
          ],
          [
            [0, '0'],
            [1, '= valeur'],
            [2, '×2'],
            [3, '×3+'],
          ],
          'Cours divisé par la valeur intrinsèque : ' + fmtN(ratio, 2)
        ),
        "Écart entre la valeur intrinsèque centrale et le cours. Benjamin Graham demandait au moins 30 % de marge pour se protéger des erreurs d'estimation."
      )
    );
  }
  crits.push(
    critBox(
      '📘',
      'Cours / valeur comptable',
      fmtN(v.pb, 2) + '×',
      v.pb < 1 ? (v.roe != null && v.roe * 0.01 >= v.r ? 'good' : 'mid') : v.pb <= 3 ? 'neu' : 'mid',
      v.pb < 1
        ? v.roe != null && v.roe * 0.01 >= v.r
          ? "Sous l'actif net et rentable : rare"
          : "Sous l'actif net, mais rentabilité faible"
        : v.pb <= 3
          ? 'Dans la norme'
          : 'Cher par rapport aux fonds propres',
      scaleLine(
        Math.min(v.pb, 5),
        0,
        5,
        [
          [0, 1, 'good'],
          [1, 3, 'neu'],
          [3, 5, 'mid'],
        ],
        [
          [0, '0'],
          [1, '1'],
          [3, '3'],
          [5, '5+'],
        ],
        'Cours sur valeur comptable ' + fmtN(v.pb, 2)
      ),
      "Combien le marché paie chaque euro de fonds propres (actif − dettes). Sous 1, on achète l'entreprise moins cher que son bilan ; c'est justifié quand elle rapporte moins que ce qu'exige un actionnaire."
    )
  );
  if (v.roe != null)
    crits.push(
      critBox(
        '🧮',
        'Rentabilité des fonds propres',
        fmtN(v.roe, 1) + ' %',
        v.roe >= v.r * 100 + 5 ? 'good' : v.roe >= v.r * 100 ? 'neu' : v.roe > 0 ? 'mid' : 'bad',
        (v.roe >= v.r * 100 ? 'Au-dessus' : 'En dessous') + ' du rendement exigé (' + fmtN(v.r * 100, 1) + ' %)',
        scaleLine(
          Math.max(-10, Math.min(v.roe, 40)),
          -10,
          40,
          [
            [-10, 0, 'bad'],
            [0, v.r * 100, 'mid'],
            [v.r * 100, 40, 'good'],
          ],
          [
            [0, '0'],
            [v.r * 100, fmtN(v.r * 100, 1)],
            [40, '40+'],
          ],
          'Rentabilité moyenne des fonds propres ' + fmtN(v.roe, 1) + ' %'
        ),
        'Résultat net ÷ fonds propres' +
          (v.nYears >= 3
            ? ', la plus basse de la médiane de ' +
              v.nYears +
              ' exercices et de la moyenne des deux derniers (prudence)'
            : ', moyenne de ' + v.nYears + ' exercice' + (v.nYears > 1 ? 's' : '')) +
          ". C'est le moteur de la valeur : une entreprise qui rapporte plus que le rendement exigé vaut plus que ses fonds propres, et moins dans le cas contraire."
      )
    );
  if (v.impliedG != null && v.zone !== 'below') {
    var g = v.impliedG,
      rp = v.r * 100;
    crits.push(
      critBox(
        '🔭',
        'Croissance que suppose le cours',
        (g > 0 ? '+' : '') + fmtN(g, 1) + ' %/an',
        g <= 2.5 ? 'good' : g < 6 ? 'mid' : 'bad',
        g >= rp - 0.5
          ? 'Aucun calcul fondé sur les comptes ne le justifie'
          : g <= 0
            ? 'Le marché anticipe un recul'
            : g <= 2.5
              ? 'Hypothèse modeste'
              : g < 6
                ? 'Hypothèse soutenue'
                : 'Hypothèse exigeante',
        scaleLine(
          Math.max(-4, Math.min(g, 10)),
          -4,
          10,
          [
            [-4, 2.5, 'good'],
            [2.5, 6, 'mid'],
            [6, 10, 'bad'],
          ],
          [
            [0, '0'],
            [2.5, '2,5'],
            [6, '6'],
            [10, '10+'],
          ],
          'Croissance implicite ' + fmtN(g, 1) + ' % par an'
        ),
        "Croissance annuelle des résultats, pour toujours, qui justifierait le cours actuel. Repère : l'économie européenne croît d'environ 3 % par an en valeur ; au-delà de 6 % durablement, peu d'entreprises y parviennent."
      )
    );
  }
  h += '<div class="crits">' + crits.join('') + '</div>';
  if (v.methods && v.methods.length)
    h +=
      '<details class="xpi"><summary>ⓘ Les ' +
      v.methods.length +
      ' estimations</summary><div class="tablewrap"><table class="grid acct"><thead><tr><th>Méthode</th><th class="num">Par action</th><th class="num">Écart au cours</th></tr></thead><tbody>' +
      v.methods
        .map(function (m) {
          var L = IV_LABEL[m.k] || [m.k, ''],
            d = (m.v / v.price - 1) * 100;
          // explication sur toute la largeur, sous la méthode (lisible sur téléphone)
          return (
            '<tr class="ivm"><th>' +
            esc(L[0]) +
            '</th><td class="num">' +
            ivNum(m.v) +
            ' ' +
            esc(cur) +
            '</td><td class="num ' +
            (d >= 0 ? 'pos' : 'neg') +
            '">' +
            pct(d) +
            '</td></tr><tr class="ivd"><td colspan="3"><small>' +
            esc(L[1]) +
            '</small></td></tr>'
          );
        })
        .join('') +
      '</tbody></table></div></details>';
  var notes = (v.notes || []).slice(),
    KIND = {
      fin: "Banque ou assurance : la valeur comptable (actif net) est la référence du secteur ; la trésorerie disponible n'a pas de sens pour ces bilans.",
      property:
        "Foncière : les immeubles sont au bilan à leur valeur d'expertise (normes IFRS), la valeur comptable approche donc l'actif net réévalué (ANR).",
      holding:
        "Holding ou société d'investissement : les participations peuvent être au bilan sous leur valeur de marché ; une décote sur l'actif net réévalué est habituelle.",
    };
  if (KIND[v.kind]) notes.unshift(KIND[v.kind]);
  if (v.intangPct != null && v.intangPct >= 50)
    notes.push(
      v.intangPct +
        " % des fonds propres sont des écarts d'acquisition et incorporels (rachats de sociétés, marques) : la valeur tangible est bien plus faible."
    );
  if (v.fx) notes.push('Comptes en ' + v.fx.split('→')[0] + ', convertis au taux du jour.');
  if (notes.length)
    h +=
      '<ul class="plain small">' +
      notes
        .map(function (t) {
          return '<li>' + esc(t.charAt(0).toUpperCase() + t.slice(1)) + (/[.!]$/.test(t) ? '' : '.') + '</li>';
        })
        .join('') +
      '</ul>';
  h +=
    '<details class="fsscale"><summary>Comment c\'est calculé ?</summary>' +
    '<p><b>Valeur comptable</b> : capitaux propres part du groupe au ' +
    esc(ES.frDate(v.date)) +
    " ÷ nombre d'actions. C'est ce qui resterait aux actionnaires si l'on vendait tous les actifs à leur valeur au bilan et payait toutes les dettes.</p>" +
    "<p><b>Valeur intrinsèque</b> : ce que vaut l'entreprise d'après ce qu'elle rapporte. Deux approches d'analyste, <b>sans aucune croissance supposée</b> (estimation prudente) : le <b>revenu résiduel</b> (modèle d'Edwards-Bell-Ohlson, fondé sur les comptes : valeur comptable + valeur de ce que la société gagne au-delà du rendement exigé) et la <b>trésorerie disponible capitalisée, moins l'endettement net</b> (dettes financières et loyers IFRS 16, moins la trésorerie : l'argent dégagé revient d'abord aux prêteurs). La valeur centrale est la médiane des estimations.</p>" +
    "<p><b>Prudence</b> : rentabilité retenue = la plus basse de la médiane des exercices disponibles et de la moyenne des deux derniers ; trésorerie disponible = la plus basse de la moyenne de tous les exercices et de celle des deux derniers (un exercice exceptionnel ne gonfle pas la valeur, une dégradation récente compte). Une décote n'est affichée en vert que si la société rapporte au moins le rendement exigé : sinon, elle peut durer (piège de valeur).</p>" +
    '<p><b>Rendement exigé</b> : ' +
    fmtN(v.r * 100, 1) +
    " % par an pour cette société (taux sans risque européen d'environ 3 % + prime de risque des actions + prime pour les plus petites valeurs : 8,5 % au-delà de 5 Md€, 9,5 % de 500 M€ à 5 Md€, 11 % en dessous).</p>" +
    '<p class="foot">Limites : comptes annuels publiés (jusqu\'à 4 mois de retard), rentabilité ramenée à 35 % au plus, croissance ignorée (les sociétés de croissance paraissent donc chères : regarder la « croissance que suppose le cours »). Aucun poids dans la note avant la revue de janvier ; mesuré en observation à chaque achat de dirigeant.</p></details>';
  return h;
}
/** 📊 Santé des comptes (pli 🔬 Analyse) : verdict et conseil, F-score détaillé, contrôles anti-piège. Les chiffres
 *  (chiffre d'affaires, marges, trésorerie…) sont dans « La société en bref » : ils ne sont pas répétés ici. */
function accHealth(i) {
  var a = S.inst[i] && S.inst[i].accounts;
  if (!a) return '';
  if (a.summary && !hasDetail(i))
    return '<p class="muted">' + esc(a.verdict ? a.verdict.text : '') + ' — chargement du détail…</p>';
  var TI = { good: '🟢', mixed: '🟡', bad: '🔴', na: '⚪' },
    p = a.plain,
    v = a.verdict,
    h = '';
  if (p && p.label)
    h +=
      '<p class="accv acc-' +
      esc(p.tone || 'na') +
      '">' +
      (TI[p.tone] || '⚪') +
      ' <b>' +
      esc(p.label) +
      '</b>' +
      (p.advice ? ' — ' + esc(p.advice) : '') +
      '</p>';
  else if (v) h += '<p class="accv acc-' + esc(v.key) + '">' + (TI[v.key] || '⚪') + ' <b>' + esc(v.text) + '</b></p>';
  var fs = a.fscore;
  if (fs && !fs.na)
    h +=
      '<h4 class="mt">F-score de Piotroski : ' +
      fsPill(fs.f9) +
      ' <span class="muted">exercice ' +
      esc(fs.year) +
      ' comparé au précédent' +
      (fs.avail < 9 ? ', ' + fs.score + ' critères remplis sur ' + fs.avail + ' calculables' : '') +
      '</span></h4>' +
      fscoreEvolution(a) +
      fscoreCriteria(fs);
  else if (fs) h += '<p class="foot">F-score : ' + esc(fs.reason) + '.</p>';
  return h + riskScores(a) + fscoreScale();
}
function accountsSection(i) {
  var a = S.inst[i] && S.inst[i].accounts;
  var h = '<section class="card accounts"><h3>📊 Analyse des comptes</h3>';
  h += kidLine(a);
  if (a && a.summary && !hasDetail(S.sel))
    return h + '<p class="muted">' + esc(a.verdict ? a.verdict.text : '') + ' — chargement du détail…</p></section>';
  if (!a || !a.years || !a.years.length)
    return (
      h +
      '<p class="muted">Comptes annuels pas encore collectés pour cette société (complétés au fil des soirs, en commençant par les sociétés où un dirigeant a acheté).</p>' +
      forecastBlock(i) +
      '</section>'
    );
  var v = a.verdict || { key: 'na', text: 'Comptes insuffisants pour conclure', good: [], bad: [] };
  if (!(a.plain && a.plain.text))
    h +=
      '<p class="accv acc-' +
      esc(v.key) +
      '">' +
      ({ good: '🟢', mixed: '🟡', bad: '🔴', na: '⚪' }[v.key] || '⚪') +
      ' <b>' +
      esc(v.text) +
      '</b>' +
      (v.good.length || v.bad.length ? ' — ' + esc(v.good.concat(v.bad).join(' ; ')) : '') +
      '</p>';
  var Y = a.years,
    f = Y[0],
    l = Y[Y.length - 1],
    R = Y.slice().reverse(),
    cur = a.currency ? ' (' + esc(a.currency) + ')' : ''; // exercice le plus récent en premier (visible sur téléphone)
  var row = function (label, key, fmt, hib) {
    if (
      Y.every(function (y) {
        return y[key] == null || !isFinite(y[key]);
      })
    )
      return '';
    return (
      '<tr><th>' +
      label +
      '</th><td class="num">' +
      (Y.length > 1 ? arrow(f[key], l[key], hib) : '') +
      '</td>' +
      R.map(function (y) {
        return '<td class="num">' + fmt(y[key]) + '</td>';
      }).join('') +
      '</tr>'
    );
  };
  var p1 = function (x) {
    return x == null || !isFinite(x)
      ? 'n.d.'
      : Math.abs(x) > 100
        ? '<span title="Valeur extrême (chiffre d\'affaires ou fonds propres très faibles)">n.s.</span>'
        : fmtN(x, 1) + ' %';
  };
  h +=
    '<div class="tablewrap"><table class="grid acct"><thead><tr><th>Exercice</th><th class="num" title="Premier exercice comparé au dernier">Tendance</th>' +
    R.map(function (y) {
      return '<th class="num">' + esc(y.year) + '</th>';
    }).join('') +
    '</tr></thead><tbody>' +
    row("Chiffre d'affaires" + cur, 'revenue', big, true) +
    row('Marge opérationnelle', 'opMargin', p1, true) +
    row('Résultat net' + cur, 'netIncome', big, true) +
    row('Trésorerie disponible (FCF)' + cur, 'fcf', big, true) +
    row(
      'Dette nette / EBITDA (comptes publiés, hors loyers)',
      'netDebtEbitda',
      function (x) {
        return x == null || !isFinite(x) ? 'n.d.' : x < 0 ? 'trésorerie nette' : fmtN(x, 1) + '×';
      },
      false
    ) +
    row('Rentabilité des fonds propres', 'roe', p1, true) +
    '</tbody></table></div>';
  h += forecastBlock(i);
  var fs = a.fscore;
  if (fs && !fs.na) {
    h +=
      '<h4 class="mt">F-score de Piotroski : ' +
      fsPill(fs.f9) +
      ' <span class="muted">exercice ' +
      esc(fs.year) +
      ' comparé au précédent' +
      (fs.avail < 9 ? ', ' + fs.score + ' critères remplis sur ' + fs.avail + ' calculables' : '') +
      '</span></h4>';
    h += fscoreEvolution(a);
    h += fscoreCriteria(fs);
  } else if (fs) h += '<p class="foot">F-score : ' + esc(fs.reason) + '.</p>';
  h += riskScores(a);
  h += fscoreScale();
  h +=
    '<p class="foot">Source : comptes annuels publiés (Yahoo Finance), ' +
    Y.length +
    ' exercice' +
    (Y.length > 1 ? 's' : '') +
    '.</p>';
  return h + '</section>';
}
function posChip(p) {
  return (
    '<span class="chip pos-' +
    p.key +
    '" title="Rang par chiffre d\'affaires dans son industrie' +
    (p.industry ? ' (' + esc(p.industry) + ')' : '') +
    ' parmi les ' +
    p.of +
    ' sociétés européennes suivies">' +
    esc(p.label) +
    ' · n° ' +
    p.rank +
    '/' +
    p.of +
    '</span>'
  );
}
function histOf(note) {
  var ref = S.snapshot && S.snapshot.selection && S.snapshot.selection.reference;
  return ref ? ES.historicRank(note, ref.histNotes) : null;
}
function histTxt(sc) {
  if (!sc.buys.length) return '';
  var r = histOf(ES.note(sc.total, S.cfg));
  return r && r.key !== 'na' ? '<br><span class="hist h-' + r.key + '">' + r.icon + ' ' + esc(r.label) + '</span>' : '';
}
/* Sélection de la semaine : la liste courte calculée chaque soir (même règles que l'email du lundi) */
function secOf(x) {
  return ES.sectorFr(x.sector || (x.fund && x.fund.sector));
}
/** Scores clés en une ligne, pour une lecture rapide d'un dossier (couleur + texte, jamais la couleur seule). */
function quickScores(isin, x) {
  // Mêmes critères, dans le même ordre, pour chaque dossier : « n.d. » quand la donnée manque, pour comparer d'un coup d'œil
  var i = S.inst[isin] || {},
    a = i.accounts || {},
    out = [],
    q = function (tone, txt, tip) {
      out.push('<span class="qs qs-' + tone + '"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + txt + '</span>');
    };
  var fs = a.fscore && !a.fscore.na ? a.fscore.f9 : null,
    tr = a.fscoreTrend ? { up: ' ↗', down: ' ↘', flat: '' }[a.fscoreTrend.key] || '' : '';
  if (fs != null)
    q(
      fs >= S.cfg.accounts.fscoreGood ? 'good' : fs <= S.cfg.accounts.fscoreBad ? 'bad' : 'mid',
      '📊 F-score ' + fs + '/9' + tr,
      'Santé des comptes (Piotroski), flèche : évolution sur les exercices disponibles'
    );
  else q('na', '📊 F-score n.d.', (a.fscore && a.fscore.reason) || 'Comptes non disponibles');
  // Contrôles anti-piège réunis : risque de défaillance (Altman) et qualité des comptes (Beneish)
  var az = a.altman && !a.altman.na && a.altman.zone ? a.altman : null,
    bm = a.beneish && !a.beneish.na && a.beneish.m != null ? a.beneish : null;
  if (az || bm) {
    var bad = (az && az.zone === 'distress') || (bm && bm.flag),
      mid = az && az.zone === 'grey';
    q(
      bad ? 'bad' : mid ? 'mid' : 'good',
      '🛡️ bilan ' + (bad ? 'à risque' : mid ? 'à surveiller' : 'sain'),
      'Altman ' +
        (az
          ? fmtN(az.z, 1) + ' (' + { safe: 'zone sûre', grey: 'zone grise', distress: 'détresse' }[az.zone] + ')'
          : 'n.d.') +
        ' · Beneish ' +
        (bm ? fmtN(bm.m, 2) + (bm.flag ? ' (alerte)' : ' (normal)') : 'n.d.')
    );
  } else q('na', '🛡️ bilan n.d.', 'Postes comptables manquants dans la source');
  var d = x && x.discountPct != null ? x.discountPct : null;
  if (d != null)
    q(
      d >= S.cfg.weights.insiders.discountMediumPct ? 'good' : 'mid',
      '🏷️ décote ' + Math.round(d) + ' %',
      'Prix payé par le dirigeant sous le plus haut des 52 semaines'
    );
  else q('na', '🏷️ décote n.d.');
  var lq = lvLine(isin);
  if (lq && (lq.s1 || lq.r1))
    q(
      lq.s1 && lq.s1.distPct >= -3 && lq.s1.kind !== 'low52'
        ? 'good'
        : (lq.r1 && lq.r1.distPct <= 3) || (lq.s1 && lq.s1.kind === 'low52' && lq.s1.distPct >= -3)
          ? 'mid'
          : 'info',
      '📐 ' +
        (lq.s1 ? 'support ' + pct(lq.s1.distPct) : 'support n.d.') +
        ' · ' +
        (lq.r1 ? 'résistance ' + pct(lq.r1.distPct) : 'au plus haut'),
      'Supports et résistances sur un an (sommets et creux répétés) : écart avec le cours actuel'
    );
  else q('na', '📐 niveaux n.d.', 'Historique de cours insuffisant');
  var c = S.computed[isin];
  if (c) {
    var z = ES.positionSize(i, c.score, (x && x.advice) || adviceOf(isin), S.cfg);
    q(
      z.pct ? 'info' : 'na',
      '⚖️ taille ' + (z.pct ? fmtN(z.pct, z.pct % 1 ? 1 : 0) + ' %' : 'aucune'),
      z.pct
        ? 'Taille suggérée : part du portefeuille au plus, seuil de protection −' + z.stopPct + ' %'
        : z.reasons.join(', ')
    );
  }
  var g = dgInfo(isin);
  if (g && !g.none) q(g.recent ? 'good' : 'mid', '👔 DG/DAF il y a ' + g.days + ' j', 'Dernier achat du DG ou du DAF');
  else q('na', '👔 DG/DAF aucun');
  return '<div class="qsr">' + out.join('') + '</div>';
}
function selectionCard() {
  var sel = S.snapshot && S.snapshot.selection;
  if (!sel || !sel.items) return '';
  var rule =
    (S.cfg.selection.requireCeoCfo ? 'Le DG ou le DAF' : 'Un dirigeant') +
    ' a acheté au moins ' +
    ES.fmtEur(S.cfg.insiders.minBuyerEur) +
    ' ces ' +
    ((S.cfg.selection || {}).recentDays || 30) +
    ' jours ; société solide' +
    (S.cfg.selection.peaOnly !== false ? ', éligible au PEA' : '') +
    '.';
  if (!sel.items.length)
    return (
      '<section class="card selc"><h3>Sélection de la semaine</h3><p class="muted">Aucune société ne remplit tous les critères en ce moment. ' +
      esc(rule) +
      '</p></section>'
    );
  var v = sel.verdict;
  return (
    '<section class="card selc"><h3>📧 Sélection de la semaine <span class="chip neutral">' +
    esc(sel.week) +
    '</span></h3>' +
    '<p class="selrule">⏱ ' +
    esc(rule) +
    '</p>' +
    (v && v.text ? '<p class="verdict v-' + esc(v.key) + '">' + (v.icon || '') + ' ' + esc(v.text) + '</p>' : '') +
    '<ol class="sel">' +
    sel.items
      .map(function (x) {
        var adv = x.advice || adviceOf(x.isin) || { why: [], signals: [] },
          sm = ES.adviceSummary(adv),
          st = ES.stars(x.score, S.cfg, x.hist && x.hist.key);
        var w = [sm.pros[0] || null, sm.cons[0] ? sm.cons[0].split(' : ')[0] : null].filter(Boolean);
        return (
          '<li class="rowlink" data-a="open" data-i="' +
          esc(x.isin) +
          '" tabindex="0"><b>' +
          flag(x.country) +
          esc(x.name) +
          '</b>' +
          (x.isNew ? ' <span class="chip newc">Nouveau</span>' : '') +
          '<span class="selnote"><span class="stars s' +
          st.n +
          '">' +
          starInner(st) +
          '</span> <b>' +
          ES.note(x.score, S.cfg) +
          '</b><span class="muted">/100</span> ' +
          advBadge(adv) +
          '</span><small>' +
          esc(w.join(' · ')) +
          '</small>' +
          (S.inst[x.isin] ? feuxHtml(x.isin) : quickScores(x.isin, x)) +
          '</li>'
        );
      })
      .join('') +
    '</ol><p class="foot">À étudier, pas un ordre d\'achat.</p></section>'
  );
}
/** Figure de tendance et verdict du plan d'entrée d'une société (calculés chaque soir avec le plan). */
var PLANS = [
  ['buyNow', "✅ Zone d'entrée"],
  ['waitSupport', '⏳ Attendre un rebond sur support'],
  ['waitBreakout', '⏳ Attendre une cassure'],
  ['avoid', '⛔ Ne pas acheter'],
];
/** Plan d'entrée d'une société : calculé le soir ; à défaut, recalculé ici à partir des cours (fichier détaillé chargé). */
/** Figure d'un plan calculé la veille, reclassée avec les règles du moteur de la page (une seule fois). */
function reclassPlan(p) {
  if (p && !p.rc && p.wedge && p.wedge.upper) {
    p.wedge = ES.reclassWedge(p.wedge, p.last);
    p.rc = 1;
  }
  return p;
}
function planFor(i) {
  var x = S.inst[i];
  if (!x) return null;
  if (x.plan && x.plan.verdict) return reclassPlan(x.plan);
  S.planCache = S.planCache || {};
  if (i in S.planCache) return S.planCache[i];
  var p = hasDetail(i) && S.prices[i],
    out = null;
  if (p && p.rows && p.rows.length >= 120) {
    try {
      out = ES.entryPlan(ES.adjustedSeries(ES.normalizeSeries(p.rows), (S.ev[i] && S.ev[i].splits) || []).slice(-260), {
        levels: x.levels || undefined,
      });
    } catch (e) {
      out = null;
    }
  }
  if (hasDetail(i)) S.planCache[i] = out;
  return out;
}
function figOf(i) {
  var p = planFor(i);
  return p ? ES.figureKey(p.wedge) : null;
}
/** Repères de timing du plan d'entrée, utilisables comme filtres (tous les repères cochés doivent être vrais). */
var TIMING = [
  [
    'rr2',
    '⚖️ Gain / risque ≥ 2',
    function (p) {
      return ES.timingKeys(p).indexOf('rr2') > -1;
    },
    "Le gain visé vaut au moins deux fois la perte acceptée jusqu'au stop",
  ],
  [
    'rsiLow',
    '📶 RSI survendu (< 30)',
    function (p) {
      return ES.timingKeys(p).indexOf('rsiLow') > -1;
    },
    'Le titre a beaucoup baissé en peu de temps : rebond technique fréquent',
  ],
  [
    'breakout',
    '🚀 Cassure récente',
    function (p) {
      return ES.timingKeys(p).indexOf('breakout') > -1;
    },
    "Résistance franchie, cours au-dessus de la droite haute de la figure ou au plus haut de l'année",
  ],
  [
    'nearSup',
    '🧱 Près du support',
    function (p) {
      return ES.timingKeys(p).indexOf('nearSup') > -1;
    },
    "Cours tout près d'un support : perte limitée jusqu'au stop",
  ],
];
function timingOk(i, keys) {
  var p = planFor(i);
  if (!p) return false;
  return keys.every(function (k) {
    var t = TIMING.filter(function (x) {
      return x[0] === k;
    })[0];
    return !t || t[2](p);
  });
}
function planVerdict(i) {
  var p = planFor(i);
  return p ? p.verdict : null;
}
function convOf(i) {
  var x = S.inst[i];
  if (!x) return null;
  var g = dgInfo(i);
  return ES.convergence({
    dgRecent: g ? !!g.recent : false,
    sectorTrend: secTrendOf(i),
    revision30d: Number.isFinite(+x.revision30d) && x.revision30d !== null ? +x.revision30d : null,
    plan: planFor(i),
  });
}
/** Tendance du secteur d'une société : calculée le soir, sinon retrouvée ici dans le classement des secteurs (même règle). */
function secTrendOf(i) {
  var x = S.inst[i] || {};
  if (x.sectorTrend) return x.sectorTrend;
  if (!S.sec || !S.sec.groups) {
    if (!S.secLoaded) loadSectors();
    return null;
  }
  if (!S.gByKey) {
    S.gByKey = {};
    S.sec.groups.forEach(function (g) {
      S.gByKey[g.key] = g;
    });
  }
  var f = x.fund || {},
    g = (f.industry && S.gByKey[f.industry]) || (f.sector && S.gByKey['Autres : ' + f.sector]) || null;
  return g
    ? { trending: !!g.trending, emerging: !!g.emerging, rank: g.rank, of: S.sec.groups.length, key: g.key }
    : null;
}
/** Phase du cycle et place du secteur d'une société dans cette phase (lecture de la rotation des secteurs, sans poids dans la note). */
function cycOf(i) {
  var x = S.inst[i] || {};
  return S.cycle ? ES.cycleFit(S.cycle, (x.fund && x.fund.sector) || x.sector) : null;
}
/** Carte « phase du cycle » : frise des 4 phases, phase actuelle, secteurs portés et à contre-cycle. compact : une ligne (Opportunités). */
function cycleCard(compact) {
  var c = S.cycle;
  if (!c) return '';
  var name = c.second ? c.label + ' ou ' + c.second.toLowerCase() : c.label;
  var secs = function (fit) {
    return Object.keys(c.rs)
      .filter(function (k) {
        return ES.cycleFit(c, k).fit === fit;
      })
      .sort(function (a, b) {
        return fit === 'up' ? c.rs[b] - c.rs[a] : c.rs[a] - c.rs[b];
      })
      .map(function (k) {
        return ES.sectorFr(k);
      });
  };
  var up = secs('up'),
    dn = secs('down');
  if (compact)
    return (
      '<button class="mood cyc-line" data-a="view" data-v="secteurs"><b>🔄 Cycle : ' +
      esc(name) +
      '</b>' +
      (up.length ? ' — portés : ' + esc(up.slice(0, 3).join(', ')) : '') +
      ' →</button>'
    );
  var track =
    '<div class="cyc" role="img" aria-label="Phase du cycle : ' +
    esc(name) +
    '">' +
    ES.CYCLE.map(function (p) {
      var on = p.key === c.key,
        alt = c.second && p.label === c.second;
      return (
        '<span class="cyc-p' +
        (on ? ' on' : alt ? ' alt' : '') +
        '"><b>' +
        p.label.replace('Ralentissement', 'Ralen\u00adtissement') +
        '</b><small>' +
        p.short +
        '</small></span>'
      );
    }).join('') +
    '</div>';
  return (
    '<section class="card cyc-card"><h3>🔄 Phase du cycle : ' +
    esc(name) +
    ' <span class="chip ' +
    (c.conf === 'nette' ? 'good' : c.conf === 'probable' ? '' : 'warn') +
    '">' +
    c.conf +
    '</span></h3>' +
    track +
    (c.shift
      ? '<p class="small">↪ Rotation en cours : ' +
        esc(c.shift.from) +
        ' sur 6 mois, ' +
        esc(c.shift.to) +
        ' sur 3 mois.</p>'
      : '') +
    (up.length ? '<p class="cyc-s"><span class="chip good">Portés</span> ' + esc(up.join(' · ')) + '</p>' : '') +
    (dn.length
      ? '<p class="cyc-s"><span class="chip warn">À contre-cycle</span> ' + esc(dn.join(' · ')) + '</p>'
      : '') +
    xpi(
      'Lecture de ce que le marché anticipe, pas une prévision : chaque phase a ses secteurs meneurs (modèle de rotation sectorielle de Fidelity et Stovall). Force de chaque secteur face au STOXX 600 sur 3 et 6 mois. ' +
        (c.second
          ? "Les deux phases sont proches : un secteur n'est dit « porté » que si les deux le portent ou si sa force le confirme déjà. "
          : '') +
        'Sans effet sur la note.'
    ) +
    '</section>'
  );
}
/**
 * Feux de décision : 7 critères lisibles d'un coup d'œil (couleur + icône + valeur courte), mêmes règles partout.
 * tone : good (favorable), mid (à surveiller), bad (défavorable), na (inconnu ou neutre).
 */
/**
 * Liquidité : échanges moyens des 20 dernières séances sur la place d'origine (euros et nombre d'actions), seuils de décision :
 * 1 M€ par jour au moins (seuil de l'univers), 200 k€ à 1 M€ (ordres à cours limité, par petits paquets), moins de 200 k€ (difficile).
 * Ordre conseillé au plus : 5 % des échanges d'une journée, pour ne pas faire bouger le cours.
 */
var PLACE = {
  ST: 'Stockholm',
  PA: 'Paris',
  DE: 'Francfort (Xetra)',
  MI: 'Milan',
  MC: 'Madrid',
  AS: 'Amsterdam',
  BR: 'Bruxelles',
  HE: 'Helsinki',
  CO: 'Copenhague',
  OL: 'Oslo',
  LS: 'Lisbonne',
  VI: 'Vienne',
  IR: 'Dublin',
};
function liqLevel(eur) {
  return eur == null
    ? null
    : {
        tone: eur >= 1e6 ? 'good' : eur >= 2e5 ? 'mid' : 'bad',
        label: eur >= 1e6 ? 'liquide' : eur >= 2e5 ? 'peu liquide' : 'très peu liquide',
      };
}
function liqOf(i) {
  var x = S.inst[i] || {},
    st = x.stats || {},
    eur = st.adv20Eur;
  if (eur == null) return null;
  var L = liqLevel(eur),
    suf = String(x.ticker || '')
      .split('.')
      .pop();
  var px = st.lastClose,
    sh = st.adv20 != null && px > 0 ? st.adv20 / px : null;
  return { eur: eur, shares: sh, tone: L.tone, label: L.label, place: PLACE[suf] || null, maxOrder: eur * 0.05 };
}
function liqTxt(q) {
  return (
    ES.fmtEur(q.eur) +
    ' par jour' +
    (q.shares
      ? ' (≈ ' + fmtInt(Math.round(q.shares / (q.shares > 1000 ? 100 : 1)) * (q.shares > 1000 ? 100 : 1)) + ' actions)'
      : '') +
    (q.place ? ' à ' + q.place : '')
  );
}
function feux(i) {
  var x = S.inst[i] || {},
    c = S.computed[i],
    out = [],
    add = function (k, icon, label, tone, txt, tip, go) {
      out.push({ k: k, icon: icon, label: label, tone: tone, txt: txt, tip: tip, go: go });
    };
  var g = dgInfo(i),
    nb = c ? c.score.buys.length : 0;
  add(
    'dg',
    '👔',
    'Dirigeants',
    g && !g.none && g.recent ? 'good' : nb ? 'mid' : 'na',
    g && !g.none ? g.days + ' j' : nb ? nb + ' achat' + (nb > 1 ? 's' : '') : '—',
    g && !g.none
      ? 'Achat du DG ou du DAF il y a ' + g.days + ' jours'
      : nb
        ? 'Achats de dirigeants, sans le DG ni le DAF'
        : 'Aucun achat récent de dirigeant',
    'Déclarations des dirigeants'
  );
  var v = x.value,
    vt = 'na',
    vx = '—',
    vtip = 'Valeur non estimable';
  if (v && v.negEquity) {
    vt = 'bad';
    vx = 'négatifs';
    vtip = 'Capitaux propres négatifs';
  } else if (v && !v.na && v.mid != null) {
    vt = ES.valueCheap(v) ? 'good' : v.zone === 'above' && v.impliedG != null && v.impliedG >= 6 ? 'bad' : 'mid';
    vx = v.marginPct >= 0 ? '−' + v.marginPct + ' %' : '×' + fmtN(v.price / v.mid, 1);
    vtip =
      v.marginPct >= 0
        ? 'Cours ' + v.marginPct + ' % sous sa valeur intrinsèque'
        : 'Cours ' + fmtN(v.price / v.mid, 1) + ' fois sa valeur intrinsèque';
  } else if (v && v.lossMaking) {
    vt = 'bad';
    vx = 'pertes';
    vtip = 'Société en pertes : valeur non estimable';
  }
  add('val', '💎', 'Valeur', vt, vx, vtip, 'Valeur de l');
  var a = x.accounts,
    fs = a && a.fscore && !a.fscore.na ? a.fscore.f9 : null,
    risky = a && ((a.altman && a.altman.zone === 'distress') || (a.beneish && a.beneish.flag));
  var vb = x.value;
  if (fs == null && vb && vb.kind === 'fin' && vb.roe != null)
    add(
      'acc',
      '📊',
      'Comptes',
      vb.roe >= vb.r * 100 ? 'good' : vb.roe > 0 ? 'mid' : 'bad',
      fmtN(vb.roe, 0) + ' %',
      'Banque ou assurance : F-score sans objet ; rentabilité des fonds propres ' +
        fmtN(vb.roe, 1) +
        ' % (rendement exigé ' +
        fmtN(vb.r * 100, 1) +
        ' %)',
      'Analyse des comptes'
    );
  else
    add(
      'acc',
      '📊',
      'Comptes',
      fs == null
        ? risky
          ? 'bad'
          : 'na'
        : risky || fs <= S.cfg.accounts.fscoreBad
          ? 'bad'
          : fs >= S.cfg.accounts.fscoreGood
            ? 'good'
            : 'mid',
      fs != null ? fs + '/9' : risky ? 'risque' : '—',
      fs != null ? 'F-score ' + fs + '/9' + (risky ? ', bilan à risque' : '') : 'Comptes non disponibles',
      'Analyse des comptes'
    );
  var pl = planFor(i),
    tr = pl && pl.trend;
  add(
    'tr',
    '📈',
    'Tendance',
    tr === 'up' ? 'good' : tr === 'down' ? 'bad' : tr ? 'mid' : 'na',
    tr === 'up' ? '↗' : tr === 'down' ? '↘' : tr ? '→' : '—',
    tr ? 'Tendance de fond ' + { up: 'haussière', down: 'baissière', mixed: 'indécise' }[tr] : 'Tendance non calculée',
    '.plan'
  );
  var st = secTrendOf(i);
  add(
    'sec',
    '🔥',
    'Secteur',
    st && (st.trending || st.emerging) ? 'good' : st ? 'na' : 'na',
    st ? st.rank + 'e' : '—',
    st
      ? 'Secteur ' +
          (st.trending ? 'en tendance' : st.emerging ? 'émergent' : 'hors tendance') +
          ' : ' +
          st.rank +
          'e sur ' +
          st.of
      : 'Secteur non classé'
  );
  var cy = cycOf(i);
  add(
    'cyc',
    '🔄',
    'Cycle',
    cy ? (cy.fit === 'up' ? 'good' : cy.fit === 'down' ? 'bad' : 'na') : 'na',
    cy ? (cy.fit === 'up' ? 'porté' : cy.fit === 'down' ? 'contre' : 'neutre') : '—',
    cy
      ? (cy.cyclical ? 'Secteur cyclique' : 'Secteur défensif') +
          ', ' +
          (cy.fit === 'up' ? 'porté par' : cy.fit === 'down' ? 'à contre-courant de' : 'neutre dans') +
          ' la phase ' +
          cy.phase
      : 'Phase du cycle inconnue'
  );
  var lq = liqOf(i);
  add(
    'liq',
    '💧',
    'Liquidité',
    lq ? lq.tone : 'na',
    lq ? ES.fmtEur(lq.eur).replace(' ', '') : '—',
    lq ? cap1(lq.label) + ' : ' + liqTxt(lq) : 'Échanges inconnus'
  );
  var vd = pl && pl.verdict;
  add(
    'tim',
    '🧭',
    'Timing',
    vd === 'buyNow' ? 'good' : vd === 'avoid' ? 'bad' : vd ? 'mid' : 'na',
    vd === 'buyNow' ? 'achat' : vd === 'avoid' ? 'éviter' : vd ? 'attendre' : '—',
    pl ? pl.label : "Plan d'entrée non calculé",
    '.plan'
  );
  return out;
}
/** Bande de feux : compacte dans les listes, détaillée (libellés, cliquable) en tête de fiche. */
function cap1(t) {
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : t;
}
function feuxHtml(i, big) {
  var L = feux(i);
  if (!big)
    return (
      '<span class="fx" role="img" aria-label="' +
      esc(
        L.map(function (f) {
          return f.label + ' : ' + f.tip;
        }).join(' ; ')
      ) +
      '">' +
      L.map(function (f) {
        return (
          '<span class="fx-i t-' +
          f.tone +
          '" title="' +
          esc(f.label + ' : ' + f.tip) +
          '">' +
          f.icon +
          (f.txt !== '—' && (f.k === 'val' || f.k === 'acc' || f.k === 'tr' || (f.k === 'dg' && / j$/.test(f.txt)))
            ? '<b>' + esc(f.txt) + '</b>'
            : '') +
          '</span>'
        );
      }).join('') +
      '</span>'
    );
  var n = { good: 0, mid: 0, bad: 0 };
  L.forEach(function (f) {
    if (n[f.tone] != null) n[f.tone]++;
  });
  return (
    '<div class="fxb">' +
    L.map(function (f) {
      return (
        '<button class="fxb-i t-' +
        f.tone +
        '"' +
        (f.go ? ' data-a="goto" data-v="' + esc(f.go) + '"' : ' disabled') +
        ' title="' +
        esc(f.tip) +
        '"><span class="fxb-ic" aria-hidden="true">' +
        f.icon +
        '</span><b>' +
        esc(f.txt) +
        '</b><small>' +
        f.label +
        '</small></button>'
      );
    }).join('') +
    '</div><p class="fxb-sum"><span class="t-good">●</span> ' +
    n.good +
    ' favorable' +
    (n.good > 1 ? 's' : '') +
    ' · <span class="t-mid">●</span> ' +
    n.mid +
    ' à surveiller · <span class="t-bad">●</span> ' +
    n.bad +
    ' défavorable' +
    (n.bad > 1 ? 's' : '') +
    '</p>'
  );
}
