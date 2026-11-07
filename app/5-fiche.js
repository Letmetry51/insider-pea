/* Euro Signal — interface : fiche d'une société, plan d'entrée, positions et revente.
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
/* ----- Fiche titre ----- */
function backView() {
  return S.back &&
    S.back.view &&
    S.back.view !== 'fiche' &&
    VIEWS.some(function (v) {
      return v[0] === S.back.view;
    })
    ? S.back.view
    : 'classement';
}
function backLabel() {
  var v = backView(),
    m = VIEWS.filter(function (x) {
      return x[0] === v;
    })[0];
  return m ? m[2] : 'Opportunités';
}
function vFiche() {
  var i = S.sel,
    x = S.inst[i];
  if (!x) {
    S.view = 'classement';
    return vClassement();
  }
  var c = S.computed[i] || computeOne(i),
    sc = c.score,
    ev = S.ev[i] || { buybacks: [], results: [], splits: [] };
  if (S.mode === 'remote' && !hasDetail(i)) loadDetailFor(i);
  var regs = {};
  (S.tx[i] || []).forEach(function (t) {
    regs[t.registry] = 1;
  });
  var h =
    '<div class="crumbs">' +
    (S.ficheFrom === 'secco'
      ? '<button class="link" data-a="secBack">← Fiche secteur de ' +
        esc(((S.secCo && S.secCo.items[S.secSym]) || {}).name || S.secSym) +
        '</button>'
      : '<button class="link" data-a="view" data-v="' + backView() + '">← ' + esc(backLabel()) + '</button>') +
    '</div>';
  var sub = [
    x.ticker,
    secOf(x) ? secOf(x) + (x.fund && x.fund.industry ? ' — ' + ES.industryFr(x.fund.industry) : '') : null,
    x.country ? COUNTRIES[x.country] || x.country : null,
  ]
    .filter(Boolean)
    .join(' · ');
  h +=
    '<header class="fhead"><div><h2>' +
    flag(x.country) +
    esc(x.name || i) +
    '</h2><p class="fsub">' +
    esc(sub) +
    (x.position ? ' ' + posChip(x.position) : '') +
    '</p></div>' +
    '<div class="fchips">' +
    (c.uni.status === 'retenu' ? '' : uniChip(c.uni)) +
    peaChip(x) +
    '</div></header>'; // « retenu » est la règle : seul l'écart est signalé ; le cycle est dans les feux
  h += missingLine(i);
  if (x.secondary && S.inst[x.secondary])
    h +=
      '<p class="liqw">ℹ️ <b>Ligne secondaire sans cours</b> (options, droits ou actions nouvelles) de la société : <button class="link" data-a="open" data-i="' +
      esc(x.secondary) +
      '">fiche de la ligne principale (' +
      esc(S.inst[x.secondary].name) +
      ')</button>.</p>';
  var anH = analysisCard(i, x.ticker, true);
  h += rankFold(rankOf(i, x.ticker)) + anH + bizCard(x.ticker, true);
  // version allégée : la note tendance + comptes, le cours avec le plan d'entrée et « Je l'ai acheté » en haut ; la lecture « dirigeants » est repliée plus bas
  var newM = !!rankData(),
    advS = adviceSection(i, c),
    cutB = advS.indexOf('<section class="card buybox">'),
    advHow = cutB > -1 ? advS.slice(0, cutB) : advS,
    advBuy = cutB > -1 ? advS.slice(cutB) : '';
  if (!newM) h += adviceCard(i, c) + advS;
  h +=
    '<details class="card fold" data-k="f-cours"><summary>📉 ' +
    (newM ? 'Cours, supports et résistances' : 'Cours et achats des dirigeants') +
    ' <span class="muted small">· plan d\'entrée</span></summary>' +
    chart(i) +
    '</details>';
  if (newM) h += advBuy;
  var nDet = 0,
    det = function (title, body, open) {
      return (
        '<details class="card fold" data-k="fiche' +
        nDet++ +
        '"' +
        (open ? ' open' : '') +
        '><summary>' +
        title +
        '</summary>' +
        body +
        '</details>'
      );
    };
  var hTop = h;
  if (newM && anH) return hTop; // comptes, valeur, dirigeants, rachats et résultats : dans le pli 🔬 Analyse, sans doublon
  h = ''; // secours (pas de cours, ou classement absent) : dossiers détaillés regroupés dans « ➕ Plus de détails »
  var acc = x.accounts,
    TI = { good: '🟢', mixed: '🟡', bad: '🔴', na: '⚪' },
    ft = acc && acc.fscoreTrend ? { up: ' ↗', down: ' ↘', flat: '' }[acc.fscoreTrend.key] || '' : '';
  var accS =
    acc && acc.plain && acc.plain.label
      ? ' <span class="muted">· ' +
        (TI[acc.plain.tone] || '⚪') +
        ' ' +
        esc(acc.plain.label) +
        (acc.fscore && !acc.fscore.na ? ', F-score ' + acc.fscore.f9 + '/9' + ft : '') +
        '</span>'
      : acc && acc.verdict
        ? ' <span class="muted">· ' + (TI[acc.verdict.key] || '⚪') + ' ' + esc(acc.verdict.text) + '</span>'
        : '';
  h += det('📊 Analyse des comptes' + accS, accountsSection(i));
  var vv0 = x.value ? ES.valueView(x.value) : null;
  h += det(
    "💎 Valeur de l'entreprise" +
      (vv0
        ? ' <span class="muted">· ' +
          ({ good: '🟢', mixed: '🟡', bad: '🔴', na: '⚪' }[vv0.tone] || '⚪') +
          ' ' +
          esc(
            x.value.mid != null
              ? x.value.marginPct >= 0
                ? 'marge de sécurité ' + x.value.marginPct + ' %'
                : 'cours au-dessus de la valeur estimée'
              : x.value.pb != null
                ? 'cours ' + fmtN(x.value.pb, 1) + '× la valeur comptable'
                : 'non estimable'
          ) +
          '</span>'
        : ''),
    valueSection(i)
  );
  var lab = ES.scoreLabel(sc.total, S.cfg),
    withBuys = Object.keys(S.computed).filter(function (k) {
      return S.computed[k].score.buys.length;
    });
  var rank =
    1 +
    withBuys.filter(function (k) {
      return S.computed[k].score.total > sc.total;
    }).length;
  var SM = S.cfg.selection.minScore,
    AM = S.cfg.alerts.minScore;
  var noteBody =
    '<section class="gauges">' +
    gauge(
      "Note d'opportunité",
      ES.note(sc.total, S.cfg),
      '<b class="slab s-' +
        lab.key +
        '">' +
        lab.label +
        '</b>' +
        (sc.buys.length
          ? ' · ' + (rank === 1 ? '1er' : rank + 'e') + ' sur ' + withBuys.length + ' sociétés avec achats'
          : '') +
        histTxt(sc) +
        ' · barème ' +
        esc(sc.version),
      'acc'
    ) +
    gauge(
      'Qualité des données',
      c.q.total,
      'Couverture et complétude',
      c.q.total >= S.cfg.quality.minForAlert ? 'good' : 'warn'
    ) +
    gauge('Surchauffe', c.oh.total, 'Expérimental, hors score', c.oh.total >= 50 ? 'bad' : 'neutral') +
    '</section>' +
    '<p class="scale"><b>' +
    ES.note(AM, S.cfg) +
    ' et plus = très fort</b> (rare) · ' +
    ES.note(SM, S.cfg) +
    ' à ' +
    (ES.note(AM, S.cfg) - 1) +
    ' = fort (sélection) · ' +
    ES.note(Math.round(SM / 2), S.cfg) +
    ' à ' +
    (ES.note(SM, S.cfg) - 1) +
    ' = moyen · en dessous = faible. 100 = dossier idéal réaliste (' +
    ((S.cfg.display || {}).scoreCeiling || 60) +
    ' points bruts ; ici ' +
    sc.total +
    ').</p>' +
    (c.uni.reasons.length
      ? '<div class="note ' +
        (c.uni.status === 'rejete' ? 'bad' : 'warn') +
        '"><b>Univers :</b> ' +
        c.uni.reasons.map(esc).join(' ; ') +
        '</div>'
      : '') +
    '<div class="cols"><div>' +
    Object.keys(sc.families)
      .map(function (k) {
        var fm = sc.families[k];
        return (
          '<div class="fam-block"><div class="fam-h"><span class="dot f-' +
          k +
          '"></span><b>' +
          esc(fm.label) +
          '</b><span class="pts">' +
          fm.points +
          ' / ' +
          fm.cap +
          (fm.capped ? ' (plafonné, brut ' + fm.raw + ')' : '') +
          '</span></div>' +
          (fm.items.length
            ? '<ul>' +
              fm.items
                .map(function (it) {
                  return (
                    '<li><span>' +
                    esc(it.label) +
                    '</span><b class="' +
                    (it.points > 0 ? 'pos' : it.points < 0 ? 'neg' : 'zero') +
                    '">' +
                    (it.points > 0 ? '+' : '') +
                    it.points +
                    '</b></li>'
                  );
                })
                .join('') +
              '</ul>'
            : '<p class="muted">Aucun élément.</p>') +
          '</div>'
        );
      })
      .join('') +
    xpi(
      'Publications depuis le ' +
        sc.windowFrom +
        '. Chaque famille est plafonnée pour ne pas compter deux fois la même information.'
    ) +
    '</div>' +
    '<div><h4>Qualité des données</h4><ul class="checks">' +
    c.q.items
      .map(function (it) {
        return (
          '<li class="' +
          (it.ok ? 'ok' : 'ko') +
          '"><span>' +
          esc(it.label) +
          '</span><b>' +
          it.points +
          '/' +
          it.max +
          '</b></li>'
        );
      })
      .join('') +
    '</ul>' +
    '<h4 class="mt">Surchauffe <span class="chip neutral">expérimental</span></h4>' +
    (c.oh.items.length
      ? '<ul class="checks">' +
        c.oh.items
          .map(function (it) {
            return '<li class="ko"><span>' + esc(it.label) + '</span><b>+' + it.points + '</b></li>';
          })
          .join('') +
        '</ul>'
      : '<p class="muted">Aucun signe de surchauffe.</p>') +
    xpi('Non disponibles : ' + c.oh.unavailable.map(esc).join(' ; ') + '.') +
    '</div></div>';
  h += newM
    ? det(
        '👔 Lecture « dirigeants » <span class="muted">· ancienne méthode, pour information</span>',
        adviceCard(i, c) + advHow + '<h4 class="mt">Détail de l\'ancienne note</h4>' + noteBody
      )
    : det('🧮 Détail de la note', noteBody);
  var nTx = (S.tx[i] || []).filter(function (t) {
    return ES.availDate(t) >= sc.windowFrom;
  }).length;
  h += det('📝 Déclarations des dirigeants <span class="muted">· ' + nTx + '</span>', txSection(i, sc));
  h += '<p class="rep">' + reportBtn(x.name || i, i, x.ticker) + '</p>';
  h += det("🔁 Rachats d'actions et résultats", eventsSection(i, ev));
  h += det(
    '🪪 Détails techniques <span class="muted">· alerte, identité du titre</span>',
    alertSection(i, c) +
      '<h4 class="mt">Identité du titre</h4><dl class="ids">' +
      kv('ISIN', i) +
      kv('Ticker', x.ticker || 'n.d.') +
      kv('Domiciliation', x.country ? COUNTRIES[x.country] || x.country : 'inconnue') +
      kv('Place de cotation', (x.venue || 'n.d.') + (x.isReference === false ? ' (secondaire)' : '')) +
      kv('Registres consultés', Object.keys(regs).join(', ') || 'aucun') +
      kv('Devise', x.currency || 'n.d.') +
      kv('Secteur', (secOf(x) || 'n.d.') + (x.fund && x.fund.industry ? ' — ' + ES.industryFr(x.fund.industry) : '')) +
      '</dl>' +
      reportBtn(x.name || i, i, x.ticker) +
      '<p class="foot">' +
      esc(
        [
          x.priceNote ? 'Cours : ' + x.priceNote : null,
          x.ticker ? 'Ticker Yahoo : ' + x.ticker : null,
          x.registry ? 'Registre : ' + x.registry : null,
          x.countrySource ? 'Domiciliation : ' + x.countrySource : null,
          "Rachats et perspectives détectés d'après les titres des communiqués ; résultats : BPA publié et consensus Yahoo figé à la publication",
        ]
          .filter(Boolean)
          .join(' · ')
      ) +
      '</p>'
  );
  return (
    hTop +
    '<details class="card fold comore" data-k="fmore"><summary>➕ Plus de détails <span class="muted">· comptes, valeur, dirigeants, rachats, résultats</span></summary>' +
    h +
    '</details>'
  );
}
/** Données manquantes d'une fiche, avec la raison : un « n.d. » ne doit jamais rester une énigme. */
function missingLine(i) {
  var x = S.inst[i] || {},
    st = x.stats || {},
    f = x.fund || {},
    v = x.value,
    out = [];
  if (!(st.lastClose > 0))
    out.push(
      'cours (introuvables chez Yahoo pour cet ISIN : retirée de la cote, ligne secondaire ou marché non suivi)'
    );
  else {
    if (!x.accounts) out.push('comptes annuels (pas encore lus chez Yahoo, complétés au fil des soirs)');
    if (!v) out.push("valeur comptable et intrinsèque (comptes ou nombre d'actions manquants)");
    else if (v.na) out.push('valeur (' + (v.reason || 'données incohérentes') + ')');
    if (!f.sector) out.push('secteur et capitalisation (fiche Yahoo absente)');
    if (st.adv20Eur == null) out.push('liquidité (volumes absents chez Yahoo)');
    if (!x.plan && !(st.sessions >= 120)) out.push("plan d'entrée (moins de 6 mois de cours)");
    if (x.revision30d == null && !x.forecast)
      out.push('prévisions des analystes (société non suivie par les analystes chez Yahoo)');
  }
  return out.length ? '<p class="miss">ℹ️ <b>Données manquantes</b> : ' + esc(out.join(' ; ')) + '.</p>' : '';
}
/** Signaler une erreur : prépare un email à soi-même avec la société et le lien (à recopier dans la conversation avec Claude). */
function reportBtn(name, isin, ticker) {
  var link = location.origin + location.pathname + (isin ? '#' + isin : '');
  var body =
    'Société : ' +
    name +
    '\n' +
    (isin ? 'ISIN : ' + isin + '\n' : '') +
    (ticker ? 'Ticker : ' + ticker + '\n' : '') +
    'Données du : ' +
    (S.today || '') +
    '\nFiche : ' +
    link +
    '\n\nCe qui ne va pas (et ce que montre Yahoo ou votre courtier) :\n';
  var url =
    'mailto:' +
    encodeURIComponent(S.email || '') +
    '?subject=' +
    encodeURIComponent('[Euro Signal] Erreur — ' + name) +
    '&body=' +
    encodeURIComponent(body);
  return '<a class="repbtn" href="' + esc(url) + '">⚑ Signaler une erreur</a>';
}
/** Résumé en langage courant en tête de fiche : ce qui ressort, ce qu'il faut vérifier. */
function brief(i, c) {
  var sc = c.score,
    d = sc.discount,
    b = sc.buys,
    x = S.inst[i],
    plus = [],
    check = [];
  if (b.length) {
    var people = {};
    b.forEach(function (t) {
      people[ES.buyerKey(t) || t.person] = 1;
    });
    var ceo = b.some(function (t) {
      return t.ceo || t.cfo;
    });
    var np = Object.keys(people).length;
    plus.push(
      b.length +
        ' achat' +
        (b.length > 1 ? 's' : '') +
        ' de dirigeants depuis le ' +
        shortDate(sc.windowFrom) +
        (sc.buyEur ? ', ' + ES.fmtEur(sc.buyEur) + ' au total' : '') +
        ' — ' +
        np +
        ' acheteur' +
        (np > 1 ? 's' : '') +
        (ceo ? ', dont le DG ou le DAF' : '') +
        '.'
    );
  }
  if (d)
    plus.push(
      'Meilleure décote : prix payé ' +
        Math.round(d.pct) +
        ' % sous le plus haut 52 semaines' +
        (d.high52 ? ' (' + fmtN(d.high52) + ' le ' + shortDate(d.high52Date) + ')' : '') +
        ', le ' +
        shortDate(d.date) +
        ' par ' +
        esc(shortName(d.person)) +
        '.'
    );
  if (sc.cluster && sc.cluster.count >= 2)
    plus.push(
      '<b>' +
        (sc.cluster.count >= S.cfg.insiders.clusterMinBuyers ? 'Cluster' : 'Achats rapprochés') +
        '</b> : ' +
        sc.cluster.count +
        ' dirigeants entre le ' +
        shortDate(sc.cluster.from) +
        ' et le ' +
        shortDate(sc.cluster.to) +
        (sc.cluster.totalEur ? ' pour ' + ES.fmtEur(sc.cluster.totalEur) : '') +
        ' — ' +
        sc.cluster.buyers
          .slice(0, 6)
          .map(function (b) {
            return esc(shortName(b.name)) + (b.eur ? ' ' + ES.fmtEur(b.eur) : '') + (b.ceo ? ' (DG/DAF)' : '');
          })
          .join(', ') +
        (sc.cluster.buyers.length > 6 ? '…' : '') +
        '.'
    );
  ['buyback', 'results'].forEach(function (k) {
    sc.families[k].items.forEach(function (it) {
      if (it.points > 0) plus.push(esc(it.label.charAt(0).toUpperCase() + it.label.slice(1)) + '.');
    });
  });
  if (!plus.length)
    plus.push('Aucun signal récent : ni achat de dirigeant, ni rachat, ni résultat au-dessus du consensus.');
  var pea = x.peaStatus || 'a_verifier';
  if (pea !== 'eligible')
    check.push(
      pea === 'non_eligible'
        ? 'Non éligible au PEA.'
        : pea === 'probable'
          ? 'PEA probable (' + esc(x.peaSource || '') + ') : à confirmer chez votre courtier.'
          : 'Éligibilité PEA à vérifier auprès de votre courtier.'
    );
  if (sc.fallingKnife)
    check.push(
      'Cours en repli : il est passé sous ses moyennes 50 et 200 séances. Un achat de dirigeant ne marque pas forcément le point bas ; entrer en plusieurs fois.'
    );
  if (sc.cluster && sc.cluster.coordinated)
    check.push(
      'Achats groupés le même jour avec des montants proches : souvent un programme collectif décidé par la société, moins parlant que des achats spontanés.'
    );
  var hl = ES.financialHealth(x.fund);
  if (hl.status === 'fragile')
    check.push(
      '<b>Solidité financière fragile</b> : ' +
        esc(hl.reasons.join(' ; ')) +
        '. Risque de piège : la baisse peut être justifiée.'
    );
  else if (hl.status === 'inconnu')
    check.push("Solidité financière non vérifiable automatiquement : regarder l'endettement et la trésorerie.");
  else plus.push('Solidité financière correcte' + (hl.notes.length ? ' : ' + esc(hl.notes.join(', ')) : '') + '.');
  if (x.nextEarnings) {
    var dj = ES.daysBetween(S.today, x.nextEarnings);
    if (dj >= 0)
      (dj <= S.cfg.alerts.earningsWarnDays ? check : plus).push(
        'Prochains résultats le ' +
          shortDate(x.nextEarnings) +
          ' (dans ' +
          dj +
          ' jours)' +
          (dj <= S.cfg.alerts.earningsWarnDays ? ' : acheter juste avant revient à parier sur leur contenu.' : '.')
      );
  }
  if (sc.marketDown)
    check.push(
      'Marché européen sous sa moyenne 200 séances : les achats de dirigeants y fonctionnent moins bien, réduire la taille des positions.'
    );
  if (sc.rel6m != null && sc.rel6m <= -S.cfg.weights.market.relWeakPts)
    check.push('Titre nettement plus faible que le marché européen sur 6 mois (' + Math.round(sc.rel6m) + ' points).');
  if (x.position)
    (x.position.key === 'leader' || x.position.key === 'challenger' ? plus : check).push(
      (x.position.key === 'leader'
        ? '<b>Leader de son industrie</b>'
        : x.position.key === 'challenger'
          ? '<b>Challenger de son industrie</b>'
          : x.position.key === 'niche'
            ? 'Acteur de niche'
            : 'Suiveur dans son industrie') +
        ' (' +
        esc(x.position.industry) +
        ') : n° ' +
        x.position.rank +
        ' sur ' +
        x.position.of +
        " sociétés européennes suivies par chiffre d'affaires, " +
        fmtN(x.position.sharePct, 1) +
        ' % du total.' +
        (x.position.key === 'niche' || x.position.key === 'follower'
          ? ' Les petits acteurs sont plus exposés aux retournements : vérifier ce qui les distingue.'
          : '')
    );
  var bpro = x.buyerProfiles || {};
  Object.keys(bpro).forEach(function (k) {
    var b = bpro[k],
      nm = esc(shortName(b.name || '?')),
      t = [];
    if (b.routine === 'inhabituel') t.push('🧭 achat <b>inhabituel</b> (pas au même mois les années précédentes)');
    else if (b.routine === 'habituel')
      t.push(
        '🔁 achat <b>habituel</b> : ' +
          (b.monthsActive >= 6
            ? 'il achète presque en continu (' + b.monthsActive + ' mois sur les 12 derniers)'
            : 'il achète à cette période ' +
              (b.sameMonthYears > 1 ? b.sameMonthYears + ' années de suite' : "l'an dernier aussi")) +
          ', chaque achat est donc peu informatif'
      );
    if (b.record) t.push('💪 <b>achat record</b> pour lui (au moins 2 fois son plus gros achat passé)');
    if (b.cohen === 'opportuniste')
      t.push('méthode de Harvard : <b>opportuniste</b> (un ordre chaque année, jamais le même mois)');
    else if (b.cohen === 'routinier')
      t.push('méthode de Harvard : <b>routinier</b> (un ordre le même mois 3 ans de suite)');
    if (b.track && b.track.n)
      t.push(
        '🏅 palmarès : ' +
          b.track.beat +
          ' achat' +
          (b.track.beat > 1 ? 's' : '') +
          ' sur ' +
          b.track.n +
          ' ont battu le marché à 3 mois (' +
          pct(b.track.avgExcess) +
          ' en moyenne)'
      );
    else if (b.pastBuys) t.push('palmarès : achats précédents trop récents pour être jugés');
    else if (b.firstBuy) t.push('premier achat connu depuis au moins un an');
    if (!t.length) return;
    ((b.routine === 'habituel' && !b.record) || (b.track && b.track.n >= 2 && b.track.beat / b.track.n <= 0.34)
      ? check
      : plus
    ).push(
      '<b>' +
        nm +
        '</b>' +
        (b.ceo ? ' (DG/DAF)' : '') +
        ' : ' +
        t.join(' ; ') +
        '.' +
        (S.snapshot && S.snapshot.history
          ? ' <button class="link small" data-a="person" data-k="' + esc(k) + '">Tout son historique →</button>'
          : '')
    );
  });
  if (x.peer) {
    var pv = x.peer,
      pvTxt =
        pv.metric +
        ' ' +
        fmtN(pv.value, 1) +
        ' contre ' +
        fmtN(pv.peerMedian, 1) +
        ' en médiane pour ' +
        pv.peers +
        ' sociétés comparables (' +
        esc(pv.level + ' : ' + (pv.group || '?')) +
        ')';
    if (pv.discountPct >= S.cfg.valuation.cheapPct)
      plus.push('<b>Valorisation ' + Math.round(pv.discountPct) + ' % sous ses pairs</b> : ' + pvTxt + '.');
    else if (pv.discountPct <= -S.cfg.valuation.richPct)
      check.push(
        'Valorisation ' +
          Math.round(-pv.discountPct) +
          ' % au-dessus de ses pairs : ' +
          pvTxt +
          ". La décote du cours ne veut pas dire que l'action est bon marché."
      );
    else plus.push('Valorisation proche de ses pairs : ' + pvTxt + '.');
  }
  if (x.value && !x.value.na) {
    var vb = ES.valueView(x.value);
    if (vb && vb.tone === 'good')
      plus.push(
        '<b>💎 ' +
          esc(vb.chip ? vb.chip.charAt(0).toUpperCase() + vb.chip.slice(1) : 'Cours sous sa valeur estimée') +
          '</b> : ' +
          esc(vb.text)
      );
    else if (vb && vb.tone === 'bad')
      check.push(
        (x.value.negEquity
          ? '<b>🕳️ Fonds propres négatifs</b> : '
          : x.value.lossMaking
            ? '<b>Société en pertes</b> : '
            : '<b>🎈 Valorisation exigeante</b> : ') + esc(vb.text)
      );
  }
  if (x.shorts) {
    var shTxt =
      fmtN(x.shorts.totalPct, 2) +
      '\u00a0% du capital vendu à découvert par ' +
      x.shorts.holders +
      ' fonds (' +
      x.shorts.top
        .map(function (p) {
          return esc(p.holder) + ' ' + fmtN(p.pct, 2) + '\u00a0%';
        })
        .join(', ') +
      ')';
    var duel = (adviceOf(i).signals || []).some(function (g) {
      return g.k === 'duel';
    });
    if (x.shorts.totalPct >= 2)
      check.push(
        '<b class="neg">⚠️ Ventes à découvert</b> : ' +
          shTxt +
          '. ' +
          (duel
            ? "⚡ Duel : les dirigeants achètent fort à contre-courant. Si les dirigeants ont raison, les vendeurs à découvert devront racheter (hausse brutale possible) ; s'ils ont tort, la baisse peut continuer. Issue binaire : position réduite."
            : "Des fonds professionnels parient sur la baisse : chercher ce qu'ils reprochent à la société.")
      );
    else check.push('Ventes à découvert modestes : ' + shTxt + '.');
  }
  if (sc.sellEur > sc.buyEur && sc.sellEur > 0)
    check.push('Les dirigeants ont plus vendu (' + ES.fmtEur(sc.sellEur) + ") qu'acheté.");
  if (c.oh.total >= 50) check.push('Signes de surchauffe du cours (indicateur expérimental).');
  if (c.q.total < S.cfg.quality.minForAlert) check.push('Données incomplètes : qualité ' + c.q.total + '/100.');
  if (!check.length) check.push('Rien de particulier signalé par les données.');
  return (
    '<section class="brief"><div><h3>Ce qui ressort</h3><ul>' +
    plus
      .map(function (t) {
        return '<li>' + t + '</li>';
      })
      .join('') +
    '</ul></div><div><h3>À vérifier avant d\'acheter</h3><ul class="chk">' +
    check
      .map(function (t) {
        return '<li>' + t + '</li>';
      })
      .join('') +
    '</ul></div></section>'
  );
}
/* ----- Conseil d'achat et de revente, alertes de revente personnelles (via votre Gmail) ----- */
function lsGet(k, d) {
  try {
    var v = window.localStorage.getItem('es.' + k);
    return v == null ? d : v;
  } catch (e) {
    return d;
  }
}
try {
  window.localStorage.removeItem('es.email'); // anciennes versions : l'adresse était gardée sur l'appareil
} catch (e) {}
function lsSet(k, v) {
  try {
    window.localStorage.setItem('es.' + k, v);
  } catch (e) {}
}
function adviceSection(i, c) {
  var x = S.inst[i],
    sc = c.score,
    hl = ES.financialHealth(x.fund),
    st = x.stats || {},
    last = st.lastCloseAdj || st.lastClose;
  var buy = [],
    sell = [],
    paid = sc.discount ? sc.discount.paid : null,
    lv = lvLine(i);
  var z = ES.positionSize(x, sc, adviceOf(i), S.cfg),
    soon =
      x.nextEarnings &&
      ES.daysBetween(S.today, x.nextEarnings) >= 0 &&
      ES.daysBetween(S.today, x.nextEarnings) <= S.cfg.alerts.earningsWarnDays;
  // Pour acheter : combien, quand, à quel prix
  if (hl.status === 'fragile')
    buy.push("<b>Prudence</b> : société fragile, l'achat du dirigeant ne compense pas ce risque.");
  else if (!sc.buys.length) buy.push('Aucun achat récent de dirigeant : pas de signal.');
  else {
    buy.push(
      z.pct
        ? '<b>⚖️ ' +
            fmtN(z.pct, z.pct % 1 ? 1 : 0) +
            ' % du portefeuille au plus</b>, protection à −' +
            z.stopPct +
            ' %.' +
            (z.reasons.length ? ' <span class="muted">Réduite : ' + esc(z.reasons.join(', ')) + '.</span>' : '')
        : '<b>⚖️ Pas de taille suggérée</b> : ' + esc(z.reasons.join(', ')) + '.'
    );
    if (!z.none)
      buy.push(
        (sc.fallingKnife || z.staged ? 'Entrer en 3 fois' : 'Entrer en 1 ou 2 fois') +
          (soon
            ? ', après les résultats du ' + shortDate(x.nextEarnings)
            : sc.fallingKnife
              ? ' : le cours est encore en repli'
              : '') +
          (sc.marketDown ? ' ; marché européen baissier' : '') +
          '.'
      );
    if (!planFor(i) && lv && (lv.s1 || lv.r1))
      buy.push(
        '📐 ' +
          (lv.s1 ? 'Support ' + fmtN(lv.s1.price) + ' (' + pct(lv.s1.distPct) + ')' : 'Aucun support proche') +
          ' · ' +
          (lv.r1 ? 'résistance ' + fmtN(lv.r1.price) + ' (' + pct(lv.r1.distPct) + ')' : "au plus haut de l'année") +
          '.' +
          (lv.s1 && lv.s1.distPct >= -3
            ? lv.s1.kind === 'low52'
              ? " Près du plus bas annuel : attendre qu'il tienne."
              : ' Près du support : entrée favorable.'
            : lv.r1 && lv.r1.distPct <= 3
              ? ' Bute sur la résistance : entrer en partie.'
              : '')
      );
    if (paid) buy.push('Le dirigeant a payé ' + fmtN(paid) + ' le ' + shortDate(sc.discount.date) + '.');
  }
  var lq0 = liqOf(i);
  if (lq0 && lq0.tone !== 'good')
    buy.push(
      '💧 ' +
        cap1(lq0.label) +
        ' : ' +
        ES.fmtEur(lq0.maxOrder) +
        ' par jour au plus (5 % des échanges), ordres à cours limité' +
        (lq0.place ? ' sur ' + esc(lq0.place) : '') +
        '.'
    );
  var pl0 = planFor(i),
    pp0 = pl0 && pl0.primary;
  var avd0 = adviceOf(i);
  if (pl0 && pl0.verdict === 'avoid') buy.push('⛔ ' + esc(pl0.label) + '.');
  else if (pp0 && pp0.target && pp0.stop && !(avd0 && avd0.key === 'avoid'))
    buy.push(
      '🧭 ' +
        esc(pl0.label) +
        ' : entrée ' +
        (pp0.zoneLo
          ? fmtN(pp0.zoneLo, pp0.zoneLo < 10 ? 2 : 1) + '–' + fmtN(pp0.zoneHi, pp0.zoneHi < 10 ? 2 : 1)
          : fmtN(pp0.entry, pp0.entry < 10 ? 2 : 1)) +
        '.'
    );
  if (x.peaStatus !== 'eligible')
    buy.push(
      x.peaStatus === 'non_eligible'
        ? '🚫 Non éligible au PEA.'
        : x.peaStatus === 'probable'
          ? 'PEA probable : à confirmer chez le courtier.'
          : 'PEA : à vérifier chez le courtier.'
    );
  // Pour revendre : objectif et stop du plan d'entrée quand il existe (mêmes chiffres partout sur la fiche)
  var pl = planFor(i),
    pp = pl && pl.verdict !== 'avoid' ? pl.primary : null,
    f4 = function (v) {
      return fmtN(v, v < 10 ? 2 : 1);
    };
  if (pp && pp.target && pp.stop) {
    sell.push('🎯 Objectif ' + f4(pp.target) + ' (' + pct(pp.targetPct) + " depuis l'entrée).");
    sell.push('🛑 Stop : clôture sous ' + f4(pp.stop) + ' (' + pct(pp.stopPct) + ').');
  } else if (lv && lv.r1)
    sell.push(
      '🎯 Objectif : ' +
        fmtN(lv.r1.price) +
        ' (' +
        pct(lv.r1.distPct) +
        ')' +
        (lv.r2 ? ', puis ' + fmtN(lv.r2.price) + ' (' + pct(lv.r2.distPct) + ')' : '') +
        '.'
    );
  var outs = [],
    hasPlan = !!(pp && pp.target && pp.stop);
  if (!hasPlan && lv && lv.s1) outs.push('clôture sous ' + fmtN(lv.s1.price) + ' (' + pct(lv.s1.distPct) + ')');
  if (z.stopPct) outs.push('−' + z.stopPct + ' % depuis votre prix');
  if (paid) outs.push('cours sous ' + fmtN(paid * 0.9) + ' (−10 % du prix du dirigeant)');
  if (outs.length && !hasPlan) sell.push('🛑 Sortir si : ' + outs.join(', ou ') + '.');
  var email = S.email || '', // adresse jamais gardée sur l'appareil : champ vide à chaque visite
    tgt = lsGet('target', '50'),
    stp = lsGet('stop', '30');
  var h =
    '<section class="card advice"><h3>Comment agir</h3><div class="cols2"><div><h4>Pour acheter</h4><ul class="plain">' +
    buy
      .map(function (t) {
        return '<li>' + t + '</li>';
      })
      .join('') +
    '</ul></div>' +
    '<div><h4>Pour revendre</h4><ul class="plain">' +
    sell
      .map(function (t) {
        return '<li>' + t + '</li>';
      })
      .join('') +
    '</ul></div></div>';
  h +=
    '</section><section class="card buybox"><details' +
    (lsGet('open.' + i, '') ? ' open' : '') +
    '><summary><span class="bb-ic" aria-hidden="true">🔔</span><span><b>Je l\'ai acheté : me prévenir pour revendre</b><small>Rappel à 6 mois, seuil de protection, vente d\'un dirigeant : un email.</small></span></summary>' +
    xpi(
      "Vos achats ne sont jamais publiés : le bouton prépare un email à vous-même, qu'Euro Signal lit chaque soir. Renvoyez-en un pour changer l'objectif."
    ) +
    '<div class="fgrid">' +
    fld(
      'Votre adresse Gmail (jamais enregistrée, à saisir à chaque visite)',
      '<input id="pos-email" type="email" autocomplete="email" value="' + esc(email) + '" placeholder="vous@gmail.com">'
    ) +
    fld(
      "Prix d'achat",
      '<input id="pos-price" inputmode="decimal" value="' +
        (last ? String(+last.toFixed(4)).replace('.', ',') : '') +
        '">'
    ) +
    fld("Date d'achat", '<input id="pos-date" type="date" value="' + esc(S.today) + '" max="' + esc(S.today) + '">') +
    fld('Objectif de hausse (%)', '<input id="pos-target" inputmode="decimal" value="' + esc(tgt) + '">') +
    fld('Seuil de protection (%)', '<input id="pos-stop" inputmode="decimal" value="' + esc(stp) + '">') +
    '</div>' +
    '<div class="row mt"><button data-a="posBuy" data-i="' +
    i +
    '">Préparer l\'email « Je l\'ai acheté »</button><button class="ghost" data-a="posSell" data-i="' +
    i +
    '">Je l\'ai vendu : arrêter le suivi</button></div>' +
    '</details></section>';
  return h;
}
function watchMail(i, on) {
  var x = S.inst[i] || (S.secCo && S.secCo.items && S.secCo.items[i]) || null,
    e = document.getElementById('watch-email'),
    to = e ? String(e.value || '').trim() : S.email || '';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
    notify('Indiquez votre adresse Gmail (celle configurée dans Euro Signal).', 'warn');
    return;
  }
  S.email = to; // gardée le temps de la visite seulement
  lsSet('watch.' + i, on ? S.today : '');
  var link = location.origin + location.pathname + '#' + (ES.isValidIsin(i) ? i : 'co=' + encodeURIComponent(i));
  var subject = '[Euro Signal] ' + (on ? 'Surveiller ' : 'Ne plus surveiller ') + i,
    mp = on ? manPlan(i) : null,
    num2 = function (v) {
      return String(+(+v).toPrecision(6)).replace('.', ',');
    };
  var body =
    'Société : ' +
    ((x && x.name) || i) +
    (ES.isValidIsin(i) ? '\nISIN : ' : '\nSymbole : ') +
    i +
    '\nDate : ' +
    S.today +
    (mp
      ? '\nEntrée ajustée : ' +
        num2(mp.e) +
        (mp.s ? '\nStop ajusté : ' + num2(mp.s) : '') +
        (mp.t ? '\nObjectif ajusté : ' + num2(mp.t) : '') +
        (mp.ref ? '\nCours à la demande : ' + num2(mp.ref) : '')
      : '') +
    '\n\n(' +
    (on
      ? "Euro Signal vous préviendra quand le plan d'entrée se déclenche. Pour arrêter : bouton « Ne plus surveiller » dans la fiche ou dans Alertes > Mes suivis : " +
        link
      : "Fin de la surveillance du plan d'entrée.") +
    " Email lu automatiquement chaque soir. Ne pas modifier l'objet.)";
  if (!window.__esMailHook) setTimeout(render, 300);
  var url =
    'mailto:' +
    encodeURIComponent(to) +
    '?subject=' +
    encodeURIComponent(subject) +
    '&body=' +
    encodeURIComponent(body);
  if (window.__esMailHook) {
    window.__esMailHook(url);
    return;
  }
  window.location.href = url;
}
function posMail(i, kind) {
  var x = S.inst[i] || (S.secCo && S.secCo.items && S.secCo.items[i]) || { name: i },
    idl = ES.isValidIsin(i) ? '\nISIN : ' : '\nSymbole : ',
    v = function (id) {
      var e = document.getElementById(id);
      return e ? String(e.value || '').trim() : '';
    };
  var to = v('pos-email');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
    notify('Indiquez votre adresse Gmail (celle configurée dans Euro Signal).', 'warn');
    return;
  }
  S.email = to; // gardée le temps de la visite seulement
  var subject, body;
  if (kind === 'buy') {
    var price = ES.parseNumber(v('pos-price')),
      tg = ES.parseNumber(v('pos-target')),
      sp = ES.parseNumber(v('pos-stop'));
    if (!(price > 0)) {
      notify("Indiquez le prix d'achat.", 'warn');
      return;
    }
    if (tg != null) lsSet('target', String(tg));
    if (sp != null) lsSet('stop', String(Math.abs(sp)));
    subject = '[Euro Signal] Position ' + i;
    body =
      'Société : ' +
      (x.name || i) +
      idl +
      i +
      "\nPrix d'achat : " +
      String(price).replace('.', ',') +
      "\nDate d'achat : " +
      (v('pos-date') || S.today) +
      (tg != null ? '\nObjectif de hausse : ' + String(tg).replace('.', ',') + ' %' : '') +
      (sp != null ? '\nSeuil de protection : ' + String(Math.abs(sp)).replace('.', ',') + ' %' : '') +
      "\n\n(Email lu automatiquement par Euro Signal chaque soir. Ne pas modifier l'objet.)";
    lsSet('open.' + i, '1');
  } else {
    subject = '[Euro Signal] Vente ' + i;
    body =
      'Société : ' +
      (x.name || i) +
      idl +
      i +
      '\nDate : ' +
      S.today +
      '\n\n(Fin du suivi de cette position par Euro Signal.)';
    lsSet('open.' + i, '');
  }
  var url =
    'mailto:' +
    encodeURIComponent(to) +
    '?subject=' +
    encodeURIComponent(subject) +
    '&body=' +
    encodeURIComponent(body);
  if (window.__esMailHook) {
    window.__esMailHook(url);
    return;
  } // tests automatiques
  window.location.href = url;
}
function kv(k, v) {
  return '<div><dt>' + k + '</dt><dd>' + esc(v) + '</dd></div>';
}
function gauge(label, v, sub, kind) {
  return (
    '<div class="gauge ' +
    kind +
    '"><span class="lbl">' +
    label +
    '</span><span class="val">' +
    v +
    '<small>/100</small></span><div class="track"><i style="width:' +
    Math.max(0, Math.min(100, v)) +
    '%"></i></div><span class="sub">' +
    sub +
    '</span></div>'
  );
}
function fld(l, input, wide) {
  var id = (input.match(/id="([^"]+)"/) || [])[1];
  return (
    '<label class="fld' +
    (wide ? ' wide' : '') +
    '"' +
    (id ? ' for="' + id + '"' : '') +
    '><span>' +
    l +
    '</span>' +
    input +
    '</label>'
  );
}

