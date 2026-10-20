/* Euro Signal — interface : achats des dirigeants, alertes, sources, aide, fiche dirigeant.
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
/* ----- Univers ----- */
function vUnivers() {
  var keys = Object.keys(S.inst).filter(function (i) {
      return !S.inst[i].benchmark;
    }),
    groups = { retenu: [], a_examiner: [], rejete: [] };
  keys.forEach(function (i) {
    groups[S.computed[i].uni.status].push(i);
  });
  var u = S.cfg.universe;
  var h =
    '<h2 class="vt">Univers</h2><p class="lead">Seuils de départ (configurables, non validés scientifiquement) : liquidité moyenne ≥ ' +
    ES.fmtEur(u.minAdv20Eur) +
    ' par jour sur 20 séances, au moins ' +
    u.minSessions +
    ' séances, dernier cours de moins de ' +
    u.maxStaleBusinessDays +
    ' jours ouvrés, volatilité annualisée ≤ ' +
    u.maxAnnualVolPct +
    " %, pas de suspension ni de variation anormale. L'univers contient uniquement ce que vous avez importé : ce n'est pas une couverture exhaustive du marché.</p>";
  h +=
    '<div class="segs" role="tablist">' +
    [
      ['retenu', 'Retenus'],
      ['a_examiner', 'À examiner'],
      ['rejete', 'Rejetés'],
    ]
      .map(function (g) {
        return (
          '<button role="tab" class="' +
          (S.uniFilter === g[0] ? 'on' : '') +
          '" data-a="uni" data-v="' +
          g[0] +
          '">' +
          g[1] +
          ' <span class="count">' +
          groups[g[0]].length +
          '</span></button>'
        );
      })
      .join('') +
    '</div>';
  var list = groups[S.uniFilter];
  if (!list.length) return h + '<p class="muted pad">Aucun titre dans cette catégorie.</p>';
  h +=
    '<div class="tablewrap"><table class="grid"><thead><tr><th>Société</th><th class="hide-s">Domicile · place</th><th class="num">Séances</th><th class="num">Liquidité 20 j</th><th class="hide-s">Dernier cours</th><th>Motifs</th></tr></thead><tbody>';
  list
    .sort(function (a, b) {
      return (S.inst[a].name || a).localeCompare(S.inst[b].name || b, 'fr');
    })
    .slice(0, 500)
    .forEach(function (i) {
      var x = S.inst[i],
        s = x.stats || {},
        c = S.computed[i];
      h +=
        '<tr class="rowlink" data-a="open" data-i="' +
        i +
        '" tabindex="0"><td><b>' +
        esc(x.name || i) +
        '</b><small>' +
        esc(i) +
        '</small></td><td class="hide-s">' +
        esc((x.country || '?') + ' · ' + (x.venue || '?')) +
        '</td><td class="num">' +
        (s.sessions || 0) +
        '</td><td class="num">' +
        (s.adv20Eur != null ? ES.fmtEur(s.adv20Eur) : 'n.d.') +
        '</td><td class="hide-s">' +
        (s.lastDate || '—') +
        '</td><td class="reasons">' +
        (c.uni.reasons.length
          ? c.uni.reasons.map(esc).join('<br>')
          : '<span class="muted">Tous les contrôles passés</span>') +
        '</td></tr>';
    });
  return h + '</tbody></table></div>';
}

/* ----- Alertes ----- */
/** Positions et plans surveillés depuis ce navigateur (rien n'est publié : la liste vit sur cet appareil). */
function mySuivis() {
  var pos = [],
    wat = [];
  try {
    for (var k = 0; k < window.localStorage.length; k++) {
      var key = window.localStorage.key(k),
        m = /^es\.(open|watch)\.([A-Z0-9][A-Z0-9.&-]{1,24})$/.exec(key || '');
      if (m && window.localStorage.getItem(key))
        (m[1] === 'open' ? pos : wat).push([m[2], window.localStorage.getItem(key)]);
    }
  } catch (e) {}
  var row = function (x, extra) {
    var es = ES.isValidIsin(x[0]),
      rk = es ? null : rankOf(null, x[0]),
      n = (S.inst[x[0]] || rk || {}).name || x[0],
      go = es
        ? 'data-a="open" data-i="' + esc(x[0]) + '"'
        : 'data-a="secCo" data-v="' + esc(x[0]) + '" data-from="rank"';
    return (
      '<li><div><button class="linkbtn suivn" ' +
      go +
      '><b>' +
      esc(n) +
      '</b> ›</button><small>' +
      extra +
      '</small></div>' +
      (x.btn ? '<span class="row-btn">' + x.btn + '</span>' : '') +
      '</li>'
    );
  };
  var h = '<section class="card"><h3>🔔 Mes suivis</h3>';
  h +=
    '<p class="small"><b>Plans d\'entrée surveillés</b></p>' +
    (wat.length
      ? '<ul class="evs">' +
        wat
          .map(function (x) {
            x.btn = ' <button class="small" data-a="watchOff" data-i="' + esc(x[0]) + '">Ne plus surveiller</button>';
            return row(
              x,
              'surveillé depuis le ' + shortDate(x[1]) + (manPlan(x[0]) ? ' · ✏️ plan ajusté à la main' : '')
            );
          })
          .join('') +
        '</ul>'
      : '<p class="muted small">Aucun depuis cet appareil.</p>');
  h +=
    '<p class="small"><b>Positions suivies pour la revente</b></p>' +
    (pos.length
      ? '<ul class="evs">' +
        pos
          .map(function (x) {
            return row(x, "bouton « Je l'ai vendu » dans la fiche pour arrêter");
          })
          .join('') +
        '</ul>'
      : '<p class="muted small">Aucune depuis cet appareil.</p>');
  h +=
    '<p class="foot">Vos suivis ne sont jamais publiés : ils partent par email vers votre propre boîte, que le calcul du soir lit. Cette liste ne montre donc que ceux faits depuis ce téléphone ou ce navigateur. Pour arrêter un suivi fait ailleurs : ouvrez la fiche de la société et touchez « Ne plus surveiller » (ou « Je l\'ai vendu »), ou envoyez-vous un email dont l\'objet est <code>[Euro Signal] Ne plus surveiller</code> suivi du code ISIN.</p></section>';
  return h;
}
function vAlertesAuto() {
  var mailReady = S.snapshot && S.snapshot.mail && S.snapshot.mail.ready;
  var det = function (title, body, k) {
    return '<details class="fsscale more" data-k="' + k + '"><summary>' + title + '</summary>' + body + '</details>';
  };
  var h =
    '<h2 class="vt">Alertes</h2>' +
    mySuivis() +
    (function () {
      var t1 = trackBox(),
        t2 = trackBox('value');
      return t1 || t2
        ? '<section class="card"><h3>📬 Que sont devenues les sélections ?</h3>' +
            (t1 ? '<p class="small"><b>🎯 Momentum</b></p>' + t1 : '') +
            (t2 ? '<p class="small"><b>💎 Valeur</b></p>' + t2 : '') +
            sigBox() +
            '<p class="foot">Résultat réel des sociétés proposées chaque semaine, comparé à l\'indice, figé à 3 et 6 mois.</p></section>'
        : '';
    })();
  h +=
    '<section class="card"><h3>📧 Emails automatiques</h3>' +
    (mailReady
      ? ''
      : '<p class="note warn">Gmail n\'est pas configuré : rien ne part, les emails sont seulement simulés.</p>') +
    '<ul class="plain"><li>📋 <b>Lundi</b> : la sélection de la semaine (5 🎯 + 2 💎, ✅ feu vert ou ⏸️ en attente).</li>' +
    '<li>🎯 <b>Feu vert</b> : une société ⏸️ du 🎯 redevient achetable (un email par société sur 30 jours au plus).</li>' +
    "<li>📉 <b>Après « Je l'ai acheté »</b> : chaque tranche de −10 %, la protection à −30 %, le rappel des 6 mois (garder ou vendre).</li>" +
    "<li>🔔 <b>Après « Surveiller »</b> : le cours entre dans la zone d'achat, casse sa résistance ou passe sous le stop ; avec un plan ✏️ ajusté à la main, vos propres niveaux.</li>" +
    "<li>⚠️ <b>Krach</b> : quand l'alerte s'allume (marché à −20 % sur un an), puis quand elle s'éteint (retour au-dessus de −15 %).</li>" +
    '<li>🔎 <b>Auto-surveillance</b> : si la méthode ou une règle perd son avantage (un email par mois au plus).</li>' +
    '<li>📊 <b>Bilan</b> chaque trimestre · 🧭 <b>point de revue</b> le 31/01/2027 · 💡 <b>piste confirmée</b> (révisions des analystes).</li>' +
    '<li>🛠️ <b>Technique</b> : seulement si un contrôle du soir échoue.</li></ul>' +
    "<p class=\"foot\">Plus d'email sur les achats de dirigeants ni de « barème ajusté » : c'est l'ancienne méthode, pas meilleure que le hasard. Les déclarations restent consultables dans l'onglet Achats.</p></section>";
  var log = Object.keys(S.alerts)
    .map(function (k) {
      return S.alerts[k];
    })
    .sort(function (x, y) {
      return (x.createdAt || '') < (y.createdAt || '') ? 1 : -1;
    });
  h +=
    '<section class="card"><h3>Journal des emails <span class="muted">· ' +
    log.length +
    '</span></h3>' +
    det(
      'Voir le journal',
      log.length
        ? '<div class="tablewrap"><table class="grid"><thead><tr><th>Date</th><th class="hide-s">Société</th><th>Objet</th><th>Statut</th></tr></thead><tbody>' +
            log
              .slice(0, 200)
              .map(function (x) {
                var st = ALERT_STATUS[x.status] || [x.status, 'neutral'];
                return (
                  '<tr><td>' +
                  esc(shortDate(String(x.createdAt || '').slice(0, 10))) +
                  '</td><td class="hide-s">' +
                  esc(x.name || x.isin) +
                  '</td><td>' +
                  esc(String(x.subject || '').replace(/^\[Euro Signal\] /, '')) +
                  (x.error ? '<small class="neg">' + esc(x.error) + '</small>' : '') +
                  '</td><td><span class="chip ' +
                  st[1] +
                  '">' +
                  st[0] +
                  '</span></td></tr>'
                );
              })
              .join('') +
            '</tbody></table></div><p class="foot">« Non confirmé » : peut-être parti, jamais renvoyé automatiquement (vérifiez vos Envoyés). « Échec » : rien n\'est parti, nouvel essai au prochain calcul.</p>'
        : '<p class="muted">Aucun email pour l\'instant.</p>',
      'al-log'
    ) +
    '</section>';
  return h;
}
/* ----- Sources ----- */
function srcState(s) {
  if (!s) return { k: 'neutral', t: 'Jamais collectée' };
  if (s.status === 'absent') return { k: 'neutral', t: 'Non configurée' };
  if (s.status === 'echec') return { k: 'bad', t: 'En échec' };
  if (s.status === 'partiel') return { k: 'warn', t: 'Partielle' };
  if (!s.lastSuccess) return { k: 'neutral', t: 'Jamais collectée' };
  var age = ES.daysBetween(s.lastSuccess, S.today);
  return age <= S.cfg.sources.maxRegistryAgeDays
    ? { k: 'good', t: 'À jour (' + age + ' j)' }
    : { k: 'warn', t: 'En retard (' + age + ' j)' };
}
function vSources() {
  var h =
    '<h2 class="vt">Sources de données</h2><p class="lead">État de chaque source. Une source en échec ou en retard bloque les alertes des titres domiciliés dans le pays concerné : l\'absence d\'opération n\'est jamais confondue avec une absence de collecte.</p>';
  h +=
    '<div class="tablewrap"><table class="grid"><thead><tr><th>Source</th><th>État</th><th class="hide-s">Pays couverts</th><th class="hide-s">Dernière collecte réussie</th><th class="hide-s">Dernier import</th></tr></thead><tbody>';
  var srcList = REGISTRIES.filter(function (r) {
    return !S.ro || S.src[r.name];
  }); // en ligne : seulement les sources réellement collectées
  Object.keys(S.src).forEach(function (n) {
    if (
      !srcList.some(function (r) {
        return r.name === n;
      })
    )
      srcList.push({ name: n, label: (S.src[n].kind ? S.src[n].kind + ' · ' : '') + (S.src[n].via || n), url: '' });
  });
  if (S.ro)
    srcList.sort(function (x, y) {
      return (S.src[y.name] ? 1 : 0) - (S.src[x.name] ? 1 : 0);
    });
  srcList.forEach(function (r) {
    var s = S.src[r.name],
      st = srcState(s),
      l = s && s.log && s.log[0];
    h +=
      '<tr><td><b>' +
      esc(r.name) +
      '</b><small>' +
      esc(r.label) +
      '</small>' +
      (s && s.via ? '<small>' + esc(s.via) + '</small>' : '') +
      (ES.safeUrl(r.url)
        ? '<small><a href="' +
          esc(ES.safeUrl(r.url)) +
          '" target="_blank" rel="noopener">' +
          esc(r.url.replace('https://', '')) +
          '</a></small>'
        : '') +
      '</td><td><span class="chip ' +
      st.k +
      '">' +
      st.t +
      '</span>' +
      (s && s.note ? '<small>' + esc(s.note) + '</small>' : '') +
      '</td><td class="hide-s">' +
      esc(s && s.countries && s.countries.length ? s.countries.join(', ') : r.country || '—') +
      '</td><td class="hide-s">' +
      ((s && s.lastSuccess) || '—') +
      (s && s.coveredFrom ? '<small>publications du ' + s.coveredFrom + ' au ' + s.coveredTo + '</small>' : '') +
      '</td><td class="hide-s">' +
      (l
        ? l.accepted +
          ' acceptées · ' +
          (l.rejected || 0) +
          ' refusées' +
          (l.added != null ? ' · ' + l.added + ' nouvelles' : '')
        : '—') +
      '</td></tr>';
  });
  h += '</tbody></table></div>';
  var ss = S.snapshot && S.snapshot.shortsSrc;
  if (ss && Object.keys(ss).length)
    h +=
      '<h3 class="mt">Positions vendeuses des fonds (≥ 0,5 % du capital)</h3><div class="tablewrap"><table class="grid"><thead><tr><th>Pays</th><th class="hide-s">Régulateur</th><th>État</th><th class="num">Positions</th></tr></thead><tbody>' +
      Object.keys(ss)
        .sort()
        .map(function (cc) {
          var x = ss[cc];
          return (
            '<tr><td>' +
            flag(cc) +
            esc(COUNTRIES[cc] || cc) +
            '</td><td class="hide-s">' +
            esc(x.name || '') +
            '</td><td><span class="chip ' +
            (x.status === 'ok' ? 'good' : 'bad') +
            '">' +
            (x.status === 'ok' ? 'À jour' : 'En échec') +
            '</span>' +
            (x.note ? '<small>' + esc(x.note) + '</small>' : '') +
            '</td><td class="num">' +
            (x.open != null ? x.open : 'n.d.') +
            '</td></tr>'
          );
        })
        .join('') +
      '</tbody></table></div><p class="foot">Information croisée, sans effet sur la note ni sur les alertes. En cas d\'échec, les positions de la veille sont conservées.</p>';
  return h;
}

