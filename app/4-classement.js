/* Euro Signal — interface : classement tendance + comptes : tuiles, sélection, 🎯, 💎, analyse.
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
/* ----- Classement tendance + comptes (barème 3.0) ----- */
var RV = {
  top: ['🟢', 'En tête', 'good'],
  good: ['🟡', 'Solide', 'warn'],
  mid: ['⚪', 'Sans plus', 'neutral'],
  out: ['⛔', 'Écartée', 'bad'],
};
function rankData() {
  return S.snapshot && S.snapshot.rank && Array.isArray(S.snapshot.rank.rows) ? S.snapshot.rank : null;
}
function rankOf(isin, sym) {
  var R = rankData();
  if (!R) return null;
  if (!S.rankBy) {
    S.rankBy = {};
    R.rows.forEach(function (r) {
      if (r.isin) S.rankBy[r.isin] = r;
      if (r.sym) S.rankBy['@' + r.sym] = r;
    });
  }
  return (isin && S.rankBy[isin]) || (sym && S.rankBy['@' + sym]) || null;
}
function rankW() {
  return (S.cfg.rank && S.cfg.rank.w) || ES.DEFAULT_CONFIG.rank.w;
}
/** Les 4 familles de la note, lisibles telles quelles : tendance, comptes, calme du cours, dirigeants. */
function rankFam(r) {
  var w = rankW(),
    p = r.parts || {};
  return [
    {
      k: 'tr',
      icon: '📈',
      label: 'Tendance',
      v: (p.mom || 0) + (p.high || 0) + (p.trend || 0),
      max: w.mom + w.high + w.trend,
      tip:
        'force sur 12 mois ' +
        (p.mom || 0) +
        '/' +
        w.mom +
        ', proximité du plus haut ' +
        (p.high || 0) +
        '/' +
        w.high +
        ', moyennes 50/200 séances ' +
        (p.trend || 0) +
        '/' +
        w.trend,
    },
    {
      k: 'acc',
      icon: '📊',
      label: 'Comptes',
      v: p.accounts || 0,
      max: w.accounts,
      tip:
        r.acc === 'good'
          ? 'comptes solides'
          : r.acc === 'mixed'
            ? 'comptes mitigés'
            : r.acc === 'fin'
              ? 'banque ou assurance'
              : 'comptes pas encore lus',
    },
    {
      k: 'calm',
      icon: '🌊',
      label: 'Calme',
      v: p.calm || 0,
      max: w.calm,
      tip: 'calme du cours (volatilité sur 6 mois)',
    },
    {
      k: 'ins',
      icon: '👔',
      label: 'Dirigeants',
      v: p.insiders || 0,
      max: w.insiders,
      tip: p.insiders > 0 ? 'achats de dirigeants' : p.insiders < 0 ? 'les dirigeants vendent' : 'aucun achat récent',
      signed: true,
    },
  ].filter(function (f) {
    return f.max > 0;
  });
}
function famTone(f) {
  return f.signed
    ? f.v > 0
      ? 'good'
      : f.v < 0
        ? 'bad'
        : 'na'
    : f.v >= 0.75 * f.max
      ? 'good'
      : f.v >= 0.4 * f.max
        ? 'mid'
        : 'bad';
}
/** Jauges nommées (fiche et guide) : une barre par famille, avec son score. */
function rankGauges(r) {
  return (
    '<div class="rgauges">' +
    rankFam(r)
      .map(function (f) {
        var pctW = f.signed
          ? Math.min(100, (Math.abs(f.v) / Math.max(1, f.signed && f.v < 0 ? 15 : f.max)) * 100)
          : (Math.max(0, f.v) / f.max) * 100;
        return (
          '<div class="rg t-' +
          famTone(f) +
          '" title="' +
          esc(f.tip) +
          '"><span class="rg-l">' +
          f.icon +
          ' ' +
          f.label +
          '</span><span class="rg-t"><i style="width:' +
          pctW.toFixed(0) +
          '%"></i></span><b class="rg-v">' +
          (f.signed ? (f.v > 0 ? '+' : '') + f.v : f.v) +
          '<small>/' +
          (f.signed ? (f.v < 0 ? '−15' : f.max) : f.max) +
          '</small></b></div>'
        );
      })
      .join('') +
    '</div>'
  );
}
function rankChip(r) {
  var v = RV[r.v] || RV.mid;
  return '<span class="chip ' + v[2] + '">' + v[0] + ' ' + v[1] + '</span>';
}
function rankOpenAttr(r) {
  return r.isin && S.inst[r.isin]
    ? 'data-a="open" data-i="' + esc(r.isin) + '"'
    : r.sym
      ? 'data-a="secCo" data-v="' + esc(r.sym) + '"'
      : '';
}
function cap1r(t) {
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : '';
}
/** Carte de la note sur une fiche (Euro Signal ou catalogue). */
/* 🔬 Analyse express : synthèse automatique d'une société, sur le modèle d'une note d'analyste réduite à l'essentiel
   (3 points, régime, chiffres clés, technique, consensus, scénarios, score de conviction, incertitude, avis). Calculée à
   l'ouverture avec les données du soir : rien d'inventé, chaque ligne vient d'un chiffre affiché ailleurs dans l'outil. */
