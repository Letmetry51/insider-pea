/* Euro Signal — interface : navigation, en-tête, rendu des onglets, liste des opportunités.
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
/* =========================== Démonstration =========================== */
/* =========================== Interface =========================== */
var toastTimer;
function notify(msg, kind) {
  var el = $('#toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'toast show ' + (kind || '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(
    function () {
      el.className = 'toast';
    },
    kind === 'bad' ? 9000 : 5000
  );
}
function busy(msg) {
  S.busy = msg;
  var el = $('#busy');
  if (el) {
    el.hidden = false;
    el.querySelector('span').textContent = msg;
  }
}
function idle() {
  S.busy = null;
  var el = $('#busy');
  if (el) el.hidden = true;
}

var VIEWS = [
  ['classement', 'Opportunités', 'Opportunités'],
  ['secteurs', 'Secteurs et thèmes', 'Secteurs'],
  ['inities', 'Achats des dirigeants', 'Achats'],
  ['alertes', 'Alertes et suivi', 'Alertes'],
  ['aide', 'Comment ça marche', 'Aide'],
];
function render() {
  var top = $('#top'),
    main = $('#main');
  if (!top || !main) return;
  // email en échec dans la semaine (mot de passe d'application révoqué, Gmail refuse) : l'email de contrôle ne peut pas le dire
  var mailKo = Object.keys(S.alerts || {}).some(function (k) {
    var a = S.alerts[k];
    return a && a.status === 'echec' && ES.daysBetween(String(a.createdAt || '').slice(0, 10), S.today) <= 7;
  });
  var mail = mailKo
    ? '<span class="chip bad">⚠️ Emails en échec</span>'
    : S.snapshot && S.snapshot.mail && S.snapshot.mail.ready
      ? '<span class="chip good">Alertes email actives</span>'
      : S.mode === 'remote'
        ? '<span class="chip warn">Emails en simulation</span>'
        : '';
  var cur =
    S.view === 'fiche'
      ? S.ficheFrom === 'secco'
        ? 'secteurs'
        : 'classement'
      : S.view === 'secco'
        ? S.secFrom === 'classement'
          ? 'classement'
          : 'secteurs'
        : S.view === 'dirigeant'
          ? 'inities'
          : S.view;
  top.innerHTML =
    '<div class="brand"><div class="logo" aria-hidden="true"><i></i><i></i><i></i></div><div><h1>Euro Signal</h1><p>' +
    (S.mode === 'remote'
      ? 'Données du ' + shortDate(S.today) + ' · mises à jour chaque soir de semaine'
      : 'Surveillance des achats de dirigeants') +
    '</p></div></div>' +
    '<div class="chips">' +
    staleChip() +
    mail +
    '</div>' +
    '<nav class="tabs" role="tablist">' +
    VIEWS.map(function (v) {
      var on = cur === v[0];
      return (
        '<button role="tab" aria-selected="' +
        on +
        '" class="' +
        (on ? 'on' : '') +
        '" data-a="view" data-v="' +
        v[0] +
        '"><span class="tl">' +
        v[1] +
        '</span><span class="ts">' +
        v[2] +
        '</span>' +
        (v[0] === 'alertes' ? alertBadge() : '') +
        '</button>'
      );
    }).join('') +
    '</nav>';
  var body = '';
  if (S.mode === 'chargement') body = '<p class="muted pad">Chargement des données du jour…</p>';
  else if (S.mode === 'erreur')
    body =
      '<div class="card bad"><h3>Données indisponibles</h3><p>Le fichier du jour n\'a pas pu être lu (' +
      esc(S.loadError) +
      "). Réessayez dans quelques minutes ; si cela persiste, regardez l'onglet Actions du dépôt GitHub.</p></div>";
  else
    try {
      body = (
        {
          classement: vClassement,
          secteurs: vSecteurs,
          secco: vSecCo,
          fiche: vFiche,
          inities: vInities,
          alertes: vAlertesAuto,
          aide: vAide,
          dirigeant: vDirigeant,
        }[S.view] || vClassement
      )();
    } catch (e) {
      body = '<div class="card bad">Erreur d\'affichage : ' + esc(e.message) + '</div>';
      console.error(e);
    }
  main.innerHTML = body;
  main.querySelectorAll('details[data-k]').forEach(function (d) {
    if (S.openDet && S.openDet[d.dataset.k]) d.open = true;
  });
  frDates(main);
  if (S.busy) busy(S.busy);
}
function alertBadge() {
  var n = Object.keys(S.computed).filter(function (i) {
    return S.computed[i].dec.send;
  }).length;
  return n ? ' <span class="count">' + n + '</span>' : '';
}

function uniChip(u) {
  if (u.status === 'rejete') {
    var why = (u.reasons || []).join(' ; '),
      short = /liquidit/.test(why)
        ? 'peu liquide'
        : /séances|historique/.test(why)
          ? 'historique trop court'
          : /cours|figé|suspen/.test(why)
            ? 'cotation suspendue'
            : null;
    return '<span class="chip bad" title="' + esc(why) + '">Hors univers' + (short ? ' : ' + short : '') + '</span>';
  }
  var m = { retenu: ['Retenu', 'good'], rejete: ['Rejeté', 'bad'], a_examiner: ['À examiner', 'warn'] }[u.status];
  return '<span class="chip ' + m[1] + '">' + m[0] + '</span>';
}
function peaChip(i) {
  var s = i.peaStatus || 'a_verifier';
  return (
    '<span class="chip ' +
    (s === 'eligible' || s === 'probable' ? 'good' : s === 'non_eligible' ? 'bad' : 'warn') +
    '" title="' +
    esc(i.peaSource ? 'Source : ' + i.peaSource + ' (' + i.peaDate + ')' : 'Aucune source enregistrée') +
    '">PEA ' +
    ES.PEA_LABEL[s] +
    '</span>'
  );
}
function alertChip(isin) {
  var c = S.computed[isin],
    d = c.dec;
  if (d.send) return '<span class="chip good">Alerte prête</span>';
  var dup = d.conditions.filter(function (x) {
    return !x.ok;
  });
  if (dup.length === 1 && /nouvelle/.test(dup[0].label) && c.score.contributing.length)
    return '<span class="chip neutral">Déjà signalée</span>';
  return (
    '<span class="chip neutral" title="' + esc(d.blocking.join('\n')) + '">Bloquée · ' + d.blocking.length + '</span>'
  );
}

/* ----- Opportunités (classement) ----- */
// Code pays en pastille (les drapeaux emoji ne s'affichent pas sous Windows) ; version texte pour les listes déroulantes
function flag(cc) {
  return cc && /^[A-Z]{2}$/.test(cc) ? '<span class="cc cc-' + cc + '">' + cc + '</span> ' : '';
}
var ROLES = [
  [
    /deputy (ceo|managing|chief)|vice[- ]ceo|stellvertret|directeur g[ée]n[ée]ral d[ée]l[ée]gu[ée]/i,
    'Directeur général délégué',
  ],
  [/employee representative|repr[ée]sentant des salari/i, 'Représentant des salariés au conseil'],
  [/chairman|chairwoman|chair of the board/i, 'Président du conseil'],
  [/other senior executive|senior executive/i, 'Cadre dirigeant'],
  [/funzioni di direzione|direction functions/i, 'Dirigeant'],
  [/funzioni di amministrazione|administrative functi/i, 'Administrateur'],
  [/chief executive|\bceo\b|vorstandsvorsitz|consejero delegado|amministratore delegato/i, 'Directeur général'],
  [/chief financial|\bcfo\b|finanzvorstand/i, 'Directeur financier'],
  [/supervisory board|aufsichtsrat|raad van commissarissen/i, 'Membre du conseil de surveillance'],
  [/management board|vorstand|raad van bestuur/i, 'Membre du directoire'],
  [/closely associated|personne étroitement liée|eng verbunden/i, 'Personne étroitement liée'],
  [
    /member of (the )?(administrative|board)|administrative, management or supervisory/i,
    'Membre d’un organe d’administration ou de direction',
  ],
  [/consejero ejecutivo/i, 'Administrateur exécutif'],
  [/consejero/i, 'Administrateur'],
  [/presidente/i, 'Président'],
  [/^director$|non-executive director|board member/i, 'Administrateur'],
];
function frRole(r) {
  if (!r) return '';
  for (var k = 0; k < ROLES.length; k++)
    if (ROLES[k][0].test(r)) return ROLES[k][1] + (ROLES[k][1].toLowerCase() === String(r).toLowerCase() ? '' : '');
  return r;
}
function frNature(n) {
  if (!n) return '';
  var x = String(n);
  return x
    .replace(/^Buy$/i, 'Achat')
    .replace(/^Sell$/i, 'Vente')
    .replace(/^Purchase\b/i, 'Achat')
    .replace(/^Sale\b/i, 'Vente')
    .replace(/Acquisition/g, 'acquisition')
    .replace(/—\s*Other$/i, '— autre');
}
function flagTxt(cc) {
  return cc && /^[A-Z]{2}$/.test(cc) ? cc + ' · ' : '';
}
/** Étoiles d'un coup d'œil (5 = très fort et remarquable dans l'historique). */
/** Dates affichées à la française (le texte seulement : attributs, liens et graphiques intacts). */
function frDates(root) {
  try {
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.parentNode && n.parentNode.closest && n.parentNode.closest('svg, script, style, textarea')
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      },
    });
    var n,
      re = /\b(\d{4})-(\d{2})-(\d{2})\b/g;
    while ((n = w.nextNode()))
      if (re.test(n.nodeValue)) {
        re.lastIndex = 0;
        n.nodeValue = n.nodeValue.replace(re, '$3/$2/$1');
      }
  } catch (e) {}
}
function starInner(st) {
  return '★★★★★'.slice(0, st.n) + (st.n < 5 ? '<i class="e">' + '☆☆☆☆☆'.slice(0, 5 - st.n) + '</i>' : '');
}
function starsHtml(total, big) {
  var r = histOf(ES.note(total, S.cfg)),
    st = ES.stars(total, S.cfg, r && r.key);
  return (
    '<span class="stars s' +
    st.n +
    (big ? ' big' : '') +
    '" role="img" aria-label="' +
    st.n +
    ' étoile' +
    (st.n > 1 ? 's' : '') +
    ' sur 5">' +
    starInner(st) +
    '</span>'
  );
}
/** Données en retard : aucun calcul du soir depuis au moins deux jours ouvrés (tâche sautée par GitHub, panne). */
function staleChip() {
  if (S.mode !== 'remote' || !S.today) return '';
  var now = new Intl.DateTimeFormat('fr-CA', {
    timeZone: 'Europe/Paris',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
  return ES.businessDaysBetween(S.today, now) >= 2
    ? '<span class="chip bad">⚠️ Données du ' + shortDate(S.today) + ', calcul du soir en retard</span>'
    : '';
}
function shortDate(d) {
  return d ? d.slice(8, 10) + '/' + d.slice(5, 7) + '/' + d.slice(2, 4) : '—';
}
function shortName(n) {
  n = String(n || '');
  if (/,/.test(n)) n = n.split(',').reverse().join(' ').trim();
  return n.length > 26 ? n.slice(0, 25) + '…' : n;
}
/** Barre « plus bas 52 s → plus haut 52 s » : ● prix payé par le dirigeant, ◆ cours actuel. */
function rangeBar(paidPos, curPos) {
  var c = function (v) {
    return Math.max(0, Math.min(100, v));
  };
  if (paidPos == null && curPos == null) return '<span class="muted">n.d.</span>';
  return (
    '<div class="rbar" role="img" aria-label="Prix payé à ' +
    (paidPos != null ? Math.round(c(paidPos)) : '?') +
    " % de l'intervalle 52 semaines, cours actuel à " +
    (curPos != null ? Math.round(c(curPos)) : '?') +
    ' %"><i class="rb-track"></i>' +
    (paidPos != null ? '<i class="rb-paid" style="left:' + c(paidPos) + '%" title="Prix payé"></i>' : '') +
    (curPos != null ? '<i class="rb-now" style="left:' + c(curPos) + '%" title="Cours actuel"></i>' : '') +
    '</div><small class="rb-lbl"><span>bas 52 s.</span><span>haut</span></small>'
  );
}
function discPill(d) {
  if (!d) return '<span class="muted">n.d.</span>';
  var v = Math.round(d.pct),
    k =
      v >= S.cfg.weights.insiders.discountBigPct
        ? 'deep'
        : v >= S.cfg.weights.insiders.discountMediumPct
          ? 'mid'
          : 'low';
  return '<span class="disc ' + k + '">' + (v > 0 ? '−' : '+') + Math.abs(v) + ' %</span>';
}
/** Avis croisé d'une société (même règle que l'email) et ses symboles. */
/** Achat du DG ou du DAF le plus récent : la sélection de la semaine n'en retient que de moins de 30 jours. */
function dgInfo(i) {
  var c = S.computed[i],
    R = (S.cfg.selection || {}).recentDays || 30;
  if (!c || !c.score.buys.length) return null;
  var d = c.score.buys
    .filter(function (t) {
      return t.ceo || t.cfo;
    })
    .map(function (t) {
      return ES.availDate(t);
    })
    .sort()
    .pop();
  if (!d) return { none: true, R: R };
  var n = ES.daysBetween(d, S.today);
  return { date: d, days: n, recent: n <= R, R: R };
}
function dgChip(i) {
  var g = dgInfo(i);
  if (!g || !(S.cfg.selection || {}).requireCeoCfo) return '';
  if (g.none)
    return (
      '<small class="dgc dg-no" title="La sélection de la semaine exige un achat du DG ou du DAF de moins de ' +
      g.R +
      ' jours">✖ Sans achat DG/DAF</small>'
    );
  return g.recent
    ? '<small class="dgc dg-ok" title="Éligible à la sélection de la semaine">✅ DG/DAF il y a ' + g.days + ' j</small>'
    : '<small class="dgc dg-old" title="La sélection de la semaine exige un achat du DG ou du DAF de moins de ' +
        g.R +
        ' jours">⏱ DG/DAF il y a ' +
        g.days +
        ' j</small>';
}
function adviceOf(i) {
  var c = S.computed[i];
  if (!c) return null;
  if (c.adv) return c.adv;
  var h = c.score.buys.length ? histOf(ES.note(c.score.total, S.cfg)) : null;
  return (c.adv = ES.advice(S.inst[i], c.score, S.cfg, {
    histKey: h && h.key,
    today: S.today,
    universe: c.uni,
    mood: S.snapshot && S.snapshot.market && S.snapshot.market.mood,
  }));
}
function advBadge(a, big) {
  return a
    ? '<span class="adv adv-' +
        a.key +
        (big ? ' big' : '') +
        '" title="' +
        esc(a.why.join(' ; ')) +
        '">' +
        a.icon +
        ' ' +
        esc(a.label) +
        '</span>'
    : '';
}
/** Synthèse en tête de fiche : étoiles, note, avis, 3 raisons, 2 points d'attention, fiabilité mesurée des dossiers comparables. */
function adviceCard(i, c) {
  var a = adviceOf(i),
    sc = c.score,
    sm = ES.adviceSummary(a),
    sel = (S.snapshot && S.snapshot.selection && S.snapshot.selection.items) || [],
    k = -1;
  sel.forEach(function (x, j) {
    if (x.isin === i) k = j;
  });
  var selTxt;
  var dg = dgInfo(i);
  if (k > -1) selTxt = '✅ Dans la sélection de la semaine (n° ' + (k + 1) + ' sur ' + sel.length + ')';
  else if (dg && S.cfg.selection.requireCeoCfo && !dg.recent && sc.buys.length)
    selTxt =
      '⏱ Hors sélection : ' +
      (dg.none ? 'aucun achat du DG/DAF' : 'achat du DG/DAF il y a ' + dg.days + ' j (' + dg.R + ' j au plus)') +
      ". L'avis reste valable";
  else {
    var bl = ES.selectionBlockers({ inst: S.inst[i], score: sc, quality: c.q, universe: c.uni }, S.cfg, S.today);
    selTxt =
      '✖ Hors sélection : ' +
      (bl.length ? bl.join(' ; ') : 'pas parmi les ' + S.cfg.selection.size + ' meilleures notes');
  }
  var note = ES.note(sc.total, S.cfg),
    lab = ES.scoreLabel(sc.total, S.cfg),
    hr = sc.buys.length ? histOf(note) : null;
  var cmp = sc.buys.length
    ? ES.comparables(S.snapshot && S.snapshot.selection && S.snapshot.selection.replayStats, note, S.cfg)
    : null;
  var li = function (l) {
    return (
      '<ul class="plain">' +
      l
        .map(function (w) {
          return '<li>' + esc(w) + '</li>';
        })
        .join('') +
      '</ul>'
    );
  };
  var old = !!rankData();
  return (
    '<section class="card advcard adv-b-' +
    a.key +
    '">' +
    (old ? '<p class="oldlbl">👔 Lecture « dirigeants » : ancien classement, gardé pour comparaison</p>' : '') +
    '<div class="synhead">' +
    (sc.buys.length
      ? starsHtml(sc.total, true) + '<span class="synnote"><b>' + note + '</b>/100 · ' + esc(lab.label) + '</span>'
      : '') +
    advBadge(a, true) +
    '</div>' +
    feuxHtml(i, true) +
    (function () {
      var q = liqOf(i);
      return q && q.tone !== 'good'
        ? '<p class="liqw">💧 <b>' +
            cap1(q.label) +
            '</b> : ' +
            esc(liqTxt(q)) +
            '. Ordres à cours limité' +
            (q.place ? ' sur ' + esc(q.place) : '') +
            ', ' +
            ES.fmtEur(q.maxOrder) +
            ' par jour au plus.' +
            (q.place && q.place !== 'Paris' && !/Francfort/.test(q.place)
              ? " Sur les places allemandes (Francfort, Tradegate), les volumes de ce titre sont bien plus faibles : passer l'ordre sur " +
                esc(q.place) +
                '.'
              : '') +
            '</p>'
        : '';
    })() +
    (hr && hr.key !== 'na' ? '<p class="hist h-' + hr.key + '">' + hr.icon + ' ' + esc(hr.label) + '</p>' : '') +
    '<div class="syn2">' +
    (sm.pros.length ? '<div class="syn-pro"><h4>Pourquoi</h4>' + li(sm.pros) + '</div>' : '') +
    (sm.cons.length ? '<div class="syn-con"><h4>Attention</h4>' + li(sm.cons) + '</div>' : '') +
    '</div>' +
    (cmp ? '<p class="cmpline">🎯 <b>Dossiers comparables</b> : ' + esc(cmp.text) + '.</p>' : '') +
    (old ? '' : '<p class="' + (/^⏱/.test(selTxt) ? 'selout' : 'foot') + '">' + esc(selTxt) + '.</p>') +
    '</section>'
  );
}
function statusChip(isin) {
  var c = S.computed[isin];
  if (c.dec.send) return '<span class="chip good">Alerte prête</span>';
  if (c.score.fallingKnife)
    return '<span class="chip warn" title="Le cours est passé sous ses moyennes 50 et 200 séances">Cours en repli</span>';
  return alertChip(isin);
}
/** Repère historique : situe la note par rapport aux dossiers des sélections passées (rejouées). */
/** Analyse des comptes : 4 derniers exercices, tendances et F-score de Piotroski point par point. */
function big(v) {
  if (v == null || !isFinite(v)) return 'n.d.';
  var a = Math.abs(v);
  return (
    (v < 0 ? '−' : '') +
    (a >= 1e9 ? fmtN(a / 1e9, 2) + ' Md' : a >= 1e6 ? fmtN(a / 1e6, 0) + ' M' : fmtN(a / 1e3, 0) + ' k')
  );
}
function arrow(a, b, higherIsBetter) {
  if (a == null || b == null || !isFinite(a) || !isFinite(b) || a === b) return '<span class="ar ar-flat">→</span>';
  var up = b > a,
    good = higherIsBetter ? up : !up;
  return '<span class="ar ' + (good ? 'ar-good' : 'ar-bad') + '">' + (up ? '↗' : '↘') + '</span>';
}
/** Lecture des comptes pour l'investisseur : synthèse chiffrée et conseil (calculés le soir à partir des comptes complets). */
function kidLine(a) {
  var p = a && a.plain;
  return p && p.text
    ? '<div class="kidline kid-' +
        esc(p.tone || 'na') +
        '"><p class="kidh">📊 <b>Lecture des comptes</b>' +
        (p.label ? ' · ' + esc(p.label) : '') +
        '</p><p>' +
        esc(p.text) +
        '</p>' +
        '<p><b>Conseil</b> : ' +
        esc(p.advice) +
        '</p>' +
        (p.explain ? xpi(esc(p.explain.replace(/^En clair : ?/, '')), 'En clair') : '') +
        '</div>'
    : '';
}
function fsKey(v) {
  return v >= 8
    ? 'top'
    : v >= S.cfg.accounts.fscoreGood
      ? 'good'
      : v <= 1
        ? 'vbad'
        : v <= S.cfg.accounts.fscoreBad
          ? 'bad'
          : 'mid';
}
function fsPill(v) {
  return '<span class="fsc fs-' + fsKey(v) + '">' + v + '/9</span>';
}
/** Évolution du F-score : un score par exercice disponible, pour voir si la santé financière va dans le bon sens. */
function fscoreEvolution(a) {
  var H = (a.fscoreHistory || []).filter(function (x) {
    return x && !x.na && x.f9 != null;
  });
  if (H.length < 2)
    return '<p class="foot">Évolution : un seul F-score calculable (il faut deux exercices consécutifs pour chacun).</p>';
  var t = a.fscoreTrend || { key: 'flat', delta: 0 },
    d = H[H.length - 1].f9 - H[0].f9;
  var verdict =
    t.key === 'up'
      ? '<b class="pos">↗ En amélioration</b> : la note gagne ' +
        d +
        ' point' +
        (d > 1 ? 's' : '') +
        ' depuis ' +
        esc(H[0].year) +
        ', les comptes vont dans le bon sens.'
      : t.key === 'down'
        ? '<b class="neg">↘ En dégradation</b> : la note perd ' +
          -d +
          ' point' +
          (-d > 1 ? 's' : '') +
          ' depuis ' +
          esc(H[0].year) +
          ', les comptes vont dans le mauvais sens.'
        : '<b>→ Stable</b> : ' +
          (d === 0 ? 'même note' : 'écart de ' + (d > 0 ? '+' : '') + d + ' point') +
          ' entre ' +
          esc(H[0].year) +
          ' et ' +
          esc(H[H.length - 1].year) +
          ', pas de tendance nette.';
  return (
    '<div class="fsev"><div class="fsbars" role="img" aria-label="F-score par exercice : ' +
    H.map(function (x) {
      return x.year + ' ' + x.f9 + ' sur 9';
    }).join(', ') +
    '">' +
    H.map(function (x, k) {
      var dv = k ? x.f9 - H[k - 1].f9 : null;
      return (
        '<div class="fsbar"><span class="fsv">' +
        x.f9 +
        '</span><i class="fs-' +
        fsKey(x.f9) +
        '" style="height:' +
        Math.max(4, x.f9 * 8) +
        'px"></i><span class="fsy">' +
        esc(x.year) +
        '</span><span class="fsd ' +
        (dv == null ? 'muted' : dv > 0 ? 'pos' : dv < 0 ? 'neg' : 'muted') +
        '">' +
        (dv == null ? '&nbsp;' : dv > 0 ? '+' + dv : dv < 0 ? '−' + -dv : '=') +
        '</span></div>'
      );
    }).join('') +
    '</div><p class="fsverdict">' +
    verdict +
    '</p></div>'
  );
}
var FS_GROUPS = [
  ['Rentabilité', ['roa', 'cfo', 'droa', 'accrual']],
  ['Structure financière', ['lev', 'liq', 'shares']],
  ['Efficacité opérationnelle', ['gm', 'ato']],
];
var FS_MEAN = {
  roa: "L'entreprise a dégagé un bénéfice sur l'exercice.",
  cfo: "Son activité a fait rentrer plus d'argent qu'elle n'en a fait sortir.",
  droa: "Elle tire plus de bénéfice de chaque euro investi dans ses actifs qu'un an plus tôt.",
  accrual: 'Son bénéfice est réellement encaissé, pas seulement comptable : signe de comptes de qualité.',
  lev: "Elle s'est désendettée par rapport à la taille de son bilan.",
  liq: "Elle a plus de marge pour payer ses dettes à moins d'un an.",
  shares: "Elle n'a pas créé d'actions nouvelles : la part de chaque actionnaire n'est pas diluée.",
  gm: 'Elle garde une part plus grande du prix de vente après le coût des produits : signe de pouvoir de prix.',
  ato: 'Elle réalise plus de ventes avec les mêmes actifs (usines, magasins, stocks) : meilleure utilisation de ses moyens.',
};
function fscoreCriteria(fs) {
  var by = {};
  (fs.items || []).forEach(function (x) {
    by[x.k] = x;
  });
  return (
    '<div class="fsgroups">' +
    FS_GROUPS.map(function (g) {
      var it = g[1]
          .map(function (k) {
            return by[k];
          })
          .filter(Boolean),
        ok = it.filter(function (x) {
          return x.ok;
        }).length;
      return (
        '<div class="fsg"><h5>' +
        g[0] +
        ' <span class="muted">' +
        ok +
        '/' +
        it.length +
        '</span></h5><ul class="fsl">' +
        it
          .map(function (x) {
            return (
              '<li class="' +
              (x.ok == null ? 'na' : x.ok ? 'ok' : 'ko') +
              '"><b>' +
              (x.ok == null ? '–' : x.ok ? '✓' : '✗') +
              '</b> ' +
              esc(x.label) +
              '<small>' +
              (x.ok == null
                ? 'Non calculable avec les comptes disponibles.'
                : x.ok
                  ? esc(FS_MEAN[x.k])
                  : '<b>Point faible cette année.</b> ' +
                    esc('Critère : ' + FS_MEAN[x.k].charAt(0).toLowerCase() + FS_MEAN[x.k].slice(1))) +
              '</small></li>'
            );
          })
          .join('') +
        '</ul></div>'
      );
    }).join('') +
    '</div>'
  );
}
/** Deux contrôles anti-piège : risque de défaillance (Altman) et comptes possiblement embellis (Beneish). */
/** Règle graduée : zones colorées et un point à la place du score (min, max, seuils, sens : bas = mauvais ou bas = bon). */
function scaleLine(v, min, max, zones, ticks, label) {
  var x = function (t) {
      return Math.max(0, Math.min(100, ((t - min) / (max - min)) * 100));
    },
    pos = x(v);
  var h =
    '<div class="scl" role="img" aria-label="' +
    esc(label) +
    '"><div class="scl-bar">' +
    zones
      .map(function (z) {
        return '<i class="z-' + z[2] + '" style="left:' + x(z[0]) + '%;width:' + (x(z[1]) - x(z[0])) + '%"></i>';
      })
      .join('') +
    '<b class="scl-dot" style="left:' +
    pos +
    '%"></b></div><div class="scl-ticks">' +
    ticks
      .map(function (t) {
        var tv = Array.isArray(t) ? t[0] : t,
          tl = Array.isArray(t) ? t[1] : fmtN(t, t % 1 ? 2 : 0);
        var xp = x(tv);
        return (
          '<span style="left:' +
          xp +
          '%' +
          (xp <= 4 ? ';transform:none' : xp >= 96 ? ';transform:translateX(-100%)' : '') +
          '">' +
          tl +
          '</span>'
        );
      })
      .join('') +
    '</div></div>';
  return h;
}
/** Critère visuel : pastille de valeur, verdict, jauge à zones et explication en une phrase (même présentation que Beneish). */
/** Explication repliée : « ⓘ » à toucher pour la lire (jamais devant l'information utile à la décision). */
function xpi(html, label) {
  return html
    ? '<details class="xpi"><summary' +
        (label === ' ' ? ' aria-label="Explication" title="Explication"' : '') +
        '>ⓘ' +
        (label === ' ' ? '' : ' ' + (label || 'Explication')) +
        '</summary>' +
        (/^<(p|ul)/.test(html) ? html : '<p>' + html + '</p>') +
        '</details>'
    : '';
}
function critBox(icon, title, chip, kind, verdict, body, expl) {
  return (
    '<div class="crit"><p class="crit-t">' +
    icon +
    ' ' +
    title +
    '</p><p class="crit-h"><span class="fsc fs-' +
    kind +
    '">' +
    chip +
    '</span> <b>' +
    verdict +
    '</b></p>' +
    body +
    xpi(expl, ' ') +
    '</div>'
  );
}
/** Petite courbe sur 3 mois avec bandes de repère (RSI : 30 et 70). */
function sparkLine(vals, min, max, bands, label) {
  if (!vals || vals.length < 5) return '';
  var W = 320,
    H = 46,
    n = vals.length,
    y = function (v) {
      return H - 2 - ((H - 4) * (Math.max(min, Math.min(max, v)) - min)) / (max - min);
    },
    x = function (k) {
      return 2 + ((W - 4) * k) / (n - 1);
    };
  var g = (bands || [])
    .map(function (b) {
      return (
        '<rect x="0" width="' +
        W +
        '" y="' +
        y(b[1]).toFixed(1) +
        '" height="' +
        (y(b[0]) - y(b[1])).toFixed(1) +
        '" class="sp-' +
        b[2] +
        '"/>'
      );
    })
    .join('');
  return (
    '<svg viewBox="0 0 ' +
    W +
    ' ' +
    H +
    '" class="spark" role="img" aria-label="' +
    esc(label) +
    '">' +
    g +
    '<path d="' +
    vals
      .map(function (v, k) {
        return (k ? 'L' : 'M') + x(k).toFixed(1) + ' ' + y(v).toFixed(1);
      })
      .join('') +
    '" class="sp-line"/><circle cx="' +
    x(n - 1).toFixed(1) +
    '" cy="' +
    y(vals[n - 1]).toFixed(1) +
    '" r="3" class="sp-dot"/></svg>'
  );
}
/** Histogramme du MACD (écart à la ligne de signal) : barres vertes au-dessus de zéro, rouges en dessous. */
function sparkBars(vals, label) {
  if (!vals || vals.length < 5) return '';
  var W = 320,
    H = 46,
    n = vals.length,
    mx = Math.max.apply(null, vals.map(Math.abs)) || 1,
    bw = (W - 4) / n,
    mid = H / 2;
  return (
    '<svg viewBox="0 0 ' +
    W +
    ' ' +
    H +
    '" class="spark" role="img" aria-label="' +
    esc(label) +
    '"><line x1="0" x2="' +
    W +
    '" y1="' +
    mid +
    '" y2="' +
    mid +
    '" class="sp-zero"/>' +
    vals
      .map(function (v, k) {
        var hgt = Math.max(1, (Math.abs(v) / mx) * (mid - 3));
        return (
          '<rect x="' +
          (2 + k * bw).toFixed(1) +
          '" width="' +
          Math.max(1, bw - 1).toFixed(1) +
          '" y="' +
          (v >= 0 ? mid - hgt : mid).toFixed(1) +
          '" height="' +
          hgt.toFixed(1) +
          '" class="' +
          (v >= 0 ? 'sp-up' : 'sp-dn') +
          '"/>'
        );
      })
      .join('') +
    '</svg>'
  );
}
/** Repères visuels du plan d'entrée : RSI, MACD, position dans la figure, entre support et résistance, gain / risque. */
function planVisuals(plan, adj) {
  var o = null;
  try {
    o = ES.oscillators(adj, { series: 60 });
  } catch (e) {
    o = null;
  }
  o = o || plan.osc;
  var f2 = function (v) {
      return fmtN(v, v < 10 ? 2 : 1);
    },
    out = [];
  if (o) {
    var rk = o.rsi < 30 ? 'good' : o.rsi > 70 ? 'bad' : 'neu';
    out.push(
      critBox(
        '📶',
        'RSI 14 jours',
        fmtN(o.rsi, 0),
        rk,
        o.rsi < 30 ? 'Survendu' : o.rsi > 70 ? 'Suracheté' : 'Neutre',
        scaleLine(
          o.rsi,
          0,
          100,
          [
            [0, 30, 'good'],
            [30, 70, 'neu'],
            [70, 100, 'bad'],
          ],
          [
            [30, '30'],
            [70, '70'],
          ],
          'RSI ' + fmtN(o.rsi, 0) + ' sur 100'
        ) +
          (o.series
            ? sparkLine(
                o.series.rsi,
                0,
                100,
                [
                  [0, 30, 'good'],
                  [70, 100, 'bad'],
                ],
                'RSI sur 3 mois'
              ) + '<p class="sp-cap">3 mois</p>'
            : ''),
        'Force des hausses face aux baisses sur 14 séances, de 0 à 100. Sous 30, le titre a beaucoup baissé : un rebond technique est fréquent. Au-dessus de 70, une pause est fréquente.'
      )
    );
    var hist = o.macd - o.signal,
      H = o.series && o.series.hist,
      mx = H ? Math.max.apply(null, H.map(Math.abs)) : Math.abs(hist),
      nv = mx ? Math.max(-1, Math.min(1, hist / mx)) : 0;
    out.push(
      critBox(
        '〽️',
        'MACD',
        o.above ? '▲ haussier' : '▼ baissier',
        o.above ? 'good' : 'bad',
        (o.above ? 'Élan haussier' : 'Élan baissier') +
          (o.cross && o.crossAgo != null && o.crossAgo <= 10 ? ' · croisé il y a ' + (o.crossAgo || 0) + ' j' : ''),
        scaleLine(
          nv,
          -1,
          1,
          [
            [-1, 0, 'bad'],
            [0, 1, 'good'],
          ],
          [
            [-1, '▼'],
            [0, 'signal'],
            [1, '▲'],
          ],
          'MACD par rapport à sa ligne de signal'
        ) + (H ? sparkBars(H, 'Histogramme du MACD sur 3 mois') + '<p class="sp-cap">3 mois</p>' : ''),
        "Mesure l'élan du cours (moyennes de 12 et 26 séances) face à sa propre moyenne, la ligne de signal. Le passage du rouge au vert (croisement haussier) marque souvent la fin d'une baisse ; l'inverse, la fin d'une hausse."
      )
    );
  }
  var w =
      plan.wedge ||
      (function () {
        try {
          return ES.wedge(adj);
        } catch (e) {
          return null;
        }
      })(),
    last = plan.last || (adj.length ? adj[adj.length - 1][4] : null);
  if (w && w.type !== 'none' && w.upperNow > w.lowerNow && last > 0) {
    var fk = ES.figureKey(w),
      tone = (ES.FIGURES[fk] || [])[2] || 'neutral',
      pos = (last - w.lowerNow) / (w.upperNow - w.lowerNow);
    var where =
      pos > 1
        ? 'Cassure par le haut'
        : pos < 0
          ? 'Cassure par le bas'
          : pos < 0.33
            ? 'Près du bas'
            : pos > 0.67
              ? 'Près du haut'
              : 'Au milieu';
    out.push(
      critBox(
        (ES.FIGURES[fk] || ['📐'])[0],
        esc(w.label),
        Math.round(pos * 100) + ' %',
        pos > 1
          ? fk === 'rising'
            ? 'neu'
            : 'good'
          : pos < 0
            ? 'bad'
            : tone === 'good'
              ? 'good'
              : tone === 'bad'
                ? 'bad'
                : 'neu',
        where,
        scaleLine(
          pos,
          -0.25,
          1.25,
          [
            [-0.25, 0, 'bad'],
            [0, 1, 'neu'],
            [1, 1.25, 'good'],
          ],
          [
            [0, f2(w.lowerNow)],
            [1, f2(w.upperNow)],
          ],
          'Position du cours entre les deux droites'
        ),
        (w.weak ? "<b>Figure peu marquée</b> : une des droites ne touche le cours qu'une fois, à confirmer. " : '') +
          esc(w.reading.charAt(0).toUpperCase() + w.reading.slice(1)) +
          '. La droite haute relie les sommets des 3 derniers mois, la droite basse les creux' +
          (w.apexIn
            ? ' ; elles se rejoignent dans environ ' + w.apexIn + ' séances, la sortie se fait en général avant'
            : '') +
          '.'
      )
    );
  }
  var sc = [plan.primary, plan.alt].filter(Boolean),
    res = null,
    sup = null;
  sc.forEach(function (c) {
    if (c.key === 'breakout' && c.level > 0) res = c.level;
    if ((c.key === 'support' || c.key === 'retest') && c.level > 0) sup = c.level;
  });
  if (sup && res && res > sup && last > 0) {
    var p2 = (last - sup) / (res - sup);
    out.push(
      critBox(
        '🧱',
        'Support / résistance',
        Math.round(p2 * 100) + ' %',
        p2 < 0.3 ? 'good' : p2 > 0.8 ? 'mid' : 'neu',
        p2 < 0
          ? 'Support cédé'
          : p2 > 1
            ? 'Résistance franchie'
            : p2 < 0.3
              ? "Zone d'achat"
              : p2 > 0.8
                ? 'Sous la résistance'
                : 'Entre les deux',
        scaleLine(
          p2,
          -0.2,
          1.2,
          [
            [-0.2, 0, 'bad'],
            [0, 0.3, 'good'],
            [0.3, 0.8, 'neu'],
            [0.8, 1, 'mid'],
            [1, 1.2, 'good'],
          ],
          [
            [0, 'S ' + f2(sup)],
            [1, 'R ' + f2(res)],
          ],
          'Position du cours entre support et résistance'
        ),
        'Un support est un niveau où les acheteurs sont revenus plusieurs fois, une résistance un niveau où les vendeurs ont repris la main. Entrer près du support limite la perte possible ; au-dessus de la résistance, la voie est libre.'
      )
    );
  }
  var pr = plan.primary;
  if (pr && pr.rr != null) {
    var rr = pr.rr;
    out.push(
      critBox(
        '⚖️',
        'Gain / risque',
        String(rr).replace('.', ','),
        rr >= 2 ? 'good' : rr >= 1.5 ? 'mid' : 'bad',
        rr >= 2 ? 'Favorable' : rr >= 1.5 ? 'Acceptable' : 'Trop faible',
        scaleLine(
          Math.min(rr, 4),
          0,
          4,
          [
            [0, 1.5, 'bad'],
            [1.5, 2, 'mid'],
            [2, 4, 'good'],
          ],
          [
            [1.5, '1,5'],
            [4, '4+'],
          ],
          'Gain sur risque ' + rr
        ) +
          (pr.prob != null && pr.prob < 20 ? '<p class="small"><b>⚠️ Niveau peu probable d\'ici 3 mois</b></p>' : '') +
          (pr.prob != null
            ? '<p class="small">🎯 Atteint d\'ici 3 mois : <b>' +
              pr.prob +
              ' %</b></p><div class="pbar"><i style="width:' +
              Math.max(0, Math.min(100, pr.prob)) +
              '%"></i></div>'
            : ''),
        "Gain visé jusqu'à l'objectif divisé par la perte acceptée jusqu'au stop. Euro Signal exige au moins 1,5 pour parler de « zone d'entrée » ; au-dessus de 2, le gain potentiel vaut largement le risque."
      )
    );
  }
  return out.length ? '<div class="crits">' + out.join('') + '</div>' : '';
}
/** Indicateur compact (secteurs, fiches) : libellé, valeur colorée, barre simple ou centrée sur zéro. */
function mini(label, txt, v, min, max, centered, tip) {
  if (v == null || !isFinite(v)) return '';
  var x = function (t) {
      return Math.max(0, Math.min(100, ((t - min) / (max - min)) * 100));
    },
    z = centered ? x(0) : 0,
    p = x(v);
  var cls = centered ? (v >= 0 ? 'up' : 'dn') : 'lv';
  return (
    '<div class="mt"' +
    (tip ? ' title="' + esc(tip) + '"' : '') +
    '><span class="mt-l">' +
    label +
    '</span><b class="mt-v ' +
    (centered ? (v >= 0 ? 'pos' : 'neg') : '') +
    '">' +
    txt +
    '</b><span class="mt-b' +
    (centered ? ' c' : '') +
    '"><i class="' +
    cls +
    '" style="left:' +
    Math.min(z, p) +
    '%;width:' +
    Math.abs(p - z) +
    '%"></i>' +
    (centered ? '<s style="left:' + z + '%"></s>' : '') +
    '</span></div>'
  );
}
/** Évolution d'un score par exercice : courbe, seuils en pointillés, points colorés selon la zone, valeur de chaque année. */
function scoreTrend(H, key, min, max, lines, zoneOf, name, upIsGood) {
  if (!H || H.length < 2) return '<p class="foot">Évolution : un seul exercice calculable pour l\'instant.</p>';
  var W = 320,
    Hh = 120,
    L = 30,
    Rr = 12,
    T = 18,
    B = 22,
    n = H.length;
  var lo = Math.min(
      min,
      Math.min.apply(
        null,
        H.map(function (h) {
          return h[key];
        })
      )
    ),
    hi = Math.max(
      max,
      Math.max.apply(
        null,
        H.map(function (h) {
          return h[key];
        })
      )
    );
  var X = function (k) {
      return L + (W - L - Rr) * (n === 1 ? 0.5 : k / (n - 1));
    },
    Y = function (v) {
      return T + (Hh - T - B) * (1 - (v - lo) / (hi - lo));
    };
  var svg =
    '<svg class="sctr" viewBox="0 0 ' +
    W +
    ' ' +
    Hh +
    '" role="img" aria-label="' +
    esc(
      name +
        ' par exercice : ' +
        H.map(function (h) {
          return h.year + ' ' + fmtN(h[key], 2);
        }).join(', ')
    ) +
    '">';
  lines.forEach(function (ln) {
    var y = Y(ln[0]);
    svg +=
      '<line x1="' +
      L +
      '" x2="' +
      (W - Rr) +
      '" y1="' +
      y +
      '" y2="' +
      y +
      '" class="sctr-th"/><text x="' +
      (L - 4) +
      '" y="' +
      (y + 3) +
      '" class="sctr-ax" text-anchor="end">' +
      fmtN(ln[0], ln[0] % 1 ? 2 : 0) +
      '</text>';
  });
  svg +=
    '<polyline class="sctr-ln" points="' +
    H.map(function (h, k) {
      return X(k) + ',' + Y(h[key]);
    }).join(' ') +
    '"/>';
  H.forEach(function (h, k) {
    var cx = X(k),
      cy = Y(h[key]);
    svg +=
      '<circle cx="' +
      cx +
      '" cy="' +
      cy +
      '" r="5" class="sctr-pt z-' +
      zoneOf(h) +
      '"/><text x="' +
      cx +
      '" y="' +
      (cy - 9) +
      '" class="sctr-v" text-anchor="middle">' +
      fmtN(h[key], 2) +
      '</text><text x="' +
      cx +
      '" y="' +
      (Hh - 6) +
      '" class="sctr-ax" text-anchor="middle">' +
      esc(h.year) +
      '</text>';
  });
  var d = H[n - 1][key] - H[0][key];
  var better = Math.abs(d) < 0.1 ? null : d > 0 === !!upIsGood;
  return (
    svg +
    '</svg>' +
    '<p class="foot">De ' +
    esc(H[0].year) +
    ' à ' +
    esc(H[n - 1].year) +
    ' : ' +
    (d >= 0 ? '+' : '−') +
    fmtN(Math.abs(d), 2) +
    (better == null
      ? ', stable'
      : better
        ? ', <b class="pos">en amélioration</b>'
        : ', <b class="neg">en dégradation</b>') +
    '.</p>'
  );
}
function riskScores(a) {
  var az = a.altman,
    bm = a.beneish,
    n = function (v) {
      return fmtN(v, 2);
    };
  var ZL = { safe: ['good', 'Zone sûre'], grey: ['mid', 'Zone grise'], distress: ['bad', 'Zone de détresse'] };
  var h = '<h4 class="mt">Contrôles anti-piège</h4><div class="fsgroups">';
  h +=
    '<div class="fsg"><h5>🧯 Risque de défaillance (Altman Z\'\')</h5>' +
    (az && !az.na
      ? '<p><span class="fsc fs-' +
        ZL[az.zone][0] +
        '">' +
        n(az.z) +
        '</span> <b>' +
        ZL[az.zone][1] +
        '</b> <span class="muted">(exercice ' +
        esc(az.year) +
        ')</span></p>' +
        (az.confirm && az.confirm.length ? '<p>Confirmé par : ' + esc(az.confirm.join(', ')) + '.</p>' : '') +
        (az.note ? '<p class="muted">' + esc(az.note.charAt(0).toUpperCase() + az.note.slice(1)) + '.</p>' : '')
      : '<p class="muted">' +
        esc(az && az.reason ? az.reason.charAt(0).toUpperCase() + az.reason.slice(1) : 'Non calculable') +
        (az && /manquants/.test(az.reason || '') ? ' : postes en cours de collecte, complétés au fil des soirs' : '') +
        '.</p>') +
    (az && !az.na
      ? scaleLine(
          az.z,
          -1,
          6,
          [
            [-1, 1.1, 'bad'],
            [1.1, 2.6, 'mid'],
            [2.6, 6, 'good'],
          ],
          [1.1, 2.6],
          'Altman ' + fmtN(az.z, 2) + ' sur une échelle de -1 à 6'
        ) +
        scoreTrend(
          a.altmanHistory,
          'z',
          0,
          3,
          [[1.1], [2.6]],
          function (h) {
            return h.zone === 'safe' ? 'good' : h.zone === 'grey' ? 'mid' : 'bad';
          },
          'Altman Z',
          true
        )
      : '') +
    xpi(
      'Combine fonds de roulement, réserves accumulées, rentabilité et solidité des fonds propres (Altman, version 1995 adaptée aux sociétés non industrielles et hors États-Unis). Au-dessus de 2,6 : risque faible ; de 1,1 à 2,6 : zone grise ; sous 1,1 : profil proche des sociétés qui ont fait défaut dans les deux ans.',
      'Méthode'
    ) +
    '</div>';
  h +=
    '<div class="fsg"><h5>🔍 Qualité des comptes (Beneish M)</h5>' +
    (bm && !bm.na
      ? '<p><span class="fsc fs-' +
        (bm.flag ? 'bad' : 'good') +
        '">' +
        n(bm.m) +
        '</span> <b>' +
        (bm.flag ? "Au-dessus du seuil d'alerte" : "Sous le seuil d'alerte") +
        '</b> <span class="muted">(exercice ' +
        esc(bm.year) +
        ')</span></p>' +
        (bm.flags && bm.flags.length ? '<p>Points relevés : ' + esc(bm.flags.join(' ; ')) + '.</p>' : '')
      : '<p class="muted">' +
        esc(bm && bm.reason ? bm.reason.charAt(0).toUpperCase() + bm.reason.slice(1) : 'Non calculable') +
        '.</p>') +
    (bm && !bm.na
      ? scaleLine(
          bm.m,
          -4,
          0,
          [
            [-4, -1.78, 'good'],
            [-1.78, 0, 'bad'],
          ],
          [-1.78],
          'Beneish ' + fmtN(bm.m, 2) + ' sur une échelle de -4 à 0'
        ) +
        scoreTrend(
          a.beneishHistory,
          'm',
          -3,
          -1.5,
          [[-1.78]],
          function (h) {
            return h.flag ? 'bad' : 'good';
          },
          'Beneish M',
          false
        )
      : '') +
    xpi(
      "Huit ratios (créances, marge brute, qualité des actifs, croissance, amortissements, frais, endettement, part du bénéfice non encaissée) comparés à l'exercice précédent (Beneish, 1999). Au-dessus de −1,78 : profil semblable aux sociétés qui ont embelli leurs comptes. Ce n'est pas une preuve de fraude, mais une raison de lire le rapport annuel de près.",
      'Méthode'
    ) +
    '</div></div>';
  return h;
}
function fscoreScale() {
  var G = S.cfg.accounts.fscoreGood,
    B = S.cfg.accounts.fscoreBad;
  var rows = [
    [
      '8 – 9',
      'top',
      'Excellent',
      'Comptes en nette amélioration sur presque tous les plans : rentable, encaisse son bénéfice, se désendette, ne dilue pas, gagne en efficacité.',
    ],
    [G + '', 'good', 'Solide', 'Majorité de signaux positifs : profil financier sain.'],
    [
      B + 1 + ' – ' + (G - 1),
      'mid',
      'Intermédiaire',
      "Autant de progrès que de reculs : pas de tendance nette, à surveiller d'une année sur l'autre.",
    ],
    [
      '2 – ' + B,
      'bad',
      'Fragile',
      'Plusieurs signaux de dégradation : la baisse du cours peut être justifiée par les comptes.',
    ],
    [
      '0 – 1',
      'vbad',
      'Très fragile',
      "Dégradation généralisée : risque de difficultés financières, de dépréciations ou d'augmentation de capital.",
    ],
  ];
  return (
    '<details class="fsscale"><summary>Comment lire le F-score de Piotroski ?</summary>' +
    "<p>Le F-score, créé par le professeur Joseph Piotroski (université de Chicago, 2000), vérifie 9 points simples dans les comptes annuels, chacun comparé à l'exercice précédent. Chaque point rempli vaut 1 ; le total va de 0 à 9. Il ne mesure pas la valorisation mais <b>le sens dans lequel évolue la santé financière</b>.</p>" +
    '<div class="tablewrap"><table class="grid small"><thead><tr><th>Score</th><th>Lecture</th><th>Ce que ça veut dire</th></tr></thead><tbody>' +
    rows
      .map(function (r) {
        return (
          '<tr><td><span class="fsc fs-' +
          r[1] +
          '">' +
          r[0] +
          '</span></td><td><b>' +
          r[2] +
          '</b></td><td>' +
          esc(r[3]) +
          '</td></tr>'
        );
      })
      .join('') +
    '</tbody></table></div>' +
    "<p><b>Les 9 points, en 3 familles :</b> rentabilité (bénéfice positif, trésorerie d'exploitation positive, rentabilité en hausse, bénéfice encaissé), structure financière (dette en baisse, liquidité en hausse, pas d'actions nouvelles), efficacité (marge brute en hausse, ventes par euro d'actif en hausse).</p>" +
    "<p><b>Pourquoi c'est utile ici :</b> un dirigeant qui achète après une forte baisse peut avoir raison… ou se tromper sur une entreprise en difficulté. Le F-score aide à distinguer une action bon marché d'une entreprise qui se dégrade. Dans l'étude d'origine (actions américaines bon marché, 1976–1996), les sociétés notées 8 ou 9 ont battu celles notées 0 ou 1 d'environ 23 % par an.</p>" +
    "<p class=\"foot\">Limites : il repose sur les comptes annuels (publiés jusqu'à 4 mois après la clôture), compare deux années seulement, et ne s'applique pas aux banques et assurances. L'évolution sur plusieurs exercices compte autant que la note du jour.</p></details>"
  );
}
/** Prévisionnels des analystes (consensus Yahoo du jour), lus avec recul : le sens des révisions compte plus que le niveau. */
function forecastBlock(i) {
  var x = S.inst[i] || {},
    v = ES.forecastView(x.forecast, x.fund),
    TI = { good: '🟢', mixed: '🟡', bad: '🔴', thin: '⚪' };
  var h =
    '<h4 class="mt">🔮 Prévisionnels des analystes' +
    (x.forecast && x.forecast.asOf
      ? ' <span class="muted">consensus du ' + esc(shortDate(x.forecast.asOf)) + '</span>'
      : '') +
    '</h4>';
  if (v.na) return h + '<p class="muted">' + esc(v.reason) + '.</p>';
  var LB = {
    good: 'Prévisions favorables',
    mixed: 'Prévisions sans élan',
    bad: 'Prévisions défavorables',
    thin: 'Consensus trop maigre',
  };
  h +=
    '<p class="accv acc-' +
    (v.tone === 'thin' ? 'na' : v.tone) +
    '">' +
    TI[v.tone] +
    ' <b>' +
    LB[v.tone] +
    '</b> — ' +
    esc(v.text) +
    '</p>';
  var pc = function (g) {
    return g == null
      ? '<span class="muted">n.d.</span>'
      : '<span class="' + (g >= 0 ? 'pos' : 'neg') + '">' + pct(g) + '</span>';
  };
  var num = function (n, d) {
    return n == null ? 'n.d.' : Math.abs(n) >= 1e6 ? big(n) : fmtN(n, d == null ? 2 : d);
  };
  var y0 = v.fy0 ? String(v.fy0) + 'e' : 'En cours',
    y1 = v.fy1 ? String(v.fy1) + 'e' : 'Suivant',
    yp = v.fy0 ? String(v.fy0 - 1) : 'Publié';
  h +=
    '<div class="tablewrap"><table class="grid acct"><thead><tr><th>Exercice</th><th class="num">' +
    esc(yp) +
    '</th><th class="num">' +
    esc(y0) +
    '</th><th class="num">' +
    esc(y1) +
    '</th></tr></thead><tbody>' +
    '<tr><th>Bénéfice par action</th><td class="num">' +
    num(v.epsPrev) +
    '</td><td class="num">' +
    num(v.eps0) +
    '<small>' +
    pc(v.epsG0) +
    '</small></td><td class="num">' +
    num(v.eps1) +
    '<small>' +
    pc(v.epsG1) +
    '</small></td></tr>' +
    '<tr><th>Chiffre d\'affaires</th><td class="num">' +
    num(v.revPrev) +
    '</td><td class="num">' +
    num(v.rev0) +
    '<small>' +
    pc(v.revG0) +
    '</small></td><td class="num">' +
    num(v.rev1) +
    '<small>' +
    pc(v.revG1) +
    '</small></td></tr>' +
    '</tbody></table></div>';
  var more = [];
  if (v.rev30 != null || v.rev90 != null)
    more.push(
      'Révisions du bénéfice attendu : ' +
        (v.rev30 != null ? pct(v.rev30) + ' sur 30 jours' : '') +
        (v.rev30 != null && v.rev90 != null ? ', ' : '') +
        (v.rev90 != null ? pct(v.rev90) + ' sur 90 jours' : '') +
        '.'
    );
  if (v.disp1 != null)
    more.push(
      "Écart entre l'estimation la plus haute et la plus basse : " +
        Math.round(v.disp1) +
        ' % du consensus' +
        (v.disp1 >= 50 ? ' (forte incertitude)' : '') +
        '.'
    );
  if (v.peg != null)
    more.push(
      'PEG (PER attendu ÷ croissance attendue) : ' +
        fmtN(v.peg, 1) +
        (v.peg < 1
          ? ', la croissance attendue paraît peu payée'
          : v.peg > 2
            ? ', la croissance attendue est déjà chère'
            : '') +
        '.'
    );
  if (v.upside != null)
    more.push(
      'Objectif de cours moyen : ' +
        pct(v.upside) +
        ' par rapport au cours' +
        (v.targetLow != null && v.targetHigh != null
          ? ' (fourchette ' + fmtN(v.targetLow) + ' à ' + fmtN(v.targetHigh) + ' ' + esc(v.targetCur || '') + ')'
          : '') +
        (v.nTarget ? ', ' + v.nTarget + ' analystes' : '') +
        '.'
    );
  if (more.length)
    h +=
      '<ul class="plain small">' +
      more
        .map(function (t) {
          return '<li>' + t + '</li>';
        })
        .join('') +
      '</ul>';
  h +=
    '<div class="kidline kid-' +
    (v.tone === 'thin' ? 'na' : v.tone) +
    '"><p class="kidx">' +
    esc(v.explain).replace(/^En clair :/, '<b>En clair :</b>') +
    '</p></div>';
  h += xpi(
    '« e » : estimé. Source : consensus Yahoo Finance du jour (montants dans la devise des comptes). Mesuré en observation à chaque achat de dirigeant (prévisions figées ce soir-là), sans poids dans la note avant la revue de janvier.',
    'Source'
  );
  return h;
}