/* ----- Validation ----- */
/** Marge d'erreur d'un pourcentage (intervalle de Wilson à 95 %). */
function ci(p, n) {
  var w = ES.wilson(p, n);
  return w
    ? '<small class="ci" title="Marge d\'erreur à 95 % : la vraie valeur se situe très probablement dans cette fourchette">' +
        w[0] +
        '–' +
        w[1] +
        ' %</small>'
    : '';
}
/* ----- Fiche dirigeant : tout l'historique connu d'une personne (fichier lu à la demande) ----- */
function loadInsiders() {
  var f = S.snapshot && S.snapshot.history && S.snapshot.history.insidersFile;
  if (S.ins || S.insLoading || S.insError || !f || !/^data\/[\w.-]+\.json$/.test(f)) {
    if (!f) S.insError = 'fichier absent';
    return;
  } // un échec n'est pas réessayé en boucle
  S.insLoading = true;
  fetch(f, { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      if (d.format !== 'euro-signal-insiders') throw new Error('format inattendu');
      S.ins = defang(d);
      S.insLoading = false;
      if (S.view === 'dirigeant') render();
    })
    .catch(function (e) {
      S.insLoading = false;
      var m = (e && e.message) || '';
      S.insError = /^HTTP|format/.test(m) ? m : 'fichier illisible, réessayez après la mise à jour du soir';
      if (S.view === 'dirigeant') render();
    });
}
var REG_FR = {
  AMF: 'France (AMF)',
  FI: 'Suède (FI)',
  BaFin: 'Allemagne (BaFin)',
  CNMV: 'Espagne (CNMV)',
  CONSOB: 'Italie (Consob)',
  FSMA: 'Belgique (FSMA)',
  AFM: 'Pays-Bas (AFM)',
};
var COHEN = {
  routinier: [
    '🔁 Routinier',
    'warn',
    'un ordre le même mois calendaire chacune des 3 dernières années : ses opérations suivent surtout un calendrier (rémunération, habitude), elles annoncent peu de choses',
  ],
  opportuniste: [
    '🧭 Opportuniste',
    'good',
    "au moins un ordre chacune des 3 dernières années, jamais au même mois : il choisit ses moments, c'est le profil que la recherche juge informatif",
  ],
  'non classé': [
    'Non classé',
    'neutral',
    "pas d'ordre chacune des 3 dernières années : trop peu d'opérations pour juger son comportement",
  ],
  inconnu: ['Historique trop court', 'neutral', "l'historique de son pays ne couvre pas encore 3 années complètes"],
};
function vDirigeant() {
  var back =
    S.personBack === 'fiche' && S.sel && S.inst[S.sel]
      ? '<button class="link" data-a="open" data-i="' +
        esc(S.sel) +
        '">← ' +
        esc(S.inst[S.sel].name || S.sel) +
        '</button>'
      : '<button class="link" data-a="view" data-v="inities">← Achats des dirigeants</button>';
  var h = '<div class="crumbs">' + back + '</div>';
  if (!S.ins) {
    loadInsiders();
    return (
      h +
      '<p class="muted pad">' +
      (S.insError
        ? 'Historique des dirigeants indisponible (' + esc(S.insError) + ').'
        : "Chargement de l'historique…") +
      '</p>'
    );
  }
  var p = S.ins.persons && S.ins.persons[S.personKey];
  if (p && !Array.isArray(p.rows)) p = null;
  if (!p)
    return (
      h +
      '<section class="card"><p>Pas de fiche pour ce déclarant : seules les personnes qui ont acheté depuis un an en ont une.</p></section>'
    );
  var ix = {};
  (Array.isArray(S.ins.cols) ? S.ins.cols : []).forEach(function (c, n) {
    ix[c] = n;
  });
  var nb = function (v) {
      return typeof v === 'number' && isFinite(v) ? v : null;
    },
    D = /^\d{4}-\d{2}-\d{2}$/;
  // lignes contrôlées une à une : date, type et nombres valides, sinon écartées ou affichées « n.d. »
  var rows = p.rows
    .filter(function (r) {
      return Array.isArray(r) && D.test(r[ix.date]) && (r[ix.type] === 'A' || r[ix.type] === 'V');
    })
    .map(function (r) {
      var o = r.slice();
      ['qty', 'price', 'eur', 'x60', 'x120'].forEach(function (k) {
        if (ix[k] != null) o[ix[k]] = nb(o[ix[k]]);
      });
      if (o[ix.price] != null && o[ix.price] <= 0) o[ix.price] = null;
      return o;
    })
    .reverse();
  var names = S.ins.issuers && typeof S.ins.issuers === 'object' ? S.ins.issuers : {};
  var buys = rows.filter(function (r) {
      return r[ix.type] === 'A' && !r[ix.excluded];
    }),
    sells = rows.filter(function (r) {
      return r[ix.type] === 'V';
    }),
    soc = {};
  rows.forEach(function (r) {
    soc[r[ix.isin]] = 1;
  });
  var judge = function (col) {
    var j = buys.filter(function (r) {
      return r[ix[col]] != null;
    });
    if (!j.length) return null;
    var b = j.filter(function (r) {
        return r[ix[col]] > 0;
      }).length,
      m =
        j.reduce(function (a, r) {
          return a + r[ix[col]];
        }, 0) / j.length;
    return { n: j.length, beat: b, mean: m };
  };
  var j60 = judge('x60'),
    j120 = judge('x120'),
    pf = p.profile && typeof p.profile === 'object' ? p.profile : {},
    co = COHEN[pf.cohen] || null;
  var regs = (Array.isArray(p.reg) ? p.reg : [])
    .map(function (r) {
      return REG_FR[r] || r;
    })
    .join(', ');
  h +=
    '<header class="fhead"><div><h2>' +
    esc(shortName(typeof p.name === 'string' ? p.name : S.personKey)) +
    '</h2><p class="fsub">' +
    esc((typeof p.role === 'string' && frRole(p.role)) || 'fonction non publiée') +
    (regs ? ' · ' + esc(regs) : '') +
    '</p></div><div class="fchips">' +
    (p.dg ? '<span class="chip good">DG ou DAF</span>' : '') +
    (co ? '<span class="chip ' + co[1] + '">' + co[0] + '</span>' : '') +
    '</div></header>';
  var jtxt = function (j) {
      return j ? j.beat + ' sur ' + j.n : 'n.d.';
    },
    jsub = function (j, lbl) {
      return j
        ? 'ont battu le STOXX 600 à ' + lbl + ' · ' + pct(j.mean) + ' en moyenne'
        : 'pas encore de recul suffisant';
    };
  h +=
    '<section class="summary">' +
    '<div class="stat"><span class="lbl">Achats</span><span class="val">' +
    buys.length +
    '</span><span class="sub">' +
    Object.keys(soc).length +
    ' société' +
    (Object.keys(soc).length > 1 ? 's' : '') +
    ' · ' +
    sells.length +
    ' vente' +
    (sells.length > 1 ? 's' : '') +
    '</span></div>' +
    '<div class="stat ' +
    (j60 && j60.n >= 3 ? (j60.beat / j60.n >= 2 / 3 ? 'good' : j60.beat / j60.n < 0.5 ? 'bad' : '') : '') +
    '"><span class="lbl">Achats gagnants à 3 mois</span><span class="val">' +
    jtxt(j60) +
    '</span><span class="sub">' +
    jsub(j60, '3 mois') +
    '</span></div>' +
    '<div class="stat"><span class="lbl">Achats gagnants à 6 mois</span><span class="val">' +
    jtxt(j120) +
    '</span><span class="sub">' +
    jsub(j120, '6 mois') +
    '</span></div>' +
    '<div class="stat"><span class="lbl">Historique connu depuis</span><span class="val">' +
    esc((D.test(p.cov || '') && ES.frDate(p.cov)) || 'n.d.') +
    '</span><span class="sub">date de début du registre de son pays</span></div></section>';
  var notes = [];
  if (co) notes.push('<b>' + co[0] + '</b> (méthode de Harvard, Cohen, Malloy et Pomorski) : ' + esc(co[2]) + '.');
  if (pf.routine === 'habituel')
    notes.push(
      "Règle simplifiée d'Euro Signal : <b>acheteur habituel</b> (achats réguliers ou à la même période), un nouvel achat de sa part compte peu."
    );
  else if (pf.routine === 'inhabituel')
    notes.push("Règle simplifiée d'Euro Signal : un achat de sa part serait <b>inhabituel</b> ce mois-ci.");
  if (j60 && j60.n < 3) notes.push('Moins de 3 achats jugés : le palmarès ne dit encore presque rien.');
  if (notes.length)
    h +=
      '<section class="card"><ul class="plain">' +
      notes
        .map(function (x) {
          return '<li>' + x + '</li>';
        })
        .join('') +
      '</ul></section>';
  var shown = S.personAll ? rows : rows.slice(0, 150),
    cell = function (v) {
      return v == null
        ? '<span class="muted">—</span>'
        : '<span class="' + (v >= 0 ? 'pos' : 'neg') + '">' + pct(v) + '</span>';
    };
  h +=
    '<section class="card"><h3>Toutes ses opérations <span class="muted">· ' +
    rows.length +
    '</span></h3><div class="tablewrap"><table class="grid cards"><thead><tr><th>Publication</th><th>Société</th><th>Opération</th><th class="num">Quantité</th><th class="num">Prix</th><th class="num">Montant</th><th class="num">vs STOXX 600 à 3 mois</th><th class="num">à 6 mois</th></tr></thead><tbody>' +
    shown
      .map(function (r) {
        var isin = String(r[ix.isin] || ''),
          nm = typeof names[isin] === 'string' ? names[isin] : isin || 'n.d.',
          inUni = !!S.inst[isin],
          via = typeof r[ix.via] === 'string' ? r[ix.via] : null;
        return (
          '<tr><td data-l="Publication">' +
          esc(shortDate(r[ix.date])) +
          '</td><td class="c-name" data-l="Société">' +
          (inUni ? '<button class="link" data-a="open" data-i="' + esc(isin) + '">' + esc(nm) + '</button>' : esc(nm)) +
          '</td>' +
          '<td data-l="Opération"><span class="chip ' +
          (r[ix.type] === 'A' ? 'good' : 'bad') +
          '">' +
          (r[ix.type] === 'A' ? 'Achat' : 'Vente') +
          '</span>' +
          (via ? ' <small class="muted">via ' + esc(shortName(via)) + '</small>' : '') +
          (r[ix.excluded] ? ' <small class="muted">(société, non comptée)</small>' : '') +
          '</td>' +
          '<td class="num" data-l="Quantité">' +
          fmtInt(r[ix.qty]) +
          '</td><td class="num" data-l="Prix">' +
          (r[ix.price] != null
            ? fmtN(r[ix.price], r[ix.price] < 1 ? 4 : 2) + ' ' + esc(r[ix.currency] || '')
            : 'n.d.') +
          '</td>' +
          '<td class="num" data-l="Montant">' +
          (r[ix.eur] != null ? (r[ix.eur] >= 1000 ? ES.fmtEur(r[ix.eur]) : fmtInt(r[ix.eur]) + ' €') : 'n.d.') +
          '</td><td class="num" data-l="vs STOXX 3 mois">' +
          (r[ix.type] === 'A' ? cell(r[ix.x60]) : '') +
          '</td><td class="num" data-l="vs STOXX 6 mois">' +
          (r[ix.type] === 'A' ? cell(r[ix.x120]) : '') +
          '</td></tr>'
        );
      })
      .join('') +
    '</tbody></table></div>' +
    (shown.length < rows.length
      ? '<p class="row mt"><button class="ghost" data-a="personAll">Afficher les ' +
        rows.length +
        ' opérations</button></p>'
      : '') +
    '<p class="foot">Résultat d\'un achat : variation du cours en euros entre la première séance qui suit la publication et 60 séances (3 mois) ou 120 séances (6 mois) plus tard, moins la variation du STOXX Europe 600 sur les mêmes dates (dividendes exclus des deux côtés). « — » : pas encore assez de recul, ou cours introuvable (société sortie de la cote). Achats faits par sa holding ou ses proches regroupés sous son nom. Sources : registres officiels (AMF, Finansinspektionen…).</p></section>';
  return h;
}
/* Saisonnalité sur 30 ans d'indices (data/seasonality.json, recalculé chaque mois) */
function loadQuality() {
  S.qualityLoaded = true;
  var get = function (f) {
    return fetch('data/diagnostics/' + f, { cache: 'no-store' })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .catch(function () {
        return null;
      });
  };
  Promise.all([get('quality.json'), get('ui-check.json')]).then(function (r) {
    S.quality = r[0];
    S.uiCheck = r[1];
    if (S.view === 'aide') render();
  });
}
/** Résultat du contrôle automatique du soir : fichiers, couverture comparée au calcul précédent, affichage sur téléphone. */
function vQuality() {
  var q = S.quality,
    u = S.uiCheck;
  if (!q && !u)
    return (
      '<p class="muted">' +
      (S.qualityLoaded ? "Pas encore de contrôle enregistré : il s'ajoute au calcul du soir." : 'Chargement…') +
      '</p>'
    );
  var h =
    '<p class="small">Chaque soir, après le calcul : contrôle des fichiers, comparaison de chaque rubrique avec le calcul précédent, puis ouverture de toutes les fiches comme sur un téléphone. Un email vous prévient seulement en cas de problème.</p>';
  if (q) {
    h +=
      '<p>' +
      (q.issues && q.issues.length
        ? '<b>⚠️ ' + q.issues.length + ' point(s) dans les fichiers</b>'
        : '✅ Fichiers : aucun problème') +
      ' <span class="muted">· ' +
      esc(shortDate(q.date)) +
      '</span></p>';
    if (q.issues && q.issues.length)
      h +=
        '<ul class="plain small">' +
        q.issues
          .map(function (t) {
            return '<li>' + esc(t) + '</li>';
          })
          .join('') +
        '</ul>';
    var cov = q.cov || {};
    if (Object.keys(cov).length)
      h +=
        '<div class="tablewrap"><table class="grid small"><thead><tr><th>Rubrique</th><th class="num">Ce soir</th><th class="num">Calcul précédent</th></tr></thead><tbody>' +
        Object.keys(cov)
          .map(function (k) {
            var a = cov[k][0],
              b = cov[k][1],
              d = b != null ? a - b : null;
            return (
              '<tr><td>' +
              esc(k) +
              '</td><td class="num">' +
              fmtInt(a) +
              '</td><td class="num ' +
              (d != null && d < 0 ? 'neg' : '') +
              '">' +
              (b == null ? '—' : fmtInt(b) + (d ? ' (' + (d > 0 ? '+' : '') + fmtInt(d) + ')' : '')) +
              '</td></tr>'
            );
          })
          .join('') +
        '</tbody></table></div>';
  }
  if (u) {
    var np = (u.problems || []).length,
      nj = (u.jsErrors || []).length;
    h +=
      '<p>' +
      (np || nj
        ? '<b>⚠️ Affichage : ' + np + ' problème(s), ' + nj + ' erreur(s)</b>'
        : '✅ Affichage : aucun problème') +
      ' <span class="muted">· ' +
      fmtInt(u.fiches || 0) +
      ' fiches et ' +
      (u.catalogue || 0) +
      ' fiches du catalogue ouvertes sur téléphone</span></p>';
    if (np || nj)
      h +=
        '<ul class="plain small">' +
        (u.problems || [])
          .slice(0, 12)
          .map(function (x) {
            return '<li>' + esc(x.kind + ' · ' + x.where + (x.detail ? ' · ' + x.detail : '')) + '</li>';
          })
          .join('') +
        (u.jsErrors || [])
          .slice(0, 5)
          .map(function (x) {
            return '<li>' + esc('erreur · ' + x.where + ' · ' + x.message) + '</li>';
          })
          .join('') +
        '</ul>';
  }
  return (
    h + '<p class="small">Une erreur vue sur une fiche ? Bouton <b>⚑ Signaler une erreur</b> en bas de la fiche.</p>'
  );
}
/** Méthode du classement tendance + comptes et étude de contrôle recalculée chaque soir. */
/** La logique de l'outil en une page : ce qui est utilisé, les chiffres des tests (5, 8 et 29 ans), ce qui a été retiré, les limites. Tests du 17/10/2026. */
/** Dépôt GitHub de cette page (https://<compte>.github.io/<dépôt>/ → https://github.com/<compte>/<dépôt>), pour les copies aussi. */
function repoUrl() {
  var u =
    /^https?:\/\/([^.]+)\.github\.io\/([^/]+)/.exec(location.href) ||
    /^https?:\/\/([^.]+)\.github\.io\/([^/]+)/.exec((S.cfg && S.cfg.dashboardUrl) || '');
  return u ? 'https://github.com/' + u[1] + '/' + u[2] : 'https://github.com/Letmetry51/insider-pea';
}
/** 📚 Sources, études et méthodes : tout ce qui a servi à construire l'outil, avec ce qui en a été retenu. */
function biblioCard() {
  var ln = function (url, txt) {
      return '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + txt + '</a>';
    },
    li = function (t) {
      return '<li>' + t + '</li>';
    },
    ref = function (st, who, title, where, role) {
      // st : ✅ appliquée dans l'outil · 🧪 testée sur nos données, non retenue · 📖 repère
      return li(
        st +
          ' <b>' +
          who +
          '</b>' +
          (title ? ', « ' + title + ' »' : '') +
          (where ? ', <i>' + where + '</i>' : '') +
          ' — ' +
          role
      );
    },
    sub = function (k, title, body) {
      return '<details class="fsscale more" data-k="' + k + '"><summary>' + title + '</summary>' + body + '</details>';
    },
    ul = function (items) {
      return '<ul class="plain small nomax biblio">' + items.join('') + '</ul>';
    };
  var data = ul([
    li(
      '📈 <b>Cours, volumes, comptes, analystes</b> : ' +
        ln('https://finance.yahoo.com', 'Yahoo Finance') +
        ' (bibliothèque ' +
        ln('https://github.com/ranaroussi/yfinance', 'yfinance') +
        ") : cours journaliers (2 ans) et hebdomadaires (5 à 8 ans), dividendes et divisions, comptes annuels (4 exercices), prévisions, avis et révisions des analystes, surprises et dates de résultats, communiqués des sociétés, description d'activité et effectif (pli 🏭 Business model). Pour les études : cours hebdomadaires de 1 067 sociétés européennes, 1985-2026."
    ),
    li(
      '👔 <b>Déclarations des dirigeants</b> (règlement européen MAR, article 19) : ' +
        ln('https://bdif.amf-france.org', 'AMF') +
        ' (France, base BDIF depuis 2021), ' +
        ln('https://marknadssok.fi.se/publiceringsklient', 'Finansinspektionen') +
        ' (Suède, registre Insynshandel depuis 2016), ' +
        ln('https://www.fsma.be', 'FSMA') +
        ' (Belgique), ' +
        ln('https://www.afm.nl/en/sector/registers', 'AFM') +
        ' (Pays-Bas).'
    ),
    li(
      '🐻 <b>Ventes à découvert</b> (règlement européen 236/2012, positions de 0,5 % du capital et plus) : AMF (' +
        ln('https://www.data.gouv.fr', 'data.gouv.fr') +
        '), ' +
        ln('https://www.consob.it', 'Consob') +
        ', ' +
        ln('https://www.cnmv.es', 'CNMV') +
        ', AFM, FSMA, ' +
        ln('https://www.bundesanzeiger.de', 'Bundesanzeiger') +
        ', ' +
        ln('https://www.fca.org.uk', 'FCA') +
        '.'
    ),
    li(
      '🌍 <b>Indices et devises</b> : STOXX Europe 600 (référence), CAC 40, S&amp;P 500 et paniers américains (baromètres des thèmes, jamais proposés), taux de change (Yahoo Finance).'
    ),
    li(
      '📰 <b>Presse</b> : ' + ln('https://news.google.com', 'Google News') + ' (flux RSS : titres et liens seulement).'
    ),
    li(
      '🎓 <b>Contrôle indépendant</b> : ' +
        ln(
          'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html',
          'Kenneth R. French Data Library'
        ) +
        ' (Dartmouth) : facteurs européens momentum et valeur depuis 1990, calculés avec toutes les sociétés, disparues comprises.'
    ),
    li(
      "🇪🇺 <b>Éligibilité au PEA</b> : siège dans l'Union européenne ou l'EEE (article L221-31 du Code monétaire et financier), foncières cotées exclues ; à confirmer chez votre courtier."
    ),
    li(
      '🔍 <b>Vérifications ponctuelles</b> : ' +
        ln('https://eodhd.com', 'EODHD') +
        ' (sociétés retirées de la cote, pour un futur test sans biais du survivant), Google Trends (essai abandonné : pas mieux que la moyenne).'
    ),
  ]);
  var studies =
    '<p class="small muted">✅ appliquée dans l\'outil · 🧪 testée sur nos données, non retenue · 📖 repère</p>' +
    '<p class="small"><b>🎯 Momentum et tendance</b></p>' +
    ul([
      ref(
        '✅',
        'Jegadeesh et Titman (1993)',
        'Returns to Buying Winners and Selling Losers',
        'Journal of Finance',
        'hausse sur 12 mois sans le dernier mois, cœur du classement.'
      ),
      ref(
        '✅',
        'George et Hwang (2004)',
        'The 52-Week High and Momentum Investing',
        'Journal of Finance',
        'proximité du plus haut sur un an (note et secteurs).'
      ),
      ref(
        '✅',
        'Moskowitz et Grinblatt (1999)',
        'Do Industries Explain Momentum?',
        'Journal of Finance',
        'secteurs en tendance.'
      ),
      ref(
        '✅',
        'Daniel et Moskowitz (2016)',
        'Momentum Crashes',
        'Journal of Financial Economics',
        'alerte krach : marché en baisse de 20 % sur un an.'
      ),
      ref(
        '✅',
        'Asness, Moskowitz et Pedersen (2013)',
        'Value and Momentum Everywhere',
        'Journal of Finance',
        'dosage 70 % 🎯 et 30 % 💎.'
      ),
      ref(
        '✅',
        'Fama et French (2012)',
        'Size, Value, and Momentum in International Stock Returns',
        'Journal of Financial Economics',
        'facteurs européens qui servent de contrôle indépendant.'
      ),
      ref(
        '🧪',
        'Barroso et Santa-Clara (2015)',
        'Momentum Has Its Moments',
        'Journal of Financial Economics',
        'volatilité du momentum : rien de plus.'
      ),
      ref(
        '🧪',
        'Da, Gurun et Warachka (2014)',
        'Frog in the Pan',
        'Review of Financial Studies',
        'hausse « en petits pas » : rien de plus.'
      ),
      ref(
        '🧪',
        'Blitz, Huij et Martens (2011)',
        'Residual Momentum',
        'Journal of Empirical Finance',
        'hausse hors effet marché : rien de plus.'
      ),
      ref(
        '🧪',
        'Bali, Cakici et Whitelaw (2011)',
        'Maxing Out: Stocks as Lotteries',
        'Journal of Financial Economics',
        'effet « loterie » : rien de plus.'
      ),
      ref(
        '🧪',
        'Frazzini et Pedersen (2014)',
        'Betting Against Beta',
        'Journal of Financial Economics',
        'bêta faible : gain trop faible dans un portefeuille de 10 lignes.'
      ),
      ref(
        '🧪',
        'Lo et MacKinlay (1988)',
        'Stock Market Prices Do Not Follow Random Walks',
        'Review of Financial Studies',
        'persistance (ratio de variance) : rien de plus.'
      ),
      ref(
        '🧪',
        'Minervini (2013)',
        'Trade Like a Stock Market Wizard',
        '',
        '« Trend Template » : doublon du classement.'
      ),
    ]) +
    '<p class="small"><b>💎 Valeur et comptes</b></p>' +
    ul([
      ref(
        '✅',
        'Piotroski (2000)',
        'Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers',
        'Journal of Accounting Research',
        'F-score des comptes, sélection 💎.'
      ),
      ref(
        '✅',
        "Altman (1968), version Z'' (1995)",
        'Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy',
        'Journal of Finance',
        'risque de défaillance.'
      ),
      ref(
        '✅',
        'Beneish (1999)',
        'The Detection of Earnings Manipulation',
        'Financial Analysts Journal',
        'comptes possiblement embellis.'
      ),
      ref(
        '✅',
        'Edwards et Bell (1961) ; Ohlson (1995)',
        'Earnings, Book Values, and Dividends in Equity Valuation',
        'Contemporary Accounting Research',
        'valeur intrinsèque par le revenu résiduel.'
      ),
      ref('📖', 'Graham (1949)', "L'Investisseur intelligent", '', 'marge de sécurité entre le cours et la valeur.'),
    ]) +
    '<p class="small"><b>📊 Résultats, analystes, dirigeants</b></p>' +
    ul([
      ref(
        '✅',
        'Chan, Jegadeesh et Lakonishok (1996)',
        'Momentum Strategies',
        'Journal of Finance',
        'révisions des analystes et surprises de résultats (secteurs, piste en observation).'
      ),
      ref(
        '✅',
        'Cohen et Frazzini (2008)',
        'Economic Links and Predictable Returns',
        'Journal of Finance',
        'clients en avance sur leurs fournisseurs (thèmes).'
      ),
      ref(
        '🧪',
        'Bernard et Thomas (1989)',
        'Post-Earnings-Announcement Drift',
        'Journal of Accounting Research',
        "dérive après les résultats : n'aide pas à choisir dans le 🎯."
      ),
      ref(
        '✅',
        'Cohen, Malloy et Pomorski (2012)',
        'Decoding Inside Information',
        'Journal of Finance',
        'achats de dirigeants « de routine » ou opportunistes.'
      ),
      ref(
        '📖',
        'Jeng, Metrick et Zeckhauser (2003)',
        'Estimating the Returns to Insider Trading',
        'Review of Economics and Statistics',
        "+0,4 % par mois aux États-Unis ; sur 4 000 achats français et suédois : pas mieux que le hasard, d'où l'abandon de cette méthode."
      ),
    ]) +
    '<p class="small"><b>🎲 Fiabilité statistique et analyse technique</b></p>' +
    ul([
      ref(
        '✅',
        'Harvey, Liu et Zhu (2016)',
        '… and the Cross-Section of Expected Returns',
        'Review of Financial Studies',
        'seuil t ≥ 3 quand beaucoup de règles ont été essayées.'
      ),
      ref(
        '✅',
        'Bailey et López de Prado (2014)',
        'The Deflated Sharpe Ratio',
        'Journal of Portfolio Management',
        "ratio de Sharpe corrigé du nombre d'essais (test des secteurs)."
      ),
      ref(
        '✅',
        'Wilder (1978)',
        'New Concepts in Technical Trading Systems',
        '',
        'RSI 14 et écart moyen journalier (ATR).'
      ),
      ref(
        '✅',
        'Appel (fin des années 1970)',
        '',
        '',
        'MACD : moyennes exponentielles 12 et 26 jours, signal sur 9 jours.'
      ),
    ]);
  var meth = ul([
    li(
      '💯 <b>Note sur 100</b> : force sur 12 mois (rang parmi toutes les sociétés) 50 points, proximité du plus haut 10, tendance 15, comptes 20, dirigeants en bonus ou malus ; sociétés écartées si peu liquides, en perte ou aux comptes fragiles.'
    ),
    li(
      "🎯 <b>Règles</b> : hausse de +60 à +200 % sur 12 mois ; pente du canal mesurée par régression du cours (en logarithme) sur 26 semaines ; 🔊 volumes de 10 semaines au moins 1,5 fois la moyenne de l'année ; 📣 semaine à +8 % ou plus sur 3 fois le volume habituel ; ⏸️ moyenne mobile 10 semaines ; ⚡ volatilité annuelle de 80 % et plus ; 🐻 ventes à découvert de 0,5 % et plus (Paris) ; 2 sociétés par secteur au plus."
    ),
    li(
      '💎 <b>Valeur</b> : tiers le moins cher en cours / fonds propres, F-score de 7 et plus, sans perte ni chute de plus de 40 % sur un an.'
    ),
    li(
      "🧭 <b>Plan d'entrée</b> : supports et résistances aux plus hauts et plus bas touchés plusieurs fois (tolérance de 1,2 ATR ou 1,5 %), complétés par le plus haut et le plus bas de l'année ; figures (canal, biseau, triangle, élargissement) tracées par les sommets et les creux ; cône de volatilité à 68 % et 90 % (loi log-normale, sans tendance supposée) ; retracements de Fibonacci (23,6 à 61,8 %)."
    ),
    li(
      "🏦 <b>Valeur intrinsèque</b> : revenu résiduel et trésorerie disponible capitalisée, sans croissance supposée ; rendement exigé de 8,5 à 11 % selon la taille (taux sans risque européen d'environ 3 % plus la prime de risque des actions)."
    ),
    li(
      "🔬 <b>Analyse des fiches</b> : score de conviction (technique 25 %, comptes 25 %, catalyseurs 15 %, valorisation 15 %, risques 20 %), scénarios tirés des objectifs des analystes et de l'amplitude habituelle du cours, incertitude d'après la volatilité."
    ),
    li(
      '💼 <b>Portefeuille</b> : garder 6 mois, protection à −30 %, 2 lignes par secteur, achats par petites touches pendant une alerte krach ; réglages issus de portefeuilles simulés sur 1997-2026 (frais de 0,3 % par achat et par vente).'
    ),
  ]);
  var tests = ul([
    li(
      '📏 <b>Mesure commune</b> : rendement à 6 mois (26 semaines) moins celui de la société moyenne de la même semaine, valeurs extrêmes écrêtées à 2 % et 98 %, part des chutes de 25 % ou plus, résultat par période (1997-2008, 2009-2017, 2018-2026).'
    ),
    li(
      "⏳ <b>Sans regard vers le futur</b> : chaque calcul n'utilise que ce qui était connu à la date (comptes comptés 120 jours après la clôture de l'exercice)."
    ),
    li(
      "🎲 <b>Contre le hasard</b> : réglages choisis sur 1997-2012 puis mesurés sur 2013-2026 ; t corrigé du chevauchement des périodes ; tirages au hasard (placebo) et rééchantillonnage par blocs pour les secteurs ; correction de Bonferroni pour les mois de l'année (seuil |t| ≥ 2,9)."
    ),
    li(
      '📒 <b>Suivi réel</b> : chaque sélection suivie depuis le 18/10/2026 et chaque règle revérifiée chaque soir ; chiffres prudents, frais et biais du survivant : voir « ⚖️ Fiabilité des chiffres ».'
    ),
    li(
      '🧾 <b>Refaire les calculs</b> : scripts publics dans ' +
        ln(repoUrl() + '/tree/main/research', 'research/') +
        ', détail de chaque chiffre dans ' +
        ln(repoUrl() + '/blob/main/research/README.md', 'research/README.md') +
        '.'
    ),
  ]);
  return (
    '<details class="card fold" data-k="aide-biblio"><summary>📚 Sources, études et méthodes <span class="muted small">· données, 27 références, calculs et tests</span></summary>' +
    '<p class="small">Tout ce qui a servi à construire Euro Signal, et ce qui en a été retenu.</p>' +
    sub('bib-data', "🗂️ Données : d'où viennent les chiffres", data) +
    sub('bib-acad', '🎓 Études académiques', studies) +
    sub('bib-meth', '📐 Méthodes de calcul', meth) +
    sub('bib-test', '🧪 Comment les règles sont testées', tests) +
    '</details>'
  );
}
/** 🆚 Euro Signal face à Yahoo Finance et aux sites gratuits : ce qu'il fait de plus, ce qu'il fait moins bien, ses limites.
 *  Les chiffres prudents de la méthode sont dans « ⚖️ Fiabilité des chiffres » (logicCard) : pas répétés ici. */
