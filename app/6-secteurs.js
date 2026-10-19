/* Euro Signal — interface : secteurs, thèmes et fiches des sociétés du catalogue.
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
/* ----- Initiés ----- */
/* ============ Secteurs en tendance, thèmes, leader et challenger (data/sectors.json, calculé chaque soir) ============ */
function loadSectors() {
  if (S.secLoading || S.secLoaded) return;
  S.secLoading = true;
  fetch('data/sectors.json', { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      if (!d || d.format !== 'euro-signal-sectors') throw new Error('format');
      S.sec = defang(d);
      S.secLoaded = true;
      S.secLoading = false;
      S.gByKey = null;
      try {
        S.cycle = ES.cyclePhase(S.sec.groups);
      } catch (e) {
        S.cycle = null;
      }
      if (S.view === 'secteurs' || S.view === 'secco' || S.view === 'classement' || S.view === 'fiche') render();
    })
    .catch(function (e) {
      S.secLoaded = true;
      S.secLoading = false;
      S.secError = (e && e.message) || 'illisible';
      if (S.view === 'secteurs' || S.view === 'secco') render();
    });
}
function secName(k) {
  if (!k) return '—';
  var m = /^Autres : (.+)$/.exec(k);
  return m ? 'Autres : ' + (ES.sectorFr(m[1]) || m[1]) : ES.industryFr(k) || k;
}
function pc100(v) {
  return v == null ? 'n.d.' : pct(v * 100);
}
function capTxt(v) {
  return v == null ? 'n.d.' : v >= 1e9 ? fmtN(v / 1e9, v >= 1e10 ? 0 : 1) + ' Md€' : fmtN(v / 1e6, 0) + ' M€';
}
/** Chiffre clé en ligne : libellé + valeur colorée (vert si positif, rouge si négatif). */
function kvNum(label, v, txt) {
  return v == null || !isFinite(v)
    ? null
    : '<span class="nw">' +
        label +
        ' <b class="' +
        (v >= 0 ? 'pos' : 'neg') +
        '">' +
        String(txt).replace(' %', '\u00a0%') +
        '</b></span>';
}
function secStock(x, role) {
  if (!x) return '';
  var sym = esc(x.symbol);
  var fa = [
    x.analysts ? x.analysts + ' analystes' + (x.upside != null ? ', objectif moyen ' + pc100(x.upside) : '') : null,
    x.revUp30 != null && x.revDown30 != null
      ? 'prévisions relevées ' + x.revUp30 + ' fois, abaissées ' + x.revDown30 + ' fois en 30 jours'
      : null,
    x.lastSurprise
      ? 'derniers résultats ' +
        (x.lastSurprise[1] >= 0 ? 'au-dessus' : 'en dessous') +
        ' du consensus (' +
        pct(x.lastSurprise[1]) +
        ', ' +
        shortDate(x.lastSurprise[0]) +
        ')'
      : null,
    x.instPct != null ? Math.round(x.instPct * 100) + ' % du capital détenu par des institutionnels' : null,
  ]
    .filter(Boolean)
    .join(' · ');
  var d = S.sec.daily && S.sec.daily[x.symbol],
    open = S.secOpen && S.secOpen[x.symbol];
  var h =
    '<div class="secst"><div class="secst-h"><span class="chip ' +
    (role === 'leader' ? 'pos-leader' : 'pos-challenger') +
    '">' +
    (role === 'leader' ? '🏆 Leader' : '🚀 Challenger') +
    '</span> ' +
    coName(x, true) +
    ' <span class="muted small">' +
    sym +
    '</span>' +
    (x.pea === false ? ' <span class="chip bad">hors PEA</span>' : '') +
    '</div><p class="secst-k">' +
    [
      capTxt(x.capEur),
      kvNum('force 6 mois', x.rs6, pc100(x.rs6)),
      kvNum('croissance', x.revGrowth, pc100(x.revGrowth)),
      x.opMargin != null ? '<span class="nw">marge ' + fmtN(x.opMargin * 100, 0) + '\u00a0%</span>' : null,
      kvNum('objectif', x.upside, pc100(x.upside)),
    ]
      .filter(Boolean)
      .join(' · ') +
    '</p>' +
    (fa ? xpi(fa, 'Analystes') : '');
  h +=
    '<div class="row-btn">' +
    (d && d.length >= 120
      ? '<button class="link" data-a="secPlan" data-v="' +
        sym +
        '">' +
        (open ? "Masquer le plan d'entrée" : "🧭 Plan d'entrée") +
        '</button>'
      : '') +
    ' <button class="link" data-a="secCo" data-v="' +
    sym +
    '">📄 Fiche complète</button>' +
    '</div>';
  if (open && d) {
    try {
      var adj = ES.normalizeSeries(d),
        esI = esIsinOfSym(x.symbol, x.isin),
        pl = (esI && planFor(esI)) || ES.entryPlan(adj);
      h += pl
        ? planCard(esI || x.symbol, pl, adj)
        : '<p class="muted small">Plan non calculable (historique trop court).</p>';
    } catch (e) {
      h += '<p class="muted small">Plan non calculable.</p>';
    }
  }
  return h + '</div>';
}
/* ============ Fiche d'une société des secteurs (data/sectors-companies.json, lue à la demande) ============ */
function coName(x, bold) {
  if (!x || !x.symbol) return '—';
  return (
    '<button class="link coname" data-a="secCo" data-v="' +
    esc(x.symbol) +
    '">' +
    (bold ? '<b>' : '') +
    flag(x.country) +
    esc(x.name || x.symbol) +
    (bold ? '</b>' : '') +
    '</button>'
  );
}
function esIsinOfSym(sym, isin) {
  if (isin && S.inst[isin]) return isin;
  if (!S.tkMap) {
    S.tkMap = {};
    Object.keys(S.inst).forEach(function (i) {
      var t = S.inst[i].ticker;
      if (t && !S.tkMap[t]) S.tkMap[t] = i;
    });
  }
  return S.tkMap[sym] || null;
}
/* Toutes les sociétés cotées : liste de recherche (data/societes-index.json) et fiches réparties en 32 fichiers (data/societes/N.json) */
function coShards() {
  return (S.coIndex && S.coIndex.shards) || 32;
}
function coReady(sym) {
  return !!(S.coShard && S.coShard[ES.shardOf(sym, coShards())] === true);
}
function loadSecCo(sym) {
  var k = ES.shardOf(sym || '', coShards());
  S.coShard = S.coShard || {};
  if (S.coShard[k]) return;
  S.coShard[k] = 'loading';
  var done = function (d) {
    d = defang(d);
    S.secCo = S.secCo || { items: {} };
    Object.assign(S.secCo.items, d.items || {});
    S.secCo.dDates = d.dDates;
    S.secCo.wDates = d.wDates;
    S.secCo.generatedAt = d.generatedAt;
    S.coShard[k] = true;
    if (S.view === 'secco' || S.view === 'fiche') render(); // fiche Euro Signal : pli 🏭 business model
  };
  fetch('data/societes/' + k + '.json', { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(done)
    .catch(function () {
      // avant le premier calcul du soir avec le catalogue : ancien fichier unique, s'il existe encore
      fetch('data/sectors-companies.json', { cache: 'no-store' })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(done)
        .catch(function () {
          S.coShard[k] = true;
          if (S.view === 'secco' || S.view === 'fiche') render(); // fiche Euro Signal : pli 🏭 business model
        });
    });
}
function loadCoIndex() {
  if (S.coIndexLoading || S.coIndex) return;
  S.coIndexLoading = true;
  fetch('data/societes-index.json', { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      S.coIndex = defang(d);
      S.coIndex.norm = (S.coIndex.rows || []).map(function (r) {
        return ES.norm([r[1], r[0], r[8]].join(' '));
      });
      S.coIndexLoading = false;
      render();
    })
    .catch(function () {
      S.coIndex = { rows: [], norm: [], missing: true };
      S.coIndexLoading = false;
      render();
    });
}
/** Résultats de recherche parmi toutes les sociétés cotées (hors celles déjà affichées dans la liste). */
function coSearch(q, exclude, max) {
  var nq = ES.norm(q || '').trim();
  if (nq.length < 2) return '';
  if (!S.coIndex) {
    loadCoIndex();
    return '<p class="muted small pad">Recherche dans toutes les sociétés cotées…</p>';
  }
  if (S.coIndex.missing)
    return '<p class="muted small pad">La liste de toutes les sociétés cotées sera disponible après le prochain calcul du soir.</p>';
  var R = S.coIndex.rows,
    N = S.coIndex.norm,
    hits = [];
  for (var k = 0; k < R.length && hits.length < 200; k++) if (N[k].indexOf(nq) > -1) hits.push(R[k]);
  var found = hits.length;
  hits = hits.filter(function (r) {
    var es = esIsinOfSym(r[0], r[8]);
    return !(exclude && ((es && exclude[es]) || exclude['@' + r[0]]));
  });
  hits.sort(function (a, b) {
    var sa = ES.norm(a[1] || '').indexOf(nq) === 0 ? 0 : 1,
      sb = ES.norm(b[1] || '').indexOf(nq) === 0 ? 0 : 1;
    return sa - sb || (b[3] || 0) - (a[3] || 0);
  });
  if (!hits.length && found) return ''; // déjà toutes affichées dans la liste au-dessus
  if (!hits.length)
    return (
      '<p class="muted small pad">Aucune autre société cotée ne correspond à « ' +
      esc(q) +
      ' » parmi ' +
      R.length +
      '.</p>'
    );
  return (
    '<section class="card"><h3>🔎 Toutes les sociétés cotées <span class="muted small">· ' +
    hits.length +
    ' sur ' +
    R.length +
    '</span></h3><ul class="evs">' +
    hits
      .slice(0, max || 20)
      .map(function (r) {
        var cap = r[3] == null ? '' : r[3] >= 1000 ? fmtN(r[3] / 1000, r[3] >= 10000 ? 0 : 1) + ' Md€' : r[3] + ' M€';
        var es = esIsinOfSym(r[0], r[8]);
        return (
          '<li><div>' +
          coName({ symbol: r[0], name: r[1], country: r[2] }, true) +
          '<small>' +
          esc([r[0], cap ? 'capitalisation ' + cap : null, ES.sectorFr(r[4])].filter(Boolean).join(' · ')) +
          '</small></div><span>' +
          (r[6] === 't'
            ? '<span class="fig good">🔥 Secteur en tendance</span> '
            : r[6] === 'e'
              ? '<span class="fig good">🌱 Secteur émergent</span> '
              : '') +
          (r[7] ? '<span class="chip good">PEA probable</span>' : '<span class="chip bad">hors PEA</span>') +
          (es ? ' <span class="chip">achats de dirigeants suivis</span>' : '') +
          '</span></li>'
        );
      })
      .join('') +
    '</ul>' +
    (hits.length > (max || 20) ? '<p class="muted small">Affinez la recherche pour voir les autres.</p>' : '') +
    "<p class=\"foot\">Toutes les actions des bourses de l'UE et de l'EEE (Paris, Francfort, Milan, Madrid, Amsterdam, Bruxelles, Lisbonne, Dublin, Vienne, Helsinki, Stockholm, Copenhague, Oslo). Touchez une société pour sa fiche : chiffres clés, cours sur 1 an et 5 ans, plan d'entrée.</p></section>"
  );
}
function lineChart(ser, five, lv) {
  var narrow = typeof window !== 'undefined' && window.innerWidth < 560;
  var W = narrow ? 380 : 640,
    H = 220,
    L = narrow ? 48 : 62,
    R = 8,
    T = 12,
    B = 26,
    n = ser.length,
    lo = Infinity,
    hi = -Infinity;
  ser.forEach(function (r) {
    lo = Math.min(lo, r[1]);
    hi = Math.max(hi, r[1]);
  });
  if (!(hi > lo)) {
    hi = lo * 1.01 + 0.01;
  }
  // supports (vert) et résistances (rouge) de l'année de cours, comme sur les fiches Euro Signal
  var lvl = lv
    ? (lv.supports || [])
        .map(function (x) {
          return { p: x.price, s: true, x: x };
        })
        .concat(
          (lv.resistances || []).map(function (x) {
            return { p: x.price, s: false, x: x };
          })
        )
        .filter(function (v) {
          return v.p > 0 && isFinite(v.p) && v.p >= lo * 0.75 && v.p <= hi * 1.35;
        })
    : [];
  lvl.forEach(function (v) {
    lo = Math.min(lo, v.p);
    hi = Math.max(hi, v.p);
  });
  var pad = (hi - lo) * 0.06;
  lo -= pad;
  hi += pad;
  var xs = function (k) {
      return L + ((W - L - R) * k) / Math.max(1, n - 1);
    },
    ys = function (v) {
      return T + ((H - T - B) * (hi - v)) / (hi - lo);
    };
  var path = ser
    .map(function (r, k) {
      return (k ? 'L' : 'M') + xs(k).toFixed(1) + ' ' + ys(r[1]).toFixed(1);
    })
    .join('');
  var f = function (v) {
      return fmtN(v, v < 10 ? 2 : v < 1000 ? 1 : 0);
    },
    last = ser[n - 1][1],
    first = ser[0][1];
  var lab = lvl
    .map(function (v) {
      return { v: v, y: ys(v.p) };
    })
    .sort(function (a, b) {
      return a.y - b.y;
    });
  // étiquettes : résistances à droite, supports à gauche (deux fois moins serrées), écartées d'une ligne si besoin
  [true, false].forEach(function (sup) {
    var prev = null;
    lab.forEach(function (o) {
      if (!!o.v.s !== sup) return;
      o.ty = Math.max(T + 9, o.y - 3);
      if (prev && o.ty - prev.ty < 11) o.ty = prev.ty + 11;
      prev = o;
    });
  });
  var lvSvg = lab
    .map(function (o) {
      var v = o.v,
        y = o.y.toFixed(1);
      return (
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
        (v.s ? 'Support ' : 'Résistance ') +
        f(v.p) +
        '</title></line><text x="' +
        (v.s ? L + 4 : W - R - 4) +
        '" y="' +
        o.ty.toFixed(1) +
        '"' +
        (v.s ? '' : ' text-anchor="end"') +
        ' class="ax lv-t ' +
        (v.s ? 'lv-ts' : 'lv-tr') +
        '">' +
        (v.s ? 'Support ' : 'Résistance ') +
        f(v.p) +
        (v.x && v.x.distPct != null ? ' (' + pct(v.x.distPct) + ')' : '') +
        '</text>'
      );
    })
    .join('');
  var svg =
    '<svg viewBox="0 0 ' +
    W +
    ' ' +
    H +
    '" class="chart" role="img" aria-label="Cours de clôture ' +
    (five ? 'sur 5 ans (une clôture par semaine)' : 'sur un an') +
    ', supports et résistances">' +
    [hi - pad, (hi + lo) / 2, lo + pad]
      .map(function (v) {
        var y = ys(v).toFixed(1);
        return (
          '<line x1="' +
          L +
          '" x2="' +
          (W - R) +
          '" y1="' +
          y +
          '" y2="' +
          y +
          '" class="grid"/><text x="' +
          (L - 6) +
          '" y="' +
          (+y + 4) +
          '" text-anchor="end" class="ax">' +
          f(v) +
          '</text>'
        );
      })
      .join('') +
    '<path d="' +
    path +
    'L' +
    xs(n - 1).toFixed(1) +
    ' ' +
    (H - B) +
    'L' +
    L +
    ' ' +
    (H - B) +
    'Z" class="area"/>' +
    lvSvg +
    '<path d="' +
    path +
    '" class="line"/>' +
    '<circle cx="' +
    xs(n - 1).toFixed(1) +
    '" cy="' +
    ys(last).toFixed(1) +
    '" r="3.5" class="last"/>' +
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
    '</text></svg>';
  return { svg: svg, perf: first > 0 ? (last / first - 1) * 100 : null, last: last, levels: lab.length };
}
/** Valeur d'une société du catalogue (fiche Yahoo) : cours / valeur comptable, rentabilité, croissance que suppose le cours. */
function secValueCard(x, es) {
  if (x.pb == null) return '';
  var r = ES.costOfEquity(x.capEur),
    roe = x.roe,
    out = [];
  out.push(
    critBox(
      '📘',
      'Cours / valeur comptable',
      fmtN(x.pb, 2) + '×',
      x.pb < 1 ? (roe != null && roe >= r ? 'good' : 'mid') : x.pb <= 3 ? 'neu' : 'mid',
      x.pb < 1
        ? roe != null && roe >= r
          ? "Sous l'actif net et rentable : rare"
          : "Sous l'actif net, mais rentabilité faible"
        : x.pb <= 3
          ? 'Dans la norme'
          : 'Cher par rapport aux fonds propres',
      scaleLine(
        Math.min(x.pb, 5),
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
        'Cours sur valeur comptable ' + fmtN(x.pb, 2)
      ),
      "Combien le marché paie chaque euro de fonds propres. Sous 1, l'entreprise vaut moins en Bourse que son bilan."
    )
  );
  if (roe != null) {
    var rp = r * 100;
    out.push(
      critBox(
        '🧮',
        'Rentabilité des fonds propres',
        fmtN(roe * 100, 1) + ' %',
        roe * 100 >= rp + 5 ? 'good' : roe >= r ? 'neu' : roe > 0 ? 'mid' : 'bad',
        (roe >= r ? 'Au-dessus' : 'En dessous') + ' du rendement exigé (' + fmtN(rp, 1) + ' %)',
        scaleLine(
          Math.max(-10, Math.min(roe * 100, 40)),
          -10,
          40,
          [
            [-10, 0, 'bad'],
            [0, rp, 'mid'],
            [rp, 40, 'good'],
          ],
          [
            [0, '0'],
            [rp, fmtN(rp, 1)],
            [40, '40+'],
          ],
          'Rentabilité ' + fmtN(roe * 100, 1) + ' %'
        ),
        "Résultat net des 12 derniers mois ÷ fonds propres. Au-dessus du rendement exigé, l'entreprise vaut plus que ses fonds propres."
      )
    );
    if (roe > 0 && Math.abs(x.pb - 1) >= 0.05) {
      var g = ((x.pb * r - roe) / (x.pb - 1)) * 100;
      if (isFinite(g) && x.pb > 1)
        out.push(
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
            'Croissance annuelle des résultats, pour toujours, qui justifierait le cours (modèle du revenu résiduel, rendement exigé ' +
              fmtN(rp, 1) +
              ' %).'
          )
        );
    }
  }
  var isin = es && S.inst[es] && S.inst[es].value ? es : null;
  return (
    '<section class="card"><h3>💎 Valeur</h3><div class="crits">' +
    out.join('') +
    '</div>' +
    (isin
      ? '<p class="small"><button class="link" data-a="open" data-i="' +
        esc(isin) +
        '" data-from="secco">Valeur intrinsèque détaillée (comptes sur 4 ans) →</button></p>'
      : '') +
    '<p class="foot">Source : fiche Yahoo Finance (derniers comptes publiés).</p></section>'
  );
}
function vSecCo() {
  var back =
    '<div class="crumbs"><button class="link" data-a="secBack">← ' +
    (S.secFrom === 'classement' ? 'Opportunités' : 'Secteurs et thèmes') +
    '</button></div>';
  if (!S.secLoaded) {
    loadSectors();
    return back + '<p class="muted pad">Chargement…</p>';
  }
  if (!coReady(S.secSym)) {
    loadSecCo(S.secSym);
    return back + '<p class="muted pad">Chargement de la fiche…</p>';
  }
  var sym = S.secSym,
    x = S.secCo && S.secCo.items && S.secCo.items[sym],
    partial = false;
  if (!x) {
    // fiches complètes pas encore calculées : on montre ce que le classement des secteurs connaît déjà
    ((S.sec && S.sec.groups) || []).concat((S.sec && S.sec.themes) || []).forEach(function (g) {
      [g.leader, g.challenger].concat(g.top || [], g.members || []).forEach(function (o) {
        if (!x && o && o.symbol === sym) x = Object.assign({}, o);
      });
    });
    if (x) {
      partial = true;
      var gr = ((S.sec && S.sec.groups) || []).filter(function (g) {
        return [g.leader, g.challenger].concat(g.top || []).some(function (o) {
          return o && o.symbol === sym;
        });
      })[0];
      if (gr) {
        x.group = gr.key;
        x.groupRank = gr.rank;
        x.groupTrending = gr.trending;
        x.groupEmerging = gr.emerging;
      }
    }
  }
  if (!x)
    return (
      back +
      '<div class="card"><p>Fiche indisponible pour ' +
      esc(sym || '?') +
      ' : elle apparaîtra après le prochain calcul du soir.</p></div>'
    );
  var es = esIsinOfSym(sym, x.isin),
    cur = x.currency || '';
  var partH = partial
    ? '<p class="note">ℹ️ Fiche abrégée : la fiche complète (tous les chiffres clés, cours sur 1 an et 5 ans, plan d\'entrée) sera calculée lors du calcul de ce soir.</p>'
    : '';
  var sub = [
    sym,
    x.exchange,
    x.country ? COUNTRIES[x.country] || x.country : null,
    [ES.sectorFr(x.sector), ES.industryFr(x.industry)].filter(Boolean).join(' — '),
  ]
    .filter(Boolean)
    .join(' · ');
  var RL = { leader: '🏆 Leader', challenger: '🚀 Challenger', member: 'Membre' },
    TH = {};
  ((S.sec && S.sec.themes) || []).forEach(function (t) {
    TH[t.key] = t.name;
  });
  var roles = (x.roles || [])
    .map(function (r) {
      return (
        '<span class="chip ' +
        (r[0] === 'leader' ? 'pos-leader' : r[0] === 'challenger' ? 'pos-challenger' : '') +
        '">' +
        RL[r[0]] +
        ' · ' +
        esc(r[1] === 't' ? 'thème ' + (TH[r[2]] || r[2]) : secName(r[2])) +
        '</span>'
      );
    })
    .join(' ');
  var nG = ((S.sec && S.sec.groups) || []).length;
  var h =
    back +
    '<header class="fhead"><div><h2>' +
    flag(x.country) +
    esc(x.name || sym) +
    '</h2><p class="fsub">' +
    esc(sub) +
    '</p><p>' +
    (/^REIT\b/i.test(String(x.industry || ''))
      ? '<span class="chip bad">hors PEA (foncière cotée)</span> '
      : x.pea === false
        ? '<span class="chip bad">hors PEA</span> '
        : x.pea
          ? '<span class="chip good">' +
            (x.basic ? "PEA probable (cotée dans l'UE ou l'EEE)" : "PEA (siège dans l'UE ou l'EEE)") +
            '</span> '
          : '') +
    roles +
    '</p></div></header>' +
    partH +
    (x.basic
      ? '<p class="note">ℹ️ Société hors du classement des secteurs (moins de 500 M€ de capitalisation ou fiche Yahoo incomplète) : cours, plan d\'entrée et chiffres de base. Vérifiez l\'éligibilité au PEA chez votre courtier.</p>'
      : '');
  h += rankFold(rankOf(es, sym)) + analysisCard(es && S.inst[es] ? es : null, sym) + bizCard(sym);
  var more = '';
  if (es)
    more +=
      '<section class="card"><p>📒 Cette société est aussi suivie par Euro Signal : achats des dirigeants, comptes sur 4 ans, résultats, rachats d\'actions, plan d\'entrée et note.</p><button data-a="open" data-i="' +
      esc(es) +
      '" data-from="secco">Ouvrir la fiche Euro Signal complète →</button></section>';
  // secteur, valeur et chiffres clés : chacun dans son pli (même présentation que les fiches Euro Signal)
  if (x.group)
    more += asFold(
      '<section class="card"><h3>Secteur</h3><p><b>' +
        esc(secName(x.group)) +
        '</b>' +
        (x.groupRank ? ' : ' + x.groupRank + 'e sur ' + nG + ' groupes' : '') +
        (x.groupTrending ? ' <span class="chip good">En tendance</span>' : '') +
        (x.groupEmerging ? ' <span class="chip warn">Émergent</span>' : '') +
        '</p>' +
        '<p class="small">Force sur 6 mois ' +
        pc100(x.rs6) +
        ' et sur 3 mois ' +
        pc100(x.rs3) +
        ' par rapport au STOXX 600' +
        (x.volume != null
          ? ' · volumes : ' +
            (x.volume > 0.05 ? 'achats dominants' : x.volume < -0.05 ? 'ventes dominantes' : 'équilibrés')
          : '') +
        '.</p></section>',
      'co-sec',
      '🧭 Secteur <span class="muted">· ' +
        esc(secName(x.group)) +
        (x.groupRank ? ', ' + x.groupRank + 'e sur ' + nG : '') +
        '</span>'
    );
  // chiffres clés
  var big = function (v) {
    return v == null
      ? null
      : Math.abs(v) >= 1e9
        ? fmtN(v / 1e9, Math.abs(v) >= 1e10 ? 0 : 1) + ' Md'
        : fmtN(v / 1e6, 0) + ' M';
  };
  var lqc = liqLevel(x.turnoverEur);
  if (lqc && lqc.tone !== 'good')
    h +=
      '<p class="liqw">💧 <b>' +
      cap1(lqc.label) +
      '</b> : ' +
      ES.fmtEur(x.turnoverEur) +
      ' échangés par jour en moyenne. Ordres à cours limité, ' +
      ES.fmtEur(x.turnoverEur * 0.05) +
      ' par jour au plus.</p>';
  var rows = [
    ['Capitalisation', capTxt(x.capEur)],
    ['Échanges quotidiens moyens', x.turnoverEur != null ? ES.fmtEur(x.turnoverEur) : null],
    [
      "Chiffre d'affaires (12 mois)",
      x.revenue != null
        ? (function () {
            var fc = cur === 'GBp' || cur === 'GBX' ? 'GBP' : cur;
            /* comptes en livres, cours en pence */ return (
              big(x.revenue) +
              ' ' +
              esc(fc) +
              (fc && fc !== 'EUR' && ES.toEur(x.revenue, fc) != null
                ? ' (≈ ' + big(ES.toEur(x.revenue, fc)) + ' €)'
                : '')
            );
          })()
        : null,
    ],
    ["Croissance du chiffre d'affaires", x.revGrowth != null ? pc100(x.revGrowth) + ' sur un an' : null],
    ['Marge brute', x.grossMargin ? fmtN(x.grossMargin * 100, 0) + ' %' : null],
    ['Marge opérationnelle', x.opMargin != null ? fmtN(x.opMargin * 100, 0) + ' %' : null],
    ['PER attendu (12 mois)', x.fwdPE != null && x.fwdPE > 0 ? fmtN(x.fwdPE, 1) : null],
    // analystes, résultats et actionnariat : dans le pli 🔬 Analyse (pas de doublon)
    ['Cours / valeur comptable', x.pb != null ? fmtN(x.pb, 2) + '×' + (x.pb < 1 ? " (sous l'actif net)" : '') : null],
    ['Rentabilité des fonds propres', x.roe != null ? fmtN(x.roe * 100, 1) + ' % sur 12 mois' : null],
  ].filter(function (r) {
    return r[1];
  });
  more += asFold(
    secValueCard(x, es),
    'co-val',
    '💎 Valeur <span class="muted">· cours / valeur comptable ' +
      (x.pb != null ? fmtN(x.pb, 2) + '×' : 'n.d.') +
      '</span>'
  );
  more += asFold(
    '<section class="card"><h3>Chiffres clés</h3><table class="kv">' +
      rows
        .map(function (r) {
          return '<tr><th>' + r[0] + '</th><td>' + r[1] + '</td></tr>';
        })
        .join('') +
      '</table><p class="small muted">Source Yahoo Finance, relevé du ' +
      shortDate(String((S.secCo || S.sec || {}).generatedAt || '').slice(0, 10)) +
      '.</p>' +
      '<p class="rep">' +
      reportBtn(x.name || sym, x.isin || null, sym) +
      '</p></section>',
    'co-kpi',
    '🧾 Chiffres clés <span class="muted">· Yahoo, 12 derniers mois</span>'
  );
  // cours
  var D = (S.secCo && S.secCo.dDates) || [],
    Wd = (S.secCo && S.secCo.wDates) || [];
  var dser = (x.d || [])
    .map(function (v, k) {
      return [D[k], v];
    })
    .filter(function (r) {
      return r[0] && r[1] > 0;
    });
  if (!dser.length && S.sec && S.sec.daily && S.sec.daily[sym])
    dser = S.sec.daily[sym]
      .map(function (r) {
        return [r[0], r[4]];
      })
      .filter(function (r) {
        return r[0] && r[1] > 0;
      });
  var wser = (x.w || [])
    .map(function (v, k) {
      return [Wd[k], v];
    })
    .filter(function (r) {
      return r[0] && r[1] > 0;
    });
  if (dser.length && wser.length && wser[wser.length - 1][0] > dser[dser.length - 1][0])
    wser[wser.length - 1][0] = dser[dser.length - 1][0];
  var five = S.range === '5y' && wser.length >= 20,
    note = '';
  if (S.range === '5y' && !five) note = "⚠️ Pas d'historique sur 5 ans pour ce titre : vue 1 an.";
  if (!five && dser.length < 20 && wser.length >= 20) {
    five = true;
    note = '⚠️ Cours journaliers indisponibles : vue 5 ans (une clôture par semaine).';
  }
  var ser = five ? wser : dser;
  h +=
    '<details class="card fold" data-k="f-cours"><summary>📉 Cours, supports et résistances <span class="muted small">· plan d\'entrée</span></summary><div class="seg" role="group" aria-label="Période du graphique"><button data-a="range" data-v="1y" class="' +
    (five ? '' : 'on') +
    '" aria-pressed="' +
    !five +
    '">1 an</button><button data-a="range" data-v="5y" class="' +
    (five ? 'on' : '') +
    '" aria-pressed="' +
    five +
    '">5 ans</button></div>' +
    (note ? '<p class="small"><b>' + note + '</b></p>' : '');
  if (ser.length >= 20) {
    for (var j = 1; j < ser.length; j++) {
      var ra = ser[j][1] / ser[j - 1][1];
      if (ra > 3 || ra < 1 / 3) {
        h +=
          '<p class="small"><b>⚠️ Saut de cours ' +
          (ra > 1 ? '×' + fmtN(ra, 1) : '÷' + fmtN(1 / ra, 1)) +
          ' le ' +
          shortDate(ser[j][0]) +
          ' : vraie chute ou envolée, ou bien opération sur le capital non ajustée. À vérifier.</b></p>';
        break;
      }
    }
    if (five && ES.daysBetween(ser[0][0], ser[ser.length - 1][0]) < 1600)
      h += '<p class="small"><b>ℹ️ Cours disponibles depuis le ' + shortDate(ser[0][0]) + ' seulement.</b></p>';
    var lvRows = (dser.length ? dser : wser).map(function (r) {
        return [r[0], null, null, null, r[1]];
      }),
      lvC = ES.completeLevels(dser.length >= 60 ? ES.supportResistance(lvRows) : null, lvRows),
      lc = lineChart(ser, five, lvC);
    h +=
      '<div class="chartwrap">' +
      lc.svg +
      '</div><p class="legend2">' +
      (lc.levels ? '<span><i class="lg-sup"></i>support</span><span><i class="lg-res"></i>résistance</span>' : '') +
      '<span class="muted">' +
      (five ? 'Une clôture par semaine' : 'Clôtures journalières') +
      ', ajustées des dividendes et splits, en ' +
      esc(cur || 'devise locale') +
      ' · dernier cours ' +
      fmtN(lc.last, lc.last < 10 ? 2 : 1) +
      ' · ' +
      (lc.perf != null ? pct(lc.perf) + ' sur la période' : '') +
      ' · graphique depuis le ' +
      shortDate(ser[0][0]) +
      ' · source Yahoo Finance</span></p>';
  } else h += '<p class="muted">Aucun cours disponible pour ce titre.</p>';
  // plan d'entrée sur les cours journaliers (dans le même pli que le graphique, comme sur les fiches Euro Signal)
  if (dser.length >= 120) {
    try {
      var adj = ES.normalizeSeries(
          dser.map(function (r) {
            return [r[0], null, null, null, r[1], null];
          })
        ),
        esJ = esIsinOfSym(sym, x.isin),
        pl = (esJ && planFor(esJ)) || ES.entryPlan(adj);
      h += pl ? planCard(esJ || sym, pl, adj) : '';
    } catch (e) {
      h += '<p class="muted small">Plan d\'entrée non calculable.</p>';
    }
  } else h += '<p class="muted small">Plan d\'entrée : pas assez de cours journaliers (6 mois au moins).</p>';
  h += '</details>';
  if (!es && dser.length) h += catBuyBox(sym, dser[dser.length - 1][1]);
  if (more)
    h +=
      '<details class="card fold comore" data-k="comore"><summary>➕ Plus de détails <span class="muted">· ' +
      (es ? 'dossier Euro Signal, ' : '') +
      'secteur, valeur, chiffres clés</span></summary>' +
      more +
      '</details>';
  var yurl = ES.safeUrl('https://finance.yahoo.com/quote/' + encodeURIComponent(sym));
  if (yurl)
    h += '<p class="small"><a href="' + esc(yurl) + '" target="_blank" rel="noopener">Voir sur Yahoo Finance ↗</a></p>';
  return h;
}
/** « Je l'ai acheté » pour une société du catalogue (sans ISIN) : même email que les fiches Euro Signal, identifiée par son symbole Yahoo. */
function catBuyBox(sym, last) {
  var email = S.email || '', // adresse jamais gardée sur l'appareil : champ vide à chaque visite
    tgt = lsGet('target', '50'),
    stp = lsGet('stop', '30');
  return (
    '<section class="card buybox"><details' +
    (lsGet('open.' + sym, '') ? ' open' : '') +
    '><summary><span class="bb-ic" aria-hidden="true">🔔</span><span><b>Je l\'ai acheté : me prévenir pour revendre</b><small>Rappel à 6 mois, seuil de protection : un email.</small></span></summary>' +
    xpi(
      "Vos achats ne sont jamais publiés : le bouton prépare un email à vous-même, qu'Euro Signal lit chaque soir. Renvoyez-en un pour changer l'objectif."
    ) +
    '<div class="fgrid">' +
    fld(
      'Votre adresse Gmail (gardée sur cet appareil)',
      '<input id="pos-email" type="email" autocomplete="email" value="' + esc(email) + '" placeholder="vous@gmail.com">'
    ) +
    fld(
      "Prix d'achat",
      '<input id="pos-price" inputmode="decimal" value="' +
        (last ? String(+(+last).toFixed(4)).replace('.', ',') : '') +
        '">'
    ) +
    fld("Date d'achat", '<input id="pos-date" type="date" value="' + esc(S.today) + '" max="' + esc(S.today) + '">') +
    fld('Objectif de hausse (%)', '<input id="pos-target" inputmode="decimal" value="' + esc(tgt) + '">') +
    fld('Seuil de protection (%)', '<input id="pos-stop" inputmode="decimal" value="' + esc(stp) + '">') +
    '</div>' +
    '<div class="row mt"><button data-a="posBuy" data-i="' +
    esc(sym) +
    '">Préparer l\'email « Je l\'ai acheté »</button><button class="ghost" data-a="posSell" data-i="' +
    esc(sym) +
    '">Je l\'ai vendu : arrêter le suivi</button></div></details></section>'
  );
}
function themeLL(t) {
  var B = S.sec && S.sec.backtest;
  return B && B.leadLag
    ? B.leadLag.filter(function (x) {
        return x.theme === t.key;
      })[0] || null
    : null;
}
function themeVerdict(t) {
  var us = t.usRs13 > 0,
    eu = t.euRs13 > 0,
    ll = themeLL(t),
    lead = ll && ll.corr && ll.corr['t+1'] >= 0.2;
  if (us && !eu)
    return [
      'warn',
      '🔭',
      lead
        ? "Amérique en hausse, Europe pas encore : fenêtre d'anticipation"
        : 'Amérique en hausse, Europe pas encore : à surveiller',
    ];
  if (us && eu) return ['good', '🟢', "Porteur des deux côtés de l'Atlantique"];
  if (!us && eu) return ['neutral', '🟡', "Europe en hausse sans l'Amérique : moins solide"];
  return ['neutral', '⚪', "Thème à l'arrêt"];
}
function vSecteurs() {
  if (!S.secLoaded) {
    loadSectors();
    return '<p class="muted pad">Chargement des secteurs…</p>';
  }
  if (!S.sec)
    return (
      '<div class="card"><h3>Secteurs</h3><p class="muted">' +
      (S.secError === 'HTTP 404'
        ? 'Le classement des secteurs sera disponible après la prochaine mise à jour du soir.'
        : 'Classement indisponible (' + esc(S.secError) + ').') +
      '</p></div>'
    );
  var X = S.sec,
    G = X.groups || [],
    h = '';
  h +=
    '<div class="toolbar"><input id="sec-q" type="search" placeholder="Rechercher une société cotée (TotalEnergies, Vusion…)" value="' +
    esc(S.secQ || '') +
    '" data-sq="q" aria-label="Rechercher une société cotée"></div>';
  if (S.secQ && S.secQ.trim().length >= 2) h += coSearch(S.secQ, null, 30);
  h +=
    '<h2 class="vt">Secteurs et thèmes</h2><p class="muted small">' +
    X.universe.n +
    ' sociétés européennes ≥ ' +
    fmtN(X.universe.minCapEur / 1e6, 0) +
    ' M€ · cours au ' +
    shortDate(X.asOf) +
    " · un radar, pas une règle d'achat</p>";
  var hTop = h;
  h = '';
  h +=
    '<details class="card fold" data-k="sec-help"><summary>ℹ️ Comment lire ces indicateurs</summary><ul class="small">' +
    '<li><b>Force 6 mois / 3 mois</b> : hausse du secteur par rapport au STOXX 600. Barre verte vers la droite = il fait mieux que le marché.</li>' +
    '<li><b>En tendance</b> : part des sociétés du secteur au-dessus de leur moyenne des 40 dernières semaines. Plus de 60 % : la hausse est large, pas portée par une ou deux valeurs.</li>' +
    '<li><b>Près des sommets</b> : part des sociétés à moins de 5 % de leur plus haut annuel.</li>' +
    '<li><b>Analystes</b> : prévisions relevées moins prévisions abaissées sur 30 jours. Positif = les analystes deviennent plus optimistes.</li>' +
    '<li><b>Résultats</b> : résultats au-dessus du consensus moins résultats en dessous.</li>' +
    '<li><b>Volumes</b> : échanges plus forts les semaines de hausse (achats) ou de baisse (ventes).</li>' +
    '<li><b>Rang</b> : moyenne des classements en force 6 mois, force 3 mois, part en tendance et part près des sommets. <b>▲ / ▼</b> : places gagnées ou perdues en 8 semaines.</li>' +
    '<li>🌱 <b>Émergent</b> : au moins ' +
    Math.max(5, Math.floor(G.length / 6)) +
    ' places gagnées en 8 semaines, et plus fort que le STOXX 600 sur 3 mois. 📈 <b>En tendance</b> : parmi les 20 % premiers, plus fort que le STOXX 600 sur 6 mois, et au moins la moitié de ses sociétés au-dessus de leur moyenne 40 semaines.</li>' +
    "<li>🧭 <b>Comment s'en servir</b> : comme un radar, pas comme un signal d'achat. Miser sur les secteurs émergents a fait −10,8 % par an face au marché, et même croisé avec 🔊 ils n'apportent rien de plus (test sur 29 ans). Le 🎯 prend d'office les sociétés d'un secteur qui monte quand leur propre hausse le justifie : rien à faire de plus. Pour une société qui vous intéresse, touchez « Surveiller » sur son plan d'entrée : un email part quand le cours entre dans la zone d'achat.</li>" +
    "<li>🔎 <b>Recherche</b> : toutes les actions cotées des bourses de l'UE et de l'EEE, même petites et sans achat de dirigeant.</li>" +
    '<li>🏆 <b>Leader</b> : plus grosse capitalisation du secteur. 🚀 <b>Challenger</b> : la plus forte des 2e à 4e capitalisations. Touchez un nom pour sa fiche complète.</li></ul></details>';
  var hHelp = h,
    hCyc = cycleCard();
  h = '';
  // thèmes

  var thRank = function (t) {
    return ['🟢', '🔭', '🟡'].indexOf(themeVerdict(t)[1]) + 1 || 4;
  };
  (X.themes || [])
    .slice()
    .sort(function (a, b) {
      return thRank(a) - thRank(b);
    })
    .forEach(function (t) {
      var v = themeVerdict(t);
      h +=
        '<details class="fold thf" data-k="thf-' +
        esc(t.key) +
        '"><summary>' +
        v[1] +
        ' ' +
        esc(t.name) +
        ' <span class="muted small">· ' +
        esc(v[2]) +
        '</span></summary><section class="card theme ' +
        v[0] +
        '">' +
        '<div class="mts">' +
        mini(
          '🇺🇸 3 mois',
          pc100(t.usRs13),
          t.usRs13,
          -0.3,
          0.3,
          true,
          'Sociétés américaines du thème (' + t.us.join(', ') + ') face au S&P 500'
        ) +
        mini('🇺🇸 6 mois', pc100(t.usRs26), t.usRs26, -0.3, 0.3, true, 'Face au S&P 500') +
        mini('🇪🇺 3 mois', pc100(t.euRs13), t.euRs13, -0.3, 0.3, true, 'Chaîne européenne du thème face au STOXX 600') +
        mini('🇪🇺 6 mois', pc100(t.euRs26), t.euRs26, -0.3, 0.3, true, 'Face au STOXX 600') +
        (t.revisions != null
          ? mini(
              'Analystes',
              (t.revisions >= 0 ? '+' : '') + Math.round(t.revisions * 100) + ' %',
              t.revisions,
              -1,
              1,
              true,
              'Révisions de prévisions nettes à la hausse en 30 jours'
            )
          : '') +
        '</div>' +
        xpi(
          '<p>Baromètre américain : ' +
            esc(t.us.join(', ')) +
            '. Barre verte vers la droite : fait mieux que son indice.</p>' +
            (function () {
              var ll = themeLL(t);
              if (!ll || !ll.corr) return '';
              var c1 = ll.corr['t+1'],
                c0 = ll.corr['t+0'],
                R = ll.rule || {},
                A = ll.alwaysEU || {};
              return (
                '<p>Par le passé : ' +
                (c0 >= 0.3
                  ? 'la chaîne européenne a monté et baissé en même temps que le baromètre américain (corrélation ' +
                    fmtN(c0, 2) +
                    ')'
                  : 'lien faible avec le baromètre américain') +
                (c1 >= 0.2
                  ? ', avec un mois de retard exploitable (' + fmtN(c1, 2) + ').'
                  : ', mais sans retard exploitable le mois suivant (' + fmtN(c1, 2) + ').') +
                (R.cagr != null && A.cagr != null
                  ? ' Ne la détenir que quand le baromètre monte : ' +
                    pc100(R.cagr) +
                    ' par an, pire baisse ' +
                    pc100(R.maxdd) +
                    ', contre ' +
                    pc100(A.cagr) +
                    ' et ' +
                    pc100(A.maxdd) +
                    ' en la gardant toujours.'
                  : '') +
                '</p>'
              );
            })(),
          'Détail'
        ) +
        secStock(t.leader, 'leader') +
        secStock(t.challenger, 'challenger') +
        '<details class="fold" data-k="th-' +
        esc(t.key) +
        '"><summary>Toute la chaîne (' +
        (t.members || []).length +
        ' sociétés)</summary><ul class="seclist">' +
        (t.members || [])
          .map(function (x) {
            return '<li>' + coName(x) + ' <span class="muted">· ' + pc100(x.rs6) + ' sur 6 mois</span></li>';
          })
          .join('') +
        '</ul></details></section></details>';
    });
  var hTh = h;
  h = '';
  // secteurs
  var trend = G.filter(function (g) {
      return g.trending;
    }),
    emer = G.filter(function (g) {
      return g.emerging && !g.trending;
    });

  var grpCard = function (g, full) {
    var mv = g.rank8w != null ? g.rank8w - g.rank : null;
    var head =
      '<span class="rk">' +
      g.rank +
      '</span> <b>' +
      esc(secName(g.key)) +
      '</b> ' +
      (g.trending ? '<span class="chip good">En tendance</span> ' : '') +
      (g.emerging ? '<span class="chip warn">Émergent</span> ' : '') +
      (mv
        ? '<span class="mv ' + (mv > 0 ? 'pos' : 'neg') + '">' + (mv > 0 ? '▲ ' : '▼ ') + Math.abs(mv) + '</span>'
        : '');
    var line =
      '<p class="small muted">' +
      g.n +
      ' sociétés</p><div class="mts">' +
      mini(
        'Force 6 mois',
        pc100(g.rs6),
        g.rs6,
        -0.3,
        0.3,
        true,
        'Hausse du secteur sur 6 mois par rapport au STOXX 600'
      ) +
      mini(
        'Force 3 mois',
        pc100(g.rs3),
        g.rs3,
        -0.3,
        0.3,
        true,
        'Hausse du secteur sur 3 mois par rapport au STOXX 600'
      ) +
      mini(
        'En tendance',
        Math.round(g.breadth * 100) + ' %',
        g.breadth,
        0,
        1,
        false,
        'Part des sociétés au-dessus de leur moyenne 40 semaines'
      ) +
      mini(
        'Près des sommets',
        Math.round(g.highs * 100) + ' %',
        g.highs,
        0,
        1,
        false,
        'Part des sociétés à moins de 5 % de leur plus haut annuel'
      ) +
      (g.revisions != null
        ? mini(
            'Analystes',
            (g.revisions >= 0 ? '+' : '') + Math.round(g.revisions * 100) + ' %',
            g.revisions,
            -1,
            1,
            true,
            'Révisions de prévisions nettes à la hausse sur 30 jours'
          )
        : '') +
      (g.surprise != null
        ? mini(
            'Résultats',
            (g.surprise >= 0 ? '+' : '') + Math.round(g.surprise * 100) + ' %',
            g.surprise,
            -1,
            1,
            true,
            'Surprises de résultats nettes : au-dessus moins en dessous du consensus'
          )
        : '') +
      (g.volume != null
        ? '<div class="mt"><span class="mt-l">Volumes</span><b class="mt-v ' +
          (g.volume > 0.15 ? 'pos' : g.volume < -0.15 ? 'neg' : '') +
          '">' +
          (g.volume > 0.15 ? '▲ achats' : g.volume < -0.15 ? '▼ ventes' : '= équilibrés') +
          '</b></div>'
        : '') +
      '</div>';
    if (!full)
      return (
        '<li class="grp">' +
        head +
        line +
        '<p class="small">🏆 ' +
        (g.leader ? coName(g.leader) : '—') +
        (g.challenger ? ' · 🚀 ' + coName(g.challenger) : '') +
        '</p></li>'
      );
    return (
      '<section class="card grpc">' +
      '<p class="grp-h">' +
      head +
      '</p>' +
      line +
      secStock(g.leader, 'leader') +
      secStock(g.challenger, 'challenger') +
      '<details class="fold" data-k="g-' +
      esc(g.key) +
      '"><summary>Les 5 plus fortes du secteur</summary><ul class="seclist">' +
      (g.top || [])
        .map(function (x) {
          return '<li>' + coName(x) + ' <span class="muted">· ' + pc100(x.rs6) + ' sur 6 mois</span></li>';
        })
        .join('') +
      '</ul></details></section>'
    );
  };
  // un pli par secteur : rang, nom, force 6 mois et progression en 8 semaines ; le détail s'ouvre au toucher
  var grpFold = function (g, ctx) {
    var mv = g.rank8w != null ? g.rank8w - g.rank : null;
    var k = 'gf' + ctx + '-' + g.key,
      open = !!(S.openDet && S.openDet[k]);
    var body = open
      ? grpCard(g, true)
          .replace(/<p class="grp-h">[\s\S]*?<\/p>/, '')
          .replace('data-k="g-', 'data-k="g' + ctx + '-')
      : '';
    return (
      '<details class="fold grpf' +
      (open ? '' : ' lazy') +
      '" data-k="' +
      esc(k) +
      '"><summary><span class="rk">' +
      g.rank +
      '</span> ' +
      esc(secName(g.key)) +
      ' <span class="muted small">· <span class="nw">6\u00a0mois ' +
      String(pc100(g.rs6)).replace(/ /g, '\u00a0') +
      '</span>' +
      (mv ? ' · <span class="nw">' + (mv > 0 ? '▲\u00a0' : '▼\u00a0') + Math.abs(mv) + '</span>' : '') +
      (g.trending && ctx === 'a' ? ' · en tendance' : '') +
      '</span></summary>' +
      body +
      '</details>'
    );
  };
  h += trend.length
    ? trend
        .map(function (g) {
          return grpFold(g, 't');
        })
        .join('')
    : '<p class="muted">Aucun secteur ne remplit les trois conditions aujourd\'hui (parmi les 20 % meilleurs, plus fort que le marché sur 6 mois, la moitié des sociétés en hausse).</p>';
  var hTr = h;
  h = '';
  if (emer.length)
    h += emer
      .map(function (g) {
        return grpFold(g, 'e');
      })
      .join('');
  var hEm = h;
  h = '';
  h +=
    '<details class="card fold" data-k="sec-all"><summary>📋 Tous les secteurs <span class="muted small">· ' +
    G.length +
    '</span></summary>' +
    G.map(function (g) {
      return grpFold(g, 'a');
    }).join('') +
    '</details>';
  var hAll = h;
  h = '';
  // preuves
  var B = X.backtest;
  if (B && B.vsUniverse) {
    var row = function (lbl, v, vs) {
      if (!v || v.t == null) return '';
      var ok = v.t >= 2,
        bad = v.t <= -2;
      return (
        '<li><b>' +
        lbl +
        '</b> : ' +
        pct(v.meanPerPeriod * 100) +
        ' par période de 4 semaines ' +
        (vs || "face à l'ensemble des sociétés") +
        ' (t = ' +
        fmtN(v.t, 1) +
        ') → ' +
        (ok
          ? '<span class="pos">avantage mesuré</span>'
          : bad
            ? '<span class="neg">désavantage</span>'
            : "pas d'écart net") +
        '</li>'
      );
    };
    h +=
      '<div><p class="small muted">' +
      B.periods +
      ' périodes de 4 semaines, du ' +
      shortDate(B.from) +
      ' au ' +
      shortDate(B.to) +
      ", frais inclus. Comparaison avec l'ensemble des sociétés à poids égaux, qui a le même biais (univers d'aujourd'hui appliqué au passé).</p><ul>" +
      row('Les 3 meilleurs secteurs', B.vsUniverse.top) +
      row('Leurs leaders', B.vsUniverse.leaders) +
      row('Leurs challengers', B.vsUniverse.challengers) +
      row('Challenger plutôt que leader', B.challengerVsLeader, 'de plus que le leader') +
      '</ul>';
    var any = ['top', 'leaders', 'challengers'].some(function (k) {
      return B.vsUniverse[k] && B.vsUniverse[k].t >= 2;
    });
    h +=
      '<p class="small"><b>Conclusion :</b> ' +
      (any
        ? 'le classement a apporté un avantage mesurable sur la période.'
        : "acheter mécaniquement les secteurs en tête n'a pas fait mieux que l'ensemble des sociétés. Ce classement sert de radar pour repérer les thèmes et les sociétés à étudier, pas de règle d'achat automatique ; la décision se prend avec le plan d'entrée et les achats des dirigeants.") +
      '</p>';
    var ST = B.stress;
    if (ST && ST.grid) {
      var gr = ST.grid.slice().sort(function (a, b) {
          return (b.t || -9) - (a.t || -9);
        }),
        SIG = {
          composite: 'Composite',
          mom12: 'Momentum 12 m',
          high52: 'Plus haut 52 s.',
          emerging: 'Émergents',
          volume: 'Volumes',
          surprise: 'Surprises',
          'composite+conservation': 'Composite (rotation réduite)',
          'mom12+conservation': 'Momentum (rotation réduite)',
        };
      h +=
        '<details class="fold" data-k="stress"><summary>🧪 Stress test : ' +
        ST.trials +
        ' variantes essayées</summary><p class="small muted">Les 8 meilleures variantes (sur ' +
        ST.trials +
        ') ; écart par an face à l\'ensemble des sociétés, frais inclus.</p><table class="cmp st"><thead><tr><th>Signal</th><th>Grp</th><th>Sem.</th><th>Écart/an</th><th>t</th></tr></thead><tbody>' +
        gr
          .slice(0, 8)
          .map(function (g) {
            return (
              '<tr><th>' +
              esc(SIG[g.signal] || g.signal) +
              '</th><td>' +
              g.top +
              '</td><td>' +
              g.step +
              '</td><td class="' +
              (g.excessPerYear > 0 ? 'pos' : 'neg') +
              '">' +
              pc100(g.excessPerYear) +
              '</td><td>' +
              fmtN(g.t, 1) +
              '</td></tr>'
            );
          })
          .join('') +
        '</tbody></table>' +
        '<ul class="small"><li>Meilleure variante : probabilité qu\'elle soit réelle, compte tenu des ' +
        ST.trials +
        ' essais (Deflated Sharpe) : <b>' +
        Math.round(ST.deflatedSharpe * 100) +
        ' %</b> (95 % exigés).</li>' +
        (ST.placebo
          ? '<li>Avant frais, la note composite fait mieux que <b>' +
            Math.round(ST.placebo.pctBelow * 100) +
            " %</b> des sélections de secteurs tirées au hasard : le signal existe, mais la rotation mensuelle et ses frais en absorbent l'essentiel.</li>"
          : '') +
        (ST.doubleCost
          ? '<li>Frais doublés : ' + pct(ST.doubleCost.meanPerPeriod * 100) + " par période face à l'ensemble.</li>"
          : '') +
        (ST.crises || [])
          .map(function (c) {
            return (
              '<li>Krach du ' +
              shortDate(c.from) +
              ' au ' +
              shortDate(c.to) +
              ' : 3 meilleurs secteurs ' +
              pc100(c.top) +
              ', ensemble des sociétés ' +
              pc100(c.universeEW) +
              ', STOXX 600 ' +
              pc100(c.stoxx) +
              '.</li>'
            );
          })
          .join('') +
        '</ul></details>';
    }
    var TR = B.trends;
    if (TR && TR.themes)
      h +=
        '<details class="fold" data-k="trends"><summary>🔎 Recherches Google (test du ' +
        shortDate(TR.at) +
        ')</summary><ul class="small">' +
        TR.themes
          .map(function (r) {
            return (
              '<li><b>' +
              esc(r.keyword) +
              '</b> : ' +
              (r.corrNext != null
                ? 'hausse des recherches et chaîne européenne le mois suivant : corrélation ' +
                  fmtN(r.corrNext, 2) +
                  ' (même mois ' +
                  fmtN(r.corrSame, 2) +
                  ')'
                : 'données indisponibles (Google limite les accès automatiques)') +
              '</li>'
            );
          })
          .join('') +
        '</ul></details>';
    var A = B.aiCase;
    if (A && A.groups)
      h +=
        '<p class="small"><b>Cas de l\'IA</b> (ChatGPT le 30/11/2022) : ' +
        A.groups
          .filter(function (g) {
            return g.firstTrending;
          })
          .map(function (g) {
            return (
              esc(secName(g.group)) +
              ' détecté le ' +
              shortDate(g.firstTrending) +
              ' (' +
              g.weeksAfterChatGPT +
              ' semaine' +
              (g.weeksAfterChatGPT > 1 ? 's' : '') +
              ' après), puis leader ' +
              pc100(g.leader12m) +
              ' et challenger ' +
              pc100(g.challenger12m) +
              ' sur 12 mois contre ' +
              pc100(g.stoxx12m) +
              ' pour le STOXX 600'
            );
          })
          .join(' ; ') +
        '.</p>';
    h += '</div>';
  }
  var hBt = h;
  h = '';
  h +=
    '<p class="muted small pad">Méthode fixée à l\'avance, sans paramètre ajusté sur le passé : force relative sectorielle (Moskowitz et Grinblatt, 1999), avance des clients sur leurs fournisseurs (Cohen et Frazzini, 2008), révisions des analystes et surprises de résultats (Chan, Jegadeesh et Lakonishok, 1996). Révisions des analystes : historique constitué chaque semaine depuis le lancement, pas encore testable. Les tendances se détectent après leur démarrage, jamais avant. Ce n\'est pas un conseil en investissement.</p>';
  var hFoot = h,
    cy = S.cycle,
    cyn = cy ? (cy.second ? cy.label + ' ou ' + cy.second.toLowerCase() : cy.label) : null;
  var nGood = (X.themes || []).filter(function (t) {
      return themeVerdict(t)[0] === 'good';
    }).length,
    nSoon = (X.themes || []).filter(function (t) {
      return themeVerdict(t)[0] === 'warn';
    }).length;
  var names = function (A) {
    return A.slice(0, 3)
      .map(function (g) {
        return secName(g.key);
      })
      .join(', ');
  };
  var fold = function (k, title, sub, body) {
    return body
      ? '<details class="card fold" data-k="' +
          k +
          '"><summary>' +
          title +
          (sub ? ' <span class="muted small">· ' + sub + '</span>' : '') +
          '</summary>' +
          body +
          '</details>'
      : '';
  };
  var tl = function (cls, ic, t, sub, k) {
    return (
      '<button class="dtile ' +
      cls +
      '" data-a="secOpen" data-v="' +
      k +
      '"><span class="dti" aria-hidden="true">' +
      ic +
      '</span><b>' +
      t +
      '</b><small>' +
      esc(sub) +
      '</small></button>'
    );
  };
  var out =
    hTop +
    '<div class="dash">' +
    tl('t-good', '📈', trend.length + ' en tendance', trend.length ? names(trend) : "aucun aujourd'hui", 'sec-trend') +
    tl(
      emer.length ? 't-warn' : '',
      '🌱',
      emer.length + ' émergent' + (emer.length > 1 ? 's' : ''),
      emer.length ? names(emer) : 'forte remontée en 8 sem.',
      'sec-emer'
    ) +
    tl(
      't-val',
      '🔄',
      cyn ? cy.label : 'Cycle',
      cyn ? 'phase du cycle' + (cy.second ? ' (incertaine)' : '') : 'non calculé',
      'sec-cyc'
    ) +
    '</div>' +
    fold('sec-trend', '📈 Secteurs en tendance', String(trend.length), hTr) +
    fold('sec-emer', '🌱 Secteurs émergents', String(emer.length), emer.length ? hEm : '') +
    fold('sec-cyc', '🔄 Cycle économique', '', hCyc) +
    fold(
      'sec-th',
      '🧭 Thèmes',
      (X.themes || []).length +
        ' suivis' +
        (nGood ? ' · 🟢 ' + nGood + ' porteur' + (nGood > 1 ? 's' : '') : '') +
        (nSoon ? ' · 🔭 ' + nSoon : ''),
      hTh
    ) +
    hAll +
    fold('sec-bt', '📏 Le test historique et la méthode', '', hBt + hFoot) +
    hHelp;
  return out;
}
function vInities() {
  var f = S.txFilter,
    from = ES.windowStart(S.today, S.cfg.insiders.windowMonths),
    rows = [],
    fq = ES.norm(f.q || '');
  Object.keys(S.tx).forEach(function (isin) {
    (S.tx[isin] || []).forEach(function (t) {
      if (ES.availDate(t) < from) return;
      if (f.registry && t.registry !== f.registry) return;
      var inst = S.inst[isin] || {};
      if (f.country && inst.country !== f.country) return;
      if (fq && ES.norm([inst.name, isin, inst.ticker, t.person, t.issuer].join(' ')).indexOf(fq) < 0) return;
      rows.push({ t: t, inst: inst, isin: isin });
    });
  });
  rows.sort(function (a, b) {
    return ES.availDate(a.t) < ES.availDate(b.t) ? 1 : -1;
  });
  // plusieurs déclarations du même dirigeant, même jour, même nature (achats fractionnés) : une seule ligne, montants additionnés
  var grouped = [],
    gix = {};
  rows.forEach(function (r) {
    var t = r.t,
      k = [r.isin, t.personKey || t.person, t.type, t.pubDate || t.txDate, t.currency, t.status].join('|');
    if (gix[k] != null) {
      var g = grouped[gix[k]];
      g.n++;
      if (t.amount > 0) g.amount = (g.amount || 0) + t.amount;
      return;
    }
    gix[k] = grouped.length;
    grouped.push({ t: t, inst: r.inst, isin: r.isin, n: 1, amount: t.amount > 0 ? t.amount : null });
  });
  rows = grouped;
  var regs = {};
  Object.keys(S.tx).forEach(function (i) {
    S.tx[i].forEach(function (t) {
      regs[t.registry] = 1;
    });
  });
  var clusterIsins = Object.keys(S.computed).filter(function (i) {
    return S.computed[i].score.families.insiders.items.some(function (it) {
      return /^cluster/.test(it.label);
    });
  });
  var buys = rows.filter(function (r) {
      return r.t.type === 'achat';
    }),
    sells = rows.filter(function (r) {
      return r.t.type === 'vente';
    }),
    others = rows.filter(function (r) {
      return r.t.type !== 'achat' && r.t.type !== 'vente';
    });
  var nCo = function (L) {
    var o = {};
    L.forEach(function (r) {
      o[r.isin] = 1;
    });
    return Object.keys(o).length;
  };
  var h =
    '<h2 class="vt">Achats et ventes des dirigeants</h2><p class="muted small">Déclarations publiées depuis le ' +
    shortDate(from) +
    ' · touchez une ligne pour la fiche</p>';
  var tl = function (cls, ic, t, sub, k) {
    return (
      '<button class="dtile ' +
      cls +
      '" data-a="secOpen" data-v="' +
      k +
      '"><span class="dti" aria-hidden="true">' +
      ic +
      '</span><b>' +
      t +
      '</b><small>' +
      sub +
      '</small></button>'
    );
  };
  h +=
    '<div class="dash dash2">' +
    tl(
      't-good',
      '🟢',
      buys.length + ' achat' + (buys.length > 1 ? 's' : ''),
      nCo(buys) +
        ' société' +
        (nCo(buys) > 1 ? 's' : '') +
        (clusterIsins.length
          ? ' · 👥 ' +
            clusterIsins.length +
            ' achat' +
            (clusterIsins.length > 1 ? 's' : '') +
            ' groupé' +
            (clusterIsins.length > 1 ? 's' : '')
          : ''),
      'ins-buy'
    ) +
    tl(
      't-bad',
      '🔴',
      sells.length + ' vente' + (sells.length > 1 ? 's' : ''),
      nCo(sells) + ' société' + (nCo(sells) > 1 ? 's' : ''),
      'ins-sell'
    ) +
    '</div>';
  h +=
    '<div class="toolbar"><input id="t-q" type="search" placeholder="Société ou dirigeant" value="' +
    esc(f.q || '') +
    '" data-tf="q" aria-label="Rechercher une société ou un dirigeant">' +
    '<select id="t-c" data-tf="country" aria-label="Pays"><option value="">Tous pays</option>' +
    Object.keys(COUNTRIES)
      .map(function (c) {
        return '<option value="' + c + '"' + (f.country === c ? ' selected' : '') + '>' + COUNTRIES[c] + '</option>';
      })
      .join('') +
    '</select>' +
    '<select id="t-reg" data-tf="registry" aria-label="Registre"><option value="">Tous registres</option>' +
    Object.keys(regs)
      .sort()
      .map(function (r) {
        return '<option' + (f.registry === r ? ' selected' : '') + '>' + esc(r) + '</option>';
      })
      .join('') +
    '</select></div>';
  var lim = Math.min(S.limit, 400),
    opened = fq || f.country || f.registry ? ' open' : '';
  var table = function (L, kind) {
    if (!L.length) return '<p class="muted small">Aucune opération ne correspond.</p>';
    var isBuy = kind === 'buy',
      h2 =
        '<div class="tablewrap"><table class="grid cards ops"><thead><tr><th>Société</th><th>Publié</th><th>Dirigeant</th>' +
        (kind === 'other' ? '<th>Nature</th>' : '') +
        '<th class="num">Montant</th>' +
        (isBuy ? '<th class="num" title="Prix payé par rapport au plus haut des 52 semaines">Décote</th>' : '') +
        '<th class="num">' +
        (kind === 'sell' ? 'Depuis la vente' : "Depuis l'achat") +
        '</th></tr></thead><tbody>';
    L.slice(0, lim).forEach(function (r) {
      var t = r.t,
        ref = (S.refs[r.isin] || {})[t.id],
        key =
          (t.type === 'achat' || t.type === 'vente') &&
          S.snapshot &&
          S.snapshot.history &&
          (ES.buyerKey(t) || t.personKey);
      var ok = ref && ref.available && !ref.outOfRange;
      h2 +=
        '<tr class="rowlink" data-a="open" data-i="' +
        r.isin +
        '" tabindex="0"><td class="c-name" data-l="Société"><b>' +
        flag(r.inst.country) +
        esc(r.inst.name || r.isin) +
        '</b></td>' +
        '<td data-l="Publié">' +
        (t.pubDate ? shortDate(t.pubDate) : '<span class="muted">tx ' + shortDate(t.txDate) + '</span>') +
        '</td>' +
        '<td data-l="Dirigeant">' +
        esc(t.person || 'n.d.') +
        (key
          ? ' <button class="link small" data-a="person" data-k="' +
            esc(key) +
            '" title="Tout l\'historique de ce dirigeant">historique →</button>'
          : '') +
        '<small>' +
        esc(frRole(t.role)) +
        ((t.ceo || t.cfo) && !ES.isLegalEntity(t.person, t.issuer) ? ' · DG/DAF' : '') +
        '</small></td>' +
        (kind === 'other'
          ? '<td data-l="Nature">' +
            ES.TX_TYPES[t.type] +
            (t.status === 'annulee' ? ' <span class="chip bad">annulée</span>' : '') +
            '</td>'
          : '') +
        '<td class="num" data-l="Montant">' +
        fmtMoney(r.n > 1 ? r.amount : t.amount, t.currency) +
        (r.n > 1 ? '<small>' + r.n + ' déclarations le même jour</small>' : '') +
        (kind !== 'other' && t.status === 'annulee' ? ' <span class="chip bad">annulée</span>' : '') +
        '</td>' +
        (isBuy
          ? '<td class="num" data-l="Sous le plus haut">' +
            (ok && ref.atPurchase && ref.atPurchase.paidVsHigh52Pct != null
              ? discPill({ pct: -ref.atPurchase.paidVsHigh52Pct })
              : '<span class="muted">—</span>') +
            '</td>'
          : '') +
        '<td class="num" data-l="' +
        (kind === 'sell' ? 'Depuis la vente' : "Depuis l'achat") +
        '">' +
        (ok
          ? '<span class="' + (ref.currentVsPaidPct >= 0 ? 'pos' : 'neg') + '">' + pct(ref.currentVsPaidPct) + '</span>'
          : '<span class="muted">—</span>') +
        '</td></tr>';
    });
    h2 += '</tbody></table></div>';
    if (L.length > lim && lim < 400)
      h2 +=
        '<p class="pad"><button class="ghost" data-a="more">Afficher ' +
        Math.min(100, Math.min(L.length, 400) - lim) +
        ' de plus (' +
        L.length +
        ' au total)</button></p>';
    else if (L.length > 400)
      h2 += '<p class="muted pad">400 lignes affichées sur ' + L.length + ' : affinez avec la recherche.</p>';
    return h2;
  };
  var fold = function (k, title, n, body) {
    return (
      '<details class="card fold" data-k="' +
      k +
      '"' +
      opened +
      '><summary>' +
      title +
      ' <span class="muted small">· ' +
      n +
      '</span></summary>' +
      body +
      '</details>'
    );
  };
  h +=
    fold('ins-buy', '🟢 Achats', buys.length, table(buys, 'buy')) +
    fold('ins-sell', '🔴 Ventes', sells.length, table(sells, 'sell')) +
    (others.length
      ? fold(
          'ins-other',
          '⚪ Autres opérations',
          others.length + ' · attributions, options, transferts',
          '<p class="muted small">Opérations non volontaires ou ambiguës : peu informatives sur l\'avis du dirigeant.</p>' +
            table(others, 'other')
        )
      : '');
  return h;
}