/** Supports et résistances : texte court d'un niveau (nombre de contacts ou plus haut / plus bas d'un an). */
function lvTouch(x) {
  return x.kind === 'high52'
    ? "plus haut d'un an"
    : x.kind === 'low52'
      ? "plus bas d'un an"
      : x.touches + ' contact' + (x.touches > 1 ? 's' : '') + (x.last ? ', dernier le ' + shortDate(x.last) : '');
}
function lvLine(isin) {
  var LV = S.inst[isin] && S.inst[isin].levels;
  if (!LV) return null;
  var s1 = (LV.supports || [])[0],
    r1 = (LV.resistances || [])[0];
  return { s1: s1 || null, r1: r1 || null, s2: (LV.supports || [])[1] || null, r2: (LV.resistances || [])[1] || null };
}
/** Historique 5 ans (une clôture par semaine et anciens achats) : chargé à la demande, quand la vue « 5 ans » est choisie. */
function loadLong() {
  if (S.longLoading || S.longLoaded) return;
  if (!S.longFile) {
    S.long = {};
    S.longLoaded = true;
    S.longError = 'local';
    return;
  }
  S.longLoading = true;
  getData(S.longFile)
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      d = defang(d);
      S.long = (d && d.items) || {};
      S.longLoaded = true;
      S.longLoading = false;
      render();
    })
    .catch(function () {
      S.long = {};
      S.longLoaded = true;
      S.longLoading = false;
      S.longError = 'reseau';
      render();
    });
}
/** Plan d'entrée : calculé chaque soir avec les plus hauts et plus bas du jour ; à défaut, recalculé ici sur les clôtures. */
function planOf(isin, adj) {
  var x = S.inst[isin] || {};
  if (x.plan && x.plan.verdict) return reclassPlan(x.plan);
  try {
    return ES.entryPlan(adj, { levels: x.levels || undefined });
  } catch (e) {
    return null;
  }
}
function chart(isin) {
  var p = S.prices[isin];
  if (!p) return '<p class="muted">Chargement des cours…</p>';
  if (!p.rows || !p.rows.length) {
    var xx = S.inst[isin] || {};
    return (
      '<p class="muted">' +
      (xx.ticker || (xx.stats && xx.stats.lastClose)
        ? 'Cours en cours de chargement ou publiés au prochain calcul du soir.'
        : 'Cours introuvables chez Yahoo Finance pour cet ISIN : société retirée de la cote, ligne secondaire (droits, actions nouvelles) ou marché que Yahoo ne suit pas (Spotlight, NGM).') +
      '</p>'
    );
  }
  var splits = (S.ev[isin] && S.ev[isin].splits) || [];
  var adj = ES.adjustedSeries(ES.normalizeSeries(p.rows), splits).slice(-260);
  var five = S.range === '5y',
    note = '';
  var segOf = function (f5) {
    return (
      '<div class="seg" role="group" aria-label="Période du graphique"><button data-a="range" data-v="1y" class="' +
      (f5 ? '' : 'on') +
      '" aria-pressed="' +
      !f5 +
      '">1 an</button><button data-a="range" data-v="5y" class="' +
      (f5 ? 'on' : '') +
      '" aria-pressed="' +
      f5 +
      '">5 ans</button></div>'
    );
  };
  var L5 = null;
  if (five) {
    if (!S.longLoaded) {
      loadLong();
      if (!S.longLoaded) return segOf(true) + '<p class="muted">Chargement de l\'historique sur 5 ans…</p>';
    }
    L5 = S.long && S.long[isin];
    if (!L5 || !Array.isArray(L5.w) || L5.w.length < 20) {
      five = false;
      note =
        S.longError === 'local'
          ? '⚠️ Vue 5 ans pas encore disponible : les 5 ans de cours arrivent avec le prochain calcul du soir. Le graphique ci-dessous reste sur 1 an.'
          : S.longError
            ? '⚠️ Historique 5 ans illisible pour le moment : le graphique ci-dessous reste sur 1 an.'
            : "⚠️ Pas d'historique sur 5 ans pour ce titre (cotation récente ou cours introuvables) : le graphique ci-dessous reste sur 1 an.";
    }
  }
  var seg = segOf(five);
  var plan = planOf(isin, adj);
  // série affichée : journalière (1 an) ou hebdomadaire (5 ans), raccordée au dernier cours journalier
  var ser = adj;
  if (five) {
    var w = L5.w.filter(function (r) {
        return r && r[1] > 0;
      }),
      wl = w[w.length - 1],
      k0 = -1;
    for (var q = adj.length - 1; q >= 0; q--)
      if (adj[q][0] <= wl[0]) {
        k0 = q;
        break;
      }
    var ratio = k0 >= 0 && wl[1] > 0 ? adj[k0][4] / wl[1] : 1;
    if (!(ratio > 0.5 && ratio < 2)) ratio = 1;
    ser = w.map(function (r) {
      return [r[0], null, null, null, r[1] * ratio, null];
    });
    if (adj[adj.length - 1][0] > wl[0]) ser.push(adj[adj.length - 1]);
  }
  if (five && ES.daysBetween(ser[0][0], ser[ser.length - 1][0]) < 1600)
    note +=
      (note ? ' ' : '') +
      'ℹ️ Cours disponibles depuis le ' +
      shortDate(ser[0][0]) +
      " seulement : la vue 5 ans montre tout l'historique connu.";
  // saut brutal de cours (regroupement d'actions non ajusté, augmentation de capital, scission) : signalé, jamais corrigé en silence
  for (var jq = 1; jq < ser.length; jq++) {
    var ra = ser[jq - 1][4] > 0 ? ser[jq][4] / ser[jq - 1][4] : 1;
    if (ra > 3 || ra < 1 / 3) {
      note +=
        (note ? ' ' : '') +
        '⚠️ Saut de cours ' +
        (ra > 1 ? '×' + fmtN(ra, 1) : '÷' + fmtN(1 / ra, 1)) +
        ' ' +
        (five ? 'la semaine du ' : 'le ') +
        shortDate(ser[jq][0]) +
        " : vraie chute ou envolée, ou bien augmentation de capital, regroupement d'actions ou scission que la source n'a pas ajustés. À vérifier avant de comparer aux cours d'avant.";
      break;
    }
  }
  var narrow = typeof window !== 'undefined' && window.innerWidth < 560;
  var W = narrow ? 380 : 640,
    H = narrow ? 250 : 230,
    L = narrow ? 48 : 62,
    R = 8,
    T = 12,
    B = 26;
  var n = ser.length,
    last = ser[n - 1][4],
    lo = Infinity,
    hi = -Infinity;
  ser.forEach(function (r) {
    lo = Math.min(lo, r[3] != null ? r[3] : r[4]);
    hi = Math.max(hi, r[2] != null ? r[2] : r[4]);
  });
  var refs = S.refs[isin] || {},
    marks = [];
  if (five)
    (L5.buys || []).forEach(function (b) {
      if (b && b[1] > 0 && b[0] >= ser[0][0]) {
        marks.push({ d: b[0], p: b[1] * (ratio || 1), buy: true, who: b[2], x: b[3], old: true, ceo: b[4] });
      }
    });
  else
    (S.tx[isin] || []).forEach(function (t) {
      var r = refs[t.id];
      if (!r || !r.available || t.status === 'annulee' || t.txDate < ser[0][0]) return;
      if (t.type !== 'achat' && t.type !== 'vente') return;
      if (r.priceSuspect) return; // prix déclaré aberrant (quantité et prix inversés, virgule…) : ignoré, comme dans les calculs
      marks.push({ d: t.txDate, p: r.paidAdj, buy: t.type === 'achat', who: t.person });
    });
  // un point très loin des cours du graphique (erreur de saisie, autre catégorie d'actions) ne doit jamais écraser la courbe
  var lo0 = lo,
    hi0 = hi,
    dropped = 0;
  marks = marks.filter(function (m) {
    var ok = m.p > 0 && m.p >= lo0 * 0.5 && m.p <= hi0 * 2;
    if (!ok) dropped++;
    return ok;
  });
  if (dropped)
    note +=
      (note ? ' ' : '') +
      'ℹ️ ' +
      dropped +
      ' prix déclaré' +
      (dropped > 1 ? 's' : '') +
      ' sans rapport avec les cours (erreur de saisie probable) non affiché' +
      (dropped > 1 ? 's' : '') +
      ' sur le graphique.';
  marks.forEach(function (m) {
    lo = Math.min(lo, m.p);
    hi = Math.max(hi, m.p);
  });
  // supports et résistances : ceux du calcul du soir, sinon recalculés ici sur l'année de cours (jamais de graphique sans niveaux)
  var LV = ES.completeLevels((S.inst[isin] && S.inst[isin].levels) || ES.supportResistance(adj), adj),
    lvl = LV
      ? (LV.supports || [])
          .map(function (x) {
            return { p: x.price, s: true, x: x };
          })
          .concat(
            (LV.resistances || []).map(function (x) {
              return { p: x.price, s: false, x: x };
            })
          )
      : [];
  lvl = lvl.filter(function (v) {
    return v.p > 0 && isFinite(v.p) && v.p >= lo * 0.75 && v.p <= hi * 1.35;
  });
  if (!lvl.length && adj.length < 10)
    note += (note ? ' ' : '') + 'ℹ️ Cotation trop récente : supports et résistances après quelques semaines de cours.';
  lvl.forEach(function (v) {
    lo = Math.min(lo, v.p);
    hi = Math.max(hi, v.p);
  });
  var pad = (hi - lo) * 0.06 || 1;
  lo -= pad;
  hi += pad;
  L = Math.max(L, 12 + 7 * fmtN(hi, hi < 10 ? 2 : 1).length); // cours à 4 chiffres (1 966,3) : marge élargie pour ne pas couper l'étiquette
  var xs = function (k) {
    return L + (W - L - R) * (n === 1 ? 0.5 : k / (n - 1));
  };
  var ys = function (v) {
    return T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  };
  var idx = {};
  ser.forEach(function (r, k) {
    idx[r[0]] = k;
  });
  var path = ser
    .map(function (r, k) {
      return (k ? 'L' : 'M') + xs(k).toFixed(1) + ' ' + ys(r[4]).toFixed(1);
    })
    .join(' ');
  var area = path + ' L' + xs(n - 1).toFixed(1) + ' ' + (H - B) + ' L' + xs(0).toFixed(1) + ' ' + (H - B) + ' Z';
  var ticks = [lo + pad, (lo + hi) / 2, hi - pad];
  var svg =
    '<svg viewBox="0 0 ' +
    W +
    ' ' +
    H +
    '" class="chart" role="img" aria-label="Cours de clôture ajustés ' +
    (five ? 'sur 5 ans (une clôture par semaine)' : 'des 260 dernières séances') +
    ', achats des dirigeants, supports, résistances ">';
  ticks.forEach(function (v) {
    svg +=
      '<line x1="' +
      L +
      '" x2="' +
      (W - R) +
      '" y1="' +
      ys(v).toFixed(1) +
      '" y2="' +
      ys(v).toFixed(1) +
      '" class="grid"/><text x="' +
      (L - 6) +
      '" y="' +
      (ys(v) + 4).toFixed(1) +
      '" text-anchor="end" class="ax">' +
      fmtN(v, v < 10 ? 2 : 1) +
      '</text>';
  });
  svg += '<path d="' + area + '" class="area"/>';
  // supports (vert) et résistances (rouge) : pointillés sur toute la largeur ; étiquettes à gauche, écartées d'au moins 10 px
  var lab = lvl
    .map(function (v) {
      return { v: v, y: ys(v.p) };
    })
    .sort(function (a, b) {
      return a.y - b.y;
    });
  lab.forEach(function (o, k) {
    o.ty = o.y - 3;
    if (k && o.ty - lab[k - 1].ty < 10) o.ty = lab[k - 1].ty + 10;
  });
  var lvOver = lab.length ? lab[lab.length - 1].ty - (H - B - 4) : 0;
  if (lvOver > 0)
    lab.forEach(function (o) {
      o.ty -= lvOver;
    }); // étiquettes serrées en bas : remontées au-dessus de l'axe des dates
  var lvLab = '';
  lab.forEach(function (o) {
    var v = o.v,
      y = o.y.toFixed(1);
    svg +=
      '<line x1="' +
      L +
      '" x2="' +
      (W - R) +
      '" y1="' +
      y +
      '" y2="' +
      y +
      '" class="' +
      (v.s ? 'lv-sup' : 'lv-res') +
      '"><title>' +
      (v.s ? 'Support' : 'Résistance') +
      ' ' +
      fmtN(v.p) +
      ' (' +
      pct(v.x.distPct) +
      ', ' +
      lvTouch(v.x) +
      ')</title></line>';
    lvLab +=
      '<text x="' +
      (L + 4) +
      '" y="' +
      o.ty.toFixed(1) +
      '" class="ax lv-t ' +
      (v.s ? 'lv-ts' : 'lv-tr') +
      '">' +
      (v.s ? 'Support ' : 'Résistance ') +
      fmtN(v.p, v.p < 10 ? 2 : 1) +
      ' (' +
      pct(v.x.distPct) +
      ')</text>';
  });
  svg += '<path d="' + path + '" class="line"/>';
  svg +=
    '<text x="' +
    L +
    '" y="' +
    (H - 6) +
    '" class="ax">' +
    shortDate(ser[0][0]) +
    '</text><text x="' +
    (W - R) +
    '" y="' +
    (H - 6) +
    '" text-anchor="end" class="ax">' +
    shortDate(ser[n - 1][0]) +
    '</text>';
  marks.forEach(function (m) {
    var k = idx[m.d];
    if (k == null) {
      k = ser.findIndex(function (r) {
        return r[0] >= m.d;
      });
      if (k < 0) return;
    }
    var cx = xs(k),
      cy = ys(m.p);
    if (m.old)
      svg +=
        '<circle cx="' +
        cx.toFixed(1) +
        '" cy="' +
        cy.toFixed(1) +
        '" r="' +
        (m.ceo ? 5 : 4) +
        '" class="mk-old ' +
        (m.x == null ? 'mk-na' : m.x > 0 ? 'mk-ok' : 'mk-ko') +
        '"><title>Achat ' +
        esc(m.who || '') +
        ' le ' +
        m.d +
        ' à ' +
        fmtN(m.p) +
        (m.x == null
          ? ' — résultat à 6 mois pas encore connu'
          : ' — 6 mois après : ' + pct(m.x) + " par rapport à l'indice") +
        '</title></circle>';
    else
      svg += m.buy
        ? '<circle cx="' +
          cx.toFixed(1) +
          '" cy="' +
          cy.toFixed(1) +
          '" r="5" class="mk-buy"><title>Achat ' +
          esc(m.who || '') +
          ' le ' +
          m.d +
          ' à ' +
          fmtN(m.p) +
          '</title></circle>'
        : '<path d="M' +
          (cx - 5).toFixed(1) +
          ' ' +
          (cy - 4).toFixed(1) +
          ' L' +
          (cx + 5).toFixed(1) +
          ' ' +
          (cy - 4).toFixed(1) +
          ' L' +
          cx.toFixed(1) +
          ' ' +
          (cy + 5).toFixed(1) +
          ' Z" class="mk-sell"><title>Vente ' +
          esc(m.who || '') +
          ' le ' +
          m.d +
          '</title></path>';
  });
  svg += '<circle cx="' + xs(n - 1).toFixed(1) + '" cy="' + ys(last).toFixed(1) + '" r="3.5" class="last"/>' + lvLab;
  svg += '</svg>';
  var old = marks.filter(function (m) {
      return m.old;
    }),
    oldK = old.filter(function (m) {
      return m.x != null;
    }),
    oldW = oldK.filter(function (m) {
      return m.x > 0;
    }).length;
  var lg = five
    ? '<span><i class="lg-buy"></i>achat passé : a battu l\'indice 6 mois après</span><span><i class="lg-buy lg-ko"></i>ne l\'a pas battu</span><span><i class="lg-buy lg-na"></i>trop récent</span>'
    : '<span><i class="lg-buy"></i>achat d\'initié (prix payé)</span><span><i class="lg-sell"></i>vente</span>';
  if (lvl.length) lg += '<span><i class="lg-sup"></i>support</span><span><i class="lg-res"></i>résistance</span>';
  var head =
    five && old.length
      ? '<p class="oldsum">' +
        old.length +
        ' achat' +
        (old.length > 1 ? 's' : '') +
        ' de dirigeants sur 5 ans' +
        (oldK.length
          ? ' ; ' + oldW + ' sur ' + oldK.length + ' ' + (oldW > 1 ? 'ont' : 'a') + " battu l'indice 6 mois après"
          : '') +
        '.</p>'
      : '';
  return (
    seg +
    (note ? '<p class="small"><b>' + note + '</b></p>' : '') +
    head +
    '<div class="chartwrap">' +
    svg +
    '</div><p class="legend2">' +
    lg +
    '<span class="muted">' +
    (five
      ? 'Une clôture par semaine, ajustée des splits et dividendes'
      : 'Clôtures ajustées des splits et dividendes') +
    ' · source ' +
    esc(p.source || 'n.d.') +
    ' · graphique depuis le ' +
    shortDate(ser[0][0]) +
    (p.truncatedFrom ? ' (tronqué au ' + p.truncatedFrom + ')' : '') +
    '</span></p>' +
    planCard(isin, plan, adj)
  );
}
/** Panneau du plan d'entrée : 3 derniers mois de cours et 3 mois à venir (cône de volatilité, zone d'achat ou déclencheur, stop, objectif). */
function planChart(isin, adj, plan) {
  if (!plan || !plan.primary || !(plan.sd > 0) || !adj || adj.length < 30) return '';
  var past = adj.slice(-Math.min(63, adj.length)),
    np = past.length,
    fut = plan.horizon || 60,
    last = past[np - 1][4],
    pr = plan.primary;
  var narrow = typeof window !== 'undefined' && window.innerWidth < 560;
  var W = narrow ? 380 : 640,
    H = narrow ? 230 : 210,
    L = narrow ? 48 : 62,
    R = 8,
    T = 10,
    B = 24;
  var cone = [];
  for (var c = 0; c <= fut; c += 5) {
    var sg = plan.sd * Math.sqrt(c);
    cone.push([
      c,
      last * Math.exp(-1.645 * sg),
      last * Math.exp(-sg),
      last * Math.exp(sg),
      last * Math.exp(1.645 * sg),
    ]);
  }
  var f = function (v) {
      return fmtN(v, v < 10 ? 2 : 1);
    },
    plv = [];
  if (pr.key === 'manual') plv.push({ k: 'trig', a: pr.entry, t: 'Entrée ' + f(pr.entry), c: 'pl-tt' });
  else if (pr.key === 'support' || pr.key === 'retest')
    plv.push({
      k: 'zone',
      a: pr.zoneLo,
      b: pr.zoneHi,
      t: "Zone d'entrée " + f(pr.zoneLo) + '–' + f(pr.zoneHi),
      c: 'pl-tz',
    });
  else if (pr.key === 'breakout')
    plv.push({ k: 'trig', a: pr.trigger, t: 'Entrée si clôture > ' + f(pr.trigger), c: 'pl-tt' });
  else
    plv.push({
      k: 'zone',
      a: Math.min(pr.entry, last) - 0.5 * (plan.atr || 0),
      b: Math.max(pr.entry, last),
      t: "Zone d'entrée",
      c: 'pl-tz',
    });
  if (pr.stop > 0) plv.push({ k: 'stop', a: pr.stop, t: 'Stop ' + f(pr.stop), c: 'pl-ts' });
  if (pr.target > 0) plv.push({ k: 'tgt', a: pr.target, t: 'Objectif ' + f(pr.target), c: 'pl-tg' });
  // support et résistance les plus proches, toujours visibles ; s'ils coïncident avec un niveau du plan, celui-ci les nomme.
  // Niveaux du calcul du soir (plus hauts et plus bas du jour), ceux sur lesquels le plan est bâti et que montre le graphique
  // des cours ; à défaut seulement, recalculés ici sur les clôtures (ils différaient alors d'un graphique à l'autre)
  var LVp = ES.completeLevels(plan.levels || (S.inst[isin] || {}).levels || ES.supportResistance(adj), adj),
    near = function (p) {
      return plv.filter(function (v) {
        return (
          Math.abs(v.a - p) / p < 0.012 ||
          (v.b != null && Math.abs(v.b - p) / p < 0.012) ||
          (v.b != null && p > Math.min(v.a, v.b) && p < Math.max(v.a, v.b))
        );
      })[0];
    };
  if (LVp) {
    [
      [(LVp.supports || [])[0], true],
      [(LVp.resistances || [])[0], false],
    ].forEach(function (q) {
      var x = q[0];
      if (!x || !(x.price > 0)) return;
      var hit = near(x.price);
      if (hit) {
        // le niveau du plan porte aussi le nom du support ou de la résistance qu'il recouvre ; une résistance collée au support
        // déjà tracé (cours coincé entre les deux) partage sa ligne au lieu de disparaître
        if (hit.k === 'sup' || hit.k === 'res') hit.t = 'Support et résistance ' + f(hit.a);
        else if (!/support|résistance/i.test(hit.t)) hit.t += q[1] ? ' (support)' : ' (résistance)';
        else if (q[1] && !/support/i.test(hit.t)) hit.t = hit.t.replace('(résistance)', '(support et résistance)');
        else if (!q[1] && !/résistance/i.test(hit.t)) hit.t = hit.t.replace('(support)', '(support et résistance)');
      } else
        plv.push({
          k: q[1] ? 'sup' : 'res',
          a: x.price,
          t: (q[1] ? 'Support ' : 'Résistance ') + f(x.price),
          c: q[1] ? 'lv-ts' : 'lv-tr',
        });
    });
  }
  var lo = Infinity,
    hi = -Infinity,
    inc = function (v) {
      if (v > 0 && isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    };
  past.forEach(function (r) {
    inc(r[4]);
  });
  inc(cone[cone.length - 1][2]);
  inc(cone[cone.length - 1][3]);
  plv.forEach(function (v) {
    inc(v.a);
    if (v.b != null) inc(v.b);
  });
  // biseau : droites des sommets et des creux des 3 derniers mois (calculées le soir, sinon ici sur les clôtures)
  var wd =
    plan.wedge ||
    (function () {
      try {
        return ES.wedge(adj);
      } catch (e) {
        return null;
      }
    })();
  if (wd && wd.type === 'none') wd = null;
  var w0 = 0;
  if (wd) {
    var wk = past.findIndex(function (r) {
      return r[0] >= wd.from;
    });
    w0 = wk < 0 ? 0 : wk;
    inc(wd.upperNow);
    inc(wd.lowerNow);
  }
  var pad = (hi - lo) * 0.08 || 1;
  lo -= pad;
  hi += pad;
  L = Math.max(L, 12 + 7 * fmtN(hi, hi < 10 ? 2 : 1).length);
  var tot = np - 1 + fut,
    xs = function (k) {
      return L + ((W - L - R) * k) / tot;
    },
    xNow = xs(np - 1),
    ys = function (v) {
      return T + (H - T - B) * (1 - (v - lo) / (hi - lo));
    };
  var cid = 'pc' + isin.replace(/\W/g, ''),
    svg =
      '<svg viewBox="0 0 ' +
      W +
      ' ' +
      H +
      '" class="chart" role="img" aria-label="Plan d\'entrée : 3 derniers mois de cours et projection sur 3 mois">';
  svg +=
    '<defs><clipPath id="' +
    cid +
    '"><rect x="' +
    L +
    '" y="' +
    T +
    '" width="' +
    (W - R - L) +
    '" height="' +
    (H - T - B) +
    '"/></clipPath></defs>';
  [lo + pad, (lo + hi) / 2, hi - pad].forEach(function (v) {
    svg +=
      '<line x1="' +
      L +
      '" x2="' +
      (W - R) +
      '" y1="' +
      ys(v).toFixed(1) +
      '" y2="' +
      ys(v).toFixed(1) +
      '" class="grid"/><text x="' +
      (L - 6) +
      '" y="' +
      (ys(v) + 4).toFixed(1) +
      '" text-anchor="end" class="ax">' +
      fmtN(v, v < 10 ? 2 : 1) +
      '</text>';
  });
  svg +=
    '<rect x="' +
    xNow.toFixed(1) +
    '" y="' +
    T +
    '" width="' +
    (W - R - xNow).toFixed(1) +
    '" height="' +
    (H - T - B) +
    '" class="futbg"/>';
  var band = function (a, b) {
    return (
      'M' +
      cone
        .map(function (c) {
          return xs(np - 1 + c[0]).toFixed(1) + ' ' + ys(c[a]).toFixed(1);
        })
        .join(' L') +
      ' L' +
      cone
        .slice()
        .reverse()
        .map(function (c) {
          return xs(np - 1 + c[0]).toFixed(1) + ' ' + ys(c[b]).toFixed(1);
        })
        .join(' L') +
      ' Z'
    );
  };
  var cl = cone[cone.length - 1];
  svg +=
    '<g clip-path="url(#' +
    cid +
    ')"><path d="' +
    band(4, 1) +
    '" class="cone90"><title>9 cas sur 10 d\'ici 3 mois : entre ' +
    f(cl[1]) +
    ' et ' +
    f(cl[4]) +
    '</title></path><path d="' +
    band(3, 2) +
    '" class="cone68"><title>2 cas sur 3 d\'ici 3 mois : entre ' +
    f(cl[2]) +
    ' et ' +
    f(cl[3]) +
    '</title></path>';
  var labs = [];
  plv.forEach(function (v) {
    if (v.k === 'zone') {
      var y1 = ys(v.b),
        y2 = ys(v.a);
      svg +=
        '<rect x="' +
        L +
        '" y="' +
        Math.min(y1, y2).toFixed(1) +
        '" width="' +
        (W - R - L) +
        '" height="' +
        Math.max(3, Math.abs(y2 - y1)).toFixed(1) +
        '" class="pl-zone"><title>' +
        esc(v.t) +
        '</title></rect>';
      labs.push({ y: Math.min(y1, y2) - 3, t: v.t, c: v.c });
    } else {
      var yy = ys(v.a).toFixed(1);
      svg +=
        '<line x1="' +
        L +
        '" x2="' +
        (W - R) +
        '" y1="' +
        yy +
        '" y2="' +
        yy +
        '" class="' +
        (v.k === 'trig'
          ? 'pl-trig'
          : v.k === 'stop'
            ? 'pl-stop'
            : v.k === 'sup'
              ? 'lv-sup'
              : v.k === 'res'
                ? 'lv-res'
                : 'pl-tgt') +
        '"><title>' +
        esc(v.t) +
        '</title></line>';
      labs.push({ y: ys(v.a) - 3, t: v.t, c: v.c });
    }
  });
  if (wd) {
    var kEnd = tot - w0,
      wl = function (l, cls, t) {
        return (
          '<line x1="' +
          xs(w0).toFixed(1) +
          '" y1="' +
          ys(l.a).toFixed(1) +
          '" x2="' +
          xs(tot).toFixed(1) +
          '" y2="' +
          ys(l.a + l.b * kEnd).toFixed(1) +
          '" class="' +
          cls +
          '"><title>' +
          t +
          '</title></line>'
        );
      };
    svg +=
      wl(wd.upper, 'pl-wdg', esc(wd.label) + ' : droite haute (sommets), ' + f(wd.upperNow) + " aujourd'hui") +
      wl(wd.lower, 'pl-wdg', esc(wd.label) + ' : droite basse (creux), ' + f(wd.lowerNow) + " aujourd'hui");
  }
  svg +=
    '</g><line x1="' +
    xNow.toFixed(1) +
    '" x2="' +
    xNow.toFixed(1) +
    '" y1="' +
    T +
    '" y2="' +
    (H - B) +
    '" class="now"/>';
  if (wd) svg += '<text x="' + (L + 4) + '" y="' + (T + 10) + '" class="ax pl-t pl-tw">' + esc(wd.label) + '</text>';
  svg +=
    '<path d="' +
    past
      .map(function (r, k) {
        return (k ? 'L' : 'M') + xs(k).toFixed(1) + ' ' + ys(r[4]).toFixed(1);
      })
      .join(' ') +
    '" class="line"/><circle cx="' +
    xNow.toFixed(1) +
    '" cy="' +
    ys(last).toFixed(1) +
    '" r="3.5" class="last"><title>Dernier cours ' +
    f(last) +
    '</title></circle>';
  labs
    .sort(function (a, b) {
      return a.y - b.y;
    })
    .forEach(function (o, k, A) {
      if (o.y < T + 9) o.y = T + 9;
      if (k && o.y - A[k - 1].y < 11) o.y = A[k - 1].y + 11;
    });
  labs.forEach(function (o) {
    svg +=
      '<text x="' +
      (W - R - 3) +
      '" y="' +
      o.y.toFixed(1) +
      '" text-anchor="end" class="ax pl-t ' +
      o.c +
      '">' +
      esc(o.t) +
      '</text>';
  });
  svg +=
    '<text x="' +
    L +
    '" y="' +
    (H - 6) +
    '" class="ax">' +
    shortDate(past[0][0]) +
    '</text><text x="' +
    xNow.toFixed(1) +
    '" y="' +
    (H - 6) +
    '" text-anchor="middle" class="ax">aujourd\'hui</text><text x="' +
    (W - R) +
    '" y="' +
    (H - 6) +
    '" text-anchor="end" class="ax">+3 mois</text></svg>';
  return (
    '<div class="chartwrap">' +
    svg +
    '</div><p class="legend2">' +
    (wd ? '<span><i class="lg-wdg"></i>' + esc(wd.label) + ' (droites des sommets et des creux)</span>' : '') +
    '<span><i class="lg-cone"></i>Cours probable dans 3 mois : entre ' +
    f(cl[2]) +
    ' et ' +
    f(cl[3]) +
    ' 2 fois sur 3 (zone foncée), entre ' +
    f(cl[1]) +
    ' et ' +
    f(cl[4]) +
    ' 9 fois sur 10</span></p>'
  );
}
/** Carte « Plan d'entrée » : que faire maintenant, à quel prix, avec quel stop, et ce qu'en disent nos données. */
/** Devise de cotation d'une société (dossier Euro Signal ou fiche du catalogue). */
function curOfKey(k) {
  var x = S.inst[k] || (S.secCo && S.secCo.items && S.secCo.items[k]) || null;
  return x ? x.currency || (x.stats && x.stats.currency) || null : null;
}
/** Équivalent en euros d'un prix coté dans une autre devise (pence pour Londres) : « ≈ 4,24 € ». */
function eurHint(v, cur) {
  if (v == null || !cur || cur === 'EUR') return '';
  var e = ES.toEur(v, cur);
  return e == null ? '' : ' <small class="eurh">≈\u00a0' + fmtN(e, e < 10 ? 2 : 1) + '\u00a0€</small>';
}
function curName(cur) {
  return cur === 'GBp' || cur === 'GBX' ? 'pence' : cur;
}
/** Plan d'entrée ajusté à la main (✏️) : { e: entrée, s: stop, t: objectif, ref: cours le jour du réglage, at: date }, sur l'appareil. */
function manPlan(id) {
  try {
    var m = JSON.parse(lsGet('plan.' + id, '') || 'null');
    return m && m.e > 0 ? m : null;
  } catch (e) {
    return null;
  }
}
function manPrimary(base, m) {
  var pc = function (v) {
    return v > 0 ? Math.round((v / m.e - 1) * 1000) / 10 : null; // comme le plan calculé : écart au prix d'entrée
  };
  return Object.assign({}, base, {
    key: 'manual',
    title: 'Plan ajusté à la main',
    entry: m.e,
    zoneLo: m.e,
    zoneHi: m.e,
    trigger: null,
    stop: m.s || null,
    stopPct: pc(m.s),
    target: m.t || null,
    targetPct: pc(m.t),
    rr: m.s > 0 && m.t > 0 && m.e > m.s ? Math.round(((m.t - m.e) / (m.e - m.s)) * 10) / 10 : null,
    prob: null, // la probabilité calculée valait pour l'objectif automatique
    bounced: false,
    touched: false,
  });
}
function planCard(isin, plan, adj) {
  if (!plan || !plan.primary) return '';
  var lastC = adj && adj.length ? adj[adj.length - 1][4] : plan.last,
    auto = plan.primary,
    man = manPlan(isin);
  if (man)
    plan = Object.assign({}, plan, {
      primary: manPrimary(plan.primary, man),
      alt: null,
      // au prix choisi (à 1 % près) : ✅ ; sinon ⏳ en attente du repli ou de la hausse jusqu'à ce prix
      verdict:
        lastC > 0 && Math.abs(lastC / man.e - 1) <= 0.01 ? 'buyNow' : lastC > man.e ? 'waitSupport' : 'waitBreakout',
      label:
        'Plan ajusté à la main : entrée ' +
        fmtN(man.e, man.e < 10 ? 2 : 1) +
        (man.s ? ', stop ' + fmtN(man.s, man.s < 10 ? 2 : 1) : '') +
        (man.t ? ', objectif ' + fmtN(man.t, man.t < 10 ? 2 : 1) : ''),
    });
  var pcur = curOfKey(isin);
  var V = { buyNow: ['good', '✅'], waitSupport: ['warn', '⏳'], waitBreakout: ['warn', '⏳'], avoid: ['bad', '⛔'] }[
    plan.verdict
  ] || ['neutral', '•'];
  var line = function (o, main) {
    if (!o) return '';
    var st =
      o.key === 'support' || o.key === 'retest'
        ? o.bounced
          ? ' · rebond en cours'
          : o.touched
            ? ' · niveau touché, rebond à confirmer'
            : ''
        : '';
    var lv = function (ic, lbl, v, pc) {
      return (
        '<span><small>' +
        ic +
        ' ' +
        lbl +
        '</small><b>' +
        fmtN(v, v < 10 ? 2 : 1) +
        '</b>' +
        eurHint(v, pcur) +
        (pc != null ? '<small class="' + (pc >= 0 ? 'pos' : 'neg') + '">' + pct(pc) + '</small>' : '') +
        '</span>'
      );
    };
    var en = o.key === 'breakout' ? o.trigger : o.key === 'highs' || o.key === 'manual' ? o.entry : o.zoneHi;
    return (
      '<li' +
      (main ? ' class="main"' : '') +
      '><b>' +
      esc(o.title) +
      '</b><small class="lhow">' +
      (o.key === 'manual'
        ? 'niveaux choisis à la main, gardés sur cet appareil'
        : o.key === 'breakout'
          ? 'sur clôture au-dessus'
          : o.key === 'highs'
            ? 'au cours'
            : 'zone ' +
              fmtN(o.zoneLo, o.zoneLo < 10 ? 2 : 1) +
              ' – ' +
              fmtN(o.zoneHi, o.zoneHi < 10 ? 2 : 1) +
              ', sur clôture de rebond') +
      st +
      '</small>' +
      '<div class="lvls">' +
      lv('🟢', 'Entrée', en) +
      lv('🛑', 'Stop', o.stop, o.stopPct) +
      lv('🎯', 'Objectif', o.target, o.targetPct) +
      '</div>' +
      '<small class="lmeta">' +
      [
        o.rr != null
          ? 'gain/risque <b class="' +
            (o.rr >= 2 ? 'pos' : o.rr < 1.2 ? 'neg' : '') +
            '">' +
            String(o.rr).replace('.', ',') +
            '</b>'
          : null,
        o.prob != null ? 'objectif atteint 3 mois : ' + o.prob + ' %' : null,
        main && o.sizePct ? 'ligne ≤ ' + o.sizePct + ' %' : null,
      ]
        .filter(Boolean)
        .join(' · ') +
      '</small></li>'
    );
  };
  var pr = plan.primary,
    obsKey = pr.key === 'breakout' || pr.key === 'retest' ? 'breakout' : pr.key === 'support' ? 'nearSupport' : null;
  var ob =
    obsKey &&
    S.snapshot &&
    S.snapshot.learning &&
    (S.snapshot.learning.observe || []).filter(function (o) {
      return o.feature === obsKey;
    })[0];
  var hz = (S.cfg.learning && S.cfg.learning.horizon) || 60;
  var obs =
    ob && ob.nWith
      ? '<p>📏 Sur nos données, achats de dirigeants faits ' +
        (obsKey === 'breakout' ? 'juste après une cassure' : "près d'un support") +
        ' : ' +
        pct(ob.meanWith) +
        " par rapport à l'indice " +
        hz +
        ' séances plus tard, contre ' +
        pct(ob.meanWithout) +
        ' pour les autres (' +
        ob.nWith +
        ' cas' +
        (/^en observation/.test(ob.action || '') ? ', mesure en cours' : ', ' + esc(ob.action)) +
        ').</p>'
      : '';
  var inEs = !!S.inst[isin];
  var PS = S.snapshot && S.snapshot.planStudy,
    histH = '';
  if (PS && PS.byVerdict && !man) {
    var hv = PS.byVerdict[plan.verdict] && PS.byVerdict[plan.verdict].h60,
      fk = ES.figureKey(plan.wedge),
      hf = fk && PS.byFigure[fk] && PS.byFigure[fk].h60;
    var hl = function (lbl, r) {
      if (!r || r.n < 30) return '';
      var net = r.t != null && Math.abs(r.t) >= 2;
      return (
        '<div class="hrow"><p class="small"><b>' +
        lbl +
        '</b> <span class="muted">· ' +
        r.n +
        ' cas</span></p><div class="mts">' +
        mini(
          "Face à l'indice",
          pct(r.mean),
          r.mean / 100,
          -0.15,
          0.15,
          true,
          "Écart moyen avec l'indice européen 60 séances plus tard"
        ) +
        '<div class="mt" title="Part des cas qui ont fait mieux que l\'indice"><span class="mt-l">Battent l\'indice</span><b class="mt-v ' +
        (r.beatPct >= 50 ? 'pos' : 'neg') +
        '">' +
        r.beatPct +
        ' %</b><span class="mt-b"><i class="lv" style="left:0;width:' +
        Math.max(0, Math.min(100, r.beatPct)) +
        '%"></i><s style="left:50%"></s></span></div>' +
        mini(
          'vs les autres',
          (r.vsAll >= 0 ? '+' : '') + String(r.vsAll).replace('.', ',') + ' pt',
          r.vsAll / 100,
          -0.1,
          0.1,
          true,
          'Écart avec la moyenne de toutes les sociétés aux mêmes dates'
        ) +
        '</div>' +
        '<p class="sp-cap">' +
        (net
          ? '✔︎ Écart net (statistiquement significatif)'
          : 'Écart non significatif : à prendre comme un repère, pas une preuve') +
        '</p></div>'
      );
    };
    var lines =
      hl('Plans « ' + esc(plan.label) + ' »', hv) +
      (fk && fk !== 'none' ? hl('Figures « ' + esc(ES.FIGURES[fk][1].toLowerCase()) + ' »', hf) : '');
    if (lines)
      histH =
        '<p class="sp-cap">60 séances plus tard. Plan recalculé chaque semaine du ' +
        shortDate(PS.from) +
        ' au ' +
        shortDate(PS.to) +
        ' avec les seuls cours connus ce jour-là, frais inclus. Le trait fin marque zéro ou 50 %.</p>' +
        lines;
  }
  var em = S.email || ''; // champ vide par défaut (adresse jamais enregistrée)
  var wd = lsGet('watch.' + isin, ''); // fiches Euro Signal (ISIN) et fiches du catalogue (symbole Yahoo)
  var watchH = wd
    ? '<details class="watch" open><summary>🔔 Plan surveillé depuis le ' +
      shortDate(wd) +
      '</summary><p class="small">Email : entrée en zone d\'achat, cassure, ou passage sous le stop.</p>' +
      '<div class="row"><input id="watch-email" type="email" autocomplete="email" value="' +
      esc(em) +
      '" placeholder="vous@gmail.com" aria-label="Votre adresse Gmail"><button data-a="watchOn" data-i="' +
      esc(isin) +
      '" title="Renvoie la demande avec le plan affiché (utile après un ajustement)">Mettre à jour</button><button class="ghost" data-a="watchOff" data-i="' +
      esc(isin) +
      '">Ne plus surveiller</button></div></details>'
    : isin
      ? '<details class="watch"><summary>🔔 Me prévenir pour ce plan</summary><p class="small">Email : entrée en zone d\'achat, cassure, ou passage sous le stop.</p>' +
        '<div class="row"><input id="watch-email" type="email" autocomplete="email" value="' +
        esc(em) +
        '" placeholder="vous@gmail.com" aria-label="Votre adresse Gmail"><button data-a="watchOn" data-i="' +
        esc(isin) +
        '">Surveiller</button><button class="ghost" data-a="watchOff" data-i="' +
        esc(isin) +
        '">Ne plus surveiller</button></div></details>'
      : '';
  var adv = inEs && S.inst[isin].stats ? S.inst[isin].stats.adv20Eur : null;
  var liqH =
    adv != null && adv < 2e5
      ? '<p class="small liqw">⚠️ <b>Très peu échangé</b> (' +
        ES.fmtEur(adv) +
        ' par jour) : niveaux fragiles, ordres à cours limité.</p>'
      : '';
  var curH =
    pcur && pcur !== 'EUR' && ES.FX[pcur]
      ? '<p class="small muted">Prix en ' +
        esc(curName(pcur)) +
        ' (1\u00a0€ = ' +
        fmtN(ES.FX[pcur], pcur === 'GBp' ? 0 : 2) +
        '\u00a0' +
        esc(curName(pcur)) +
        '), équivalent en euros en gris.</p>'
      : '';
  var PKr = (function () {
      var pk = pickSet();
      for (var k in pk) {
        if (pk[k].isin === isin || pk[k].sym === isin) return pk[k];
      }
      return null;
    })(),
    PE = PKr ? ES.pickEntry(PKr) : null;
  var pickH = PE
    ? '<div class="pickent ' +
      (PE.k === 'buy' ? 'good' : 'warn') +
      '"><b>🎯 ' +
      PE.icon +
      ' ' +
      esc(PE.label) +
      "</b><small>Règle testée sur 1997-2026 pour les sociétés du 🎯 : attendre un repli n'a pas fait mieux. Les niveaux et indicateurs ci-dessous viennent de l'analyse technique classique : testés, ils n'aident pas à choisir le moment.</small></div>"
    : '';
  // ✏️ ajustement à la main : sous les indicateurs et les raisons du plan, juste avant 🔔 « Me prévenir »
  var adjH = (function () {
    var pr0 = plan.primary,
      e0 = pr0.key === 'breakout' ? pr0.trigger : pr0.key === 'highs' || pr0.key === 'manual' ? pr0.entry : pr0.zoneHi,
      fv = function (v) {
        // même arrondi que l'affichage : 1 décimale dès 10, 2 de 1 à 10, 3 chiffres significatifs en dessous
        return v > 0
          ? String(+(v >= 10 ? v.toFixed(1) : v >= 1 ? v.toFixed(2) : v.toPrecision(3))).replace('.', ',')
          : '';
      },
      inp = function (id, lbl, v) {
        return (
          '<label><small>' +
          lbl +
          '</small><input data-pl="' +
          id +
          '" type="text" inputmode="decimal" value="' +
          fv(v) +
          '"></label>'
        );
      };
    return (
      '<details class="planadj"' +
      (man ? ' open' : '') +
      '><summary>✏️ ' +
      (man ? 'Plan ajusté à la main · modifier' : 'Ajuster ce plan') +
      '</summary><div class="adjgrid">' +
      inp('e', '🟢 Entrée', e0) +
      inp('s', '🛑 Stop', pr0.stop) +
      inp('t', '🎯 Objectif', pr0.target) +
      '</div><div class="row"><button data-a="planSave" data-i="' +
      esc(isin) +
      '" data-last="' +
      (lastC > 0 ? lastC : '') +
      '">Enregistrer</button>' +
      (man
        ? '<button class="ghost" data-a="planReset" data-i="' + esc(isin) + '">Revenir au plan calculé</button>'
        : '') +
      '</div><p class="small muted">Gardé sur cet appareil : le graphique et les niveaux suivent vos valeurs. Pour que les alertes du soir les utilisent, touchez ensuite «\u00a0' +
      (wd ? 'Mettre à jour' : 'Surveiller') +
      '\u00a0» dans 🔔 ci-dessous.' +
      (man && auto ? ' Plan calculé : ' + esc(String(auto.title || '').toLowerCase() || 'automatique') + '.' : '') +
      '</p></details>'
    );
  })();
  var vis = planVisuals(plan, adj);
  // plan d'entrée toujours ouvert : titre et verdict en tête, indicateurs visibles sans pli
  return (
    '<section class="plan ' +
    V[0] +
    '"><h4>🧭 Plan d\'entrée</h4><p class="verdict">' +
    V[1] +
    ' <b>' +
    esc(plan.label) +
    '</b></p>' +
    pickH +
    curH +
    liqH +
    planChart(isin, adj, plan) +
    '<ul class="sc">' +
    line(pr, true) +
    (plan.alt ? line(plan.alt, false) : '') +
    '</ul>' +
    '<p class="small muted">Repères pour entrer. Une fois acheté : garder 6 mois, protection à −30 %.</p>' +
    // indicateurs toujours visibles (plus de pli)
    (vis ? '<div class="pvis"><p class="small pvh"><b>📟 Indicateurs</b></p>' + vis + '</div>' : '') +
    (plan.why && plan.why.length
      ? '<ul class="why">' +
        plan.why
          .map(function (w) {
            return '<li>' + esc(w.charAt(0).toUpperCase() + w.slice(1)) + '</li>';
          })
          .join('') +
        '</ul>'
      : '') +
    adjH +
    watchH +
    (obs || histH ? xpi(obs + histH, 'Par le passé') : '') +
    xpi(
      "Analyse technique classique (supports, résistances, moyennes mobiles, RSI, MACD). Testée avec le 🎯 sur 1997-2026 : ni ces niveaux ni ces indicateurs n'aident à choisir le moment ; c'est un repère pour placer un ordre, pas un signal (détail : Comment ça marche, « Testé et retiré »). Le cône montre l'amplitude probable des variations d'ici 3 mois si la volatilité récente se maintient (" +
        (plan.volYearPct != null ? plan.volYearPct + ' % par an' : 'n.d.') +
        "), sans prévoir la direction. Ce n'est pas un conseil en investissement.",
      'Méthode'
    ) +
    '</section>'
  );
}

function txSection(i, sc) {
  var all = (S.tx[i] || []).slice().sort(function (a, b) {
    return ES.availDate(a) < ES.availDate(b) ? 1 : -1;
  });
  var from = sc.windowFrom,
    inW = all.filter(function (t) {
      return ES.availDate(t) >= from;
    }),
    older = all.length - inW.length;
  var h =
    '<section class="card"><h3>Opérations des dirigeants <span class="muted">· ' +
    inW.length +
    ' dans la fenêtre' +
    (older ? ', ' + older + ' plus anciennes conservées pour la validation' : '') +
    '</span></h3>';
  if (!inW.length)
    return (
      h +
      '<p class="muted">Aucune déclaration publiée depuis le ' +
      from +
      ". Cela ne prouve pas l'absence d'opération si la source du pays n'a pas été collectée (voir Qualité des données).</p></section>"
    );
  h +=
    '<div class="ops">' +
    inW
      .map(function (t) {
        return opCard(i, t);
      })
      .join('') +
    '</div>';
  h +=
    xpi(
      "Formules : écart cours/prix payé = cours actuel ÷ prix payé − 1 (positif = le cours est au-dessus du prix payé). Position dans l'intervalle = (prix − plus bas) ÷ (plus haut − plus bas) : 0 % au plus bas, 100 % au plus haut. Les « extrêmes disponibles » portent sur l'historique importé, jamais présenté comme un plus haut historique absolu. Prix ajustés des splits déclarés.",
      'Formules'
    ) + '</section>';
  return h;
}
function opCard(isin, t) {
  var r = (S.refs[isin] || {})[t.id],
    cls = t.status === 'annulee' ? 'cancel' : t.type === 'achat' ? 'buy' : t.type === 'vente' ? 'sell' : 'other';
  var pk = ES.buyerKey(t) || t.personKey,
    hist =
      pk && (t.type === 'achat' || t.type === 'vente') && S.snapshot && S.snapshot.history
        ? ' <button class="link small" data-a="person" data-k="' +
          esc(pk) +
          '">historique' +
          (t.associated ? ' du dirigeant' : '') +
          ' →</button>'
        : '';
  var h =
    '<article class="op ' +
    cls +
    '"><header><div><b>' +
    esc(t.person || 'Déclarant inconnu') +
    '</b>' +
    hist +
    '<small>' +
    esc(frRole(t.role) || 'fonction non publiée') +
    (t.associated
      ? ' · personne étroitement liée' + (t.linkedTo ? ' à ' + esc(t.linkedTo) : ' (dirigeant non identifié)')
      : '') +
    '</small></div><span class="chip ' +
    (cls === 'buy' ? 'good' : cls === 'sell' ? 'bad' : 'neutral') +
    '">' +
    ES.TX_TYPES[t.type] +
    (t.planned ? ' · planifiée' : '') +
    '</span></header>';
  h +=
    '<dl class="mar">' +
    mar('4b', 'Nature', esc(frNature(t.natureText) || ES.TX_TYPES[t.type])) +
    mar(
      '4c',
      'Prix · volume',
      (t.price != null ? fmtN(t.price, t.price < 10 ? 3 : 2) + ' ' + esc(t.currency || '?') : 'prix n.d.') +
        ' · ' +
        (t.qty != null ? fmtInt(t.qty) + ' titres' : 'quantité non publiée') +
        ' · ' +
        fmtMoney(t.amount, t.currency) +
        (t.amountComputed ? ' (calculé)' : '')
    ) +
    mar('4e', 'Transaction', ES.frDate(t.txDate)) +
    mar(
      '',
      'Publication',
      (t.pubDate ? ES.frDate(t.pubDate) : 'inconnue') +
        (t.pubTime ? ' ' + esc(t.pubTime) : '') +
        (t.pubPrecision ? ' <span class="muted">(précision : ' + esc(t.pubPrecision) + ')</span>' : '')
    ) +
    mar('4f', 'Lieu', esc(t.venue || 'n.d.')) +
    mar('', 'Vue par Euro Signal', ES.frDate((t.firstSeen || '').slice(0, 10)) || 'n.d.') +
    mar(
      '',
      'Détention',
      esc(t.holding || 'n.d.') +
        (t.stakeAfter != null ? ' · participation après opération : ' + fmtN(t.stakeAfter, 2) : '')
    ) +
    mar(
      '',
      'Source',
      '<a href="' +
        esc(ES.safeUrl(ES.sourceLink(t)) || '#') +
        '" target="_blank" rel="noopener">' +
        esc(t.registry) +
        (t.registryId ? ' · ' + esc(t.registryId) : '') +
        '</a>' +
        (t.alsoSeenIn && t.alsoSeenIn.length
          ? ' · aussi vue chez ' +
            t.alsoSeenIn
              .map(function (a) {
                return esc(a.registry);
              })
              .join(', ')
          : '') +
        (t.corrected ? ' · <b>corrigée</b>' : '') +
        (t.status === 'annulee' ? ' · <b>annulée</b>' : '')
    ) +
    '</dl>';
  if (r && r.available) {
    var ap = r.atPurchase,
      td = r.today;
    h +=
      '<div class="tablewrap"><table class="cmp"><thead><tr><th></th><th>Connu à l\'achat (' +
      t.txDate +
      ")</th><th>Aujourd'hui (" +
      r.lastDate +
      ')</th></tr></thead><tbody>' +
      '<tr><th>Cours actuel / prix payé</th><td>—</td><td class="' +
      (r.currentVsPaidPct >= 0 ? 'pos' : 'neg') +
      '">' +
      pct(r.currentVsPaidPct) +
      '</td></tr>' +
      '<tr><th>Prix payé / plus bas 52 sem.</th><td>' +
      (ap ? pct(ap.paidVsLow52Pct) : 'n.d.') +
      '</td><td>' +
      pct(td.paidVsLow52Pct) +
      '</td></tr>' +
      '<tr><th>Prix payé / plus haut 52 sem.</th><td>' +
      (ap ? pct(ap.paidVsHigh52Pct) : 'n.d.') +
      '</td><td>' +
      pct(td.paidVsHigh52Pct) +
      '</td></tr>' +
      '<tr><th>Position du prix payé (52 sem.)</th><td>' +
      posTxt(ap && ap.paidPos52) +
      '</td><td>' +
      posTxt(td.paidPos52) +
      '</td></tr>' +
      '<tr><th>Position du cours actuel (52 sem.)</th><td>—</td><td>' +
      posTxt(td.currentPos52) +
      '</td></tr>' +
      '<tr><th>Prix payé / extrêmes disponibles</th><td>' +
      (ap ? pct(ap.paidVsLowAllPct) + ' / ' + pct(ap.paidVsHighAllPct) : 'n.d.') +
      '</td><td>' +
      posTxt(td.paidPosAll) +
      " de l'intervalle</td></tr>" +
      '<tr><th>Position du cours (extrêmes disponibles)</th><td>—</td><td>' +
      posTxt(td.currentPosAll) +
      '</td></tr>' +
      '</tbody></table></div><p class="foot">Base : ' +
      (ap && ap.ex52 ? ap.ex52.basis + ', 52 sem. depuis ' + ap.ex52.from + '; ' : '') +
      'extrêmes disponibles depuis ' +
      (td.exAll ? td.exAll.from : 'n.d.') +
      ' (' +
      (td.exAll ? td.exAll.basis : '') +
      '). ' +
      r.notes.map(esc).join(' ; ') +
      '</p>';
  } else if (t.type === 'achat' || t.type === 'vente')
    h +=
      '<p class="muted">Comparaisons indisponibles : ' + esc(r ? r.notes.join(' ; ') : 'cours non chargés') + '.</p>';
  if (t.history && t.history.length)
    h +=
      '<p class="foot">Versions précédentes : ' +
      t.history
        .map(function (v) {
          return 'v' + v.version + ' (' + esc(v.status) + ', prix ' + fmtN(v.snapshot.price) + ')';
        })
        .join(' ; ') +
      '</p>';
  return h + '</article>';
}
function mar(code, k, v) {
  return '<div><dt>' + (code ? '<span class="code">' + code + '</span>' : '') + k + '</dt><dd>' + v + '</dd></div>';
}
function posTxt(v) {
  return v == null ? 'n.d.' : Math.round(v) + ' %';
}

/** Rachats d'actions (communiqués) et évolution du nombre d'actions : contenu sans titre, réutilisé par le pli 🔬 Analyse.
 *  quiet : sans la ligne « aucun rachat repéré » (l'évolution du nombre d'actions suffit). */
function buybackBlock(i, ev, quiet) {
  var h = '';
  h += ev.buybacks.length
    ? '<ul class="evs">' +
      ev.buybacks
        .slice()
        .sort(function (a, b) {
          return a.date < b.date ? 1 : -1;
        })
        .map(function (b) {
          return (
            '<li><div><b>' +
            STAGES[b.stage] +
            '</b> · ' +
            b.date +
            (b.amount ? ' · ' + fmtMoney(b.amount, 'EUR') : '') +
            (b.pctCapital != null ? ' · ' + fmtN(b.pctCapital, 1) + ' % du capital' : '') +
            (b.note ? '<small>' + esc(b.note) + '</small>' : '') +
            (ES.safeUrl(b.sourceUrl)
              ? '<small><a href="' +
                esc(ES.safeUrl(b.sourceUrl)) +
                '" target="_blank" rel="noopener">source</a></small>'
              : '') +
            '</div>' +
            (b.confirmed ? '<span class="chip good">Confirmé</span>' : '<span class="chip warn">À vérifier</span>') +
            '</li>'
          );
        })
        .join('') +
      '</ul>'
    : quiet
      ? ''
      : '<p class="muted">Aucun rachat repéré dans les communiqués.</p>';
  var sc = (S.inst[i] || {}).sharesChange;
  if (sc && sc.corporate)
    h +=
      "<p><b>Nombre d'actions</b> : " +
      pct(sc.pct) +
      ' du ' +
      shortDate(sc.from) +
      ' au ' +
      shortDate(sc.to) +
      " → variation trop forte pour des rachats : regroupement ou division d'actions (opération sur le capital), sans effet sur la part de chaque actionnaire.</p>";
  else if (sc)
    h +=
      "<p><b>Nombre d'actions</b> : " +
      (sc.pct <= -1.5
        ? '<span class="pos">' +
          pct(sc.pct) +
          '</span> du ' +
          shortDate(sc.from) +
          ' au ' +
          shortDate(sc.to) +
          " → la société rachète et annule ses actions (chaque action restante détient une plus grande part de l'entreprise)."
        : sc.pct >= 3
          ? '<span class="neg">' +
            pct(sc.pct) +
            '</span> du ' +
            shortDate(sc.from) +
            ' au ' +
            shortDate(sc.to) +
            " → émission d'actions nouvelles (dilution des actionnaires)."
          : pct(sc.pct) + ' du ' + shortDate(sc.from) + ' au ' + shortDate(sc.to) + ' : stable.') +
      '</p>' +
      mini(
        'Actions en circulation sur un an',
        pct(sc.pct),
        -sc.pct / 100,
        -0.1,
        0.1,
        true,
        "Vert : moins d'actions (rachats) ; rouge : plus d'actions (dilution)"
      );
  return h;
}
/** Publications de résultats (BPA et chiffre d'affaires face au consensus) : contenu sans titre, réutilisé par le pli
 *  🔬 Analyse. max : nombre de publications listées (les plus récentes) ; noSum : sans le bilan « au-dessus du consensus
 *  N fois sur M » (repris dans le titre du pli de l'analyse). */
function resultsBlock(i, ev, max, noSum) {
  var L = ev.results.slice().sort(function (a, b) {
    return a.pubDate < b.pubDate ? 1 : -1;
  });
  if (!L.length) return '<p class="muted">Aucune publication repérée.</p>';
  var S2 = L.map(function (r) {
      return ES.surprise(r.epsActual, r.epsConsensus);
    }),
    known = S2.filter(function (e) {
      return e != null;
    }),
    beats = known.filter(function (e) {
      return e > 0;
    }).length;
  var h =
    known.length >= 3 && !noSum
      ? '<p class="small">Bénéfice par action au-dessus du consensus <b>' +
        beats +
        ' fois sur ' +
        known.length +
        '</b> publications.</p>'
      : '';
  var n = max && L.length > max ? max : L.length;
  h +=
    '<ul class="evs">' +
    L.slice(0, n)
      .map(function (r, k) {
        var e = S2[k],
          v = ES.surprise(r.revActual, r.revConsensus),
          parts = [];
        if (r.epsActual != null)
          parts.push(
            'BPA ' +
              fmtN(r.epsActual) +
              (r.epsConsensus != null ? ' contre ' + fmtN(r.epsConsensus) + ' attendu' : '') +
              (e != null ? ' <span class="' + (e >= 0 ? 'pos' : 'neg') + '">(' + pct(e) + ')</span>' : '')
          );
        if (r.revActual != null)
          parts.push(
            "chiffre d'affaires " +
              fmtN(r.revActual, 0) +
              (r.revConsensus != null ? ' contre ' + fmtN(r.revConsensus, 0) + ' attendu' : '') +
              (v != null ? ' <span class="' + (v >= 0 ? 'pos' : 'neg') + '">(' + pct(v) + ')</span>' : '')
          );
        return (
          '<li><div><b>' +
          esc(r.period || 'Résultats') +
          '</b> · ' +
          shortDate(r.pubDate) +
          (parts.length ? '<small>' + parts.join(' · ') + '</small>' : '') +
          (r.note ? '<small>' + esc(r.note) + '</small>' : '') +
          (ES.safeUrl(r.sourceUrl)
            ? '<small><a href="' +
              esc(ES.safeUrl(r.sourceUrl)) +
              '" target="_blank" rel="noopener">communiqué</a></small>'
            : '') +
          '</div></li>'
        );
      })
      .join('') +
    '</ul>' +
    (n < L.length ? '<p class="small muted">' + (L.length - n) + ' publications plus anciennes non listées.</p>' : '');
  return h;
}
function eventsSection(i, ev) {
  return (
    '<div class="cols"><section class="card"><h3>Rachats d\'actions</h3>' +
    buybackBlock(i, ev) +
    '</section><section class="card"><h3>Résultats et perspectives</h3>' +
    resultsBlock(i, ev) +
    '</section></div>'
  );
}

function alertSection(i, c) {
  var d = c.dec;
  return (
    '<h4>Conditions de l\'email d\'alerte</h4><ul class="checks">' +
    d.conditions
      .map(function (x) {
        return (
          '<li class="' +
          (x.ok ? 'ok' : 'ko') +
          '"><span>' +
          esc(ES.frText(x.label)) +
          '</span><b>' +
          (x.ok ? 'oui' : 'non') +
          '</b></li>'
        );
      })
      .join('') +
    '</ul>' +
    '<p class="foot">' +
    (d.send ? "Tout est rempli : l'email part au calcul du soir." : "Pas d'email tant qu'une condition manque.") +
    '</p>'
  );
}