function anRsi(c, n) {
  if (c.length < n + 1) return null;
  var g = 0,
    l = 0;
  for (var k = c.length - n; k < c.length; k++) {
    var d = c[k] - c[k - 1];
    if (d > 0) g += d;
    else l -= d;
  }
  return l === 0 ? 100 : Math.round(100 - 100 / (1 + g / l));
}
function anEma(c, n) {
  var k = 2 / (n + 1),
    e = c[0],
    out = [e];
  for (var j = 1; j < c.length; j++) {
    e = c[j] * k + e * (1 - k);
    out.push(e);
  }
  return out;
}
function anMacd(c) {
  if (c.length < 60) return null;
  var a = anEma(c, 12),
    b = anEma(c, 26),
    m = a.map(function (v, j) {
      return v - b[j];
    }),
    s = anEma(m, 9);
  return { up: m[m.length - 1] > s[s.length - 1], pos: m[m.length - 1] > 0 };
}
function anCtx(isin, sym) {
  var r = rankOf(isin, sym),
    x = isin ? S.inst[isin] : null,
    co = sym && S.secCo && S.secCo.items ? S.secCo.items[sym] : null;
  var o = {
    r: r || {},
    isin: isin || null,
    sym: sym || null,
    name: (x && x.name) || (co && co.name) || (r && r.name) || isin || sym,
    closes: [],
  };
  if (x) {
    var p = S.prices[isin];
    if (p && p.rows)
      o.closes = ES.normalizeSeries(p.rows)
        .map(function (q) {
          return q[4];
        })
        .filter(function (v) {
          return v > 0;
        })
        .slice(-260);
    var st = x.stats || {},
      f = x.fund || {},
      fc = x.forecast || {},
      ac = x.accounts || {};
    o.cur = st.currency || x.currency;
    o.last = st.lastClose;
    o.vol = st.volAnnPct;
    o.rsi = st.rsi14;
    o.hi = st.ex52 && st.ex52.high;
    o.lo = st.ex52 && st.ex52.low;
    o.cap = f.marketCap;
    o.capCur = f.currency;
    o.cashNet = f.totalCash != null && f.totalDebt != null ? f.totalCash - f.totalDebt : null;
    o.margin = f.profitMargins;
    o.roe = f.returnOnEquity;
    o.pe = f.forwardPE > 0 ? f.forwardPE : f.trailingPE > 0 ? f.trailingPE : null;
    o.evE = f.evToEbitda > 0 ? f.evToEbitda : null;
    o.pb = f.priceToBook;
    if (fc.target && fc.target.mean > 0) o.tgt = fc.target;
    var tr = fc.trend && fc.trend['+1y'];
    if (tr && tr.cur != null && tr.d30 != null && tr.d30 !== 0) o.rev = (tr.cur / tr.d30 - 1) * 100;
    if (fc.rev && fc.rev['+1y'] && fc.rev['+1y'].growth != null) o.growth = fc.rev['+1y'].growth * 100;
    if (x.value && !x.value.na && x.value.mid > 0) o.val = x.value;
    if (x.peer && x.peer.discountPct != null) o.peer = x.peer;
    o.acc = ac.plain || (ac.verdict ? { tone: ac.verdict.key, label: ac.verdict.text } : null);
    o.f9 = ac.fscore && !ac.fscore.na ? ac.fscore.f9 : null;
    o.nextE = x.nextEarnings;
    o.plan = x.plan;
    o.years = ac.years && ac.years.length ? ac.years.slice(-4) : null;
    o.accCur = ac.currency;
    o.rev1 = fc.rev && fc.rev['+1y'] && fc.rev['+1y'].avg ? fc.rev['+1y'] : null;
    o.ev = S.ev[isin] || null;
    o.shares = x.sharesChange && !x.sharesChange.corporate ? x.sharesChange : null;
    o.pea =
      x.peaStatus === 'non_eligible'
        ? false
        : x.peaStatus === 'eligible' || x.peaStatus === 'probable'
          ? true
          : r && r.pea != null
            ? r.pea
            : null;
  } else if (co) {
    o.closes = (co.d || [])
      .filter(function (v) {
        return v > 0;
      })
      .slice(-260);
    o.cur = co.currency;
    o.last = o.closes.length ? o.closes[o.closes.length - 1] : null;
    o.pea = co.pea != null ? co.pea : null;
    o.cap = co.capEur;
    o.capCur = 'EUR';
    o.margin = co.opMargin;
    o.roe = co.roe;
    o.pe = co.fwdPE > 0 ? co.fwdPE : null;
    o.pb = co.pb;
    o.growth = co.revGrowth != null ? co.revGrowth * 100 : null;
    if (co.upside != null && o.last) o.tgt = { mean: o.last * (1 + co.upside), n: co.analysts || null };
    if (co.revUp30 != null && co.revDown30 != null && co.revUp30 + co.revDown30 > 0)
      o.rev = co.revUp30 > co.revDown30 ? 1 : co.revUp30 < co.revDown30 ? -1 : 0;
    o.surprise = co.lastSurprise ? co.lastSurprise[1] : null;
    o.reco = co.reco;
    var pw = r && r.pw;
    if (pw && pw.p)
      o.plan = {
        primary: {
          level: pw.p.level,
          zoneLo: pw.p.zoneLo,
          zoneHi: pw.p.zoneHi,
          stop: pw.p.stop,
          trigger: pw.p.trigger,
        },
        label: pw.label,
      };
  }
  var c = o.closes;
  if (c.length >= 60) {
    if (o.rsi == null) o.rsi = anRsi(c, 14);
    o.macd = anMacd(c);
    if (!o.hi) {
      o.hi = Math.max.apply(null, c.slice(-252));
      o.lo = Math.min.apply(null, c.slice(-252));
    }
    if (o.vol == null) {
      var rr = [];
      for (var k = Math.max(1, c.length - 250); k < c.length; k++) rr.push(Math.log(c[k] / c[k - 1]));
      var m =
        rr.reduce(function (a, b) {
          return a + b;
        }, 0) / rr.length;
      o.vol =
        Math.sqrt(
          (rr.reduce(function (a, b) {
            return a + (b - m) * (b - m);
          }, 0) /
            rr.length) *
            252
        ) * 100;
    }
  }
  if (r && r.m10 == null && c.length >= 50) {
    var s50 =
      c.slice(-50).reduce(function (a, b) {
        return a + b;
      }, 0) / 50;
    o.m10 = Math.round((c[c.length - 1] / s50 - 1) * 1000) / 10;
  } else o.m10 = r ? r.m10 : null;
  if (o.acc == null && r && r.acc)
    o.acc = {
      tone: r.acc === 'good' ? 'good' : r.acc === 'bad' ? 'bad' : 'mixed',
      label: r.acc === 'good' ? 'comptes solides' : r.acc === 'bad' ? 'comptes en dégradation' : 'comptes mitigés',
    };
  if (o.f9 == null && r && r.f9 != null) o.f9 = r.f9;
  var pk = pickSet();
  o.inPick = !!(r && pk[r.key]);
  var R = rankData();
  o.inVal = !!(
    R &&
    r &&
    ES.pickValue(R.rows || [], { n: 10 }).picks.some(function (v) {
      return v.key === r.key;
    })
  );
  var N = R && R.breadth && R.breadth.now;
  o.crash = R && R.crashOn != null ? !!R.crashOn : !!(N && N.m52 != null && N.m52 <= ES.MOM_CRASH_M52);
  return o;
}
function loadNews() {
  S.newsLoaded = true;
  fetch('data/news.json', { cache: 'no-store' })
    .then(function (r) {
      return r.ok ? r.json() : null;
    })
    .catch(function () {
      return null;
    })
    .then(function (j) {
      S.news = j || { items: {} };
      if (S.view === 'fiche' || S.view === 'secco') render();
    });
}
/** Bloc 📰 Qualitatif : titres des 30 derniers jours citant la société, classés ⚠️ / ✅ par mots-clés ; lien vers toute l'actualité. */
function newsOf(o) {
  if (!S.newsLoaded) loadNews();
  var it = (S.news && S.news.items) || {},
    k = o.r && o.r.key;
  return (k && it[k]) || (o.r && o.r.sym && it[o.r.sym]) || [];
}
function newsBlock(o, list) {
  var q = encodeURIComponent(
    '"' +
      String(o.name)
        .replace(/\b(S\.?A\.?|SE|AG|ASA|N\.?V\.?|plc|S\.p\.A\.|AB|\(publ\)|Oyj)\b\.?/gi, '')
        .replace(/[,]/g, '')
        .trim() +
      '"'
  );
  var link =
    '<a href="https://news.google.com/search?q=' +
    q +
    '&hl=fr&gl=FR&ceid=FR:fr" target="_blank" rel="noopener">🔎 Toute l\'actualité</a>';
  if (!S.news) return '<h4>📰 Qualitatif</h4><p class="small muted">Chargement… · ' + link + '</p>';
  if (!list.length) return '<p class="small muted">📰 Pas d\'article relevé · ' + link + '</p>';
  return (
    '<h4>📰 Qualitatif <span class="muted small">· 30 jours</span></h4><ul class="annews">' +
    list
      .slice(0, 5)
      .map(function (n) {
        return (
          '<li class="' +
          (n.k || 'n') +
          '"><span>' +
          (n.k === 'neg' ? '⚠️' : n.k === 'pos' ? '✅' : '•') +
          '</span><div><a href="' +
          esc(ES.safeUrl ? ES.safeUrl(n.u) || '#' : n.u) +
          '" target="_blank" rel="noopener">' +
          esc(n.t) +
          '</a><small>' +
          esc([shortDate(n.d), n.s].filter(Boolean).join(' · ')) +
          '</small></div></li>'
        );
      })
      .join('') +
    '</ul><p class="small">' +
    link +
    ' <span class="muted">· ⚠️ / ✅ : repérés par mots-clés dans le titre, à lire avant de décider.</span></p>'
  );
}
/** Trajectoire (4 exercices), gestion du capital (dividendes, rachats, nombre d'actions, dette) et agenda : sociétés suivies par Euro Signal. */
function anExtra(o) {
  var p = anExtraParts(o);
  return p.traj + p.cap + p.agenda;
}
function anExtraParts(o) {
  var h = '',
    parts = {},
    big = function (v) {
      return v == null ? '—' : Math.abs(v) >= 1e9 ? fmtN(v / 1e9, 1) + ' Md' : fmtN(v / 1e6, 0) + ' M';
    };
  if (o.years) {
    var Y = o.years;
    h +=
      '<h4>Trajectoire <span class="muted small">· ' +
      esc(o.accCur || '') +
      '</span></h4><div class="tablewrap"><table class="kv antraj"><tr><th></th>' +
      Y.map(function (y) {
        return '<th>' + esc(y.year) + '</th>';
      }).join('') +
      (o.rev1 ? '<th>' + (+Y[Y.length - 1].year + 1) + ' (prév.)</th>' : '') +
      '</tr>' +
      "<tr><th>Chiffre d'affaires</th>" +
      Y.map(function (y) {
        return '<td>' + big(y.revenue) + '</td>';
      }).join('') +
      (o.rev1 ? '<td>' + big(o.rev1.avg) + '</td>' : '') +
      '</tr>' +
      '<tr><th>Marge opé.</th>' +
      Y.map(function (y) {
        return '<td>' + (y.opMargin != null ? fmtN(y.opMargin, 1) + ' %' : '—') + '</td>';
      }).join('') +
      (o.rev1 ? '<td></td>' : '') +
      '</tr>' +
      '<tr><th>Résultat net</th>' +
      Y.map(function (y) {
        return '<td class="' + (y.netIncome < 0 ? 'neg' : '') + '">' + big(y.netIncome) + '</td>';
      }).join('') +
      (o.rev1 ? '<td></td>' : '') +
      '</tr></table></div>';
    var f0 = Y[0],
      f1 = Y[Y.length - 1];
    if (f0.revenue > 0 && f1.revenue > 0 && Y.length >= 3)
      h +=
        '<p class="small muted">' +
        esc(
          "Chiffre d'affaires " +
            pct((Math.pow(f1.revenue / f0.revenue, 1 / (Y.length - 1)) - 1) * 100) +
            ' par an sur ' +
            (Y.length - 1) +
            ' ans' +
            (f0.opMargin != null && f1.opMargin != null
              ? ', marge opérationnelle ' +
                (f1.opMargin >= f0.opMargin ? 'en hausse' : 'en baisse') +
                ' (' +
                fmtN(f0.opMargin, 1) +
                ' → ' +
                fmtN(f1.opMargin, 1) +
                ' %)'
              : '') +
            (o.rev1 && o.rev1.growth != null ? ' ; prévision ' + pct(o.rev1.growth * 100) + " l'an prochain" : '') +
            '.'
        ) +
        '</p>';
  }
  parts.traj = h;
  h = '';
  var ev = o.ev,
    items = [],
    since = ES.addDays(S.today, -365);
  if (ev || o.shares || o.years) {
    var divs = ((ev && ev.splits) || []).filter(function (d) {
        return d.dividend && d.amount > 0 && d.date >= since;
      }),
      dsum = divs.reduce(function (a, d) {
        return a + d.amount;
      }, 0),
      dy = dsum && o.last ? (dsum / o.last) * 100 : null;
    var bb = ((ev && ev.buybacks) || []).slice().sort(function (a, b) {
        return a.date < b.date ? 1 : -1;
      })[0],
      bbRecent = bb && bb.date >= since && bb.stage !== 'suspension';
    var nd = o.years ? o.years[o.years.length - 1].netDebtEbitda : null,
      ncash = o.years ? o.years[o.years.length - 1].netCash : null;
    if (dy) items.push('💶 Dividendes détachés sur 12 mois : ' + fmtN(dsum, 2) + ' (rendement ' + fmtN(dy, 1) + ' %)');
    if (bb)
      items.push(
        "🔁 Rachat d'actions : " +
          (STAGES[bb.stage] || bb.stage) +
          ' le ' +
          shortDate(bb.date) +
          (bb.pctCapital != null ? ' (' + fmtN(bb.pctCapital, 1) + ' % du capital)' : '')
      );
    if (o.shares && o.shares.pct != null)
      items.push(
        (o.shares.pct <= -1
          ? "📉 Nombre d'actions en baisse "
          : o.shares.pct >= 2
            ? "📈 Dilution : nombre d'actions en hausse "
            : "➖ Nombre d'actions stable ") +
          '(' +
          pct(o.shares.pct) +
          ' depuis le ' +
          shortDate(o.shares.from) +
          ')'
      );
    if (ncash) items.push('🏦 Plus de trésorerie que de dettes');
    else if (nd != null)
      items.push('🏦 Dette nette / EBITDA : ' + fmtN(nd, 1) + (nd > 3 ? ' (élevée)' : nd < 1.5 ? ' (faible)' : ''));
    if (items.length) {
      var good = (dy >= 2 || bbRecent || (o.shares && o.shares.pct <= -1.5)) && (ncash || (nd != null && nd < 2)),
        bad = (o.shares && o.shares.pct >= 3) || (nd != null && nd > 3.5);
      var lvl = bad ? ['🔴', 'faible'] : good ? ['🟢', 'exemplaire'] : ['🟡', 'standard'];
      h +=
        '<h4>Gestion du capital · ' +
        lvl[0] +
        ' ' +
        lvl[1] +
        '</h4><ul class="plain small anlist">' +
        items
          .map(function (t) {
            return '<li>' + esc(t) + '</li>';
          })
          .join('') +
        '</ul>';
    }
  }
  parts.cap = h;
  h = '';
  var ag = [];
  if (o.nextE && o.nextE >= S.today) ag.push([o.nextE, '📅 Prochains résultats']);
  // chronologie de l'année : achats et ventes des dirigeants, bond sur gros volume, actualité marquante
  var txs = (o.isin && S.tx[o.isin]) || [],
    byDay = {};
  txs.forEach(function (t) {
    var d = t.pubDate || t.txDate;
    if (!d || d < since || (t.type !== 'achat' && t.type !== 'vente') || t.status === 'annulee') return;
    var k = d + t.type;
    if (!byDay[k]) byDay[k] = { d: d, type: t.type, n: 0, eur: 0 };
    byDay[k].n++;
    byDay[k].eur += ES.toEur ? ES.toEur(t.amount || 0, t.currency) || 0 : 0;
  });
  Object.keys(byDay)
    .map(function (k) {
      return byDay[k];
    })
    .sort(function (a, b) {
      return a.d < b.d ? 1 : -1;
    })
    .slice(0, 4)
    .forEach(function (z) {
      ag.push([
        z.d,
        (z.type === 'achat' ? '👔 Achat' : '👔 Vente') +
          ' de dirigeant' +
          (z.n > 1 ? 's (' + z.n + ')' : '') +
          (z.eur >= 1e4 ? ' · ' + fmtN(z.eur / 1e3, 0) + ' k€' : ''),
      ]);
    });
  var bw = bumpOf(o.r);
  if (bw != null) ag.push([ES.addDays(S.today, -7 * bw), '📣 Bond sur gros volume']);
  var lr =
    ev &&
    (ev.results || []).slice().sort(function (a, b) {
      return a.pubDate < b.pubDate ? 1 : -1;
    })[0];
  if (lr)
    ag.push([
      lr.pubDate,
      '📊 Derniers résultats' +
        (lr.epsActual != null && lr.epsConsensus
          ? ' : bénéfice par action ' +
            (lr.epsActual >= lr.epsConsensus ? 'au-dessus' : 'en dessous') +
            ' du consensus (' +
            pct((lr.epsActual / lr.epsConsensus - 1) * 100) +
            ')'
          : ''),
    ]);
  var ld =
    ev &&
    (ev.splits || [])
      .filter(function (d) {
        return d.dividend;
      })
      .sort(function (a, b) {
        return a.date < b.date ? 1 : -1;
      })[0];
  if (ld) ag.push([ld.date, '💶 Dernier dividende détaché (' + fmtN(ld.amount, 2) + ')']);
  if (ag.length)
    h +=
      '<ul class="plain small anlist">' +
      ag
        .sort(function (a, b) {
          return a[0] < b[0] ? 1 : -1;
        })
        .map(function (z) {
          return '<li><b>' + shortDate(z[0]) + '</b> · ' + esc(z[1]) + '</li>';
        })
        .join('') +
      '</ul>';
  parts.agenda = h;
  return parts;
}
function bumpOf(r) {
  var b = r ? (r.bp != null ? r.bp : r.bump) : null;
  return b == null ? null : b;
}
function bumpTxt(b) {
  return b ? 'il y a ' + b + ' sem.' : 'cette semaine';
}
/** Supports et résistances de l'analyse : les mêmes que le graphique (calcul du soir, sinon recalculés, toujours complétés). */
function anLevels(o) {
  var x = o.isin && S.inst[o.isin],
    p = o.isin && S.prices[o.isin],
    co = !(p && p.rows && p.rows.length) && o.sym && S.secCo && S.secCo.items ? S.secCo.items[o.sym] : null,
    D = (S.secCo && S.secCo.dDates) || [],
    rows =
      p && p.rows && p.rows.length
        ? ES.normalizeSeries(p.rows).slice(-260)
        : co && co.d
          ? co.d
              .map(function (v, k) {
                return [D[k], null, null, null, v];
              })
              .filter(function (q) {
                return q[0] && q[4] > 0;
              })
              .slice(-260)
          : [];
  if (!rows || rows.length < 10) return null;
  return ES.completeLevels((x && x.levels) || ES.supportResistance(rows), rows);
}
function analysisCard(isin, sym) {
  var o = anCtx(isin, sym),
    r = o.r,
    cl = function (v) {
      return Math.max(0, Math.min(10, v));
    };
  if (!o.last) return '';
  var up = o.tgt ? (o.tgt.mean / o.last - 1) * 100 : null,
    vm = o.val ? o.val.marginPct : null;
  var pros = [],
    cons = [],
    add = function (L, w, t) {
      L.push([w, t]);
    };
  // 1. score de conviction : cinq critères, pondérés
  var T = 5;
  if (r.trend === 'up') T += 2;
  else if (r.trend === 'down') T -= 2;
  if (r.sc === 'strong') T += 1.5;
  else if (r.sc === 'mid') T += 0.75;
  if (o.m10 != null) T += o.m10 >= 0 ? 1 : -1.5;
  if (o.macd) T += o.macd.up ? 0.5 : -0.5;
  var F = 5;
  if (o.acc) F += o.acc.tone === 'good' ? 2.5 : o.acc.tone === 'bad' ? -3 : 0;
  if (o.f9 != null) F += o.f9 >= 7 ? 1 : o.f9 <= 3 ? -1.5 : 0;
  if (o.margin != null) F += o.margin > 0.1 ? 1 : o.margin < 0 ? -2 : 0;
  if (o.cashNet != null) F += o.cashNet > 0 ? 0.5 : 0;
  if (o.roe != null) F += o.roe > 0.15 ? 0.5 : o.roe < 0 ? -1 : 0;
  var NW = newsOf(o),
    nNeg = NW.filter(function (n) {
      return n.k === 'neg';
    }),
    nPos = NW.filter(function (n) {
      return n.k === 'pos';
    });
  var K = 5 + (nPos.length ? 1 : 0) - (nNeg.length ? 1.5 : 0);
  if (r.vx >= 1.5) K += 1.5;
  if (bumpOf(r) != null) K += 1;
  if (o.rev != null) K += o.rev > 0 ? 1.5 : o.rev < 0 ? -1.5 : 0;
  if (o.surprise != null) K += o.surprise >= 0 ? 1 : -1;
  if (r.brk != null) K += 1;
  var C = 5;
  if (up != null) C += up > 20 ? 2 : up > 10 ? 1 : up < 0 ? -2 : 0;
  if (vm != null) C += vm > 20 ? 1.5 : vm < -30 ? -1.5 : 0;
  if (o.peer) C += o.peer.discountPct > 20 ? 1 : o.peer.discountPct < -30 ? -1 : 0;
  if (o.reco != null) C += o.reco <= 2 ? 0.5 : o.reco >= 3.5 ? -1 : 0;
  var Rk = 8;
  if (o.vol != null) Rk -= o.vol > 60 ? 2 : o.vol > 40 ? 1 : 0;
  if (r.sh != null) Rk -= r.sh >= 2 ? 2 : r.sh >= 0.5 ? 1 : 0;
  if (o.acc && o.acc.tone === 'bad') Rk -= 2;
  if (o.crash) Rk -= 2;
  if (r.mom != null && r.mom > 200) Rk -= 1;
  if (r.ratio != null && r.ratio < 70) Rk -= 1;
  var crit = [
    ['📈 Technique', cl(T), 0.25],
    ['📊 Comptes', cl(F), 0.25],
    ['⚡ Catalyseurs', cl(K), 0.15],
    ['🎯 Valorisation', cl(C), 0.15],
    ['🛡️ Risques faibles', cl(Rk), 0.2],
  ];
  var score = crit.reduce(function (a, k) {
    return a + k[1] * k[2];
  }, 0);
  var V =
    score >= 7
      ? ['🟢', 'Positif', 'good']
      : score >= 5.5
        ? ['🟡', 'Constructif avec réserves', 'warn']
        : score >= 4
          ? ['⚪', 'Neutre', 'neutral']
          : ['🔴', 'Prudence', 'bad'];
  // 2. pour et contre
  if (r.trend === 'up')
    add(
      pros,
      3,
      'tendance de fond haussière' +
        (r.slope6 != null && r.sc
          ? ', pente ' +
            (r.sc === 'strong' ? 'forte' : r.sc === 'mid' ? 'moyenne' : 'légère') +
            ' (' +
            (r.slope6 >= 0 ? '+' : '') +
            r.slope6 +
            ' % en 6 mois)'
          : '')
    );
  if (r.mom != null && r.mom > 0 && r.momPct != null && r.momPct >= 67)
    add(pros, 3, '+' + Math.round(r.mom) + ' % sur 12 mois, mieux que ' + r.momPct + ' % des sociétés');
  if (bumpOf(r) != null)
    add(pros, 2.2, '📣 bond sur gros volume ' + bumpTxt(bumpOf(r)) + " : souvent suivi d'une hausse prolongée");
  if (r.vx >= 1.5) add(pros, 2, 'volumes en hausse (×' + String(r.vx).replace('.', ',') + ' sur 10 semaines)');
  if (o.acc && o.acc.tone === 'good')
    add(pros, 2.5, o.acc.label.toLowerCase() + (o.f9 != null ? ' (F-score ' + o.f9 + '/9)' : ''));
  if (o.margin != null && o.margin > 0.1) add(pros, 1.5, 'marge nette de ' + Math.round(o.margin * 100) + ' %');
  if (o.cashNet != null && o.cashNet > 0) add(pros, 1, 'plus de trésorerie que de dettes');
  if (up != null && up > 10)
    add(pros, 2, 'objectif des analystes ' + pct(up) + (o.tgt.n ? ' (' + o.tgt.n + ' analystes)' : ''));
  if (vm != null && vm > 20) add(pros, 2, 'sous sa valeur estimée (marge de sécurité ' + Math.round(vm) + ' %)');
  if (o.peer && o.peer.discountPct > 20)
    add(pros, 1.5, 'moins chère que ses pairs (' + Math.round(o.peer.discountPct) + ' % de décote)');
  if (o.rev != null && o.rev > 0) add(pros, 1.5, 'prévisions des analystes relevées');
  if (o.surprise != null && o.surprise > 0) add(pros, 1, 'derniers résultats au-dessus du consensus');
  if (o.m10 != null && o.m10 < 0)
    add(cons, 3, 'sous sa moyenne 10 semaines (' + String(o.m10).replace('.', ',') + ' %) : élan cassé');
  if (up != null && up >= 0 && up < 10) add(cons, 0.5, 'peu de potentiel selon les analystes (' + pct(up) + ')');
  if (o.rsi != null && o.rsi >= 80) add(cons, 0.4, 'RSI ' + o.rsi + ' : très tendu à court terme');
  if (r.trend === 'down') add(cons, 3, 'tendance de fond baissière');
  if (r.sh != null && r.sh >= 0.5) add(cons, 3, String(r.sh).replace('.', ',') + ' % du capital vendu à découvert');
  if (r.vo != null && r.vo >= 60) add(cons, 2, 'cours très agité (' + r.vo + ' % par an)');
  if (o.acc && o.acc.tone === 'bad') add(cons, 3, o.acc.label.toLowerCase());
  if (o.margin != null && o.margin < 0) add(cons, 2.5, 'en perte (marge ' + Math.round(o.margin * 100) + ' %)');
  if (o.cashNet != null && o.cap && o.cashNet < -0.5 * o.cap)
    add(cons, 1.5, 'dette nette élevée (plus de la moitié de la capitalisation)');
  if (up != null && up < 0) add(cons, 2, "cours au-dessus de l'objectif des analystes (" + pct(up) + ')');
  if (vm != null && vm < -30) add(cons, 1.5, 'cher par rapport à sa valeur estimée');
  if (o.rev != null && o.rev < 0) add(cons, 1.5, 'prévisions des analystes abaissées');
  if (o.surprise != null && o.surprise < 0) add(cons, 1, 'derniers résultats sous le consensus');
  if (r.ratio != null && r.ratio < 70) add(cons, 1.5, Math.round(100 - r.ratio) + " % sous son plus haut d'un an");
  if (r.mom != null && r.mom > 200)
    add(cons, 1, 'déjà +' + Math.round(r.mom) + ' % sur un an : chutes plus fréquentes');
  if (o.crash) add(cons, 2, 'marché en baisse de plus de 20 % sur un an (krach du momentum)');
  if (nNeg.length)
    add(
      cons,
      3.5,
      'actualité : « ' +
        nNeg[0].t.slice(0, 90) +
        (nNeg[0].t.length > 90 ? '…' : '') +
        ' » (' +
        shortDate(nNeg[0].d) +
        ')'
    );
  if (nPos.length)
    add(
      pros,
      1.6,
      'actualité : « ' +
        nPos[0].t.slice(0, 90) +
        (nPos[0].t.length > 90 ? '…' : '') +
        ' » (' +
        shortDate(nPos[0].d) +
        ')'
    );
  var top = function (L) {
    return L.sort(function (a, b) {
      return b[0] - a[0];
    })
      .slice(0, 3)
      .map(function (z) {
        return z[1];
      });
  };
  var P3 = top(pros),
    C3 = top(cons);
  var priced = [
    o.pe ? 'PER ' + fmtN(o.pe, 1) : null,
    o.evE ? 'VE/EBITDA ' + fmtN(o.evE, 1) : null,
    o.pb ? 'cours/actif net ' + fmtN(o.pb, 2) + (o.peer ? ' (pairs ' + fmtN(o.peer.peerMedian, 2) + ')' : '') : null,
    up != null ? 'objectif ' + pct(up) : null,
  ].filter(Boolean);
  // 3. action selon les règles testées
  var E = o.inPick ? ES.pickEntry(r) : null;
  var act = o.inPick
    ? E && E.k === 'wait'
      ? '🎯 ⏸️ Dans le 🎯, en attente : sous sa moyenne 10 semaines'
      : '🎯 ✅ Dans le 🎯 : conditions des règles testées réunies'
    : o.inVal
      ? '💎 ✅ Dans le 💎 : conditions réunies (complément valeur)'
      : r.out && r.out.length
        ? '⛔ Hors des règles : ' + r.out[0]
        : '👀 Ni dans le 🎯 ni dans le 💎 : hors des sélections de nos règles';
  // 4. régime, technique, scénarios
  var dot = function (k) {
    return k > 0 ? '🟢' : k < 0 ? '🔴' : '🟡';
  };
  var reg = [
    [
      'Court terme',
      o.m10 != null
        ? dot(o.m10 >= 0 ? 1 : -1) +
          ' ' +
          (o.m10 >= 0 ? 'au-dessus' : 'sous') +
          ' sa moyenne 10 sem. (' +
          (o.m10 >= 0 ? '+' : '') +
          String(o.m10).replace('.', ',') +
          ' %)' +
          (o.rsi != null ? ' · RSI ' + o.rsi : '')
        : '—',
    ],
    [
      'Moyen terme',
      r.trend
        ? dot(r.trend === 'up' ? 1 : r.trend === 'down' ? -1 : 0) +
          ' tendance ' +
          (r.trend === 'up' ? 'haussière' : r.trend === 'down' ? 'baissière' : 'hésitante') +
          (r.slope6 != null ? ' · pente ' + (r.slope6 >= 0 ? '+' : '') + r.slope6 + ' %/6 mois' : '')
        : '—',
    ],
    [
      'Long terme',
      r.momPct != null
        ? dot(r.momPct >= 67 ? 1 : r.momPct < 33 ? -1 : 0) +
          ' 12 mois ' +
          (r.mom >= 0 ? '+' : '') +
          Math.round(r.mom) +
          ' % (mieux que ' +
          r.momPct +
          ' %)'
        : '—',
    ],
  ];
  var fibH = '';
  if (o.hi && o.lo && o.hi > o.lo) {
    var rg = o.hi - o.lo,
      retr = ((o.hi - o.last) / rg) * 100;
    fibH =
      'Fibonacci (1 an) : retracement ' +
      fmtN(retr, 0) +
      ' % · ' +
      [23.6, 38.2, 50, 61.8]
        .map(function (k) {
          return String(k).replace('.', ',') + ' % = ' + fmtN(o.hi - (rg * k) / 100, o.hi < 10 ? 2 : 1);
        })
        .join(' · ');
  }
  var pl = o.plan && o.plan.primary,
    lv = [];
  if (pl) {
    if (pl.zoneLo)
      lv.push('support ' + fmtN(pl.zoneLo, pl.zoneLo < 10 ? 2 : 1) + '–' + fmtN(pl.zoneHi, pl.zoneHi < 10 ? 2 : 1));
    if (pl.trigger) lv.push('résistance ' + fmtN(pl.trigger, pl.trigger < 10 ? 2 : 1));
  }
  if (o.plan && o.plan.alt && o.plan.alt.trigger)
    lv.push('résistance ' + fmtN(o.plan.alt.trigger, o.plan.alt.trigger < 10 ? 2 : 1));
  var sc,
    sg6 = o.vol ? (o.vol / 100) * Math.sqrt(0.5) : 0.2;
  if (o.tgt && o.tgt.low > 0 && o.tgt.high > 0 && (o.tgt.n || 0) >= 2)
    sc = [o.tgt.low, o.tgt.mean, o.tgt.high, 'objectifs des analystes (bas, moyen, haut)'];
  else if (o.tgt && o.tgt.mean > 0)
    sc = [
      Math.min(o.tgt.mean, o.last) * Math.exp(-sg6),
      o.tgt.mean,
      Math.max(o.tgt.mean, o.last) * Math.exp(sg6 / 2),
      'objectif moyen des analystes, et amplitude habituelle du cours autour',
    ];
  else if (o.val && o.val.low > 0) sc = [o.val.low, o.val.mid, o.val.high, 'valeur estimée (comptes)'];
  else if (o.vol) {
    var sg = (o.vol / 100) * Math.sqrt(0.5);
    sc = [o.last * Math.exp(-sg), o.last, o.last * Math.exp(sg), 'amplitude habituelle du cours sur 6 mois'];
  }
  var scH = '';
  if (sc) {
    var w = 0.25 * sc[0] + 0.5 * sc[1] + 0.25 * sc[2],
      gp = sc[0] < o.last ? (sc[2] - o.last) / (o.last - sc[0]) : null,
      d = function (v) {
        return pct((v / o.last - 1) * 100);
      };
    scH =
      '<div class="anscen">' +
      [
        ['🐻 Baissier', sc[0], '1 chance sur 4'],
        ['⚖️ Central', sc[1], '1 chance sur 2'],
        ['🚀 Haussier', sc[2], '1 chance sur 4'],
      ]
        .map(function (z) {
          return (
            '<span><small>' +
            z[0] +
            '</small><b>' +
            fmtN(z[1], z[1] < 10 ? 2 : 1) +
            '</b><small>' +
            d(z[1]) +
            ' · ' +
            z[2] +
            '</small></span>'
          );
        })
        .join('') +
      '</div>' +
      '<p class="small muted">Source : ' +
      sc[3] +
      '. Valeur pondérée ' +
      fmtN(w, w < 10 ? 2 : 1) +
      ' (' +
      d(w) +
      ')' +
      (gp != null && gp > 0 ? ' · gain/perte ' + fmtN(gp, 1) : '') +
      '.</p>';
  }
  var unc =
    o.vol == null
      ? null
      : o.vol < 25
        ? 'faible'
        : o.vol < 40
          ? 'moyenne'
          : o.vol < 60
            ? 'élevée'
            : o.vol < 80
              ? 'très élevée'
              : 'extrême';
  var cu = sc ? (sc[1] / o.last - 1) * 100 : null,
    stars = cu == null ? null : cu >= 30 ? 5 : cu >= 15 ? 4 : cu >= 0 ? 3 : cu >= -15 ? 2 : 1;
  var cur = o.cur && o.cur !== 'EUR' ? ' ' + o.cur : ' €';
  var kpis = [
    ['Cours', fmtN(o.last, o.last < 10 ? 2 : 1) + cur],
    [
      'Capitalisation',
      o.cap ? (o.capCur && o.capCur !== 'EUR' ? fmtN(o.cap / 1e9, 1) + ' Md ' + o.capCur : capTxt(o.cap)) : null,
    ],
    [
      'Trésorerie nette',
      o.cashNet != null ? (o.cashNet >= 0 ? '+' : '−') + fmtN(Math.abs(o.cashNet) / 1e6, 0) + ' M' : null,
    ],
    ['Marge nette', o.margin != null ? fmtN(o.margin * 100, 0) + ' %' : null],
    ['Rentabilité (ROE)', o.roe != null ? fmtN(o.roe * 100, 0) + ' %' : null],
    ['Croissance attendue', o.growth != null ? pct(o.growth) : null],
    ['F-score', o.f9 != null ? o.f9 + '/9' : null],
    // carte d'identité : éligibilité, échanges, ventes à découvert, prochains résultats
    ['Échanges / jour', r.liq ? (r.liq >= 1e6 ? fmtN(r.liq / 1e6, 1) + ' M€' : fmtN(r.liq / 1e3, 0) + ' k€') : null],
    [
      'Vente à découvert',
      r.sh != null ? String(r.sh).replace('.', ',') + ' %' + (r.shn ? ' · ' + r.shn + ' fonds' : '') : null,
    ],
    ['Prochains résultats', o.nextE && o.nextE >= S.today ? shortDate(o.nextE) : null],
  ]
    .filter(function (k) {
      return k[1];
    })
    .slice(0, 12);
  var h =
    '<details class="card fold anfold" data-k="analyse"><summary>🔬 Analyse · ' + V[0] + ' ' + V[1] + '</summary>';
  h +=
    '<p class="anact ' +
    (o.inPick || o.inVal ? (E && E.k === 'wait' ? 'warn' : 'good') : 'neutral') +
    '">' +
    esc(act) +
    '</p>';
  h +=
    '<div class="an3"><div class="good"><b>✅ Ce qui porte</b>' +
    (P3.length
      ? '<ul>' +
        P3.map(function (t) {
          return '<li>' + esc(cap1(t)) + '</li>';
        }).join('') +
        '</ul>'
      : '<p class="muted small">rien de net</p>') +
    '</div>' +
    '<div class="bad"><b>⚠️ Ce qui menace</b>' +
    (C3.length
      ? '<ul>' +
        C3.map(function (t) {
          return '<li>' + esc(cap1(t)) + '</li>';
        }).join('') +
        '</ul>'
      : '<p class="muted small">rien de net</p>') +
    '</div>' +
    (priced.length
      ? '<div class="neutral"><b>💶 Ce que le cours intègre</b><p class="small">' +
        esc(priced.join(' · ')) +
        '</p></div>'
      : '') +
    '</div>';
  h += newsBlock(o, NW);
  // 📊 Le détail : petits plis, pour ne lire que ce qui intéresse (inspiré d'une analyse complète, en plus court)
  o.news = NW;
  var ex = anExtraParts(o),
    sub = function (title, body) {
      return body ? '<details class="ansub"><summary>' + title + '</summary>' + body + '</details>' : '';
    },
    f2 = function (v) {
      return fmtN(v, v < 10 ? 2 : 1);
    };
  var regH =
    '<table class="kv antab">' +
    reg
      .map(function (z) {
        return '<tr><th>' + z[0] + '</th><td>' + esc(z[1]) + '</td></tr>';
      })
      .join('') +
    '</table>';
  var kpiH =
    '<div class="ankpi">' +
    kpis
      .map(function (k) {
        return '<span><small>' + k[0] + '</small><b>' + esc(k[1]) + '</b></span>';
      })
      .join('') +
    '</div>';
  // supports et résistances : les mêmes niveaux que sur le graphique, en tableau (du plus haut au plus bas)
  var LVa = anLevels(o),
    srH = '';
  if (LVa) {
    var lvRow = function (x, sup) {
      return (
        '<tr class="' +
        (sup ? 'sup' : 'res') +
        '"><th>' +
        (sup ? '🟢 Support' : '🔴 Résistance') +
        '</th><td>' +
        f2(x.price) +
        '</td><td>' +
        (x.distPct != null ? pct(x.distPct) : '') +
        '</td><td class="muted small">' +
        esc(lvTouch(x)) +
        '</td></tr>'
      );
    };
    srH =
      '<table class="kv ansr">' +
      (LVa.resistances || [])
        .slice(0, 2)
        .reverse()
        .map(function (x) {
          return lvRow(x, false);
        })
        .join('') +
      '<tr class="now"><th>▶ Cours</th><td><b>' +
      f2(o.last) +
      '</b></td><td></td><td></td></tr>' +
      (LVa.supports || [])
        .slice(0, 2)
        .map(function (x) {
          return lvRow(x, true);
        })
        .join('') +
      '</table>';
  }
  var wd = o.plan && o.plan.wedge && o.plan.wedge.type && o.plan.wedge.type !== 'none' ? o.plan.wedge : null;
  var techH =
    srH +
    '<p class="small">' +
    esc(
      [
        o.rsi != null ? 'RSI 14 : ' + o.rsi + (o.rsi >= 70 ? ' (tendu)' : o.rsi <= 30 ? ' (survendu)' : '') : null,
        o.macd ? 'MACD ' + (o.macd.up ? 'au-dessus de son signal (haussier)' : 'sous son signal (baissier)') : null,
        wd && wd.label ? 'figure : ' + wd.label : null,
      ]
        .filter(Boolean)
        .join(' · ')
    ) +
    '</p>' +
    (fibH ? '<p class="small muted">' + esc(fibH) + '</p>' : '');
  // analystes et scénarios, avec la place du cours entre le scénario baissier et le haussier
  var RECO = function (v) {
    return v == null
      ? null
      : v <= 1.5
        ? 'achat fort'
        : v <= 2.5
          ? 'achat'
          : v <= 3.5
            ? 'conserver'
            : v <= 4.5
              ? 'vente'
              : 'vente forte';
  };
  var anaH =
    (o.tgt
      ? '<p class="small">' +
        esc(
          (o.tgt.n ? o.tgt.n + ' analystes' : 'Analystes') +
            (o.reco != null ? ' · avis moyen « ' + RECO(o.reco) + ' »' : '') +
            ' · objectif moyen ' +
            f2(o.tgt.mean) +
            cur +
            ' (' +
            pct(up) +
            ')' +
            (o.tgt.low > 0 && o.tgt.high > 0 ? ', fourchette ' + f2(o.tgt.low) + ' à ' + f2(o.tgt.high) : '') +
            (o.rev != null
              ? ' · prévisions ' + (o.rev > 0 ? 'relevées' : o.rev < 0 ? 'abaissées' : 'stables') + ' sur 30 jours'
              : '')
        ) +
        '</p>'
      : '<p class="small muted">Pas de consensus d\'analystes publié.</p>') + scH;
  if (sc && sc[2] > sc[0]) {
    var posP = Math.max(0, Math.min(100, ((o.last - sc[0]) / (sc[2] - sc[0])) * 100));
    anaH +=
      '<div class="anbar" role="img" aria-label="Cours à ' +
      Math.round(posP) +
      ' % entre le scénario baissier et le haussier"><i style="left:' +
      posP.toFixed(0) +
      '%"></i></div><p class="small muted anbarl"><span>🐻 ' +
      f2(sc[0]) +
      '</span><span>cours ' +
      f2(o.last) +
      '</span><span>🚀 ' +
      f2(sc[2]) +
      '</span></p>';
  }
  var convH =
    '<div class="ancrit">' +
    crit
      .map(function (k) {
        return (
          '<div><span>' +
          k[0] +
          ' <small class="muted">' +
          Math.round(k[2] * 100) +
          ' %</small></span><i style="width:' +
          k[1] * 10 +
          '%" class="' +
          (k[1] >= 6.5 ? 'g' : k[1] >= 4.5 ? 'w' : 'b') +
          '"></i><b>' +
          fmtN(k[1], 1) +
          '</b></div>'
        );
      })
      .join('') +
    '</div>' +
    '<p class="small"><b>Incertitude</b> : ' +
    (unc || 'n.d.') +
    (o.vol != null ? ' (volatilité ' + Math.round(o.vol) + ' % par an)' : '') +
    ' · <b>Prix / valeur</b> : ' +
    (stars ? '★★★★★'.slice(0, stars) + '☆☆☆☆☆'.slice(0, 5 - stars) : 'n.d.') +
    '</p>';
  h +=
    '<details class="andet"><summary>📊 Le détail <span class="muted">· chiffres, supports et résistances, scénarios, conviction ' +
    fmtN(score, 1) +
    '/10</span></summary>' +
    sub('🧭 Régime et chiffres clés', regH + kpiH + ex.traj) +
    sub('📐 Supports, résistances et technique', techH) +
    sub('🎯 Analystes et scénarios', anaH) +
    sub("🗓️ Chronologie de l'année et agenda", ex.agenda) +
    sub(
      '🏦 Gestion du capital',
      ex.cap.replace(/^<h4>Gestion du capital · ([^<]*)<\/h4>/, '<p class="small"><b>$1</b></p>')
    ) +
    sub('🧮 Score de conviction · ' + fmtN(score, 1) + '/10', convH) +
    '<p class="small muted ansrc">Sources : Yahoo Finance (cours, comptes, analystes) · registres AMF, FI, FSMA, AFM (dirigeants) · AMF, Consob, CNMV, AFM, FSMA, Bundesanzeiger, FCA (ventes à découvert) · Google News (presse) · données du ' +
    shortDate(S.today) +
    '.</p>';
  h += '</details>';
  return (
    h +
    '<p class="foot">Automatique, données du soir. Seules les règles 🎯 et 💎 sont testées. Pas un conseil.</p></details>'
  );
}
/** Une carte « <section><h3>titre</h3>… » devient un pli fermé ; le titre court du pli porte l'essentiel. */
function asFold(html, key, summ) {
  if (!html) return '';
  var m = html.match(/^<section class="card([^"]*)"><h3>([\s\S]*?)<\/h3>/);
  if (!m || html.slice(-10) !== '</section>') return html;
  return (
    '<details class="card fold' +
    m[1] +
    '" data-k="' +
    key +
    '"><summary>' +
    (summ || m[2]) +
    '</summary>' +
    html.slice(m[0].length, -10) +
    '</details>'
  );
}
/** Pli « Classement » d'une fiche : note et verdict dans le titre. */
function rankFold(r) {
  var sm = r
    ? '📈 Classement <span class="muted small">· ' +
      (r.out && r.out.length
        ? '⛔ écartée'
        : r.note + '/100 · ' + ((RV[r.v] || RV.mid)[0] + ' ' + (RV[r.v] || RV.mid)[1])) +
      '</span>'
    : '📈 Classement <span class="muted small">· hors classement</span>';
  return asFold(rankCard(r), 'f-rank', sm);
}
function rankCard(r) {
  var R = rankData();
  if (!r)
    return R
      ? '<section class="card rcard"><h3>📈 Classement tendance + comptes</h3><p class="muted small">Société hors du classement : pas assez liquide ou absente du catalogue des sociétés cotées.</p></section>'
      : '';
  var w = rankW(),
    p = r.parts || {};
  var h = '<section class="card rcard"><h3>📈 Classement tendance + comptes</h3>';
  if (r.out && r.out.length) {
    h +=
      '<p class="rhead"><span class="rnote muted">' +
      r.note +
      '</span><span class="muted">/100</span> ' +
      rankChip(r) +
      '</p><p><b>Écartée du classement :</b></p><ul class="plain rwhy">' +
      r.out
        .map(function (t) {
          return '<li>⛔ ' + esc(cap1r(t)) + '</li>';
        })
        .join('') +
      '</ul>';
  } else {
    h +=
      '<p class="rhead"><span class="rnote">' +
      r.note +
      '</span><span class="muted">/100</span> ' +
      rankChip(r) +
      (r.pos
        ? ' <span class="muted small">' +
          r.pos +
          '<sup>' +
          (r.pos === 1 ? 'er' : 'e') +
          '</sup> sur ' +
          R.counts.ranked +
          '</span>'
        : '') +
      '</p>' +
      rankGauges(r) +
      ((r.warn || []).length
        ? '<ul class="plain rwhy">' +
          r.warn
            .map(function (t) {
              return '<li class="t-warn">⚠ ' + esc(cap1r(t)) + '</li>';
            })
            .join('') +
          '</ul>'
        : '');
  }
  h +=
    '<details class="xpi"><summary>ⓘ Détail des points</summary>' +
    (r.why && r.why.length && !(r.out && r.out.length)
      ? '<ul class="plain small">' +
        r.why
          .map(function (t) {
            return '<li>✓ ' + esc(cap1r(t)) + '</li>';
          })
          .join('') +
        '</ul>'
      : '') +
    '<ul class="plain small">' +
    '<li>📈 Tendance : force sur 12 mois ' +
    (p.mom || 0) +
    '/' +
    w.mom +
    ', proximité du plus haut ' +
    (p.high || 0) +
    '/' +
    w.high +
    ', moyennes 50 et 200 séances ' +
    (p.trend || 0) +
    '/' +
    w.trend +
    '</li>' +
    '<li>📊 Comptes ' +
    (p.accounts || 0) +
    '/' +
    w.accounts +
    (w.calm ? ' · 🌊 Calme du cours ' + (p.calm || 0) + '/' + w.calm : '') +
    ' · 👔 Dirigeants ' +
    ((p.insiders || 0) > 0 ? '+' : '') +
    (p.insiders || 0) +
    ' (de ' +
    ((S.cfg.rank || {}).insFloor || -15) +
    ' à +' +
    w.insiders +
    ')</li></ul>' +
    '<p class="small">Vert : bon score, orange : moyen, rouge : faible. <button class="linkbtn" data-a="rankWhy">Pourquoi cette méthode ?</button></p></details></section>';
  return h;
}
/** 📋 La sélection de la semaine : 5 🎯 (celles de l'email du lundi) + 2 💎, soit 70/30, avec l'état de chacune (✅ feu vert, ⏸️ en attente). */
function rankSelCard() {
  var R = rankData();
  if (!R) return '';
  var sel = R.selection || { items: [], week: '' },
    t = sel.track,
    V = ES.pickValue(R.rows || [], { n: 2, peaOnly: true }).picks;
  var li = function (r, tag, act, sub) {
    return (
      '<li class="rowlink" ' +
      rankOpenAttr(r) +
      ' data-from="rank" tabindex="0"><span class="seltag">' +
      tag +
      '</span><b>' +
      flag(r.country) +
      esc(r.name) +
      '</b>' +
      (r.isNew ? ' <span class="chip newc">Nouveau</span>' : '') +
      '<span class="selact">' +
      act +
      '</span><small>' +
      esc(sub) +
      '</small></li>'
    );
  };
  var h =
    '<details class="card fold selc" data-k="buy"><summary>📋 Sélection de la semaine <span class="muted small">· ' +
    sel.items.length +
    ' 🎯 + ' +
    V.length +
    ' 💎</span></summary><p class="selrule small muted">PEA · lignes égales (≈ 70/30) · envoyée par email le lundi · ' +
    esc(sel.week) +
    '</p>';
  var subs = pick3Card(sel.items) + valueCard(V);
  if (R.breadth && R.breadth.now && R.breadth.now.regime === 'high')
    h +=
      '<p class="note warn">😃 Marché euphorique : historiquement moins favorable ; mieux valait entrer en plusieurs fois.</p>';
  if (!sel.items.length && !V.length)
    return (
      h + '<p class="muted">Rien ne passe les règles cette semaine : mieux vaut attendre.</p>' + subs + '</details>'
    );
  h +=
    '<ol class="sel sel2">' +
    sel.items
      .map(function (r) {
        var E = ES.pickEntry(r);
        return li(
          r,
          '🎯',
          E ? E.icon + ' ' + (E.k === 'buy' ? 'Feu vert' : 'En attente') : '✅ Feu vert',
          [
            r.sector,
            'note ' + r.note,
            r.mom != null ? '12 m ' + (r.mom >= 0 ? '+' : '') + Math.round(r.mom) + ' %' : null,
            bumpOf(r) != null ? '📣 bond' : null,
            E && E.k === 'wait' ? 'sous sa moyenne 10 sem.' : null,
          ]
            .filter(Boolean)
            .join(' · ')
        );
      })
      .join('') +
    V.map(function (r) {
      return li(
        r,
        '💎',
        '✅ Feu vert',
        [r.sector, 'F-score ' + r.f9 + '/9', 'cours / fonds propres ' + fmtN(r.pb, 2)].filter(Boolean).join(' · ')
      );
    }).join('') +
    '</ol>' +
    '<p class="foot">Puis : garder 6 mois, protection à −30 %. Les emails préviennent du reste.' +
    (t && t.n
      ? ' Sélections précédentes : ' +
        pct(t.avg) +
        ' en moyenne' +
        (t.bench != null ? ' (indice ' + pct(t.bench) + ')' : '') +
        ', détail dans Alertes.'
      : '') +
    '</p>';
  return h + subs + '</details>';
}
/** Classe de pente du canal haussier (régression sur 6 mois, rythme annuel), seulement en tendance de fond haussière. */
function rkSc(r) {
  return r.sc !== undefined
    ? r.sc
    : (ES.slopeClass(r.slope6 != null ? Math.pow(1 + r.slope6 / 100, 2) - 1 : null, r.trend) || {}).key || null;
}
/** Sortie de base récente (moins de 4 semaines) sur une société classée ou seulement écartée pour sa baisse sur 12 mois. */
function rkBrk(r) {
  return r.brk != null && (!r.out.length || (r.out.length === 1 && /tiers le plus faible/.test(r.out[0])));
}
/** Explication du signal précoce, avec la combinaison qui a le mieux marché et l'état actuel du marché. */
function brkNote() {
  var R = rankData(),
    rg = R && R.breadth && R.breadth.now ? R.breadth.now.regime : null;
  var mk =
    rg === 'high'
      ? '<b class="brk-bad">😃 euphorique, défavorable</b>'
      : rg === 'low'
        ? '<b class="brk-good">😟 pessimiste, très favorable</b>'
        : rg === 'mid'
          ? '<b class="brk-good">😐 neutre, favorable</b>'
          : 'inconnu';
  return (
    '<p class="small brkx">🚀 seul apporte peu (1 sur 9 font +40 % en 6 mois, contre 1 sur 10). Avec ⬆⬆ et un marché non euphorique : 1 sur 4 à 5. Marché actuel : ' +
    mk +
    '.</p>'
  );
}
var SLOPE_TXT = { strong: ['⬆⬆', 'forte', 'good'], mid: ['⬆', 'moyenne', 'warn'], light: ['↗', 'légère', 'neutral'] };
/** Psychologie du marché : part des sociétés en tendance haussière (ampleur), plus hauts et plus bas de l'année, volatilité, et ce qui a suivi dans le passé. */
function psyCard() {
  var R = rankData(),
    b = R && R.breadth;
  if (!b || !b.now) return '';
  var N = b.now,
    G = b.regimes || {},
    mood = S.snapshot && S.snapshot.market && S.snapshot.market.mood;
  var L = {
    low: ['😟', 'Marché pessimiste', 'peu de sociétés en tendance haussière'],
    mid: ['😐', 'Marché neutre', 'ni peur ni euphorie'],
    high: ['😃', 'Marché euphorique', 'beaucoup de sociétés en tendance haussière'],
  }[N.regime];
  var g6 = function (k) {
    var o = G[k] && G[k].h26;
    return o ? (o.mean >= 0 ? '+' : '') + fmtN(o.mean, 1) + ' %' : 'n.d.';
  };
  // petite courbe de l'ampleur avec les deux seuils
  var H = b.hist || [],
    svg = '';
  if (H.length > 10) {
    var vals = H.map(function (r) {
        return r[1];
      }).concat(b.cuts),
      y0 = Math.max(0, Math.min.apply(null, vals) - 3),
      y1 = Math.min(100, Math.max.apply(null, vals) + 3);
    var w = 320,
      hgt = 56,
      x = function (k) {
        return ((k / (H.length - 1)) * w).toFixed(1);
      },
      y = function (v) {
        return (hgt - ((v - y0) / (y1 - y0)) * hgt).toFixed(1);
      };
    svg =
      '<svg class="psyline" viewBox="0 0 ' +
      w +
      ' ' +
      hgt +
      '" preserveAspectRatio="none" role="img" aria-label="Part des sociétés en tendance haussière depuis ' +
      esc(shortDate(b.from)) +
      '">' +
      '<rect x="0" y="' +
      y(b.cuts[0]) +
      '" width="' +
      w +
      '" height="' +
      (hgt - y(b.cuts[0])).toFixed(1) +
      '" class="psy-low"/><rect x="0" y="0" width="' +
      w +
      '" height="' +
      y(b.cuts[1]) +
      '" class="psy-high"/>' +
      '<polyline fill="none" class="psy-l" points="' +
      H.map(function (r, k) {
        return x(k) + ',' + y(r[1]);
      }).join(' ') +
      '"/><circle cx="' +
      x(H.length - 1) +
      '" cy="' +
      y(H[H.length - 1][1]) +
      '" r="3.5" class="psy-dot"/></svg>' +
      '<p class="small muted psyax"><span>' +
      esc(shortDate(b.from)) +
      '</span><span>vert : peur · rouge : euphorie</span><span>' +
      esc(shortDate(b.to)) +
      '</span></p>';
  }
  return (
    '<section class="card psy psy-' +
    N.regime +
    '"><h3>🧠 Psychologie du marché</h3>' +
    '<p class="psyh"><span class="psyi" aria-hidden="true">' +
    L[0] +
    '</span><b>' +
    L[1] +
    '</b> : ' +
    fmtN(N.up, 0) +
    ' % des sociétés en tendance haussière (' +
    L[2] +
    ' ; ' +
    (N.pct <= 50 ? 'plus bas que ' + (100 - N.pct) : 'plus haut que ' + N.pct) +
    ' % des semaines depuis ' +
    esc(String(b.from).slice(0, 4)) +
    ').</p>' +
    '<p class="small">Plus hauts de l\'année : <b>' +
    fmtN(N.hi, 0) +
    " %</b> des sociétés · plus bas de l'année : <b>" +
    fmtN(N.lo, 0) +
    ' %</b>' +
    (mood && mood.label ? ' · volatilité : ' + esc(mood.icon || '') + ' ' + esc(mood.label) : '') +
    '.</p>' +
    svg +
    '<p class="small"><b>Six mois plus tard</b>, une société moyenne a fait :</p><p class="psyg">' +
    [
      ['low', '😟 pessimiste'],
      ['mid', '😐 neutre'],
      ['high', '😃 euphorique'],
    ]
      .map(function (o) {
        return '<span class="psyc' + (o[0] === N.regime ? ' on' : '') + '">' + o[1] + ' <b>' + g6(o[0]) + '</b></span>';
      })
      .join('') +
    '</p>' +
    xpi(
      "Quand peu de sociétés sont en tendance haussière, la peur domine et les cours sont bas : historiquement, les six mois suivants ont été meilleurs que quand tout le monde est euphorique. C'est une information sur le moment d'investir (entrer franchement quand le marché est pessimiste, étaler ses achats quand il est euphorique), pas sur le choix des sociétés. Mesuré sur " +
        esc(b.source || 'les sociétés cotées') +
        " : peu de cycles complets, donc un ordre de grandeur, pas une certitude. Les recherches Google ne sont pas utilisées : Google bloque leur lecture automatique et, dans les études, elles annoncent surtout des emballements de courte durée suivis d'un retour en arrière."
    ) +
    '</section>'
  );
}
/** Autres filtres gardés (version allégée) : comptes solides et repli, les seuls utiles une fois la note et la pente appliquées. */
/** Tableau de bord : marché, règles 🎯, règle de revente ; une ligne de chiffres en dessous. */
function dashTiles(R, rows) {
  var N = R.breadth && R.breadth.now,
    rg = N ? N.regime : null,
    C = R.counts || {};
  var crash = !!(N && N.m52 != null) && (R.crashOn != null ? !!R.crashOn : N.m52 <= ES.MOM_CRASH_M52);
  var mk = crash
    ? [
        '⚠️',
        'Marché en chute',
        fmtN(N.m52, 0) + ' % en un an : historiquement, mieux valait entrer par petites touches',
        'bad',
      ]
    : rg === 'high'
      ? ['😃', 'Marché euphorique', 'étalez vos achats', 'warn']
      : rg === 'low'
        ? ['😟', 'Marché pessimiste', 'bon moment pour entrer', 'good']
        : ['😐', 'Marché neutre', N ? fmtN(N.up, 0) + ' % des sociétés en hausse' : 'conditions normales', 'good'];
  var brkS = rows.filter(function (r) {
    return rkBrk(r) && rkSc(r) === 'strong';
  }).length;
  var VV = ES.pickValue(rows, { n: 10 });
  var P = ES.pickN(rows, { n: 10, peaOnly: true }),
    nHot = P.picks.filter(function (r) {
      return r.pickHot;
    }).length;
  var tile = function (cls, ic, t, sub, act) {
    return (
      '<button class="dtile ' +
      cls +
      '"' +
      (act ? ' data-a="' + act + '"' : ' disabled') +
      '><span class="dti" aria-hidden="true">' +
      ic +
      '</span><b>' +
      t +
      '</b><small>' +
      sub +
      '</small></button>'
    );
  };
  return (
    '<div class="dash">' +
    tile('t-' + mk[3], mk[0], mk[1], esc(mk[2]), 'psyOpen') +
    tile(
      't-good',
      '🎯',
      P.pool + ' société' + (P.pool > 1 ? 's' : '') + '',
      'toutes les règles réunies' + (nHot ? ' · 🔊 ' + nHot : ''),
      'pick3'
    ) +
    tile('t-val', '💎', VV.pool + ' valeur' + (VV.pool > 1 ? 's' : ''), 'bon marché, comptes solides', 'valueOpen') +
    '</div>' +
    (crash
      ? '<p class="note warn small">⚠️ Après une telle chute (2001-2003, 2009, 2022), les plus fortes hausses passées ont fait 12,5 points de moins que la moyenne à 6 mois : mieux valait entrer par petites touches.</p>'
      : '') +
    '<p class="dashl small muted">' +
    fmtInt(C.ranked || 0) +
    ' sociétés classées sur ' +
    fmtInt(C.catalogue || 0) +
    (brkS
      ? ' · <button type="button" class="linkbtn" data-a="weekBrk">🚀 ' +
        brkS +
        ' sortie' +
        (brkS > 1 ? 's' : '') +
        ' de base en ⬆⬆</button>'
      : '') +
    ' · <button type="button" class="linkbtn" data-a="rankWhy">la méthode →</button></p>'
  );
}
/** Bouton « Choisir 3 sociétés » : les règles testées appliquées au classement du soir (ES.pickThree). */
/** Pli intérieur de la sélection : les 🎯 suivants (remplaçants), règles et probabilités. */
function pick3Card(inSel) {
  var R = rankData();
  if (!R) return '';
  var taken = {};
  (inSel || []).forEach(function (r) {
    taken[r.key] = 1;
  });
  var P = ES.pickN(R.rows || [], { n: 10, peaOnly: true });
  var plan = function (r) {
    var o =
      r.plan &&
      PLANS.filter(function (x) {
        return x[0] === r.plan.v;
      })[0];
    return o ? o[1] : null;
  };
  var rest = P.picks.filter(function (r) {
    return !taken[r.key];
  });
  var h =
    '<details class="subf pick3" data-k="pick3"><summary>🎯 Remplaçants et règles <span class="muted small">· ' +
    rest.length +
    '</span></summary>';
  if (!rest.length) h += '<p class="muted small">Pas d\'autre société 🎯 ce soir.</p>';
  else
    h +=
      '<p class="small muted">Si une société de la liste ne vous convient pas, prendre la suivante :</p><ol class="pick3l">' +
      rest
        .map(function (r, k) {
          var pl = plan(r),
            sep =
              r.pickTier > 0 && (k === 0 || rest[k - 1].pickTier !== r.pickTier)
                ? '<li class="pick3sep">' +
                  (r.pickTier === 1
                    ? 'Règles assouplies : pente moyenne ou +30 à +60 % sur 12 mois'
                    : 'Règles assouplies : comptes mitigés ou pas lus') +
                  '</li>'
                : '';
          return (
            sep +
            '<li value="' +
            (k + 1) +
            '" class="rowlink' +
            (r.pickTier ? ' pick3x' : '') +
            '" ' +
            rankOpenAttr(r) +
            ' data-from="rank" tabindex="0"><b>' +
            flag(r.country) +
            esc(r.name) +
            '</b> <span class="muted">· ' +
            r.note +
            '/100</span>' +
            (r.vx >= 1.5 ? ' <span class="chip good">🔊 volumes ×' + String(r.vx).replace('.', ',') + '</span>' : '') +
            (bumpOf(r) != null
              ? ' <span class="chip good" title="Semaine à +8 % ou plus avec 3 fois le volume habituel">📣 bond ' +
                bumpTxt(bumpOf(r)) +
                '</span>'
              : '') +
            '<small>' +
            esc(
              [
                r.sector,
                '12\u00a0m ' + (r.mom >= 0 ? '+' : '') + Math.round(r.mom) + '\u00a0%',
                r.ratio != null
                  ? r.ratio >= 99.5
                    ? 'au plus haut'
                    : 'haut ' + Math.round(r.ratio - 100) + '\u00a0%'
                  : null,
                (function () {
                  var E = ES.pickEntry(r);
                  return E
                    ? E.icon + ' ' + E.short
                    : pl
                      ? pl.split(' : ')[0].replace(/Attendre une? /, 'attendre ')
                      : null;
                })(),
                (r.liq || 0) < 5e6 ? '💧 ordres limités' : null,
                r.pickNotPea ? 'hors PEA' : null,
              ]
                .filter(Boolean)
                .join(' · ')
            ) +
            '</small></li>'
          );
        })
        .join('') +
      '</ol>';
  h +=
    '<p class="p3rules">⬆⬆ pente forte · +60 à +200 % sur 12 mois · 📊 comptes solides · 🔊 volumes puis 📣 bond d\'abord (📣 repêche pente moyenne ou +30 %) · 2 par secteur · sans ⚡ ni 🐻</p>' +
    xpi(
      P.pool +
        ' société' +
        (P.pool > 1 ? 's passent' : ' passe') +
        " toutes les règles ce soir (au moins 3 M€ échangés par jour, PEA seulement). Au-delà, règles assouplies par paliers, signalés en orange. Volumes : 10 semaines au moins 1,5 fois la moyenne de l'année. Sur 1997-2026 : +6,7 points à 6 mois, +10,2 avec des volumes en hausse. Chiffre prudent (années jamais vues au réglage, frais et faillites supposées déduits) : environ +4, voir Aide."
    );
  h +=
    '<div class="probs"><small>Sur 29 ans, 6 mois après l\'achat (sociétés 🎯 au-dessus de leur moyenne 10 semaines) :</small><div class="pbs">' +
    [
      ['2 sur 3', 'en hausse', '65 %'],
      ['1 sur 3', 'à +20 % ou plus', '36 %'],
      ['1 sur 8', 'à +50 % ou plus', '12 %'],
      ['1 sur 14', 'à −25 % ou pire', '7 %'],
    ]
      .map(function (x, k) {
        return '<span class="pb' + (k === 3 ? ' neg' : '') + '"><b>' + x[0] + '</b><small>' + x[1] + '</small></span>';
      })
      .join('') +
    '</div><small class="muted">Toutes sociétés : 61 % en hausse, 1 sur 4 à +20 %, 1 sur 16 à +50 %, 1 sur 12 à −25 %. Médiane +10 % contre +6 %.</small></div>';
  if (P.rejected.length)
    h +=
      '<details class="xpi"><summary>Pourquoi pas les autres ?</summary><ul class="plain small">' +
      P.rejected
        .slice(0, 10)
        .map(function (x) {
          return '<li><b>' + esc(x.r.name) + '</b> (' + x.r.note + ') : ' + esc(x.why) + '</li>';
        })
        .join('') +
      '</ul></details>';
  return h + '</details>';
}
/** Suivi réel du 🎯 : les 10 sociétés proposées chaque semaine, résultat à 3 et 6 mois comparé à l'indice (pas un test sur le passé). */
/** 💎 Valeur : complément du 🎯 (sens inverse du momentum), règles de Piotroski appliquées aux lignes publiées (ES.pickValue). */
/** Pli intérieur de la sélection : les 💎 suivants, règles et dosage. */
function valueCard(inSel) {
  var R = rankData();
  if (!R) return '';
  var taken = {};
  (inSel || []).forEach(function (r) {
    taken[r.key] = 1;
  });
  var peaOnly = true,
    V = ES.pickValue(R.rows || [], { peaOnly: true }),
    rest = V.picks.filter(function (r) {
      return !taken[r.key];
    });
  var h =
    '<details class="subf vcard" data-k="value"><summary>💎 Remplaçants et règles <span class="muted small">· ' +
    rest.length +
    '</span></summary>';
  if (!rest.length) h += '<p class="muted small">Pas d\'autre société 💎 ce soir.</p>';
  else
    h +=
      '<ol class="pick3l">' +
      rest
        .map(function (r, k) {
          return (
            '<li value="' +
            (k + 1) +
            '" class="rowlink" ' +
            rankOpenAttr(r) +
            ' data-from="rank" tabindex="0"><b>' +
            flag(r.country) +
            esc(r.name) +
            '</b> <span class="muted">· F-score ' +
            r.f9 +
            '/9</span>' +
            '<small>' +
            esc(
              [
                r.sector,
                'cours / fonds propres ' + fmtN(r.pb, 2),
                '12\u00a0m ' + (r.mom >= 0 ? '+' : '') + Math.round(r.mom) + '\u00a0%',
                (r.liq || 0) < 5e6 ? '💧 ordres limités' : null,
                r.pea === false ? 'hors PEA' : null,
                r.sh ? '🐻 ' + String(r.sh).replace('.', ',') + ' %' : null,
              ]
                .filter(Boolean)
                .join(' · ')
            ) +
            '</small></li>'
          );
        })
        .join('') +
      '</ol>';
  h +=
    '<p class="p3rules">💰 tiers le moins cher (cours / fonds propres' +
    (V.cut ? ' < ' + fmtN(V.cut, 2) : '') +
    ') · 📊 F-score ≥ 7 · sans perte ni chute de plus de 40 % · 2 par secteur · sans ⚡ ni 🐻</p>' +
    '<div class="probs"><small>Dosage conseillé du PEA (facteurs européens, toutes sociétés, 1990-2026) :</small><div class="pbs pbs3">' +
    [
      ['70 % 🎯 + 30 % 💎', 'plus grosse perte −30 % au lieu de −46 %'],
      ['+8,5 %/an', "d'avantage au lieu de +10,3"],
      ['−0,32', 'corrélation : ils gagnent à des moments différents'],
    ]
      .map(function (x) {
        return '<span class="pb"><b>' + x[0] + '</b><small>' + x[1] + '</small></span>';
      })
      .join('') +
    '</div></div>' +
    xpi(
      V.pool +
        ' société' +
        (V.pool > 1 ? 's passent' : ' passe') +
        ' les règles ce soir' +
        (peaOnly ? ' (PEA seulement)' : ' (hors PEA compris)') +
        ". Méthode de Piotroski (2000) : parmi les sociétés bon marché, celles aux comptes les plus solides font nettement mieux que les autres. Tri : meilleur F-score, puis prix le plus bas. Testée sur nos données de 2024 à 2026 (seuls comptes disponibles) : les 10 premières ont fait +5,1 points à 6 mois face à la société moyenne (+4,1 après frais), avec 2 fois moins de chutes ; 2 ans, c'est trop court pour une preuve, qui vient des études publiées et du facteur valeur européen de Kenneth French. Pas de règle de moyenne 10 semaines ici : la valeur s'achète justement quand le cours a déçu."
    );
  return h + '</details>';
}
/** Auto-contrôle : chaque règle du 🎯 vérifiée sur les vraies sélections, et les pistes testées seules (révisions d'analystes). */
function sigBox() {
  var R = rankData();
  if (!R || !R.signalTrack) return '';
  var sg = function (v) {
    return v == null ? 'n.d.' : (v >= 0 ? '+' : '−') + fmtN(Math.abs(v), 1) + ' %';
  };
  var li = R.signalTrack
    .map(function (x) {
      var y = x.yes && (x.yes.m6 || x.yes.m3),
        n = x.no && (x.no.m6 || x.no.m3),
        six = x.yes && x.yes.m6 && x.no && x.no.m6;
      return (
        '<li>' +
        x.icon +
        ' <b>' +
        esc(x.label) +
        '</b> : ' +
        (y && n
          ? sg(y.avg) +
            ' avec, ' +
            sg(n.avg) +
            ' sans (' +
            y.n +
            ' / ' +
            n.n +
            ' lignes, ' +
            (six ? '6' : '3') +
            ' mois)' +
            (x.ok === true ? ' ✅' : x.ok === false ? ' ✗' : '')
          : '<span class="muted">pas encore de recul</span>') +
        '</li>'
      );
    })
    .join('');
  var T = R.revTest,
    rv = T
      ? T.ready
        ? T.verdict === 'confirmee'
          ? '✅ confirmées (' + sg(T.gap) + ' à 3 mois)'
          : "pas d'effet net, piste écartée"
        : T.weeks + ' semaine' + (T.weeks > 1 ? 's' : '') + ' mesurée' + (T.weeks > 1 ? 's' : '') + ' sur ' + T.need
      : 'archive en cours (depuis le 18/10/2026)';
  return (
    '<p class="small"><b>🧪 Les règles en réel</b> <span class="muted">· verdict à 30 lignes de chaque côté à 6 mois</span></p><ul class="plain small">' +
    li +
    '<li>💡 <b>Révisions des analystes</b> (test automatique) : ' +
    rv +
    '</li></ul>'
  );
}
function trackBox(which) {
  var R = rankData(),
    T = R && (which === 'value' ? R.valueTrack : R.pickTrack);
  if (!T) return '';
  var sg = function (v) {
    return v == null ? 'n.d.' : (v >= 0 ? '+' : '−') + fmtN(Math.abs(v), 1) + ' %';
  };
  var tile = function (lbl, g, wait) {
    return (
      '<div class="tk"><small>' +
      lbl +
      '</small>' +
      (g
        ? '<b class="' +
          (g.bench != null && g.avg >= g.bench ? 'pos' : g.avg >= 0 ? '' : 'neg') +
          '">' +
          sg(g.avg) +
          '</b><small>indice ' +
          sg(g.bench) +
          (g.beat != null ? ' · ' + g.beat + ' % le battent' : '') +
          ' · ' +
          g.n +
          ' lignes</small>'
        : '<b class="muted">—</b><small>' + wait + '</small>') +
      '</div>'
    );
  };
  var d3 = ES.addDays(T.since, 91),
    d6 = ES.addDays(T.since, 182);
  return (
    '<div class="trackb"><p class="small"><b>📒 Suivi réel</b> <span class="muted">· depuis le ' +
    shortDate(T.since) +
    ', ' +
    T.weeks +
    ' semaine' +
    (T.weeks > 1 ? 's' : '') +
    ' notée' +
    (T.weeks > 1 ? 's' : '') +
    '</span></p><div class="tks">' +
    tile('En cours', T.open, '') +
    tile('À 3 mois', T.m3, 'dès le ' + shortDate(d3)) +
    tile('À 6 mois', T.m6, 'dès le ' + shortDate(d6)) +
    '</div></div>'
  );
}
/** Sociétés proposées ce soir par le 🎯 (10, règles par défaut), par clé ; calculé une fois par jeu de données. */
function pickSet() {
  var R = rankData();
  if (!R) return {};
  if (S._pkFor !== R) {
    S._pk = {};
    ES.pickN(R.rows || [], { n: 10 }).picks.forEach(function (p) {
      S._pk[p.key] = p;
    });
    S._pkFor = R;
  }
  return S._pk;
}
function rankQuick() {
  return {
    pea: [
      '🇪🇺 PEA seulement',
      function (r) {
        return r.pea !== false;
      },
    ],
    acc: [
      '📊 Comptes solides',
      function (r) {
        return r.acc === 'good';
      },
    ],
    near: [
      '↘️ 2 à 10 % sous le plus haut',
      function (r) {
        return r.ratio != null && r.ratio >= 90 && r.ratio < 98;
      },
    ],
  };
}
/** Critères de tri du classement : [libellé, valeur] (valeur absente = en fin de liste). */
var RSORT = {
  note: [
    'Note',
    function (r) {
      return r.note;
    },
  ],
  trend: [
    '📈 Points de tendance',
    function (r) {
      var p = r.parts || {};
      return (p.mom || 0) + (p.high || 0) + (p.trend || 0);
    },
  ],
  acc: [
    '📊 Points de comptes',
    function (r) {
      return (r.parts || {}).accounts;
    },
  ],
  mom: [
    'Hausse sur 12 mois',
    function (r) {
      return r.mom;
    },
  ],
  high: [
    'Écart au plus haut',
    function (r) {
      return r.ratio == null ? null : r.ratio - 100;
    },
  ],
  slope: [
    'Pente du canal (6 mois)',
    function (r) {
      return r.slope6;
    },
  ],
  liq: [
    'Liquidité (échanges par jour)',
    function (r) {
      return r.liq;
    },
  ],
  name: [
    'Nom',
    function (r) {
      return r.name || '';
    },
  ],
};
function vClassement() {
  if (!rankData()) return vInsRank();
  if (!S.cycle && !S.secLoaded) loadSectors();
  var R = rankData(),
    f = (S.rf = S.rf || {});
  ['quick', 'figures', 'plans', 'timing', 'slope'].forEach(function (k) {
    if (!Array.isArray(f[k])) f[k] = [];
  });
  f.figures = [];
  f.timing = []; // filtres retirés (version allégée) : ne pas garder un ancien choix invisible
  var Q0 = rankQuick();
  f.quick = f.quick.filter(function (k) {
    return Q0[k];
  });
  var Q = rankQuick(),
    q = ES.norm(f.q || ''),
    rows = R.rows;
  var shownV = f.v || (q ? '' : 'in');
  // base(r, sans) : filtres de base ; « sans » ignore la pente ou la sortie de base (pour compter ce que donnerait chaque case)
  var base = function (r, sans) {
    var useBrk = sans === 'brk' ? true : f.brk && sans !== 'brk0';
    if ((sans === 'vol' || (f.vol && sans !== 'vol0')) && !(r.vx >= ES.VOL_SURGE)) return false;
    if (q && ES.norm([r.name, r.sym, r.isin].join(' ')).indexOf(q) < 0) return false;
    if (f.country && r.country !== f.country) return false;
    if (f.sector && r.sector !== f.sector) return false;
    if (sans !== 'slope' && f.slope && f.slope.length && f.slope.indexOf(rkSc(r) || 'none') < 0) return false;
    if (useBrk && !rkBrk(r)) return false;
    // la sortie de base arrive souvent quand le cours est encore dans le tiers faible sur 12 mois : on la montre quand même
    if (shownV === 'in' && r.out.length && !(useBrk && rkBrk(r))) return false;
    if (shownV && shownV !== 'in' && r.v !== shownV) return false;
    return true;
  };
  var plf = function (r) {
    var p = r.plan || {};
    if (f.figures.length && f.figures.indexOf(p.f || 'none') < 0) return false;
    if (f.plans.length && f.plans.indexOf(p.v) < 0) return false;
    if (
      f.timing.length &&
      !f.timing.every(function (k) {
        return (p.t || []).indexOf(k) > -1;
      })
    )
      return false;
    return true;
  };
  var qf = function (r, skip) {
    return f.quick.every(function (k) {
      return k === skip || !Q[k] || Q[k][1](r);
    });
  };
  var list = rows.filter(function (r) {
    return base(r) && qf(r) && plf(r);
  });
  // Tri sur chaque critère affiché, croissant ou décroissant (les sociétés sans valeur et les écartées restent en fin de liste)
  var sk = RSORT[f.sort] ? f.sort : 'note',
    dir = f.dir === 'asc' ? 1 : f.dir === 'desc' ? -1 : sk === 'name' ? 1 : -1,
    get = RSORT[sk][1];
  list.sort(function (a, b) {
    var o = (a.out.length ? 1 : 0) - (b.out.length ? 1 : 0);
    if (o) return o;
    var va = get(a),
      vb = get(b);
    if (va == null || vb == null) return va == null && vb == null ? b.note - a.note : va == null ? 1 : -1;
    var c = typeof va === 'string' ? va.localeCompare(vb, 'fr') : va - vb;
    return c * dir || b.note - a.note;
  });
  var ctry = {},
    secs = {},
    cv = {};
  rows.forEach(function (r) {
    if (r.country) ctry[r.country] = 1;
    if (r.sector) secs[r.sector] = 1;
    cv[r.v] = (cv[r.v] || 0) + 1;
  });
  var h = dashTiles(R, rows);
  h += rankSelCard();
  var psy = psyCard();
  if (psy)
    h +=
      '<details class="card fold psyfold" data-k="psy"><summary>🧠 Marché <span class="muted small">· historique</span></summary>' +
      psy +
      '</details>';
  // « Toutes les sociétés » : un seul pli ; ouvert d'office si une recherche ou un filtre est actif
  var allOn = !!(
    f.q ||
    f.slope.length ||
    f.vol ||
    f.brk ||
    f.quick.length ||
    f.country ||
    f.sector ||
    f.v ||
    f.figures.length ||
    f.plans.length ||
    f.timing.length
  );
  h +=
    '<details class="card fold allfold" data-k="all"' +
    (allOn ? ' open' : '') +
    '><summary>📋 Toutes <span class="muted small">· ' +
    fmtInt((R.counts || {}).ranked || 0) +
    ' sociétés, filtres</span></summary>';
  // filtres rapides, avec le nombre de résultats si l'on coche ce filtre en plus des autres
  var pool = rows.filter(function (r) {
    return base(r) && plf(r);
  });
  h +=
    '<div class="toolbar"><input id="r-q" type="search" placeholder="Rechercher une société" value="' +
    esc(f.q || '') +
    '" data-rf="q" aria-label="Rechercher"></div>';
  // pente du canal haussier : barre toujours visible, cumulable (forte + moyenne par exemple)
  var slN = {};
  rows.forEach(function (r) {
    if (base(r, 'slope') && qf(r) && plf(r)) {
      var k = rkSc(r) || 'none';
      slN[k] = (slN[k] || 0) + 1;
    }
  });
  var brkN = rows.filter(function (r) {
    return base(r, 'brk') && qf(r) && plf(r);
  }).length;
  var volN = rows.filter(function (r) {
    return base(r, 'vol') && qf(r) && plf(r);
  }).length;
  var nF =
    f.slope.length +
    (f.vol ? 1 : 0) +
    (f.brk ? 1 : 0) +
    f.quick.length +
    (f.country ? 1 : 0) +
    (f.sector ? 1 : 0) +
    (f.v ? 1 : 0) +
    f.figures.length +
    f.plans.length +
    f.timing.length;
  h +=
    '<details class="card fold ffold" data-k="rfilt"' +
    (nF ? ' open' : '') +
    '><summary>⚙️ Filtres' +
    (nF
      ? ' <span class="chip good">' + nF + '</span>'
      : ' <span class="muted small">· pente, PEA, pays, secteur…</span>') +
    '</summary>';
  h +=
    '<div class="slbar" role="group" aria-label="Pente du canal haussier"><span class="slt">Pente <span class="muted">· 6 mois</span></span><div class="fchips">' +
    [
      ['strong', '⬆⬆ Forte', '≥ +40 %'],
      ['mid', '⬆ Moyenne', '+15 à +40 %'],
      ['light', '↗ Légère', '< +15 %'],
    ]
      .map(function (o) {
        var on = f.slope.indexOf(o[0]) > -1;
        return (
          '<button class="fchip sl-' +
          o[0] +
          (on ? ' on' : '') +
          '" aria-pressed="' +
          on +
          '" data-a="rfSlope" data-v="' +
          o[0] +
          '"><span aria-hidden="true">' +
          (on ? '☑' : '☐') +
          '</span> ' +
          o[1] +
          ' <small>' +
          o[2] +
          '</small> <span class="count">' +
          (slN[o[0]] || 0) +
          '</span></button>'
        );
      })
      .join('') +
    (f.slope.length ? '<button class="fchip" data-a="rfSlope" data-v="all">Toutes</button>' : '') +
    '</div>' +
    '<span class="slt">Signaux <span class="muted">· hors note</span></span><div class="fchips">' +
    '<button class="fchip' +
    (f.vol ? ' on' : '') +
    '" aria-pressed="' +
    !!f.vol +
    '" data-a="rfVol" title="Volumes des 10 dernières semaines au moins deux fois la moyenne de l\'année"><span aria-hidden="true">' +
    (f.vol ? '☑' : '☐') +
    '</span> 🔊 Volumes ×2 <span class="count">' +
    volN +
    '</span></button>' +
    '<button class="fchip brk' +
    (f.brk ? ' on' : '') +
    '" aria-pressed="' +
    !!f.brk +
    '" data-a="rfBrk" title="Nouveau plus haut sur un an dans les 4 dernières semaines, alors que le cours était à plus de 25 % sous son plus haut il y a 6 mois"><span aria-hidden="true">' +
    (f.brk ? '☑' : '☐') +
    '</span> 🚀 Nouveau plus haut après une base <span class="count">' +
    brkN +
    '</span></button></div>' +
    (f.brk ? brkNote() : '') +
    '<span class="slt">Filtres</span><div class="fchips">' +
    Object.keys(Q)
      .map(function (k) {
        var on = f.quick.indexOf(k) > -1,
          n = pool.filter(function (r) {
            return Q[k][1](r) && qf(r, k);
          }).length;
        return (
          '<button class="fchip' +
          (on ? ' on' : '') +
          '" aria-pressed="' +
          on +
          '" data-a="rfQuick" data-v="' +
          k +
          '"><span aria-hidden="true">' +
          (on ? '☑' : '☐') +
          '</span> ' +
          Q[k][0] +
          ' <span class="count">' +
          n +
          '</span></button>'
        );
      })
      .join('') +
    '</div></div>';
  var nSel = (f.country ? 1 : 0) + (f.sector ? 1 : 0) + (f.v ? 1 : 0);
  h +=
    '<details class="card fold ffold" data-k="rsel"' +
    (nSel ? ' open' : '') +
    '><summary>Pays, secteur, avis' +
    (nSel ? ' <span class="chip good">' + nSel + '</span>' : '') +
    '</summary><div class="toolbar">' +
    '<select data-rf="country" aria-label="Pays"><option value="">Tous les pays</option>' +
    Object.keys(ctry)
      .sort()
      .map(function (c) {
        return (
          '<option value="' +
          c +
          '"' +
          (f.country === c ? ' selected' : '') +
          '>' +
          flagTxt(c) +
          (COUNTRIES[c] || c) +
          '</option>'
        );
      })
      .join('') +
    '</select>' +
    '<select data-rf="sector" aria-label="Secteur"><option value="">Tous les secteurs</option>' +
    Object.keys(secs)
      .sort(function (a, b) {
        return a.localeCompare(b, 'fr');
      })
      .map(function (c) {
        return '<option value="' + esc(c) + '"' + (f.sector === c ? ' selected' : '') + '>' + esc(c) + '</option>';
      })
      .join('') +
    '</select>' +
    '<select data-rf="v" aria-label="Avis"><option value="">Classées (sans les écartées)</option>' +
    ['top', 'good', 'mid', 'out']
      .map(function (k) {
        return (
          '<option value="' +
          k +
          '"' +
          (f.v === k ? ' selected' : '') +
          '>' +
          RV[k][0] +
          ' ' +
          RV[k][1] +
          ' (' +
          (cv[k] || 0) +
          ')</option>'
        );
      })
      .join('') +
    '</select>' +
    '</div></details>';
  // figure, plan d'entrée, repères de timing
  var cf = {},
    cp = {},
    ct = {},
    pool2 = rows.filter(function (r) {
      return base(r) && qf(r);
    });
  pool2.forEach(function (r) {
    var p = r.plan;
    if (!p) return;
    cf[p.f || 'none'] = (cf[p.f || 'none'] || 0) + 1;
    cp[p.v] = (cp[p.v] || 0) + 1;
    (p.t || []).forEach(function (k) {
      ct[k] = (ct[k] || 0) + 1;
    });
  });
  var chip = function (act, k, txt, n, on, tone) {
    return (
      '<button class="fchip ' +
      (tone || '') +
      (on ? ' on' : '') +
      '" aria-pressed="' +
      on +
      '" data-a="' +
      act +
      '" data-v="' +
      k +
      '"><span aria-hidden="true">' +
      (on ? '☑' : '☐') +
      '</span> ' +
      txt +
      ' <span class="count">' +
      (n || 0) +
      '</span></button>'
    );
  };
  var nf = f.figures.length + f.plans.length + f.timing.length;
  h +=
    '<details class="card fold ffold" data-k="rfilters"' +
    (nf ? ' open' : '') +
    "><summary>Plan d'entrée" +
    (nf ? ' <span class="chip good">' + nf + ' filtre' + (nf > 1 ? 's' : '') + '</span>' : '') +
    '</summary>' +
    '<div class="fchips">' +
    PLANS.map(function (o) {
      return chip('rfPlan', o[0], o[1], cp[o[0]], f.plans.indexOf(o[0]) > -1);
    }).join('') +
    '</div>' +
    xpi(
      "2 à 10 % sous le plus haut : aussi bon qu'au plus haut sur 29 ans ; au-delà de 10 %, deux fois plus de chutes."
    ) +
    (nf ? '<button class="link" data-a="rfFClear">Tout décocher</button>' : '') +
    '</details></details>';
  h +=
    '<details class="help"><summary>Légende</summary><ul class="plain small legend">' +
    '<li><b class="big">78</b> note /100 : 🟢 en tête, 🟡 solide, ⚪ moyenne, ⛔ écartée</li>' +
    '<li><span class="rb sl-strong">⬆⬆ +45 %</span> pente du canal sur 6 mois : ⬆⬆ forte (≥ +40 %), ⬆ moyenne, ↗ légère</li>' +
    '<li><span class="rb t-good">🔊 ×2,1</span> volumes des 10 dernières semaines / moyenne de l\'année</li>' +
    '<li><span class="rb t-good">📣 bond</span> semaine à +8 % ou plus avec 3 fois le volume habituel (8 dernières semaines)</li>' +
    '<li><span class="rb t-good">🚀</span> nouveau plus haut après 6 mois de base (signal, hors note)</li>' +
    '<li><span class="rb t-bad">🐻 1,4 %</span> capital vendu à découvert par des fonds : à Paris, écartée du 🎯 (−11,6 pts à 6 mois sur 2013-2026) ; ailleurs signalée</li>' +
    '<li><span class="rb t-warn">⚡ 85 %/an</span> cours très volatil (≥ 80 % par an) : deux fois plus de chutes, écarté du 🎯</li>' +
    "<li><b>12 mois</b> hausse sur un an · <b>Plus haut</b> écart avec le plus haut d'un an</li>" +
    '<li>🎯 ✅ / ⏸ pour les sociétés du 🎯 : feu vert au-dessus de la moyenne 10 semaines, sinon en attente (règle testée) ; ailleurs ✅ ⏳ ⛔ : analyse technique classique</li></ul></details>';
  // barre de tri visible : critère + sens ; en-têtes du tableau cliquables sur grand écran
  h +=
    '<div class="rsort" role="group" aria-label="Trier"><label for="r-sort">Trier par</label><select id="r-sort" data-rf="sort">' +
    Object.keys(RSORT)
      .map(function (k) {
        return '<option value="' + k + '"' + (k === sk ? ' selected' : '') + '>' + RSORT[k][0] + '</option>';
      })
      .join('') +
    '</select>' +
    '<button class="ghost" data-a="rfDir" aria-label="Inverser l\'ordre" title="Inverser l\'ordre">' +
    (dir < 0 ? '↓ décroissant' : '↑ croissant') +
    '</button></div>';
  var th = function (k, label, cls) {
    var on = sk === k;
    return (
      '<th' +
      (cls ? ' class="' + cls + '"' : '') +
      '><button class="thsort' +
      (on ? ' on' : '') +
      '" data-a="rfSort" data-v="' +
      k +
      '">' +
      label +
      (on ? (dir < 0 ? ' ↓' : ' ↑') : '') +
      '</button></th>'
    );
  };
  h +=
    '<div class="tablewrap"><table class="grid cards rtab"><thead><tr>' +
    th('name', 'Société') +
    th('note', 'Note', 'num') +
    th('mom', '12 mois', 'num') +
    th('high', 'Plus haut', 'num') +
    '<th>Entrée</th></tr></thead><tbody>';
  var PK = pickSet();
  list.slice(0, S.limit).forEach(function (r) {
    var pl = r.plan,
      P = pl
        ? PLANS.filter(function (o) {
            return o[0] === pl.v;
          })[0]
        : null,
      F = pl && pl.f && ES.FIGURES[pl.f];
    var sc = rkSc(r),
      bd = [];
    if (r.out.length) bd.push('<span class="rb t-bad">⛔ ' + esc(cap1r(r.out[0]).split(' (')[0]) + '</span>');
    else {
      if (sc && r.slope6 != null)
        bd.push(
          '<span class="rb sl-' +
            sc +
            '" title="Pente du canal haussier sur 6 mois">' +
            SLOPE_TXT[sc][0] +
            ' ' +
            (r.slope6 >= 0 ? '+' : '') +
            r.slope6 +
            ' %</span>'
        );
      if (r.acc === 'good') bd.push('<span class="rb t-good" title="Comptes solides">📊</span>');
    }
    if (bumpOf(r) != null)
      bd.push(
        '<span class="rb t-good" title="Semaine à +8 % ou plus avec 3 fois le volume habituel, ' +
          bumpTxt(bumpOf(r)) +
          '">📣 bond</span>'
      );
    if (r.vx >= ES.VOL_SURGE)
      bd.push(
        '<span class="rb t-good" title="Volumes des 10 dernières semaines / moyenne de l\'année">🔊 ×' +
          String(r.vx).replace('.', ',') +
          '</span>'
      );
    if (rkBrk(r))
      bd.push(
        '<span class="rb t-good" title="Nouveau plus haut sur un an après 6 mois de base">🚀' +
          (r.brk ? ' ' + r.brk + ' sem.' : '') +
          '</span>'
      );
    if (r.vo != null && r.vo >= ES.VOL_WILD * 100)
      bd.push(
        '<span class="rb t-warn" title="Cours très volatil : deux fois plus de chutes, écarté du bouton 🎯">⚡ ' +
          r.vo +
          ' %/an</span>'
      );
    if (r.sh != null && r.sh >= ES.SHORT_MIN)
      bd.push(
        '<span class="rb ' +
          (ES.shortBlocks(r) ? 't-bad' : 't-warn') +
          '" title="Part du capital vendue à découvert par des fonds (positions publiées)">🐻 ' +
          String(r.sh).replace('.', ',') +
          ' %</span>'
      );
    if (r.pea === false) bd.push('<span class="rb t-warn">hors PEA</span>');
    if (r.dj != null)
      bd.push(
        '<span class="rb t-warn" title="Plus de 40 % sur la dernière séance : à vérifier">⚠️ ' +
          (r.dj > 0 ? '+' : '') +
          r.dj +
          ' % hier</span>'
      );
    var V = RV[r.v] || RV.mid;
    h +=
      '<tr class="rowlink" ' +
      rankOpenAttr(r) +
      ' data-from="rank" tabindex="0"><td class="c-name"><b>' +
      flag(r.country) +
      esc(r.name) +
      '</b><small>' +
      esc(r.sector || r.sym || '') +
      '</small>' +
      (bd.length ? '<span class="rbs">' + bd.join('') + '</span>' : '') +
      '</td>' +
      '<td class="num scorecell" data-l="Note"><span class="big nb-' +
      V[2] +
      '" title="' +
      esc(V[1]) +
      '">' +
      r.note +
      '</span></td>' +
      '<td class="num" data-l="12 mois">' +
      (r.mom != null
        ? '<span class="' +
          (r.mom >= 0 ? 'pos' : 'neg') +
          '">' +
          (r.mom >= 0 ? '+' : '−') +
          fmtInt(Math.abs(Math.round(r.mom))) +
          '\u00a0%</span>'
        : '<span class="muted">n.d.</span>') +
      '</td>' +
      '<td class="num" data-l="Plus haut">' +
      (r.ratio != null
        ? r.ratio >= 99.5
          ? '<span class="pos">au top</span>'
          : '<span>−' + Math.round(100 - r.ratio) + '\u00a0%</span>'
        : '<span class="muted">n.d.</span>') +
      '</td>' +
      '<td data-l="Entrée">' +
      (PK[r.key] && ES.pickEntry(r)
        ? '<span class="rplan" title="' +
          esc(ES.pickEntry(r).label) +
          '">🎯 ' +
          ES.pickEntry(r).icon +
          ' ' +
          esc(cap1r(ES.pickEntry(r).short)) +
          '</span>'
        : P
          ? '<span class="rplan" title="' + esc(P[1] + (F ? ' · ' + F[1] : '')) + '">' + esc(P[1]) + '</span>'
          : '') +
      '</td></tr>';
  });
  h += '</tbody></table></div>';
  if (!list.length)
    h += '<p class="muted pad">Aucune société ne correspond.' + (q ? '' : ' Retirez un filtre.') + '</p>';
  if (list.length > S.limit)
    h +=
      '<p class="pad"><button class="ghost" data-a="more">Afficher ' +
      Math.min(100, list.length - S.limit) +
      ' de plus (' +
      list.length +
      ' au total)</button></p>';
  if (q && q.trim().length >= 2) {
    var shown = {};
    list.forEach(function (r) {
      if (r.isin) shown[r.isin] = 1;
      if (r.sym) shown['@' + r.sym] = 1;
    });
    h += coSearch(f.q, shown, 20);
  }
  h +=
    '<p class="small muted pad">Barème ' +
    esc(R.version) +
    ' depuis le ' +
    shortDate(R.since) +
    ' · cours du catalogue du ' +
    shortDate(R.coDate || R.today) +
    ". À étudier, pas un ordre d'achat.</p></details>";
  h +=
    '<p class="foot pad">Résultats automatiques de règles statistiques appliquées à des données publiques : ni conseil en ' +
    'investissement, ni recommandation personnalisée. Les performances passées ne préjugent pas des performances futures ; ' +
    "l'auteur peut détenir des titres cités.</p>";
  return h;
}
function vInsRank() {
  var f = S.filters,
    keys = Object.keys(S.inst).filter(function (i) {
      return !S.inst[i].benchmark;
    });
  if (!keys.length) return emptyState();
  var from7 = ES.addDays(S.today, -7),
    ready = 0,
    recent = 0,
    withBuys = 0,
    topN = 0;
  keys.forEach(function (i) {
    var c = S.computed[i];
    if (c.dec.send) ready++;
    if (c.score.buys.length) withBuys++;
    if (c.score.buys.length && c.score.total >= S.cfg.alerts.minScore && c.uni.status === 'retenu') topN++;
    if (
      c.score.buys.some(function (t) {
        return ES.availDate(t) >= from7;
      })
    )
      recent++;
  });
  var srcs = Object.keys(S.src).map(function (n) {
    return srcState(S.src[n]);
  });
  var srcBad = srcs.filter(function (s) {
    return s.k === 'bad';
  }).length;
  var q = ES.norm(f.q),
    W = S.cfg.weights.insiders;
  var QUICK = {
    buys: [
      'Avec achats de dirigeants',
      function (c) {
        return c.score.buys.length > 0;
      },
    ],
    deep: [
      'Décote ≥ ' + W.discountBigPct + ' %',
      function (c) {
        return c.score.discount && c.score.discount.pct >= W.discountBigPct;
      },
    ],
    dg30: [
      'DG/DAF < ' + ((S.cfg.selection || {}).recentDays || 30) + ' jours',
      function (c, i) {
        var g = dgInfo(i);
        return !!(g && g.recent);
      },
    ],
    conv3: [
      'Convergence ≥ 3 sur 5',
      function (c, i) {
        var v = convOf(i);
        return !!(v && v.n >= 3);
      },
    ],
    secTrend: [
      '🔥 Secteur en tendance',
      function (c, i) {
        var t = secTrendOf(i);
        return !!(t && (t.trending || t.emerging));
      },
    ],
    cycUp: [
      '🔄 Porté par le cycle',
      function (c, i) {
        var f = cycOf(i);
        return !!(f && f.fit === 'up');
      },
    ],
    liq: [
      '💧 Liquide (≥ 1 M€/jour)',
      function (c, i) {
        var q = liqOf(i);
        return !!(q && q.tone === 'good');
      },
    ],
    fs8: [
      'F-score 8 ou 9',
      function (c, i) {
        var a = S.inst[i] && S.inst[i].accounts;
        return !!(a && a.fscore && !a.fscore.na && a.fscore.f9 >= 8);
      },
    ],
    ivCheap: [
      '💎 Sous sa valeur intrinsèque',
      function (c, i) {
        return ES.valueCheap(S.inst[i] && S.inst[i].value);
      },
    ],
    belowBook: [
      '📘 Sous sa valeur comptable',
      function (c, i) {
        var v = S.inst[i] && S.inst[i].value;
        return !!(v && !v.na && !v.negEquity && v.pb != null && v.pb < 1);
      },
    ],
    all: [
      'Tous les titres',
      function () {
        return true;
      },
    ],
  };
  var qsel = (Array.isArray(f.quick) ? f.quick : [f.quick || 'buys']).filter(function (k) {
    return QUICK[k] && k !== 'all';
  });
  var qf = function (c, i) {
    return qsel.every(function (k) {
      return QUICK[k][1](c, i);
    });
  };
  var list = keys.filter(function (i) {
    var x = S.inst[i],
      c = S.computed[i];
    if (q && ES.norm([x.name, x.isin, x.ticker].join(' ')).indexOf(q) < 0) return false;
    if (x.secondary && !q) return false; // ligne secondaire sans cours : seulement par la recherche
    if (f.country && x.country !== f.country) return false;
    if (f.sector && secOf(x) !== f.sector) return false;
    if (f.advice && (!c.score.buys.length || adviceOf(i).key !== f.advice)) return false;
    if (f.figures && f.figures.length && f.figures.indexOf(figOf(i)) < 0) return false;
    if (f.plans && f.plans.length && f.plans.indexOf(planVerdict(i)) < 0) return false;
    if (f.timing && f.timing.length && !timingOk(i, f.timing)) return false;
    return qf(c, i);
  });
  var dv = function (i) {
    var d = S.computed[i].score.discount;
    return d ? d.pct : -999;
  };
  var mv = function (i) {
    var v = S.inst[i] && S.inst[i].value;
    return v && v.marginPct != null ? v.marginPct : -9999;
  };
  var AVR = { priority: 0, watch: 1, wait: 2, avoid: 3 },
    av = function (i) {
      var a = adviceOf(i);
      return a && AVR[a.key] != null ? AVR[a.key] : 4;
    };
  var sorters = {
    advice: function (a, b) {
      return av(a) - av(b) || S.computed[b].score.total - S.computed[a].score.total;
    },
    discount: function (a, b) {
      return dv(b) - dv(a) || S.computed[b].score.total - S.computed[a].score.total;
    },
    value: function (a, b) {
      return mv(b) - mv(a) || S.computed[b].score.total - S.computed[a].score.total;
    },
    score: function (a, b) {
      return S.computed[b].score.total - S.computed[a].score.total;
    },
    event: function (a, b) {
      return (S.computed[b].score.lastEventDate || '') < (S.computed[a].score.lastEventDate || '') ? -1 : 1;
    },
    name: function (a, b) {
      return (S.inst[a].name || a).localeCompare(S.inst[b].name || b, 'fr');
    },
  };
  list.sort(sorters[f.sort] || sorters.advice);
  var ctry = {},
    secs = {};
  keys.forEach(function (i) {
    if (S.inst[i].country) ctry[S.inst[i].country] = 1;
    var sc = secOf(S.inst[i]);
    if (sc && qf(S.computed[i], i)) secs[sc] = (secs[sc] || 0) + 1;
  });
  var h =
    '<section class="hero"><h2>Où les dirigeants achètent-ils ?</h2>' +
    (rankData()
      ? '<p class="small">Ancien classement, fondé sur les achats de dirigeants : conservé pour comparaison jusqu\'à la revue du 31/01/2027. La sélection du lundi vient du classement tendance + comptes.</p>'
      : '') +
    '<p><button type="button" class="linkbtn" data-a="guide">📖 Lire une fiche en 30 s</button> · <button type="button" class="linkbtn" data-a="proof">Méthode et résultats →</button></p></section>';
  h +=
    '<section class="summary">' +
    (S.cfg.alerts.buyEmails === false
      ? stat(
          'Très forts ★★★★',
          String(topN),
          topN ? 'note ≥ ' + ES.note(S.cfg.alerts.minScore, S.cfg) : "aucun aujourd'hui",
          'classement',
          topN ? 'good' : ''
        )
      : stat(
          'Alertes prêtes',
          String(ready),
          ready ? 'à regarder en priorité' : "aucune aujourd'hui",
          'alertes',
          ready ? 'good' : ''
        )) +
    stat(
      'Achats cette semaine',
      String(recent),
      withBuys + ' sur ' + S.cfg.insiders.windowMonths + ' mois',
      'inities'
    ) +
    '</section>' +
    (srcBad
      ? '<p class="mood mood-fear"><b>⚠️ ' +
        srcBad +
        ' source(s) de données en échec</b> — détail dans Aide → État des données.</p>'
      : '');
  var mood = S.snapshot && S.snapshot.market && S.snapshot.market.mood;
  if (mood && (mood.key === 'fear' || mood.key === 'greed'))
    h +=
      '<p class="mood mood-' +
      esc(mood.key) +
      '"><b>' +
      mood.icon +
      ' Humeur du marché : ' +
      esc(mood.label) +
      '</b> — ' +
      esc(mood.text) +
      '</p>';
  if (!S.cycle && !S.secLoaded) loadSectors();
  h += cycleCard(true);
  h += selectionCard();
  h +=
    '<div class="segs" role="group" aria-label="Filtres rapides">' +
    Object.keys(QUICK)
      .map(function (k) {
        // nombre de résultats si l'on coche ce filtre, en plus de ceux déjà cochés (jamais « 15 » puis une liste vide)
        var others = qsel.filter(function (o) {
          return o !== k;
        });
        var n =
          k === 'all'
            ? keys.length
            : keys.filter(function (i) {
                var c = S.computed[i];
                return (
                  QUICK[k][1](c, i) &&
                  others.every(function (o) {
                    return QUICK[o][1](c, i);
                  })
                );
              }).length;
        var on = k === 'all' ? !qsel.length : qsel.indexOf(k) > -1;
        return (
          '<button class="' +
          (on ? 'on' : '') +
          '" aria-pressed="' +
          on +
          '" data-a="quick" data-v="' +
          k +
          '">' +
          (k === 'all' ? '' : '<span class="box" aria-hidden="true">' + (on ? '☑' : '☐') + '</span> ') +
          QUICK[k][0] +
          ' <span class="count">' +
          n +
          '</span></button>'
        );
      })
      .join('') +
    '</div>';
  var nSel = (f.country ? 1 : 0) + (f.sector ? 1 : 0) + (f.advice ? 1 : 0) + (f.sort && f.sort !== 'advice' ? 1 : 0);
  h +=
    '<div class="toolbar"><input id="f-q" type="search" placeholder="Rechercher une société" value="' +
    esc(f.q) +
    '" data-f="q" aria-label="Rechercher"></div>' +
    '<details class="card fold ffold" data-k="fsel"' +
    (nSel ? ' open' : '') +
    '><summary>Pays, secteur, avis, tri' +
    (nSel ? ' <span class="chip good">' + nSel + '</span>' : '') +
    '</summary><div class="toolbar">' +
    '<select id="f-country" data-f="country" aria-label="Pays"><option value="">Tous les pays</option>' +
    Object.keys(ctry)
      .sort()
      .map(function (c) {
        return (
          '<option value="' +
          c +
          '"' +
          (f.country === c ? ' selected' : '') +
          '>' +
          flagTxt(c) +
          (COUNTRIES[c] || c) +
          '</option>'
        );
      })
      .join('') +
    '</select>' +
    '<select id="f-sector" data-f="sector" aria-label="Secteur"><option value="">Tous les secteurs</option>' +
    Object.keys(secs)
      .sort(function (a, b) {
        return a.localeCompare(b, 'fr');
      })
      .map(function (c) {
        return (
          '<option value="' +
          esc(c) +
          '"' +
          (f.sector === c ? ' selected' : '') +
          '>' +
          esc(c) +
          ' (' +
          secs[c] +
          ')</option>'
        );
      })
      .join('') +
    '</select>' +
    (function () {
      var AV = [
          ['priority', '🟢 À étudier en priorité'],
          ['watch', '🟡 À surveiller'],
          ['avoid', "🔴 Éviter pour l'instant"],
          ['wait', '⚪ Attendre'],
        ],
        cnt = {};
      keys.forEach(function (i) {
        var c = S.computed[i];
        if (c.score.buys.length && qf(c, i)) {
          var k = adviceOf(i).key;
          cnt[k] = (cnt[k] || 0) + 1;
        }
      });
      return (
        '<select id="f-advice" data-f="advice" aria-label="Avis"><option value="">Tous les avis</option>' +
        AV.map(function (o) {
          return (
            '<option value="' +
            o[0] +
            '"' +
            (f.advice === o[0] ? ' selected' : '') +
            '>' +
            o[1] +
            ' (' +
            (cnt[o[0]] || 0) +
            ')</option>'
          );
        }).join('') +
        '</select>'
      );
    })() +
    '<select id="f-sort" data-f="sort" aria-label="Tri">' +
    [
      ['advice', "Trier par avis (🟢 d'abord)"],
      ['discount', 'Trier par décote'],
      ['value', 'Trier par marge de sécurité'],
      ['score', 'Trier par note'],
      ['event', 'Trier par date'],
      ['name', 'Trier par nom'],
    ]
      .map(function (o) {
        return (
          '<option value="' + o[0] + '"' + ((f.sort || 'advice') === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'
        );
      })
      .join('') +
    '</select></div></details>';
  h += (function () {
    var cf = {},
      cp = {},
      ct = {},
      any = false,
      seen = 0;
    keys.forEach(function (i) {
      if (!qf(S.computed[i], i)) return;
      seen++;
      var k = figOf(i),
        v = planVerdict(i);
      if (k) {
        cf[k] = (cf[k] || 0) + 1;
        any = true;
      }
      if (v) cp[v] = (cp[v] || 0) + 1;
      var pl = planFor(i);
      if (pl)
        TIMING.forEach(function (t) {
          if (t[2](pl)) ct[t[0]] = (ct[t[0]] || 0) + 1;
        });
    });
    if (!any) {
      if (!seen) return ''; // aucune société avec ces filtres : rien à annoncer
      if (S.mode === 'remote' && !S.detailLoaded)
        return (
          '<details class="card fold ffold" data-k="ffilters" open><summary>Tendance et plan d\'entrée</summary><p class="small">' +
          (S.detailLoading
            ? 'Calcul des tendances à partir des cours… (quelques secondes)'
            : "Les tendances (canal haussier, canal baissier, biseau…) et les plans d'entrée seront calculés automatiquement dès ce soir. Pour les obtenir tout de suite, je les calcule à partir des cours :") +
          '</p>' +
          (S.detailLoading
            ? ''
            : '<button class="primary" data-a="figLoad">Calculer les tendances maintenant</button>') +
          '</details>'
        );
      return '<p class="muted small">Tendances indisponibles : cours non chargés pour ces sociétés.</p>';
    }
    var chip = function (act, k, txt, n, on, tone) {
      return (
        '<button class="fchip ' +
        (tone || '') +
        (on ? ' on' : '') +
        '" aria-pressed="' +
        on +
        '" data-a="' +
        act +
        '" data-v="' +
        k +
        '"><span aria-hidden="true">' +
        (on ? '☑' : '☐') +
        '</span> ' +
        txt +
        ' <span class="count">' +
        (n || 0) +
        '</span></button>'
      );
    };
    var nf = (f.figures || []).length + (f.plans || []).length + (f.timing || []).length;
    return (
      '<details class="card fold ffold" data-k="ffilters"' +
      (nf ? ' open' : '') +
      "><summary>Tendance et plan d'entrée" +
      (nf ? ' <span class="chip good">' + nf + ' filtre' + (nf > 1 ? 's' : '') + '</span>' : '') +
      '</summary>' +
      '<div class="fchips">' +
      Object.keys(ES.FIGURES)
        .map(function (k) {
          var F = ES.FIGURES[k];
          return chip('figT', k, F[0] + ' ' + F[1], cf[k], (f.figures || []).indexOf(k) > -1, F[2]);
        })
        .join('') +
      '</div>' +
      '<div class="fchips">' +
      PLANS.map(function (o) {
        return chip('planT', o[0], o[1], cp[o[0]], (f.plans || []).indexOf(o[0]) > -1);
      }).join('') +
      '</div>' +
      '<p class="small fgrp">⏱️ Repères de timing <span class="muted">(cumulables : tous doivent être vrais)</span></p><div class="fchips">' +
      TIMING.map(function (t) {
        return chip('timT', t[0], t[1], ct[t[0]], (f.timing || []).indexOf(t[0]) > -1, 'good').replace(
          '<button ',
          '<button title="' + esc(t[3]) + '" '
        );
      }).join('') +
      '</div>' +
      xpi(
        "Une société est gardée si elle correspond à l'une des tendances cochées <b>et</b> à l'un des plans cochés <b>et</b> à tous les repères de timing cochés. Les repères de timing servent à choisir le moment d'entrée sur un dossier déjà bon, pas à choisir la société ; leur effet est mesuré dans le journal de bord."
      ) +
      (nf ? '<button class="link" data-a="fClear">Tout décocher</button>' : '') +
      '</details>'
    );
  })();
  h +=
    '<details class="help"><summary>Comment lire ce tableau ?</summary><ul class="plain">' +
    '<li><b>Feux</b> : 👔 dirigeants · 💎 valeur · 📊 comptes · 📈 tendance · 🔥 secteur · 🔄 cycle · 💧 liquidité · 🧭 moment d\'achat. <span class="t-good">●</span> favorable, <span class="t-mid">●</span> à surveiller, <span class="t-bad">●</span> défavorable, gris : inconnu.</li>' +
    '<li><b>Décote</b> : de combien le prix payé par le dirigeant était sous le plus haut des 52 semaines. <span class="disc deep">−40 % et plus</span> <span class="disc mid">−25 à −40 %</span> <span class="disc low">moins de −25 %</span></li>' +
    "<li><b>Prix payé / cours</b> : sur la barre des 52 dernières semaines (plus bas à gauche, plus haut à droite), ○ = prix payé par le dirigeant, ■ = cours actuel. Carré à droite du rond : le cours a monté depuis l'achat.</li>" +
    "<li><b>Depuis l'achat</b> : évolution du cours depuis le prix payé.</li>" +
    '<li><b>Note /100</b> : force du signal (initiés, rachats, résultats, tendance). Très fort à partir de ' +
    ES.note(S.cfg.alerts.minScore, S.cfg) +
    ". L'avis, lui, tient compte des risques.</li>" +
    '<li><b>Attention</b> : une forte décote ne garantit pas le point bas. En 2026, le DG de Rheinmetall a acheté à −21 %, −37 % et −42 % avant de nouvelles baisses ; seul son achat à −52 %, au plus bas, a rapporté rapidement.</li></ul></details>';
  h +=
    '<div class="tablewrap"><table class="grid cards"><thead><tr><th>Société</th><th>Décote</th><th>Prix payé <span class="lg-dot">○</span> / cours <span class="lg-sq">■</span></th><th class="num">Depuis l\'achat</th><th class="num">Note</th><th>Avis</th></tr></thead><tbody>';
  list.slice(0, S.limit).forEach(function (i) {
    var x = S.inst[i],
      c = S.computed[i],
      d = c.score.discount,
      r = d && (S.refs[i] || {})[d.id];
    var who = d
      ? 'payé ' +
        fmtN(d.paid) +
        ' le ' +
        shortDate(d.date) +
        ' · ' +
        esc(shortName(d.person)) +
        (d.ceo ? ' (DG/DAF)' : '')
      : c.score.buys.length
        ? c.score.buys.length + ' achat(s), cours indisponibles'
        : 'aucun achat récent';
    h +=
      '<tr class="rowlink" data-a="open" data-i="' +
      i +
      '" tabindex="0"><td class="c-name"><b>' +
      flag(x.country) +
      esc(x.name || i) +
      '</b><small>' +
      esc([x.ticker, secOf(x)].filter(Boolean).join(' · ') || i) +
      '</small>' +
      feuxHtml(i) +
      '</td>' +
      '<td data-l="Décote">' +
      discPill(d) +
      '<small>' +
      who +
      '</small></td>' +
      '<td data-l="Payé ○ / cours ■">' +
      rangeBar(
        r && r.today && r.today.paidPos52 != null ? r.today.paidPos52 : d && d.pos52,
        r && r.today ? r.today.currentPos52 : null
      ) +
      '</td>' +
      '<td class="num" data-l="Depuis l\'achat">' +
      (r && r.available && !r.outOfRange
        ? '<span class="' + (r.currentVsPaidPct >= 0 ? 'pos' : 'neg') + '">' + pct(r.currentVsPaidPct) + '</span>'
        : '<span class="muted">n.d.</span>') +
      '</td>' +
      '<td class="num scorecell" data-l="Note">' +
      (c.score.buys.length ? starsHtml(c.score.total) : '') +
      '<span class="big">' +
      ES.note(c.score.total, S.cfg) +
      '</span></td>' +
      '<td data-l="Avis">' +
      (c.score.buys.length ? advBadge(adviceOf(i)) + dgChip(i) : statusChip(i)) +
      '</td></tr>';
  });
  h += '</tbody></table></div>';
  if (!list.length) h += '<p class="muted pad">Aucune société ne correspond. Essayez « Tous les titres ».</p>';
  if (list.length > S.limit)
    h +=
      '<p class="pad"><button class="ghost" data-a="more">Afficher ' +
      Math.min(100, list.length - S.limit) +
      ' de plus (' +
      list.length +
      ' au total)</button></p>';
  // une recherche porte aussi sur toutes les sociétés cotées, même sans achat de dirigeant (TotalEnergies, Vusion…)
  if (f.q && f.q.trim().length >= 2) {
    var shown = {};
    list.forEach(function (i) {
      shown[i] = 1;
    });
    h += coSearch(f.q, shown, 20);
  }
  return h;
}
function stat(label, big, small, view, kind) {
  return (
    '<button class="stat ' +
    (kind || '') +
    '" data-a="view" data-v="' +
    view +
    '"><span class="lbl">' +
    label +
    '</span><span class="val">' +
    big +
    '</span><span class="sub">' +
    small +
    '</span></button>'
  );
}
function emptyState() {
  return '<div class="empty"><h2>Aucun titre pour l\'instant</h2><p>Les données du jour ne contiennent encore aucune déclaration. Revenez après le passage du soir.</p></div>';
}
