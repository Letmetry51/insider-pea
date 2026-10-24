/* Euro Signal — interface : actions (clics, saisies) et démarrage.
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
/* =========================== Actions =========================== */
document.addEventListener('click', function (ev) {
  var el = ev.target.closest('[data-a]');
  if (!el) return;
  var a = el.dataset.a,
    i = el.dataset.i;
  if (el.tagName === 'A') return;
  ev.preventDefault();
  if (a === 'view') {
    var ret = (S.view === 'fiche' || S.view === 'secco') && S.back && S.back.view === el.dataset.v; // onglet depuis une fiche : retour à la liste, au même endroit
    if (ret && S.pushed && location.hash) {
      S.pushed = false;
      history.back();
      return;
    } // l'écouteur hashchange rétablit la liste
    S.view = el.dataset.v;
    S.limit = ret ? Math.max(50, S.back.limit || 50) : 50;
    if (location.hash) history.replaceState(null, '', location.pathname + location.search);
    render();
    if (ret) restoreBack();
    else window.scrollTo(0, 0);
  } else if (a === 'secPlan') {
    S.secOpen = S.secOpen || {};
    S.secOpen[el.dataset.v] = !S.secOpen[el.dataset.v];
    var ys2 = window.scrollY;
    render();
    window.scrollTo(0, ys2);
  } else if (a === 'range') {
    S.range = el.dataset.v === '5y' ? '5y' : '1y';
    try {
      localStorage.setItem('es-range', S.range);
    } catch (e) {}
    var yr = window.scrollY;
    render();
    window.scrollTo(0, yr);
  } else if (a === 'pfCore') {
    S.pfCore = el.dataset.v === '1';
    var yy = window.scrollY;
    render();
    window.scrollTo(0, yy);
  } else if (a === 'methH') {
    S.methH = +el.dataset.v;
    var ym = window.scrollY;
    render();
    window.scrollTo(0, ym);
  } else if (a === 'proofH') {
    S.proofH = +el.dataset.v;
    var y = window.scrollY;
    render();
    window.scrollTo(0, y);
  } else if (a === 'guide') {
    S.view = 'aide';
    render();
    var gd = document.getElementById('logique');
    if (gd) gd.scrollIntoView();
  } else if (a === 'goto') {
    var tg = el.dataset.v,
      node =
        tg.charAt(0) === '.'
          ? document.querySelector(tg)
          : [].slice
              .call(document.querySelectorAll('details.fold > summary'))
              .filter(function (sm) {
                return sm.textContent.indexOf(tg) > -1;
              })
              .map(function (sm) {
                return sm.parentNode;
              })[0];
    if (node) {
      // ouvre le pli visé et ceux qui le contiennent (le plan d'entrée est dans le pli des cours)
      for (var pn = node; pn; pn = pn.parentElement) if (pn.tagName === 'DETAILS') pn.open = true;
      node.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } else if (a === 'proof') {
    S.view = 'aide';
    render();
    var pr = document.getElementById('preuves');
    if (pr) pr.scrollIntoView();
  } else if (a === 'secCo') {
    var fromRank = el.dataset.from === 'rank' || (S.view === 'classement' && !el.dataset.from);
    if (S.view === 'secteurs') S.secScroll = window.scrollY;
    if (fromRank) {
      S.back = { view: 'classement', y: window.scrollY, i: el.dataset.v, limit: S.limit };
      try {
        history.pushState(null, '', '#co=' + encodeURIComponent(el.dataset.v));
        S.pushed = true;
      } catch (e) {}
    } else if (S.view !== 'secco') S.secFrom = null;
    if (fromRank) S.secFrom = 'classement';
    S.secSym = el.dataset.v;
    S.view = 'secco';
    S.ficheFrom = null;
    render();
    window.scrollTo(0, 0);
  } else if (a === 'rankMode') {
    S.rankMode = el.dataset.v === 'ins' ? 'ins' : 'rank';
    S.limit = 50;
    try {
      localStorage.setItem('es-rankmode', S.rankMode);
    } catch (e) {}
    render();
  } else if (a === 'rfDir') {
    S.rf = S.rf || {};
    var dsk = RSORT[S.rf.sort] ? S.rf.sort : 'note',
      cur0 = S.rf.dir || (dsk === 'name' ? 'asc' : 'desc');
    S.rf.dir = cur0 === 'asc' ? 'desc' : 'asc';
    S.limit = 50;
    var yd = window.scrollY;
    render();
    window.scrollTo(0, yd);
  } else if (a === 'rfSort') {
    S.rf = S.rf || {};
    var nk = el.dataset.v,
      ck = RSORT[S.rf.sort] ? S.rf.sort : 'note';
    if (nk === ck) {
      var c1 = S.rf.dir || (ck === 'name' ? 'asc' : 'desc');
      S.rf.dir = c1 === 'asc' ? 'desc' : 'asc';
    } else {
      S.rf.sort = nk;
      S.rf.dir = nk === 'name' ? 'asc' : 'desc';
    }
    S.limit = 50;
    var ys = window.scrollY;
    render();
    window.scrollTo(0, ys);
  } else if (a === 'rfVol') {
    S.rf = S.rf || {};
    S.rf.vol = !S.rf.vol;
    S.limit = 50;
    var yvo = window.scrollY;
    render();
    window.scrollTo(0, yvo);
  } else if (a === 'rfBrk') {
    S.rf = S.rf || {};
    S.rf.brk = !S.rf.brk;
    S.limit = 50;
    var ybk = window.scrollY;
    render();
    window.scrollTo(0, ybk);
  } else if (a === 'secOpen') {
    S.openDet = S.openDet || {};
    S.openDet[el.dataset.v] = true;
    render();
    var so = document.querySelector('details[data-k="' + el.dataset.v + '"]');
    if (so) so.scrollIntoView({ block: 'start' });
  } else if (a === 'psyOpen') {
    S.openDet = S.openDet || {};
    S.openDet.psy = true;
    render();
    var pf = document.querySelector('.psyfold');
    if (pf) pf.scrollIntoView({ block: 'start' });
  } else if (a === 'valueOpen') {
    S.openDet = S.openDet || {};
    S.openDet.buy = true;
    render();
    var vc = document.querySelector('.selc');
    if (vc) vc.scrollIntoView({ block: 'start' });
  } else if (a === 'pick3') {
    S.openDet = S.openDet || {};
    S.openDet.buy = true;
    render();
    var pc3 = document.querySelector('.selc');
    if (pc3) pc3.scrollIntoView({ block: 'start' });
  } else if (a === 'weekBrk') {
    S.rf = S.rf || {};
    S.rf.brk = true;
    S.rf.slope = ['strong'];
    S.limit = 50;
    render();
    var sb = document.querySelector('.slbar');
    if (sb) sb.scrollIntoView({ block: 'start' });
  } else if (a === 'rfSlope') {
    S.rf = S.rf || {};
    var cs = Array.isArray(S.rf.slope) ? S.rf.slope : [],
      vs = el.dataset.v;
    S.rf.slope =
      vs === 'all'
        ? []
        : cs.indexOf(vs) > -1
          ? cs.filter(function (x) {
              return x !== vs;
            })
          : cs.concat([vs]);
    S.limit = 50;
    var ysl = window.scrollY;
    render();
    window.scrollTo(0, ysl);
  } else if (a === 'rfQuick') {
    S.rf = S.rf || {};
    var cq = Array.isArray(S.rf.quick) ? S.rf.quick : [],
      vq = el.dataset.v;
    S.rf.quick =
      vq === 'all'
        ? []
        : cq.indexOf(vq) > -1
          ? cq.filter(function (x) {
              return x !== vq;
            })
          : cq.concat([vq]);
    S.limit = 50;
    var yk = window.scrollY;
    render();
    window.scrollTo(0, yk);
  } else if (a === 'rfFig' || a === 'rfPlan' || a === 'rfTim') {
    S.rf = S.rf || {};
    var kk = a === 'rfFig' ? 'figures' : a === 'rfPlan' ? 'plans' : 'timing',
      ar = Array.isArray(S.rf[kk]) ? S.rf[kk].slice() : [],
      ix2 = ar.indexOf(el.dataset.v);
    if (ix2 > -1) ar.splice(ix2, 1);
    else ar.push(el.dataset.v);
    S.rf[kk] = ar;
    S.limit = 50;
    var yr2 = window.scrollY;
    render();
    window.scrollTo(0, yr2);
  } else if (a === 'rfFClear') {
    S.rf.figures = [];
    S.rf.plans = [];
    S.rf.timing = [];
    S.limit = 50;
    var yc2 = window.scrollY;
    render();
    window.scrollTo(0, yc2);
  } else if (a === 'rfToggle') {
    S.rf = S.rf || {};
    S.rf[el.dataset.v] = !S.rf[el.dataset.v];
    S.limit = 50;
    var yq = window.scrollY;
    render();
    window.scrollTo(0, yq);
  } else if (a === 'rfV') {
    S.rf = S.rf || {};
    S.rf.v = S.rf.v === el.dataset.v ? '' : el.dataset.v;
    S.limit = 50;
    var yv = window.scrollY;
    render();
    window.scrollTo(0, yv);
  } else if (a === 'rankWhy') {
    S.view = 'aide';
    S.openDet = S.openDet || {};
    S.openDet['aide-rank'] = true;
    if (location.hash) history.replaceState(null, '', location.pathname + location.search);
    render();
    var rw = document.getElementById('logique');
    if (rw) rw.scrollIntoView();
  } else if (a === 'secBack') {
    if (
      S.view === 'fiche' &&
      S.ficheFrom === 'secco' &&
      S.pushed &&
      location.hash &&
      S.back &&
      S.back.view === 'secco'
    ) {
      S.pushed = false;
      history.back();
    } else if (S.view === 'fiche' && S.ficheFrom === 'secco') {
      S.view = 'secco';
      S.ficheFrom = null;
      render();
      window.scrollTo(0, 0);
    } else if (S.view === 'secco' && S.secFrom === 'classement') {
      if (S.pushed && location.hash) {
        S.pushed = false;
        history.back();
        return;
      }
      S.view = 'classement';
      S.secFrom = null;
      render();
      restoreBack();
    } else {
      S.view = 'secteurs';
      S.ficheFrom = null;
      render();
      window.scrollTo(0, S.secScroll || 0);
    }
  } else if (a === 'open') {
    var fromList = S.view !== 'fiche' && S.view !== 'person';
    if (fromList) S.back = { view: S.view, y: window.scrollY, i: i, limit: S.limit };
    S.ficheFrom = el.dataset.from || null;
    S.sel = i;
    S.view = 'fiche';
    // depuis une liste : nouvelle entrée d'historique, pour que le geste « retour » du téléphone revienne à la liste
    try {
      if (fromList && !location.hash) {
        history.pushState(null, '', '#' + i);
        S.pushed = true;
      } else history.replaceState(null, '', '#' + i);
    } catch (e) {}
    render();
    window.scrollTo(0, 0);
  } else if (a === 'person') {
    if (!S.ins) S.insError = null;
    S.personKey = el.dataset.k;
    S.personBack = S.view === 'dirigeant' ? S.personBack : S.view;
    S.view = 'dirigeant';
    S.personAll = false;
    loadInsiders();
    render();
    window.scrollTo(0, 0);
  } else if (a === 'personAll') {
    S.personAll = true;
    var yp = window.scrollY;
    render();
    window.scrollTo(0, yp);
  } else if (a === 'more') {
    S.limit += 100;
    render();
  } else if (a === 'quick') {
    var cur = Array.isArray(S.filters.quick) ? S.filters.quick.slice() : [S.filters.quick || 'buys'],
      v = el.dataset.v,
      at = cur.indexOf(v);
    S.filters.quick =
      v === 'all'
        ? []
        : at > -1
          ? cur.filter(function (x) {
              return x !== v && x !== 'all';
            })
          : cur
              .filter(function (x) {
                return x !== 'all';
              })
              .concat([v]);
    S.limit = 50;
    yq = window.scrollY;
    render();
    window.scrollTo(0, yq);
  } else if (a === 'figT' || a === 'planT' || a === 'timT') {
    var key = a === 'figT' ? 'figures' : a === 'planT' ? 'plans' : 'timing',
      arr = (S.filters[key] || []).slice(),
      w = el.dataset.v,
      ix = arr.indexOf(w);
    if (ix > -1) arr.splice(ix, 1);
    else arr.push(w);
    S.filters[key] = arr;
    S.limit = 50;
    var yf = window.scrollY;
    render();
    window.scrollTo(0, yf);
  } else if (a === 'figLoad') {
    loadDetail();
    var yl = window.scrollY;
    render();
    window.scrollTo(0, yl);
  } else if (a === 'fClear') {
    S.filters.figures = [];
    S.filters.plans = [];
    S.filters.timing = [];
    S.limit = 50;
    var yc = window.scrollY;
    render();
    window.scrollTo(0, yc);
  } else if (a === 'posBuy' || a === 'posSell') posMail(i, a === 'posBuy' ? 'buy' : 'sell');
  else if (a === 'watchOn' || a === 'watchOff') watchMail(i, a === 'watchOn');
  else if (a === 'planSave' || a === 'planReset') {
    // ✏️ plan ajusté à la main : entrée, stop, objectif (stop < entrée < objectif), gardé sur l'appareil
    var watched = !!lsGet('watch.' + i, ''),
      upd = ' Touchez «\u00a0Mettre à jour\u00a0» (🔔) pour que les alertes du soir suivent.';
    if (a === 'planReset') {
      try {
        window.localStorage.removeItem('es.plan.' + i);
      } catch (e) {}
      notify('Retour au plan calculé.' + (watched ? upd : ''), 'ok');
    } else {
      var box = el.closest('.planadj'), // plusieurs plans peuvent être ouverts sur la même page (onglet Secteurs)
        gv = function (k) {
          var e = box && box.querySelector('[data-pl="' + k + '"]');
          return e ? ES.parseNumber(String(e.value || '').trim()) : null;
        },
        pe = gv('e'),
        ps = gv('s'),
        pt = gv('t');
      if (!(pe > 0)) return notify("Indiquez un prix d'entrée.", 'warn');
      if (ps != null && !(ps > 0 && ps < pe)) return notify("Le stop doit être sous le prix d'entrée.", 'warn');
      if (pt != null && !(pt > pe)) return notify("L'objectif doit être au-dessus du prix d'entrée.", 'warn');
      lsSet(
        'plan.' + i,
        JSON.stringify({ e: pe, s: ps || null, t: pt || null, ref: +el.dataset.last || null, at: S.today })
      );
      notify('Plan enregistré sur cet appareil.' + (watched ? upd : ''), 'ok');
    }
    var ypl = window.scrollY;
    render();
    window.scrollTo(0, ypl);
  } else if (a === 'uni') {
    S.uniFilter = el.dataset.v;
    render();
  }
});
document.addEventListener(
  'toggle',
  function (ev) {
    var d = ev.target;
    if (!(d && d.tagName === 'DETAILS' && d.dataset && d.dataset.k)) return;
    S.openDet = S.openDet || {};
    S.openDet[d.dataset.k] = d.open;
    if (d.open && d.classList.contains('lazy')) {
      var y = window.scrollY;
      render();
      window.scrollTo(0, y);
    } // contenu construit à la première ouverture
  },
  true
);
document.addEventListener('change', function (ev) {
  var t = ev.target;
  if (t.dataset.f) {
    S.filters[t.dataset.f] = t.type === 'checkbox' ? t.checked : t.value;
    S.limit = 50;
    render();
    return;
  }
  if (t.dataset.rf && t.dataset.rf !== 'q') {
    S.rf = S.rf || {};
    S.rf[t.dataset.rf] = t.value;
    if (t.dataset.rf === 'sort') S.rf.dir = t.value === 'name' ? 'asc' : 'desc';
    S.limit = 50;
    render();
    return;
  }
  if (t.dataset.tf && t.dataset.tf !== 'q') {
    S.txFilter[t.dataset.tf] = t.value;
    S.limit = 50;
    render();
  }
});
document.addEventListener('input', function (ev) {
  var t = ev.target;
  if (t.dataset.tf === 'q') {
    S.txFilter.q = t.value;
    S.limit = 50;
    clearTimeout(t._tm);
    t._tm = setTimeout(function () {
      var pos = t.selectionStart;
      render();
      var n = $('#t-q');
      if (n) {
        n.focus();
        try {
          n.setSelectionRange(pos, pos);
        } catch (e) {}
      }
    }, 250);
    return;
  }
  if (t.dataset.rf === 'q') {
    S.rf = S.rf || {};
    S.rf.q = t.value;
    S.limit = 50;
    clearTimeout(t._tm);
    t._tm = setTimeout(function () {
      var pos = t.selectionStart;
      render();
      var n = $('#r-q');
      if (n) {
        n.focus();
        try {
          n.setSelectionRange(pos, pos);
        } catch (e) {}
      }
    }, 250);
    return;
  }
  if (t.dataset.sq === 'q') {
    S.secQ = t.value;
    clearTimeout(t._tm);
    t._tm = setTimeout(function () {
      var pos = t.selectionStart;
      render();
      var n = $('#sec-q');
      if (n) {
        n.focus();
        try {
          n.setSelectionRange(pos, pos);
        } catch (e) {}
      }
    }, 250);
    return;
  }
  if (t.dataset.f === 'q') {
    S.filters.q = t.value;
    clearTimeout(t._tm);
    t._tm = setTimeout(function () {
      var pos = t.selectionStart;
      render();
      var n = $('#f-q');
      if (n) {
        n.focus();
        try {
          n.setSelectionRange(pos, pos);
        } catch (e) {}
      }
    }, 250);
  }
});
// Portefeuille simulé : réticule et infobulle au survol
document.addEventListener('mousemove', function (ev) {
  var hit = ev.target.closest && ev.target.closest('.pf-hit');
  var wrap = hit && hit.closest('.pfwrap');
  document.querySelectorAll('.pfwrap').forEach(function (w) {
    if (w !== wrap) {
      var t = w.querySelector('.pftip');
      if (t) t.hidden = true;
      var x = w.querySelector('.pf-x');
      if (x) x.style.display = 'none';
    }
  });
  if (!hit || !S.pfPts) return;
  var svg = hit.ownerSVGElement,
    box = svg.getBoundingClientRect(),
    W = +hit.dataset.w,
    L = +hit.dataset.l,
    Rm = +hit.dataset.r;
  var x = ((ev.clientX - box.left) / box.width) * W,
    k = Math.max(0, Math.min(S.pfPts.length - 1, Math.round(((x - L) / (W - L - Rm)) * (S.pfPts.length - 1)))),
    p = S.pfPts[k];
  var X = L + (W - L - Rm) * (S.pfPts.length === 1 ? 0.5 : k / (S.pfPts.length - 1)),
    line = svg.querySelector('.pf-x');
  line.setAttribute('x1', X);
  line.setAttribute('x2', X);
  line.style.display = '';
  var tip = wrap.querySelector('.pftip');
  tip.hidden = false;
  tip.innerHTML =
    '<b>' +
    shortDate(p.d) +
    '</b><br>Règle actuelle : ' +
    fmtN(p.r, 1) +
    (p.a != null ? '<br>Tout dirigeant : ' + fmtN(p.a, 1) : '') +
    (p.b != null ? '<br>STOXX 600 : ' + fmtN(p.b, 1) : '');
  var left = (X / W) * box.width;
  tip.style.left = Math.min(box.width - 150, Math.max(0, left + 10)) + 'px';
});
document.addEventListener('keydown', function (ev) {
  if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.classList && ev.target.classList.contains('rowlink')) {
    ev.preventDefault();
    ev.target.click();
  }
});
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