function compareCard() {
  var nb = function (t) {
      return t.replace(/ %/g, '\u00a0%'); // « −30 % » jamais coupé en fin de ligne
    },
    row = function (need, es, other) {
      return '<tr><th>' + need + '</th><td>' + nb(es) + '</td><td>' + nb(other) + '</td></tr>';
    };
  var a = function (u, t) {
    return '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + t + '</a>';
  };
  return (
    '<details class="card fold" data-k="aide-cmp"><summary>🆚 Face à Yahoo Finance et aux sites gratuits <span class="muted small">· ce qu\'il fait de plus, ses limites</span></summary>' +
    '<p class="small">Pas plus complet que Yahoo Finance : l\'outil utilise surtout ses données. Mais il fait ce que ni Yahoo ni les sites gratuits ne font : trier les sociétés européennes avec des règles testées, et dire quoi acheter, quand, et quand vendre.</p>' +
    '<div class="tablewrap"><table class="grid small cmpt"><thead><tr><th>Besoin</th><th>Euro Signal</th><th>Yahoo Finance et autres sites gratuits</th></tr></thead><tbody>' +
    row(
      'Quoi acheter dans un PEA',
      '✅ règles testées, sélection du lundi',
      '❌ (Stockopedia le fait, mais il est payant)'
    ) +
    row('Quand vendre', '✅ emails à −10 %, −30 %, 6 mois, krach', 'alertes de prix simples') +
    row(
      'Dirigeants et ventes à découvert en Europe',
      '✅ registres officiels (AMF, etc.)',
      'Yahoo : surtout pour les sociétés américaines ; base AMF brute ; InsiderScreener payant'
    ) +
    row(
      'Analyse en français',
      '✅ comptes, valeur, scénarios',
      'Yahoo : chiffres bruts, en anglais ; Zonebourse, en partie payant'
    ) +
    row(
      'Cours en séance, graphiques',
      '❌ mise à jour une fois par soir',
      '✅ Yahoo ; TradingView (2 indicateurs par graphique en gratuit)'
    ) +
    row('Actualités', 'titres Google News seulement', '✅ Yahoo, Boursorama, Zonebourse') +
    row('Historique des comptes', '4 ans', 'Yahoo : 5 ans ; Koyfin : 2 ans en gratuit') +
    '</tbody></table></div>' +
    "<p class=\"small\"><b>Fait-il mieux pour gagner de l'argent ?</b> Pas encore prouvé en réel : l'avantage mesuré vient du momentum (acheter ce qui monte déjà), un effet connu ; chiffres prudents et suivi réel dans « ⚖️ Fiabilité des chiffres » (📘 La logique en 1 minute). Hors PEA, un ETF momentum (Amundi MSCI Europe Momentum, 0,23\u00a0% de frais par an) capte cet effet sans effort ; il n'est pas éligible au PEA : dans un PEA, l'outil comble ce manque.</p>" +
    '<p class="small"><b>Limites de l\'outil</b></p><ul class="plain small nomax">' +
    "<li>🔌 Il dépend d'un accès non officiel aux données de Yahoo (cours, comptes, analystes) : si Yahoo le coupe, l'outil perd l'essentiel de ses données.</li>" +
    "<li>🧾 Il reprend les erreurs de Yahoo. Certaines sont corrigées (par exemple, la rentabilité sur 12 mois remplacée par celle du dernier exercice publié), pas toutes : en cas de doute, « ⚑ Signaler une erreur » en bas de l'analyse d'une fiche.</li>" +
    '<li>🌙 Données mises à jour une fois par soir de semaine : pas de cours en séance.</li>' +
    '<li>📰 Actualités : titres seulement, repérés par mots-clés.</li>' +
    '<li>👤 Outil personnel et gratuit, sans support ni garantie de service.</li></ul>' +
    '<p class="small"><b>En pratique</b> : Euro Signal pour décider, TradingView gratuit pour le graphique en séance, Boursorama ou Zonebourse pour l\'actualité.</p>' +
    '<p class="foot">Comparaison du 20/10/2026, les offres gratuites changent : ' +
    a('https://help.yahoo.com/kb/SLN29276.html', 'formules Yahoo Finance') +
    ' · ' +
    a('https://quantroutine.com/tools/tradingview-free-vs-pro/', 'TradingView gratuit') +
    ' · ' +
    a('https://costbench.com/software/financial-data-terminals/koyfin/free-plan/', 'Koyfin gratuit') +
    ' · ' +
    a('https://www.abcbourse.com/cotation/MCEUp', 'ETF Amundi MSCI Europe Momentum (PEA : non)') +
    '.</p></details>'
  );
}
function logicCard() {
  var tr = function (cells, head) {
    return (
      '<tr>' +
      cells
        .map(function (c, k) {
          return (head ? '<th' : '<td') + (k ? ' class="num"' : '') + '>' + c + (head ? '</th>' : '</td>');
        })
        .join('') +
      '</tr>'
    );
  };
  var tbl = function (head, rows) {
    return (
      '<div class="tablewrap"><table class="grid small lgt"><thead>' +
      tr(head, true) +
      '</thead><tbody>' +
      rows
        .map(function (r) {
          return tr(r);
        })
        .join('') +
      '</tbody></table></div>'
    );
  };
  var fl = function (ic, t, sub) {
    return '<li><span class="lgi" aria-hidden="true">' + ic + '</span><b>' + t + '</b><small>' + sub + '</small></li>';
  };
  var kn = function (big, sub) {
    return '<div class="lgk"><b>' + big + '</b><small>' + sub + '</small></div>';
  };
  var h =
    '<section class="card proof" id="logique"><h3>📘 La logique en 1 minute</h3>' +
    '<p class="lgone">Repérer ce qui monte déjà le plus, avec des comptes sains, et le garder 6 mois.</p>' +
    '<ol class="lgflow">' +
    fl(
      '🧹',
      'Écarter',
      'peu liquides, pertes, comptes fragiles, en baisse sur 12 mois ; ⚡ très volatiles et 🐻 vendues à découvert (Paris) hors du 🎯'
    ) +
    fl('💯', 'Noter /100', 'force sur 12 mois 50 · plus haut 10 · tendance 15 · comptes 20 · dirigeants ±') +
    fl('⬆⬆', 'Pente forte', 'canal haussier ≥ +40 % sur 6 mois') +
    fl(
      '🎯',
      'Choisir',
      "+60 à +200 % sur 12 mois · 🔊 volumes puis 📣 bond d'abord · ⏸️ sous la moyenne 10 sem. en dernier · 2 par secteur"
    ) +
    fl('⏱️', 'Entrer', 'au-dessus de la moyenne 10 semaines, sans attendre de repli') +
    fl('⏳', 'Garder 6 mois', 'protection à −30 % ; emails à chaque −10 %, à −30 % et à 6 mois') +
    '</ol>' +
    '<p class="small lgw">💎 <b>Complément Valeur</b> : sociétés bon marché aux comptes solides (Piotroski). Momentum et valeur gagnent à des moments différents : 70 % 🎯 + 30 % 💎 a ramené la plus grosse perte de −46 % à −30 % sur 1990-2026 (facteurs européens de Kenneth French), pour un peu moins de gain.</p>' +
    '<div class="lgkeys">' +
    kn('+7 pts', 'à 6 mois face à la société moyenne, sur des années jamais vues au réglage') +
    kn('+4 pts', 'chiffre prudent : frais et faillites supposées déduits') +
    kn('53 %', "battent la société moyenne (46 % pour l'ensemble)") +
    '</div>' +
    '<p class="small lgw">🎲 <b>6 mois après l\'achat</b> (29 ans, chiffres bruts) : 2 fois sur 3 en hausse · 1 sur 3 à +20 % · 1 sur 8 à +50 % · 1 sur 14 à −25 % ou pire (toutes sociétés : 61 %, 1 sur 4, 1 sur 16, 1 sur 12).</p>' +
    trackBox() +
    "<p class=\"small lgw\">📧 <b>Automatique</b> : le lundi, la sélection avec ✅ feu vert ou ⏸️ en attente pour chaque société ; dès qu'une société ⏸️ du 🎯 repasse au-dessus de sa moyenne 10 semaines, un email « feu vert » ; après « Je l'ai acheté » : un email à chaque palier de −10 %, à la protection de −30 % et au rappel des 6 mois (garder si encore dans le 🎯, sinon vendre) ; un email quand l'alerte krach s'allume ou s'éteint ; 📊 un bilan chaque trimestre (suivi réel, règles en réel, pistes) et le point de revue le 31/01/2027.</p>" +
    (function () {
      var W = (rankData() || {}).watchdog;
      return (
        "<p class=\"small lgw\">🔎 <b>Auto-surveillance</b> : chaque soir, l'outil vérifie que la méthode garde son avantage (suivi réel 📒 et étude du soir) ; il ne change jamais ses règles seul, mais envoie un email de revue si l'avantage se dégrade. Chaque règle (🔊 📣 ⏸️) est aussi vérifiée sur les vraies sélections, et les révisions des analystes sont testées seules dès qu'il y a un an d'archive (💡 email si la piste se confirme)." +
        (W
          ? ' État : ' +
            (W.status === 'ok' ? '✅ avantage intact' : '⚠️ ' + esc(W.reasons.join(' ; '))) +
            ' (' +
            shortDate(W.checked) +
            ').'
          : '') +
        '</p>'
      );
    })() +
    '<p class="small lgw">⚠️ Si le marché perd 20 % en un an, la méthode souffre (−12,5 pts) : une alerte rouge s\'affiche en haut. 🇪🇺 Hors PEA (Suisse, Royaume-Uni, foncières) : compte-titres seulement.</p>';
  h +=
    '<details class="fsscale more" data-k="lg-tests"><summary>📊 Chiffres détaillés des tests</summary><p class="small">Écart de performance à 6 mois avec la société moyenne de la même semaine. Trois échantillons : 5 ans (≈ 760 sociétés liquides, 2021–2026), 8 ans (≈ 900 sociétés de plus de 500 M€, 2018–2026) et tout l\'historique disponible chez Yahoo (1 067 sociétés, 1997–2026, avec la bulle internet et le krach de 2008).</p>' +
    tbl(
      ['Repère', '5 ans', '8 ans', '29 ans'],
      [
        ['Classement (12 mois parmi le tiers le plus fort + tendance)', '+3,6', '+2,4', '+2,5'],
        ['<b>Classement + pente forte</b>', '<b>+5,1</b>', '<b>+4,1</b>', '<b>+5,5</b>'],
        ['Pente légère', '+0,6', '−1,0', '−0,4'],
        ['Déjà +100 à +200 % sur 12 mois', '+8,3', '+5,0', '+7,4'],
        ['Déjà plus de +200 % : part des chutes de 25 % ou plus', '23 %', '16 %', '16 %'],
        ['Filtres du bouton 🎯, sans les comptes (positif dans chaque période)', '—', '—', '+6,7'],
        [
          '<b>… avec 🔊 volumes ≥ ×1,5</b> (positif dans chaque période ; sans hausse de volume : +5,8)',
          '—',
          '—',
          '<b>+10,2</b>',
        ],
        [
          '<b>… 🔊 + 📣 bond sur gros volume</b> (semaine ≥ +8 % à 3× le volume ; 🔊 sans bond : +9,2 ; net depuis 2009, nul avant)',
          '—',
          '—',
          '<b>+13,2</b>',
        ],
        [
          '<b>… pente moyenne ou +30-60 % mais 📣</b> (repêchée ; sans 📣 : +4,7 ; règles strictes sans 📣 : +7,4 ; mieux dans chaque période)',
          '—',
          '—',
          '<b>+10,0</b>',
        ],
        [
          '<b>Classement + 🔊 volumes ×2</b> (positif dans chaque période ; sans volumes en hausse : +2,3)',
          '—',
          '—',
          '<b>+7,7</b>',
        ],
        ['Classement après une baisse du marché de 20 % sur un an (krach du momentum)', '—', '—', '−12,5'],
        ['Filtres 🎯 vendues à découvert, 🐻 ≥ 0,5 % (2013-2026, Paris et Londres ; sans : +8,6)', '—', '—', '−2,1'],
        ['… dont Paris (28 % de chutes ≥ 25 %, négatif dans les deux périodes)', '—', '—', '−11,6'],
        [
          'Filtres 🎯 sous leur moyenne 10 semaines (24 % des cas ; repli de plus de 5 % sur le mois : +5,8)',
          '—',
          '—',
          '+4,9',
        ],
        [
          "Filtres 🎯 près du plus haut : 1er nouveau plus haut de l'année / 2e à 4e / 5e ou plus",
          '—',
          '—',
          '+4,9 / +7 / +4,6',
        ],
        [
          'Filtres 🎯 avec un cours ⚡ très volatil (≥ 80 %/an, 3 % des cas ; 17 % de chutes ≥ 25 % au lieu de 7,5 %)',
          '—',
          '—',
          '0,0',
        ],
        ['🚀 + pente forte + marché non euphorique (5 et 8 ans : hausse ≥ 40 % 1 fois sur 4 à 5)', '—', '—', '+8,1'],
        ['Au creux (12 mois négatif, sous la moyenne 40 semaines) : écartées', '−3,4', '−2,9', '−3,3'],
      ]
    ) +
    '<p class="small"><b>Règle de revente</b> : 5 premières du classement achetées à leur arrivée, part des positions gagnantes.</p>' +
    tbl(
      ['Sortie', '5 ans', '8 ans', '29 ans'],
      [
        ['<b>Garder 6 mois</b>', '<b>65 %</b>', '<b>64 %</b>', '<b>62 %</b>'],
        ['6 mois, protection −30 %', '62 %', '62 %', '62 %'],
        ['6 mois, stop −15 %', '52 %', '51 %', '55 %'],
        ['Stop suiveur −20 %', '49 %', '46 %', '53 %'],
        ['Vendre sous la moyenne 40 semaines (≈ 200 séances)', '48 %', '46 %', '50 %'],
      ]
    ) +
    xpi(
      "Un stop serré limite les pertes (le pire dixième des positions perd environ 20 % au lieu de 25 %) mais coupe trop tôt des sociétés qui repartent : moins de positions gagnantes, pour un rendement annuel voisin. La protection à −30 % ne sert qu'en cas d'accident."
    ) +
    '</details>';
  h +=
    '<details class="fsscale more" data-k="lg-stress"><summary>🧪 Stress test : au plus haut ? portefeuille simulé</summary>' +
    "<p class=\"small\"><b>Au plus haut ?</b> Parmi les sociétés qui passent les filtres 🎯, celles à leur plus haut et celles 2 à 10 % en dessous ont fait aussi bien (+5 à +10 points à 6 mois selon la période) ; celles à plus de 10 % sous leur plus haut ont fait un peu moins bien, avec deux fois plus de chutes de 25 %. Être près du plus haut n'est donc pas un défaut : c'est le signe que la hausse continue. Le plan d'entrée de la fiche sert seulement à ne pas acheter sur un pic d'une journée.</p>" +
    tbl(
      ['Portefeuille simulé (10 sociétés, gardées 6 mois, frais déduits)', '1997–2008', '2009–2017', '2018–2026'],
      [
        ['Règles 🎯 (sans les comptes)', '+31 %/an', '+40 %/an', '+33 %/an'],
        ['10 sociétés au hasard', '+14 %/an', '+19 %/an', '+11 %/an'],
        ['Perte maximale de la stratégie (marché)', '−51 % (−54 %)', '−27 % (−26 %)', '−39 % (−34 %)'],
      ]
    ) +
    "<p class=\"small\">Les deux premières périodes n'ont pas servi à régler les seuils : ce sont de vrais tests. L'écart avec le hasard (environ 15 à 20 points par an) est le chiffre à retenir ; les rendements eux-mêmes sont gonflés, car seules les sociétés encore cotées aujourd'hui sont dans l'historique. Les seuils changent peu le résultat (de +29 à +31 %/an en faisant varier hausse mini, hausse maxi et pente) : la méthode ne tient pas à un réglage fin. Elle ne protège pas des krachs : les pertes maximales sont celles du marché.</p></details>" +
    '<details class="fsscale more" data-k="lg-out"><summary>🗑️ Testé et retiré</summary><ul class="plain small">' +
    "<li><b>Achats de dirigeants</b> comme critère principal : environ 4 000 achats en France et en Suède n'ont pas fait mieux qu'un titre pris au hasard une fois publiés (+0,3 point, 48 % de gagnants). Gardés en petit bonus, consultables dans l'onglet Achats. Croisés avec le 🎯 au feu vert (France depuis 2021, Suède depuis 2016) : pas d'avantage, +1,5 point à 6 mois avec un achat de dirigeant dans les 3 derniers mois contre +4,6 sans (moins de chutes, mais moins de hausse, sur peu de cas) ; ce petit bonus sera réexaminé à la revue du 31/01/2027.</li>" +
    '<li><b>Signaux de début de hausse</b> : tendance qui vient de tourner, sortie de creux, compression de volatilité, base serrée, accélération sur 3 mois, croisement de moyennes, recherches Google : pas mieux que la moyenne.</li>' +
    '<li><b>Doublons</b> : Trend Template de Minervini, secteur fort, RSI, F-score 8–9, convergence : rien de plus que le classement.</li>' +
    "<li><b>Saisonnalité des secteurs</b> : les bons mois de 2018–2021 ne l'étaient plus en 2022–2026 ; acheter les secteurs « saisonniers » n'a rien rapporté.</li>" +
    "<li><b>Peur du marché (VIX, volatilité)</b> : sur 29 ans, l'avantage reste de +4 à +5 points que le marché soit calme ou agité ; seule une baisse de 20 % sur un an est dangereuse (alerte rouge déjà en place).</li>" +
    "<li><b>Plus hauts à répétition</b> : une société qui fait son 2e, 3e ou 4e nouveau plus haut de l'année continue aussi bien (+7 points) ; dès le 5e, un peu moins et plus de chutes (10 % au lieu de 6,5 %), mais trop rare (3 % des cas) pour une règle.</li>" +
    "<li><b>Bêta faible, « loterie », persistance, asymétrie</b> (pistes académiques) : seul le bêta faible fait mieux société par société (+8,8 points contre +6,1, moins de chutes), mais dans un portefeuille de 10 lignes l'écart tombe à +0,6 point par an : pas retenu, pour garder l'outil simple.</li>" +
    '<li><b>Variantes du momentum</b> (hausse hors effet marché, hausse « en petits pas », part des mois en hausse) : rien de mieux que la hausse sur 12 mois. Seul garde-fou retenu : ⚡ cours très volatil.</li>' +
    "<li><b>Moment d'achat</b> : attendre un repli, un RSI plus bas, plusieurs semaines de hausse ou un cours calme n'a pas fait mieux ; un cours très au-dessus de sa moyenne n'est pas un danger (+8 à +10 points). Le mois d'achat change d'une période à l'autre. Seule règle retenue : au-dessus de la moyenne 10 semaines.</li>" +
    "<li><b>Gestion du portefeuille</b> (simulation 29 ans) : tailles de ligne selon la volatilité (−1,4 point par an, même perte maximale) ; garder à 6 mois celles encore dans le 🎯 (perte maximale −66 % au lieu de −57 %) ; pause des achats pendant l'alerte krach (perte maximale −51 % au lieu de −57 %, mais environ −1 point par an : compromis, l'outil conseille d'acheter par petites touches).</li>" +
    "<li><b>Après un 📣 bond</b> : bond récent, petit ou gros, cours revenu sous la clôture du bond ou pas : tous bons (+10 à +14 points), pas de règle de plus. <b>Force du secteur</b>, <b>ampleur du marché</b> (part des sociétés en tendance) et <b>distance au plus haut</b> : pas d'effet stable. <b>Secteur émergent</b>, même avec 🔊 : rien de plus (dans le 🎯 : +6,6 points contre +8,4 ailleurs ; pour anticiper hors 🎯 : +3,7, comme les autres secteurs).</li>" +
    "<li><b>Indicateurs du plan d'entrée</b> (RSI, MACD, canal de 6 mois, support et résistance), croisés avec le 🎯 au feu vert (1997-2026) : aucun n'aide à choisir le moment, de +7,0 à +8,5 points à 6 mois selon le cas contre +8,1 en moyenne. Un RSI « suracheté » (70 à 80) n'est pas un handicap (+7,9, moins de chutes). Les 4 voyants au vert ne font pas mieux (+8,5, sur 5 % des cas seulement, avec plus de chutes) et, hors 🎯, font moins bien que la moyenne (−0,6). Sur les cours journaliers (2025-2026), les verdicts du plan (entrer, attendre un repli, attendre la cassure) ne se distinguent pas non plus. Le plan d'entrée reste un repère pour placer un ordre, sans poids dans la sélection.</li>" +
    "<li><b>Résultats publiés</b> (2020-2026) : la surprise sur le bénéfice n'aide pas à choisir dans le 🎯 ; acheter 1 à 2 semaines avant la publication n'a pas été pire, plutôt mieux (+5,1 points contre +3,6, moins de chutes) : inutile d'attendre les résultats. Trop peu d'années pour en faire une règle.</li>" +
    '<li><b>Rattrapage</b> : les sociétés en retard dans un secteur qui démarre ne rattrapent pas.</li>' +
    '<li><b>Attendre le bon moment du marché</b> pour entrer : pas de gain mesurable.</li>' +
    '<li><b>Stops serrés et sorties sur moyennes mobiles</b> : moins de positions gagnantes (voir le tableau).</li>' +
    '<li><b>Volumes : variantes</b> (4, 10 ou 20 semaines, ×1,5 à ×3, avec ou sans hausse du cours) : toutes positives ; ×2 sur 10 semaines retenu, le plus simple et le plus stable.</li>' +
    "<li><b>Valeur intrinsèque, cycle, figures chartistes</b> : non testables sur l'historique (données du jour seulement), retirés des filtres, consultables sur les fiches.</li></ul></details>";
  h +=
    '<details class="fsscale more" data-k="lg-lim"><summary>⚖️ Fiabilité des chiffres : du flatteur au prudent</summary>' +
    '<p class="small">🎯, écart à 6 mois avec la société moyenne de la même semaine, dividendes inclus :</p>' +
    tbl(
      ['Étape', 'Écart'],
      [
        ["Tout l'historique, 1997-2026", '+8,1 pts'],
        ['Années jamais vues au réglage, 2013-2026', '+7,1 pts'],
        ['… moins 1 % de frais par achat-vente', '+6,1 pts'],
        ['… moins 2 % de sélections supposées en faillite (−100 %)', '<b>+3,8 pts</b>'],
      ]
    ) +
    '<p class="small">À retenir : <b>environ +4 points tous les 6 mois</b> face à la société moyenne (≈ +8 par an), avec des années nulles ou en perte.</p><ul class="plain small nomax">' +
    '<li>🪦 <b>Biais du survivant</b> (sociétés disparues absentes) : faillites supposées ci-dessus, hypothèse sévère ; et contrôle indépendant par le facteur momentum européen de Kenneth French, calculé avec les sociétés disparues : +9,7 % par an contre +10,0 % pour nous (1998-2026, corrélation 0,83).</li>' +
    "<li>🎲 <b>Trop d'essais</b> (512 réglages) : chiffre retenu sur les années jamais vues (réglages choisis sur 1997-2012, les nôtres 13<sup>es</sup> sur 512) et seuil exigeant t ≥ 3 au lieu de 2 (Harvey, Liu et Zhu, 2016). Le 🎯 passe (t 3,3) ; 📣 non (rien avant 2013) ; ⏸️ et ⚡ faibles depuis 2013.</li>" +
    "<li>💶 <b>Frais, impôts, dividendes</b> : dividendes inclus (cours ajustés) ; frais de 0,5 à 2 % par achat-vente selon le courtier (plus 0,4 % de taxe à l'achat des sociétés françaises de plus d'1 Md€) ; dans un PEA, aucun impôt tant que l'argent y reste, puis 18,6 % des gains en prélèvements sociaux après 5 ans (taux 2026), comme pour un fonds indiciel dans le même PEA.</li>" +
    '<li>💎 <b>Valeur</b> testée sur nos données, 2024-2026 (seuls comptes disponibles, ≈ 520 sociétés liquides par mois) : les 10 premières +5,1 points à 6 mois (+4,1 après frais), 4 % de chutes de 25 % contre 8 % ; t 1,7 : encourageant, pas encore une preuve. Le dosage 70/30 repose sur le facteur valeur européen de Kenneth French.</li>' +
    '<li>📒 <b>Suivi réel</b> : automatique depuis le ' +
    (function () {
      var T0 = (rankData() || {}).pickTrack,
        d0 = (T0 && T0.since) || '2026-10-18';
      return (
        shortDate(d0) +
        '\u00a0; premiers résultats à 3 mois le ' +
        shortDate(ES.addDays(d0, 91)) +
        ', à 6 mois le ' +
        shortDate(ES.addDays(d0, 182))
      );
    })() +
    " ; chaque règle (🔊 📣 ⏸️) jugée sur 30 sélections de chaque côté, email de revue si l'avantage se dégrade.</li>" +
    '<li>🧾 <b>Refaire les calculs</b> : scripts publics dans <a href="' +
    esc(repoUrl()) +
    '/tree/main/research" target="_blank" rel="noopener">research/</a> ; <code>chiffres_cles.py</code> recalcule ce tableau en une commande.</li>' +
    '<li>Une position sur deux seulement bat la société moyenne (53 %) : la méthode gagne surtout par ses fortes hausses. Pas de données gratuites fiables avant 1997.</li></ul></details>';
  return (
    h + '<p class="foot">Tests du 17 au 19/10/2026. Aide à la décision, pas un conseil en investissement.</p></section>'
  );
}
function methodCard() {
  var R = rankData();
  if (!R) return '';
  var st = R.study,
    H = S.methH || 26;
  var h =
    '<details class="card fold proof" id="methode" data-k="meth"><summary>📏 Contrôle recalculé chaque soir</summary>';
  if (st && st['h' + H]) {
    var g = st['h' + H];
    h +=
      '<p class="small">' +
      fmtInt(st.companies) +
      ' sociétés (' +
      esc(st.source || 'cotées') +
      '), chaque semaine du ' +
      shortDate(st.from) +
      ' au ' +
      shortDate(st.to) +
      ' : résultat ' +
      (H === 13 ? '3' : '6') +
      ' mois plus tard, comparé au titre moyen de la même semaine.</p>' +
      '<div class="segs" role="group" aria-label="Horizon">' +
      [
        [13, 'à 3 mois'],
        [26, 'à 6 mois'],
      ]
        .map(function (x) {
          return (
            '<button class="' +
            (H === x[0] ? 'on' : '') +
            '" data-a="methH" data-v="' +
            x[0] +
            '">' +
            x[1] +
            '</button>'
          );
        })
        .join('') +
      '</div>' +
      '<div class="tablewrap"><table class="grid cards"><thead><tr><th>Groupe</th><th class="num">Écart moyen</th><th class="num">Battent la moyenne</th><th class="num">Fiabilité</th></tr></thead><tbody>' +
      st.groups
        .map(function (gr) {
          var o = g[gr.key];
          if (!o || o.mean == null) return '';
          var t = o.t,
            rel = t == null ? 'n.d.' : Math.abs(t) >= 3 ? 'solide' : Math.abs(t) >= 2 ? 'probable' : 'incertain';
          return (
            '<tr><td class="c-name" data-l="Groupe">' +
            esc(gr.label) +
            '<small>' +
            fmtInt(o.n) +
            ' relevés sur ' +
            o.weeks +
            ' semaines</small></td><td class="num" data-l="Écart"><b class="' +
            (o.mean >= 0 ? 'pos' : 'neg') +
            '">' +
            (o.mean >= 0 ? '+' : '') +
            fmtN(o.mean, 1) +
            ' pts</b></td><td class="num" data-l="Battent">' +
            o.beat +
            ' %</td><td class="num" data-l="Fiabilité">' +
            rel +
            (t != null ? '<small>t ≈ ' + fmtN(t, 1) + '</small>' : '') +
            '</td></tr>'
          );
        })
        .join('') +
      '</tbody></table></div>' +
      xpi(
        "« Fiabilité » : écart moyen rapporté à sa variabilité d'une semaine à l'autre, corrigé du chevauchement des périodes (t). Solide à partir de 3, probable à partir de 2. Les sociétés disparues de la cote ne sont pas dans l'étude : les titres effondrés y paraissent donc un peu meilleurs qu'en réalité. Comptes : connus 120 jours après la clôture de l'exercice."
      );
  }
  return h + '</details>';
}
function vAide() {
  var h = '<h2 class="vt">Comment ça marche</h2>' + logicCard() + compareCard() + biblioCard() + methodCard();
  h +=
    "<p class=\"foot pad\">🌙 Mis à jour chaque soir de semaine · 📧 sélection le lundi · 📱 « Ajouter à l'écran d'accueil » pour l'ouvrir comme une application. Aide à la décision, jamais un ordre d'achat.</p>";
  var nD = 0,
    det = function (title, body) {
      return (
        '<details class="card fold" data-k="aide' + nD++ + '"><summary>' + title + '</summary>' + body + '</details>'
      );
    };
  if (!S.qualityLoaded) loadQuality();
  var qa = S.quality,
    qn = qa
      ? (qa.issues || []).length +
        ((S.uiCheck && S.uiCheck.problems) || []).length +
        ((S.uiCheck && S.uiCheck.jsErrors) || []).length
      : null;
  h += det(
    '🩺 Contrôle du soir' +
      (qa
        ? ' <span class="muted">· ' + (qn ? '⚠️ ' + qn + ' point(s) à vérifier' : '✅ aucun problème') + '</span>'
        : ''),
    '<div data-nocheck>' + vQuality() + '</div>' // le rapport cite les textes fautifs : le contrôle suivant ne doit pas s'y relire
  );
  h += det('État des données', vSources());
  h += det('Titres suivis', vUnivers());
  return h;
}
function step(t, d) {
  return '<li><b>' + t + '</b><p>' + d + '</p></li>';
}
