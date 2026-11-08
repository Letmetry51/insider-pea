/* Grain Signal — page (lecture seule de data/grain/*.json, publiés chaque matin). Tout texte venu des données est inséré
   comme texte ; seul le rapport du comité est du HTML, déjà nettoyé au calcul et nettoyé une seconde fois ici. */
'use strict';

const GS = { data: null, comite: null, journal: [], tab: 'signaux' };
const ICON = { ble: '🌾', escourgeon: '🍺', orge_printemps: '🍺', colza: '🌼', mais: '🌽' };
const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const moisFr = (m) => (m && m.length >= 7 ? `${MOIS[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}` : m || '');
const FEU = { attendre: '⏸️', executer: '✅', accelerer: '⚡', inconnu: '❔' };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.appendChild(typeof kid === 'string' || typeof kid === 'number' ? document.createTextNode(String(kid)) : kid);
  }
  return el;
}

const fmt = (v, d = 2) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : Number(v).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v, d = 1) => (v === null || v === undefined ? '—' : (v > 0 ? '+' : '') + fmt(v, d) + ' %');
const sgn = (v, d = 2) => (v === null || v === undefined ? '—' : (v > 0 ? '+' : '') + fmt(v, d));
const cls = (v) => (v === null || v === undefined ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');
function dfr(iso) {
  if (!iso) return '—';
  const d = new Date(iso.length === 10 ? iso + 'T12:00:00' : iso);
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
}
function chipFor(sig) {
  const s = String(sig || '');
  if (/VENDRE|ACHETER_LARGE/.test(s)) return 'good';
  if (/ATTENDRE/.test(s)) return 'bad';
  if (/FRACTIONNER|COUVRIR/.test(s)) return 'warn';
  return 'info';
}

/* ---------------------------------------------------------------------------------------------- graphique SVG */
const NS = 'http://www.w3.org/2000/svg';
function svgEl(svg, tag, a, text) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(a)) el.setAttribute(k, v);
  if (text !== undefined) el.textContent = text;
  svg.appendChild(el);
  return el;
}

// droite de régression sur les n derniers points (canal de tendance) et écart-type des résidus
function regression(vals, n) {
  const v = vals.slice(-n);
  const m = v.length;
  if (m < 15) return null;
  const xm = (m - 1) / 2,
    ym = v.reduce((x, y) => x + y, 0) / m;
  let sxy = 0,
    sxx = 0;
  v.forEach((y, i) => {
    sxy += (i - xm) * (y - ym);
    sxx += (i - xm) ** 2;
  });
  const slope = sxy / sxx,
    icpt = ym - slope * xm;
  const sd = Math.sqrt(v.reduce((x, y, i) => x + (y - (icpt + slope * i)) ** 2, 0) / (m - 2));
  return { slope, icpt, sd, start: vals.length - m };
}

// volatilité journalière (écart-type des variations log des 63 dernières séances)
function vol(vals) {
  const r = [];
  for (let i = Math.max(1, vals.length - 63); i < vals.length; i++) r.push(Math.log(vals[i] / vals[i - 1]));
  if (r.length < 15) return null;
  const m = r.reduce((x, y) => x + y, 0) / r.length;
  return Math.sqrt(r.reduce((x, y) => x + (y - m) ** 2, 0) / (r.length - 1));
}

/* Graphique des cours : MM20, MM50, canal de tendance (3 mois), niveaux nommés (ordres, révision, support), fourchette
   probable à 20 séances (±1 et ±2 écarts-types de la volatilité récente : une marge statistique, pas une prévision). */
function chart(rows, opts = {}) {
  const pts = rows.filter((r) => r[1] !== null && r[1] !== undefined);
  if (pts.length < 2) return h('p', { class: 'note', text: 'Historique trop court pour un graphique.' });
  const closes = pts.map((r) => r[1]);
  const fut = opts.cone === false ? 0 : 20;
  const narrow = window.innerWidth < 600; // téléphone : repère plus petit, textes lisibles
  const W = narrow ? 420 : 680,
    H = opts.h || (narrow ? 250 : 260),
    P = { l: 40, r: 6, t: 22, b: 22 };
  const n = pts.length + fut;
  const reg = opts.channel === false ? null : regression(closes, Math.min(63, closes.length));
  const sig = fut ? vol(closes) : null;
  const last = closes[closes.length - 1];
  const all = pts.flatMap((r) => r.slice(1, 5).filter((v) => v !== null && v !== undefined));
  (opts.levels || []).forEach((l) => all.push(l.v));
  if (sig) all.push(last * Math.exp(1.6 * sig * Math.sqrt(fut)), last * Math.exp(-1.6 * sig * Math.sqrt(fut)));
  let lo = Math.min(...all),
    hi = Math.max(...all);
  const pad = (hi - lo) * 0.06 || 1;
  lo -= pad;
  hi += pad;
  const x = (i) => P.l + (i / (n - 1)) * (W - P.l - P.r);
  const y = (v) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'chart');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', opts.label || 'Graphique des cours');
  const defs = svgEl(svg, 'defs', {});
  const clip = svgEl(defs, 'clipPath', { id: 'c' + Math.random().toString(36).slice(2, 8) });
  svgEl(clip, 'rect', { x: P.l, y: P.t, width: W - P.l - P.r, height: H - P.t - P.b });
  const clipUrl = `url(#${clip.id})`;
  // graduations rondes (pas de 1, 2, 2,5 ou 5 × puissance de 10) : des prix lisibles sur l'axe
  const raw = (hi - lo) / 5;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw) || 10 * mag;
  const dec = step >= 1 ? (Number.isInteger(step) ? 0 : 1) : step >= 0.1 ? 1 : 2;
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
    svgEl(svg, 'line', { x1: P.l, x2: W - P.r, y1: y(v), y2: y(v), stroke: 'var(--line)', 'stroke-width': 1 });
    svgEl(
      svg,
      'text',
      { x: P.l - 6, y: y(v) + 4, 'text-anchor': 'end', 'font-size': 11, fill: 'var(--muted)' },
      fmt(v, dec)
    );
  }
  [...new Set(pts.length < 5 ? [0, pts.length - 1] : [0, Math.floor((pts.length - 1) / 2), pts.length - 1])].forEach(
    (i) => {
      svgEl(
        svg,
        'text',
        {
          x: x(i),
          y: H - 6,
          'text-anchor': i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle',
          'font-size': 11,
          fill: 'var(--muted)',
        },
        dfr(pts[i][0])
      );
    }
  );
  const li = pts.length - 1;
  // fourchette probable
  if (sig) {
    [
      [2, 'var(--cone-2)'],
      [1, 'var(--cone-1)'],
    ].forEach(([k, fill]) => {
      let up = '',
        dn = '';
      for (let j = 0; j <= fut; j++) {
        const s = k * sig * Math.sqrt(j);
        up += (j ? 'L' : 'M') + x(li + j).toFixed(1) + ' ' + y(last * Math.exp(s)).toFixed(1);
        dn = 'L' + x(li + j).toFixed(1) + ' ' + y(last * Math.exp(-s)).toFixed(1) + dn;
      }
      svgEl(svg, 'path', { d: up + dn + 'Z', fill, stroke: 'none', 'clip-path': clipUrl });
    });
    svgEl(svg, 'line', {
      x1: x(li),
      x2: x(li),
      y1: P.t,
      y2: H - P.b,
      stroke: 'var(--muted)',
      'stroke-width': 1,
      'stroke-dasharray': '2 4',
    });
  }
  // canal de tendance
  let canal = null;
  if (reg) {
    const yAt = (i) => reg.icpt + reg.slope * (i - reg.start);
    [-2, 0, 2].forEach((k) => {
      const i0 = reg.start,
        i1 = n - 1;
      svgEl(svg, 'line', {
        x1: x(i0),
        x2: x(i1),
        y1: y(yAt(i0) + k * reg.sd),
        y2: y(yAt(i1) + k * reg.sd),
        stroke: 'var(--channel)',
        'stroke-width': k ? 1.6 : 1,
        'stroke-dasharray': k ? '7 5' : '2 4',
        opacity: k ? 1 : 0.7,
        'clip-path': clipUrl,
      });
    });
    const pctMonth = ((reg.slope * 21) / last) * 100;
    canal = { pente: pctMonth, sens: pctMonth > 0.8 ? 'haussier' : pctMonth < -0.8 ? 'baissier' : 'horizontal' };
    canal.position = (last - (yAt(li) - 2 * reg.sd)) / (4 * reg.sd);
    svgEl(
      svg,
      'text',
      { x: P.l + 6, y: P.t - 6, 'font-size': 12, 'font-weight': 700, fill: 'var(--channel)', class: 'halo' },
      `Canal ${canal.sens}`
    );
  }
  // niveaux nommés
  const usedY = [];
  (opts.levels || []).forEach((l) => {
    if (l.zone) {
      svgEl(svg, 'rect', {
        x: P.l,
        y: y(l.zone[1]),
        width: W - P.l - P.r,
        height: Math.max(2, y(l.zone[0]) - y(l.zone[1])),
        fill: l.fill,
        stroke: l.c,
        'stroke-width': 1,
      });
    } else {
      svgEl(svg, 'line', {
        x1: P.l,
        x2: W - P.r,
        y1: y(l.v),
        y2: y(l.v),
        stroke: l.c,
        'stroke-width': 1.6,
        'stroke-dasharray': '3 3',
      });
    }
    // étiquettes jamais superposées : décalées vers le haut ou le bas jusqu'à trouver une place libre
    let ly = y(l.v) - 5;
    for (let k = 1; usedY.some((u) => Math.abs(u - ly) < 14) && k < 12; k++)
      ly = y(l.v) - 5 + (k % 2 ? -1 : 1) * Math.ceil(k / 2) * 14;
    usedY.push(ly);
    svgEl(
      svg,
      'text',
      { x: W - P.r - 4, y: ly, 'text-anchor': 'end', 'font-size': 12, 'font-weight': 700, fill: l.c, class: 'halo' },
      `${l.t} : ${fmt(l.v, 2)}${l.u ? ' ' + l.u : ''}`
    );
  });
  // cours et moyennes mobiles
  [
    [3, 'var(--chart-3)', 1.3],
    [2, 'var(--chart-2)', 1.3],
    [1, opts.mainColor || 'var(--chart-1)', opts.mainWidth || 2.4],
    [4, 'var(--chart-1)', 2.6],
  ].forEach(([col, color, w]) => {
    let d = '';
    pts.forEach((r, i) => {
      if (r[col] === null || r[col] === undefined) return;
      d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[col]).toFixed(1);
    });
    if (d) svgEl(svg, 'path', { d, fill: 'none', stroke: color, 'stroke-width': w, 'stroke-linejoin': 'round' });
  });
  if (opts.col4Dots)
    pts.forEach((r, i) => {
      if (r[4] !== null && r[4] !== undefined)
        svgEl(svg, 'circle', {
          cx: x(i),
          cy: y(r[4]),
          r: 3.5,
          fill: 'var(--chart-1)',
          stroke: 'var(--surface)',
          'stroke-width': 1.5,
        });
    });
  if (opts.dot !== false)
    svgEl(svg, 'circle', {
      cx: x(li),
      cy: y(last),
      r: 5,
      fill: 'var(--chart-1)',
      stroke: 'var(--surface)',
      'stroke-width': 2,
    });
  const wrap = h('div', {}, svg);
  wrap.canal = canal;
  return wrap;
}

/* ---------------------------------------------------------------------------------------------- cartes d'indicateurs */
// jauge horizontale : segments colorés, curseur rond, repères
function gauge(value, min, max, segs, ticks) {
  const pos = (v) => Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
  const bar = h('div', { class: 'gauge' });
  let from = min;
  segs.forEach(([to, color]) => {
    bar.append(
      h('span', { class: 'seg', style: `left:${pos(from)}%;width:${pos(to) - pos(from)}%;background:${color}` })
    );
    from = to;
  });
  if (value !== null && value !== undefined && !Number.isNaN(value))
    bar.append(h('span', { class: 'knob', style: `left:${pos(value)}%` }));
  const tk = h('div', { class: 'ticks' });
  (ticks || []).forEach(([v, t]) => tk.append(h('span', { style: `left:${pos(v)}%`, text: t })));
  return h('div', { class: 'gwrap' }, bar, tk);
}

function spark(values, opts = {}) {
  const v = values.map((x) => (x === null || x === undefined ? null : x));
  const ok = v.filter((x) => x !== null);
  if (ok.length < 5) return null;
  const W = 300,
    H = 54;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'spark');
  svg.setAttribute('aria-hidden', 'true');
  const x = (i) => (i / (v.length - 1)) * W;
  if (opts.bars) {
    const m = Math.max(...ok.map(Math.abs)) || 1;
    const bw = W / v.length;
    v.forEach((val, i) => {
      if (val === null) return;
      const hgt = (Math.abs(val) / m) * (H / 2 - 2);
      svgEl(svg, 'rect', {
        x: i * bw,
        y: val >= 0 ? H / 2 - hgt : H / 2,
        width: Math.max(1, bw - 0.6),
        height: Math.max(0.8, hgt),
        fill: val >= 0 ? 'var(--good)' : 'var(--bad)',
      });
    });
    return svg;
  }
  const y = (val) => H - 2 - ((val - 0) / 100) * (H - 4);
  svgEl(svg, 'rect', { x: 0, y: y(100), width: W, height: y(70) - y(100), fill: 'var(--good-soft)' });
  svgEl(svg, 'rect', { x: 0, y: y(30), width: W, height: y(0) - y(30), fill: 'var(--bad-soft)' });
  let d = '';
  v.forEach((val, i) => {
    if (val === null) return;
    d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(val).toFixed(1);
  });
  svgEl(svg, 'path', { d, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 1.4 });
  const lv = ok[ok.length - 1];
  svgEl(svg, 'circle', { cx: W - 2, cy: y(lv), r: 3, fill: 'var(--ink)' });
  return svg;
}

let ICMODE = 'vendeur';
const ACHAT = {
  'Survente : ne pas vendre': 'Survente : bon moment pour acheter',
  'Surachat : vendre': 'Surachat : attendre pour acheter',
  'Élan haussier': 'Élan haussier : ne pas trop attendre',
  'Élan haussier qui ralentit': 'Hausse qui ralentit',
  'Élan baissier': 'Élan baissier : attendre peut payer',
  'Près du support': 'Près du support : bon prix d’achat',
  'Près de la résistance': 'Près de la résistance : cher',
};
function icard(icon, title, help, badge, badgeCls, label, ...body) {
  if (ICMODE === 'acheteur') {
    badgeCls = { good: 'bad', bad: 'good' }[badgeCls] || badgeCls;
    label = ACHAT[label] || label;
  }
  return h(
    'div',
    { class: 'icard' },
    h(
      'div',
      { class: 'ihead' },
      h('span', { text: `${icon} ${title}` }),
      h('span', { class: 'i', title: help, 'aria-label': help, tabindex: '0', text: 'ⓘ' })
    ),
    h(
      'div',
      { class: 'ival' },
      h('span', { class: 'badge ' + badgeCls, text: badge }),
      h('span', { class: 'ilabel', text: label })
    ),
    ...body
  );
}

/* Cartes lues du point de vue du vendeur : vert = bon moment pour vendre, rouge = mauvais moment pour vendre. */
function indicatorCards(a, series, niv, canal, mode = 'vendeur') {
  if (!a || a.insuffisant) return null;
  ICMODE = mode;
  const cards = [];
  const r = a.rsi;
  if (r !== null && r !== undefined) {
    const [lab, cl] =
      r < 30
        ? ['Survente : ne pas vendre', 'bad']
        : r > 70
          ? ['Surachat : vendre', 'good']
          : r < 40
            ? ['Faible', 'warn']
            : r > 60
              ? ['Fort', 'info']
              : ['Neutre', 'neutral'];
    cards.push(
      icard(
        '📶',
        'RSI 14 jours',
        'Force des hausses face aux baisses sur 14 séances. Sous 30 : marché survendu, rebond fréquent, mauvais moment pour vendre. Au-dessus de 70 : surachat, bon moment pour une tranche.',
        fmt(r, 0),
        cl,
        lab,
        gauge(
          r,
          0,
          100,
          [
            [30, 'var(--bad)'],
            [70, 'var(--neutral)'],
            [100, 'var(--good)'],
          ],
          [
            [30, '30'],
            [70, '70'],
          ]
        ),
        series && series.rsi ? spark(series.rsi) : null,
        series && series.rsi ? h('div', { class: 'imeta', text: '3 mois' }) : null
      )
    );
  }
  if (a.histo !== null && a.histo !== undefined) {
    const up = a.histo > 0;
    const fading = a.histo_5j !== null && a.histo_5j !== undefined && Math.abs(a.histo) < Math.abs(a.histo_5j);
    cards.push(
      icard(
        '〽️',
        'MACD',
        "Écart entre moyennes exponentielles 12 et 26 jours, comparé à sa moyenne 9 jours (signal). Histogramme positif : élan haussier ; négatif : élan baissier ; qui se resserre : l'élan s'essouffle.",
        up ? '▲ haussier' : '▼ baissier',
        up ? 'good' : 'bad',
        up
          ? fading
            ? 'Élan haussier qui ralentit'
            : 'Élan haussier'
          : fading
            ? 'Baisse qui s’essouffle'
            : 'Élan baissier',
        series && series.histo ? spark(series.histo, { bars: true }) : null,
        h('div', {
          class: 'imeta',
          text: a.croisement_macd ? `Croisement ${a.croisement_macd.sens} le ${dfr(a.croisement_macd.date)}` : '3 mois',
        })
      )
    );
  }
  if (a.mm20 !== undefined) {
    const e20 = a.ecart_mm20,
      e50 = a.ecart_mm50;
    const sens =
      e50 !== undefined
        ? e20 > 0 && e50 > 0
          ? 'haussière'
          : e20 < 0 && e50 < 0
            ? 'baissière'
            : 'indécise'
        : e20 > 0
          ? 'haussière'
          : 'baissière';
    cards.push(
      icard(
        sens === 'haussière' ? '📈' : sens === 'baissière' ? '📉' : '➡️',
        'Tendance (moyennes mobiles)',
        'Position du cours par rapport à ses moyennes mobiles 20 et 50 séances (et 200 quand l’historique le permet).',
        pct(e20),
        e20 > 0 ? 'good' : 'bad',
        `Tendance ${sens}`,
        h(
          'dl',
          { class: 'kv' },
          [h('dt', { text: 'MM20' }), h('dd', { text: `${fmt(a.mm20)} (${pct(e20)})` })],
          a.mm50 ? [h('dt', { text: 'MM50' }), h('dd', { text: `${fmt(a.mm50)} (${pct(e50)})` })] : null,
          a.mm200 ? [h('dt', { text: 'MM200' }), h('dd', { text: `${fmt(a.mm200)} (${pct(a.ecart_mm200)})` })] : null
        )
      )
    );
  }
  if (canal) {
    const p = Math.round(canal.position * 100);
    const [lab, cl] =
      p < 0
        ? ['Cassure par le bas', 'bad']
        : p > 100
          ? ['Cassure par le haut', 'good']
          : p < 25
            ? ['Bas du canal', 'warn']
            : p > 75
              ? ['Haut du canal', 'good']
              : ['Milieu du canal', 'neutral'];
    cards.push(
      icard(
        canal.sens === 'haussier' ? '↗️' : canal.sens === 'baissier' ? '↘️' : '↔️',
        `Canal ${canal.sens}`,
        'Droite de tendance des 3 derniers mois, ± 2 écarts-types. Haut du canal : zone de vente ; bas du canal : attendre le rebond ; sortie du canal : changement de rythme.',
        `${p} %`,
        cl,
        lab,
        gauge(
          p,
          -20,
          120,
          [
            [0, 'var(--bad)'],
            [25, 'var(--warn)'],
            [75, 'var(--neutral)'],
            [100, 'var(--good)'],
            [120, 'var(--good)'],
          ],
          [
            [0, 'bas'],
            [100, 'haut'],
          ]
        ),
        h('div', { class: 'imeta', text: `Pente ${sgn(canal.pente, 1)} % par mois` })
      )
    );
  }
  if (a.haut3m !== undefined && a.bas3m !== undefined && a.haut3m > a.bas3m) {
    const p = Math.round(((a.dernier - a.bas3m) / (a.haut3m - a.bas3m)) * 100);
    const [lab, cl] =
      p <= 15
        ? ['Près du support', 'bad']
        : p >= 85
          ? ['Près de la résistance', 'good']
          : ['Entre les deux', 'neutral'];
    cards.push(
      icard(
        '🧱',
        'Support / résistance',
        'Position du cours entre le plus bas (support) et le plus haut (résistance) des 3 derniers mois. Vendre près de la résistance, pas sur le support.',
        `${p} %`,
        cl,
        lab,
        gauge(
          p,
          0,
          100,
          [
            [15, 'var(--bad)'],
            [85, 'var(--neutral)'],
            [100, 'var(--good)'],
          ],
          [
            [0, `S ${fmt(a.bas3m)}`],
            [100, `R ${fmt(a.haut3m)}`],
          ]
        )
      )
    );
  }
  if (a.boll_pb !== null && a.boll_pb !== undefined) {
    const b = a.boll_pb;
    const [lab, cl] =
      b < 0.05
        ? ['Bande basse touchée', 'bad']
        : b > 0.95
          ? ['Bande haute touchée', 'good']
          : b < 0.3
            ? ['Moitié basse', 'warn']
            : b > 0.7
              ? ['Moitié haute', 'info']
              : ['Au centre', 'neutral'];
    cards.push(
      icard(
        '🎚️',
        'Bandes de Bollinger',
        'Position dans les bandes 20 séances ± 2 écarts-types (0 = bande basse, 1 = bande haute). Largeur faible : compression, un mouvement fort se prépare.',
        fmt(b, 2),
        cl,
        lab,
        gauge(
          b,
          0,
          1,
          [
            [0.05, 'var(--bad)'],
            [0.95, 'var(--neutral)'],
            [1, 'var(--good)'],
          ],
          [
            [0, 'basse'],
            [1, 'haute'],
          ]
        ),
        h('div', {
          class: 'imeta',
          text: `Largeur ${fmt(a.boll_largeur, 1)} %${a.boll_largeur < 6 ? ' : compression' : ''}`,
        })
      )
    );
  }
  if (niv && niv.ordres && niv.ordres.length && niv.revision) {
    const gain = ((niv.ordres[0] - a.dernier) / a.dernier) * 100,
      risk = ((a.dernier - niv.revision) / a.dernier) * 100;
    const ratio = risk > 0 ? gain / risk : null;
    const [lab, cl] =
      ratio === null
        ? ['Sous la révision', 'bad']
        : ratio >= 1.5
          ? ['Attendre l’ordre vaut le coup', 'good']
          : ratio >= 1
            ? ['Équilibré', 'neutral']
            : ['Risque supérieur au gain', 'bad'];
    cards.push(
      icard(
        '⚖️',
        'Attendre l’ordre : gain / risque',
        "Pour une tranche à vendre : gain si le premier ordre est atteint, rapporté à la perte si le cours tombe au seuil de révision. Au-dessus de 1,5 : attendre l'ordre est favorable ; sous 1 : mieux vaut ne pas trop attendre.",
        ratio === null ? '—' : fmt(ratio, 1),
        cl,
        lab,
        gauge(
          ratio === null ? 0 : Math.min(ratio, 4),
          0,
          4,
          [
            [1, 'var(--bad)'],
            [1.5, 'var(--warn)'],
            [4, 'var(--good)'],
          ],
          [
            [1.5, '1,5'],
            [4, '4+'],
          ]
        ),
        h('div', {
          class: 'imeta',
          text: `🎯 Ordre ${fmt(niv.ordres[0])} (${pct(gain)}) · 🛑 révision ${fmt(niv.revision)} (${pct(-risk)})`,
        })
      )
    );
  }
  if (a.divergence && a.divergence !== 'aucune') {
    cards.push(
      icard(
        a.divergence === 'haussière' ? '🔄' : '⚠️',
        'Divergence RSI',
        'Le prix fait un nouveau plus bas (ou plus haut) sans que le RSI suive : le mouvement perd de sa force, retournement possible.',
        a.divergence,
        a.divergence === 'haussière' ? 'warn' : 'good',
        a.divergence === 'haussière' ? 'La baisse perd de sa force' : 'La hausse perd de sa force'
      )
    );
  }
  ICMODE = 'vendeur';
  return h(
    'div',
    {},
    h('h4', {
      class: 'ititle',
      text:
        mode === 'acheteur'
          ? '🧭 Indicateurs (lecture acheteur : vert = bon moment pour acheter)'
          : '🧭 Indicateurs (lecture vendeur : vert = bon moment pour vendre)',
    }),
    h('div', { class: 'igrid' }, cards)
  );
}

/* Graphique à périodes (3 mois, 1 an, 5 ans) + cartes d'indicateurs + tableau complet.
   p = { nom, graphique, long: { an, cinq_ans }, technique, series, niveaux, mode, legendLong: [[couleur, libellé]], noteLong,
         legend3m, mainColor, col4Dots } */
function periodPanel(p) {
  if (!p.graphique) return null;
  const ta = p.technique;
  const box = h('div', {});
  const periods = [['3m', '3 mois']].concat(
    p.long
      ? [
          ['1a', '1 an'],
          ['5a', '5 ans'],
        ]
      : []
  );
  const draw = (per) => {
    box.textContent = '';
    if (per === '3m') {
      const g3 = chart(p.graphique, {
        levels: chartLevels(p.niveaux, ta, p.unite || '€/t'),
        label: `${p.nom} : 3 mois`,
        mainColor: p.mainColor,
        col4Dots: p.col4Dots,
        cone: p.cone,
        channel: p.channel,
      });
      box.append(g3, p.legend3m || chartLegend());
      return g3;
    }
    const g = chart(per === '1a' ? p.long.an : p.long.cinq_ans, {
      channel: false,
      cone: false,
      dot: false,
      mainColor: p.longMain || 'var(--chart-1)',
      mainWidth: p.longMain ? 1.6 : 2.2,
      col4Dots: p.col4Dots,
      label: `${p.nom} : ${per === '1a' ? '1 an' : '5 ans'}`,
    });
    const mm = per === '1a' ? ['MM50', 'MM200'] : ['MM 10 sem.', 'MM 40 sem.'];
    box.append(
      g,
      h(
        'div',
        { class: 'legend' },
        (p.legendLong || [['var(--chart-1)', 'Cours']]).map(([c, t]) =>
          h('span', {}, h('i', { style: `background:${c}` }), t)
        ),
        h('span', {}, h('i', { style: 'background:var(--chart-2)' }), mm[0]),
        h('span', {}, h('i', { style: 'background:var(--chart-3)' }), mm[1])
      ),
      p.noteLong ? h('p', { class: 'note', text: p.noteLong }) : null
    );
    return g;
  };
  const sw = h(
    'div',
    { class: 'periods', role: 'group', 'aria-label': 'Période du graphique' },
    periods.map(([k, t]) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(k === '3m'), text: t });
      b.addEventListener('click', () => {
        sw.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        draw(k);
      });
      return b;
    })
  );
  const g = draw('3m');
  return h(
    'div',
    {},
    periods.length > 1 ? sw : null,
    box,
    ta && !ta.insuffisant
      ? indicatorCards(ta, p.series, p.niveaux, g.canal, p.mode)
      : h('p', { class: 'note', text: 'Indicateurs disponibles à partir de 30 séances.' }),
    ta && !ta.insuffisant ? h('details', {}, h('summary', { text: '📋 Tous les chiffres' }), techTable(ta)) : null
  );
}

// vues 1 an / 5 ans d'une orge : celles du blé décalées de l'écart orge/blé du jour, prix physiques relevés par-dessus
function orgeLong(o, eb) {
  if (!o.estime || !o.estime.long_depuis_ble || !eb || !eb.long) return null;
  const g = o.estime.ecart;
  const phys = Object.fromEntries((o.graphique || []).map((r) => [r[0], r[1]]));
  const sh = (r) => [
    r[0],
    ...r.slice(1, 4).map((x) => (x === null || x === undefined ? null : Math.round((x + g) * 100) / 100)),
  ];
  return {
    an: eb.long.an.map((r) => [...sh(r), phys[r[0]] ?? null]),
    cinq_ans: eb.long.cinq_ans.map((r) => [...sh(r), null]),
    nom: eb.long.nom,
    euronext_depuis: eb.long.euronext_depuis,
  };
}

function chartLevels(niv, a, u = '€/t') {
  const lv = [];
  // « 1er ordre : 235,50 €/t » et non « Ordre 1 235,50 », qui se lisait 1 235,50 €
  (niv && niv.ordres ? niv.ordres : []).forEach((v, i) =>
    lv.push({ v, c: 'var(--good)', t: `🎯 ${i === 0 ? '1er' : `${i + 1}e`} ordre`, u })
  );
  if (niv && niv.revision) lv.push({ v: niv.revision, c: 'var(--bad)', t: '🛑 Révision', u });
  if (a && a.bas3m) lv.push({ v: a.bas3m, c: 'var(--warn)', t: '🧱 Support', u });
  return lv;
}

function chartLegend() {
  return h(
    'div',
    { class: 'legend' },
    h('span', {}, h('i', { style: 'background:var(--chart-1)' }), 'Cours'),
    h('span', {}, h('i', { style: 'background:var(--chart-2)' }), 'MM20'),
    h('span', {}, h('i', { style: 'background:var(--chart-3)' }), 'MM50'),
    h('span', {}, h('i', { style: 'background:var(--channel)' }), 'Canal 3 mois'),
    h('span', {}, h('i', { class: 'cone' }), 'Fourchette probable 20 séances')
  );
}

/* ---------------------------------------------------------------------------------------------- plan de vente */
const PLAN_ICON = {
  patienter: '⏸️',
  ordre: '🎯',
  executer: '✅',
  vendre: '🟢',
  attendre: '🔴',
  couvrir: '🛡️',
  rien: '💤',
};
function planBlock(plan) {
  if (!plan || !plan.length) return null;
  return h(
    'div',
    { class: 'plan' },
    h('b', { class: 'plan-t', text: '📅 Plan de vente' }),
    plan.map((p) =>
      h(
        'div',
        { class: 'plan-l plan-' + p.code },
        h(
          'div',
          { class: 'plan-h' },
          h('span', { class: 'plan-r', text: `Récolte ${p.recolte}` }),
          h('span', { text: `${p.statut === 'due' ? 'Tranche due' : 'Prochaine tranche'} : ${p.pct} % · ${p.periode}` })
        ),
        h('div', { class: 'plan-a', text: `${PLAN_ICON[p.code] || ''} ${p.action}` }),
        h(
          'div',
          { class: 'imeta' },
          `Cumul visé ${p.cumul_vise} % de la récolte` +
            (p.reference
              ? ` · référence ${p.reference.contrat} ${moisFr(p.reference.echeance)} : ${fmt(p.reference.prix)} €/t`
              : '')
        )
      )
    )
  );
}

const STRAT = {
  S0: 'Tout vendre à la moisson',
  S1: 'Même quantité chaque mois',
  S2: 'Calendrier Grain Signal',
  S3: 'Calendrier + timing technique',
  S4: 'Calendrier + timing + tendance',
  E0: 'Tout acheter en janvier',
  E1: 'Même quantité chaque mois',
  E2: 'Saison seule (avril-juillet)',
  E3: 'Règles Grain Signal',
};
function btTable(b, unite, achat) {
  const best = Object.entries(b).sort((x, y) => y[1].ecart_moyen - x[1].ecart_moyen)[0][0];
  return h(
    'div',
    { class: 'scroll' },
    h(
      'table',
      {},
      h(
        'tr',
        {},
        [
          'Stratégie',
          `Prix moyen (${unite})`,
          achat ? 'Économie / mensuel' : 'Gain / mensuel',
          'Campagnes gagnantes',
          'Pire / meilleure',
        ].map((t, i) => h('th', { class: i ? 'n' : '', text: t }))
      ),
      Object.entries(b).map(([k, v]) =>
        h(
          'tr',
          { class: k === best ? 'best' : '' },
          h('td', { text: `${k === best ? '🏆 ' : ''}${STRAT[k] || k}` }),
          h('td', { class: 'n', text: fmt(v.moyenne, 1) }),
          h('td', { class: 'n ' + cls(v.ecart_moyen), text: `${sgn(v.ecart_moyen, 1)}` }),
          h('td', { class: 'n', text: `${v.gagnantes} / ${v.campagnes}` }),
          h('td', { class: 'n', text: `${sgn(v.pire, 1)} / ${sgn(v.meilleure, 1)}` })
        )
      )
    )
  );
}
function backtestSection() {
  const bt = GS.backtest;
  if (!bt)
    return h(
      'div',
      { class: 'card', style: 'margin-top:12px' },
      h('h3', { text: '🧪 Backtest' }),
      h('p', { class: 'note', text: 'Résultats au prochain calcul.' })
    );
  const parts = [h('h3', { text: '🧪 Backtest : ce que les règles auraient rapporté' })];
  for (const v of Object.values(bt.ventes || {})) {
    if (v.erreur) {
      parts.push(h('p', { class: 'note', text: `${v.nom} : ${v.erreur}` }));
      continue;
    }
    const b = v.bilan_vs_S1;
    const g = (k) => `${sgn(b[k].ecart_moyen, 1)} €/t (gagnant ${b[k].gagnantes} fois sur ${b[k].campagnes})`;
    parts.push(
      h('h4', { class: 'ititle', text: `${v.nom} — ${v.campagnes.length} campagnes depuis ${v.campagnes[0].recolte}` }),
      h('p', {
        text: `Par rapport à une vente mensuelle régulière : calendrier ${g('S2')} ; avec le timing technique ${g('S3')} ; avec la tendance ${g('S4')}.`,
      }),
      btTable(b, '€/t'),
      h('p', {
        class: 'note',
        text: `Meilleur réglage du timing testé : RSI < ${v.variantes_timing[0].rsi} et bas du range ≤ ${v.variantes_timing[0].pos} % (${sgn(v.variantes_timing[0].ecart_moyen_vs_S2)} €/t par rapport au calendrier seul). Réglage actuel : RSI < 40 et ≤ 20 %.`,
      })
    );
  }
  const e = bt.engrais || {};
  if (e.bilan_vs_E1) {
    parts.push(
      h('h4', { class: 'ititle', text: `🧪 Achats d'azote — ${e.campagnes.length} campagnes (${e.nom})` }),
      btTable(e.bilan_vs_E1, '$/t', true)
    );
  }
  parts.push(
    h(
      'details',
      {},
      h('summary', { text: 'Limites du test' }),
      h(
        'ul',
        { class: 'list note' },
        (bt.limites || []).map((t) => h('li', { text: t }))
      )
    )
  );
  return h('div', { class: 'card', style: 'margin-top:12px' }, parts);
}

function calendarTable() {
  const cal = ((GS.data || {}).config || {}).calendrier || {};
  const noms = {
    ble: '🌾 Blé tendre',
    escourgeon: '🍺 Escourgeon',
    orge_printemps: '🍺 Orge de printemps',
    colza: '🌼 Colza',
    mais: '🌽 Maïs',
  };
  const lab = (r) => {
    const k = r - 1;
    const yr = Math.floor(k / 12);
    return MOIS[((k % 12) + 12) % 12] + (yr < 0 ? ' (N−1)' : yr > 0 ? ' (N+1)' : '');
  };
  return h(
    'div',
    { class: 'card scroll' },
    h('h3', { text: '📅 Calendrier de vente par défaut (N = année de récolte)' }),
    h(
      'table',
      {},
      h('tr', {}, h('th', { text: 'Culture' }), h('th', { text: 'Tranches' })),
      Object.entries(cal).map(([k, v]) => {
        let cum = 0;
        return h(
          'tr',
          {},
          h('td', { text: noms[k] || k }),
          h('td', {
            text: v.tranches
              .map(([a, b, p]) => ((cum += p), `${lab(a)}–${lab(b)} : ${p} % (cumul ${cum} %)`))
              .join(' · '),
          })
        );
      })
    ),
    h('p', {
      class: 'note',
      text: "Au plus 35 % vendus avant la moisson. « Tenir le plan » = vendre la tranche due ; « vendre » = avancer la tranche suivante ; « attendre » = décaler ; « couvrir » = protéger le prix sans livrer. Le timing technique décide du moment : au creux, la tranche part par ordre au-dessus du marché. Pour une récolte à venir, les ordres sont décalés de l'écart entre son échéance et l'échéance du jour. Réglable dans grain_signal/config.json.",
    })
  );
}

/* ---------------------------------------------------------------------------------------------- onglets */
/* ---------------------------------------------------------------------------------------------- en un coup d'œil */
const DECISION = {
  ordre: ['🎯', 'ORDRE', 'warn'],
  executer: ['✅', 'VENDRE', 'good'],
  vendre: ['🟢', 'AVANCER', 'good'],
  attendre: ['🔴', 'ATTENDRE', 'bad'],
  couvrir: ['🛡️', 'COUVRIR', 'info'],
  rien: ['💤', 'RIEN', 'neutral'],
  patienter: ['⏸️', 'PATIENTER', 'warn'],
};
function court(p, sur) {
  if (!p) return '—';
  if (p.code === 'rien') return `Prochaine tranche : ${p.periode}`;
  const prix = p.ordre ? `${sur ? 'blé ≥ ' : 'à '}${fmt(p.ordre)} €/t` : '';
  if (p.code === 'ordre') return `${p.pct} % ${prix}`;
  if (p.code === 'executer') return `${p.pct} % ${prix || 'cette période'}`.trim();
  if (p.code === 'attendre') return `Décaler les ${p.pct} %`;
  if (p.code === 'patienter') return `${p.pct} % au prochain rebond`;
  if (p.code === 'couvrir') return `Couvrir ${p.pct} %`;
  return `${p.pct} %`;
}
function glance(d) {
  const tiles = [];
  for (const [k, c] of Object.entries(d.cultures || {})) {
    const plan = c.plan || [];
    const due =
      plan.find((p) => p.statut === 'due' && !p.avant_moisson) || plan.find((p) => p.statut === 'due') || plan[0];
    const autre = plan.find((p) => p !== due && p.statut === 'due');
    const [ic, lab, cl] = DECISION[(due || {}).code] || ['❔', '—', 'neutral'];
    const con = (d.contrats || {})[c.contrat] || {};
    const ta = con.technique || {};
    const phys = c.physique;
    const cours = phys && phys.prix ? phys.prix : con.dernier_reel;
    const v1 = ta.var1s;
    const tend = ta.ecart_mm20 === undefined ? '' : ta.ecart_mm20 > 0 ? '↗' : '↘';
    tiles.push(
      h(
        'div',
        { class: 'gtile g-' + cl },
        h('div', { class: 'gname', text: `${ICON[k] || ''} ${c.nom.replace(' brassicole', '')}` }),
        h(
          'div',
          { class: 'gdec' },
          h('span', { class: 'badge ' + cl, text: `${ic} ${lab}` }),
          h('span', { class: 'gwhat', text: court(due, (c.niveaux_retenus || {}).sur_ble) })
        ),
        h(
          'div',
          { class: 'gline' },
          cours ? `${fmt(cours)} €/t${phys && phys.prix ? ' (physique)' : ''}` : '',
          tend && !c.proxy ? ` ${tend} ${pct(v1)} sur 1 sem.` : ''
        ),
        due
          ? h('div', {
              class: 'gsub',
              text: `Récolte ${due.recolte} · ${due.periode}${due.code === 'ordre' ? ' · ne pas vendre au creux' : ''}`,
            })
          : null,
        autre
          ? h('div', {
              class: 'gsub',
              text: `Récolte ${autre.recolte} : ${court(autre, (c.niveaux_retenus || {}).sur_ble)}`,
            })
          : null
      )
    );
  }
  const e = d.engrais || {};
  const ec = e.comite || {};
  const sig = ec.signal || e.signal;
  const ED = {
    ACHETER_LARGE: ['🟢', 'ACHETER', 'good'],
    SUIVRE: ['🟡', 'SUIVRE', 'info'],
    FRACTIONNER: ['🟠', 'FRACTIONNER', 'warn'],
    ATTENDRE: ['🔴', 'ATTENDRE', 'bad'],
  };
  const [eic, elab, ecl] = ED[sig] || ['❔', '—', 'neutral'];
  const ur = (e.france || {}).uree || {};
  tiles.push(
    h(
      'div',
      { class: 'gtile g-' + ecl },
      h('div', { class: 'gname', text: '🧪 Azote (achat)' }),
      h(
        'div',
        { class: 'gdec' },
        h('span', { class: 'badge ' + ecl, text: `${eic} ${elab}` }),
        h('span', { class: 'gwhat', text: ec.pct ? ec.pct.split('(')[0].trim() : e.a_acheter || '' })
      ),
      h('div', {
        class: 'gline',
        text: ur.prix
          ? `Urée ${fmt(ur.prix)} €/t ${ur.var1m !== undefined ? (ur.var1m > 0 ? '↗' : '↘') + ' ' + pct(ur.var1m) + ' sur 1 mois' : ''}`
          : '',
      }),
      h('div', {
        class: 'gsub',
        text: `Ratio azote/blé : ${e.percentile_retenu ?? '—'}e percentile${ec.prix_plafond ? ` · plafond ${fmt(ec.prix_plafond, 0)} €/t` : ''}`,
      })
    )
  );
  const cal = ((d.comite || {}).calendrier || [])
    .filter((x) => x.date >= d.date)
    .sort((a, b) => (a.date < b.date ? -1 : 1));
  const nAl = (d.declencheurs || []).length;
  return h(
    'section',
    { class: 'glance' },
    h(
      'div',
      { class: 'ghead' },
      h('h2', { text: '🧭 Décisions du jour' }),
      h(
        'div',
        { class: 'gmeta' },
        `Séance du ${dfr((d.contrats.EBM || {}).seance || d.date)}`,
        cal.length ? ` · 📅 ${dfr(cal[0].date)} : ${cal[0].evenement}` : '',
        nAl ? ` · ⚠️ ${nAl} alerte${nAl > 1 ? 's' : ''}` : ' · aucune alerte'
      )
    ),
    h('div', { class: 'ggrid' }, tiles),
    h(
      'p',
      { class: 'note' },
      '🎯 ORDRE = placer un ordre de vente au prix indiqué (ne pas vendre au prix du jour) · ⏸️ PATIENTER = attendre un rebond · ✅ VENDRE = la tranche peut partir · 🔴 ATTENDRE = décaler · 💤 RIEN = pas de tranche prévue maintenant. Détails, raisons et niveaux plus bas.'
    )
  );
}

function vSignaux() {
  const d = GS.data;
  const out = [glance(d)];
  const com = d.comite || {};
  if (!com.valide) {
    out.push(
      h(
        'div',
        { class: 'alert info' },
        com.erreur ||
          "Pas d'avis du comité de moins de 8 jours : les signaux restent sur « tenir le plan », avec la lecture de marché et le timing technique du matin."
      )
    );
  } else if (com.erreur) {
    out.push(h('div', { class: 'alert' }, com.erreur));
  }
  if (com.resume)
    out.push(
      h('div', { class: 'card wide' }, h('h3', { text: `Comité du ${dfr(com.date)}` }), h('p', { text: com.resume }))
    );
  out.push(h('h2', { text: '🔎 Détails par culture' }));
  const grid = h('div', { class: 'grid' });
  for (const [k, c] of Object.entries(d.cultures || {})) {
    const cc = c.comite || {};
    // niveaux retenus (comité, sinon technique) ; escourgeon et orge de printemps : niveaux du blé Euronext
    const nr = c.niveaux_retenus || { ordres: [], revision: null };
    const ordres = nr.ordres || [];
    const revision = nr.revision;
    const ech = nr.echeance ? ` (${c.contrat} ${moisFr(nr.echeance)})` : '';
    const contrat = (d.contrats || {})[c.contrat] || {};
    grid.append(
      h(
        'section',
        { class: 'card' },
        h('h3', { text: `${ICON[k] || ''} ${c.nom}` }),
        h('div', { class: 'sig', text: c.libelle || '—' }),
        h(
          'div',
          {},
          h('span', {
            class: 'chip ' + (c.source === 'comite' ? 'good' : ''),
            text: c.source === 'comite' ? 'Avis du comité' : 'Sans comité',
          }),
          c.proxy ? h('span', { class: 'chip', text: 'suit le blé Euronext' }) : null,
          c.lecture_marche
            ? h('span', { class: 'chip ' + chipFor(c.lecture_marche), text: 'Marché : ' + sgn(c.score_marche) })
            : null
        ),
        (() => {
          const ta = contrat.proxy && contrat.proxy.technique ? contrat.proxy.technique : contrat.technique;
          if (!ta || ta.insuffisant) return null;
          const pos =
            ta.haut3m > ta.bas3m ? Math.round(((ta.dernier - ta.bas3m) / (ta.haut3m - ta.bas3m)) * 100) : null;
          return h(
            'div',
            { class: 'minis' },
            h('span', {
              class: 'mini ' + (ta.rsi < 30 ? 'bad' : ta.rsi > 70 ? 'good' : ''),
              title: 'RSI 14 jours',
              text: `📶 RSI ${fmt(ta.rsi, 0)}`,
            }),
            h('span', {
              class: 'mini ' + (ta.histo > 0 ? 'good' : 'bad'),
              title: 'MACD',
              text: `〽️ ${ta.histo > 0 ? '▲' : '▼'} MACD`,
            }),
            pos !== null
              ? h('span', {
                  class: 'mini ' + (pos <= 15 ? 'bad' : pos >= 85 ? 'good' : ''),
                  title: 'Position entre support et résistance (3 mois)',
                  text: `🧱 ${pos} % du range`,
                })
              : null,
            ta.divergence && ta.divergence !== 'aucune'
              ? h('span', { class: 'mini warn', text: `🔄 divergence ${ta.divergence}` })
              : null
          );
        })(),
        c.a_revoir ? h('div', { class: 'alert', text: c.a_revoir }) : null,
        cc.texte ? h('p', { class: 'note', text: cc.texte }) : c.note ? h('p', { class: 'note', text: c.note }) : null,
        h(
          'dl',
          { class: 'kv' },
          cc.pct ? [h('dt', { text: 'Avis du comité' }), h('dd', { text: cc.pct })] : null,
          [
            h('dt', { text: nr.sur_ble ? '🎯 Blé à' : '🎯 Ordres' }),
            h('dd', {
              text: ordres.length
                ? ordres.map((v) => fmt(v)).join(' · ') +
                  ' €/t' +
                  ech +
                  (nr.sur_ble
                    ? ' : vendre une tranche d’orge' +
                      (nr.equivalent_orge && nr.equivalent_orge.ordres.length
                        ? ` (≈ ${nr.equivalent_orge.ordres.map((v) => fmt(v)).join(' · ')} €/t d'orge)`
                        : '')
                    : '')
                : '—',
            }),
          ],
          [h('dt', { text: '🛑 Révision' }), h('dd', { text: revision ? `sous ${fmt(revision)} €/t${ech}` : '—' })],
          nr.source && nr.source !== 'aucun'
            ? [
                h('dt', { text: 'Niveaux' }),
                h('dd', {
                  class: 'muted',
                  text:
                    nr.source === 'comite' ? 'fixés par le comité' : 'techniques (MM20, Fibonacci, plus bas 3 mois)',
                }),
              ]
            : null,
          c.score_actualise !== undefined
            ? [
                h('dt', { text: 'Score' }),
                h('dd', { text: `${sgn(cc.score)} au comité → ${sgn(c.score_actualise)} ce matin` }),
              ]
            : null,
          c.physique && c.physique.prix
            ? [
                h('dt', { text: 'Physique' }),
                h('dd', {
                  text:
                    `${fmt(c.physique.prix)} €/t ${c.physique.place || ''}` +
                    (c.physique.prime !== undefined && c.physique.prime !== null
                      ? `, prime ${sgn(c.physique.prime)} €/t sur la fourragère`
                      : '') +
                    `, ${dfr(c.physique.date)}`,
                }),
              ]
            : null,
          !c.proxy && contrat.dernier_reel !== undefined && contrat.dernier_reel !== null
            ? [
                h('dt', { text: 'Euronext' }),
                h('dd', {
                  text: `${fmt(contrat.dernier_reel)} €/t (${contrat.echeance || ''}), ${dfr(contrat.seance)}`,
                }),
              ]
            : null,
          contrat.courbe && contrat.courbe.lecture
            ? [h('dt', { text: 'Courbe' }), h('dd', { text: contrat.courbe.lecture })]
            : null
        ),
        planBlock(c.plan),
        c.feu
          ? h(
              'div',
              { class: 'feu feu-' + c.feu.code },
              h('b', { text: `${FEU[c.feu.code] || ''} Timing technique` }),
              c.feu.texte
            )
          : null
      )
    );
  }
  const e = d.engrais || {};
  const ec = e.comite || {};
  grid.append(
    h(
      'section',
      { class: 'card' },
      h('h3', { text: '🧪 Engrais azotés' }),
      h('div', {
        class: 'sig',
        text: ec.signal
          ? {
              ACHETER_LARGE: '🟢 ACHETER LARGE',
              SUIVRE: '🟡 SUIVRE LE PLAN',
              FRACTIONNER: '🟠 FRACTIONNER',
              ATTENDRE: '🔴 ATTENDRE',
            }[ec.signal]
          : e.libelle || '—',
      }),
      h('span', {
        class: 'chip ' + (ec.signal ? 'good' : ''),
        text: ec.signal ? 'Avis du comité' : 'Règles chiffrées',
      }),
      ec.signal && ec.signal !== e.signal
        ? h('span', { class: 'chip', text: 'Règles du matin : ' + (e.libelle || '—') })
        : null,
      h(
        'dl',
        { class: 'kv' },
        [h('dt', { text: 'À acheter' }), h('dd', { text: ec.pct || e.a_acheter || '—' })],
        [
          h('dt', { text: 'Ratio azote/blé' }),
          h('dd', {
            text:
              e.percentile_retenu !== undefined && e.percentile_retenu !== null
                ? e.percentile_retenu + 'e percentile (10 ans)'
                : '—',
          }),
        ],
        [
          h('dt', { text: 'Rattrapage gaz' }),
          h('dd', { text: e.rattrapage !== undefined ? sgn(e.rattrapage, 0) + ' pts sur 3 mois' : '—' }),
        ],
        [h('dt', { text: 'Saison' }), h('dd', { text: e.saison || '—' })],
        e.forme_moins_chere ? [h('dt', { text: 'Moins cher/uN' }), h('dd', { text: e.forme_moins_chere })] : null
      ),
      h(
        'ul',
        { class: 'list note' },
        (e.notes || []).map((n) => h('li', { text: n }))
      )
    )
  );
  out.push(grid);
  out.push(h('h2', { text: 'Déclencheurs' }));
  const trig = d.declencheurs || [];
  out.push(
    trig.length
      ? h(
          'ul',
          { class: 'list' },
          trig.map((t) =>
            h(
              'li',
              {},
              h('b', { text: (t.grave ? '⚠️ ' : '') + t.titre }),
              h('br'),
              h('span', { class: 'muted', text: t.detail })
            )
          )
        )
      : h('p', { class: 'muted', text: 'Aucun déclencheur ce matin.' })
  );
  const hist = (d.historique_declencheurs || []).filter((t) => !trig.some((x) => x.id === t.id));
  if (hist.length)
    out.push(
      h(
        'details',
        {},
        h('summary', { text: `Déclencheurs précédents (${hist.length})` }),
        h(
          'ul',
          { class: 'list' },
          hist.map((t) => h('li', { text: `${dfr(t.id.slice(0, 10))} — ${t.titre}` }))
        )
      )
    );
  if (com.calendrier && com.calendrier.length) {
    out.push(h('h2', { text: 'Calendrier' }));
    out.push(
      h(
        'ul',
        { class: 'list' },
        com.calendrier
          .filter((c) => c.date >= d.date)
          .map((c) => h('li', {}, h('b', { text: dfr(c.date) }), ' — ' + c.evenement))
      )
    );
  }
  return out;
}

function techTable(a) {
  const row = (k, v, c) => h('tr', {}, h('td', { text: k }), h('td', { class: 'n ' + (c || ''), text: v }));
  const cross = a.croisement_macd ? `${a.croisement_macd.sens} le ${dfr(a.croisement_macd.date)}` : '—';
  return h(
    'table',
    {},
    row('Variation 1 sem. / 1 mois', `${pct(a.var1s)} / ${pct(a.var1m)}`, cls(a.var1m)),
    row('MM20 (écart)', `${fmt(a.mm20)} (${pct(a.ecart_mm20)})`, cls(a.ecart_mm20)),
    row('MM50 (écart)', a.mm50 ? `${fmt(a.mm50)} (${pct(a.ecart_mm50)})` : '—', cls(a.ecart_mm50)),
    row('MM200 (écart)', a.mm200 ? `${fmt(a.mm200)} (${pct(a.ecart_mm200)})` : '—', cls(a.ecart_mm200)),
    row('RSI 14 (il y a 5 j)', `${fmt(a.rsi, 1)} (${fmt(a.rsi_5j, 1)})`, a.rsi < 30 ? 'up' : a.rsi > 70 ? 'down' : ''),
    row('MACD / signal', `${sgn(a.macd)} / ${sgn(a.macd_signal)}`),
    row('Histogramme (il y a 5 j)', `${sgn(a.histo)} (${sgn(a.histo_5j)})`, cls(a.histo)),
    row('Dernier croisement MACD', cross),
    row('Bollinger %B / largeur', `${fmt(a.boll_pb)} / ${fmt(a.boll_largeur, 1)} %`),
    row('Divergence RSI', a.divergence || '—'),
    row('Plus haut / bas 3 mois', `${fmt(a.haut3m)} / ${fmt(a.bas3m)}`),
    a.fibo
      ? row(
          `Fibonacci (${a.fibo.sens}) 38,2 / 50 / 61,8`,
          `${fmt(a.fibo['38.2'])} / ${fmt(a.fibo['50'])} / ${fmt(a.fibo['61.8'])}`
        )
      : null
  );
}

function vTechnique() {
  const d = GS.data;
  const out = [
    h('p', {
      class: 'note',
      text: "Sur les marchés agricoles, la technique sert au timing d'exécution (où placer les ordres, quand déclencher une tranche) ; elle ne renverse jamais seule un signal fondamental.",
    }),
  ];
  const grid = h('div', { class: 'stack' });
  const orgGrid = h('div', { class: 'stack' });
  for (const [code, c] of Object.entries(d.contrats || {})) {
    const a = c.technique || {};
    grid.append(
      h(
        'section',
        { class: 'card' },
        h('h3', { text: `${ICON[c.culture] || '📊'} ${c.nom} — Euronext ${code}` }),
        h('p', {
          class: 'note',
          text: `Série continue (échéance de référence ${c.echeance || '—'}), ${a.seances || 0} séances, dernière : ${dfr(c.seance)}`,
        }),
        c.alerte_raccord ? h('div', { class: 'alert', text: c.alerte_raccord }) : null,
        c.proxy ? h('div', { class: 'alert info', text: c.proxy.texte }) : null,
        (() => {
          const src = c.proxy && c.proxy.graphique ? c.proxy : c;
          return periodPanel({
            nom: c.nom,
            graphique: src.graphique,
            long: c.long,
            technique: c.proxy && c.proxy.technique ? c.proxy.technique : a,
            series: src.series,
            // lecture de secours recalée sur Euronext : les niveaux retenus (en €/t Euronext) s'y lisent directement
            niveaux: c.niveaux_retenus || c.niveaux,
            longMain: 'var(--muted)',
            legendLong: c.long
              ? [
                  ['var(--chart-1)', `Euronext (depuis le ${dfr(c.long.euronext_depuis)})`],
                  ['var(--muted)', `${c.long.nom} recalé sur Euronext`],
                ]
              : null,
            noteLong: c.long
              ? `L'historique Euronext se construit chaque jour depuis le ${dfr(c.long.euronext_depuis)}. Pour la tendance longue : ${c.long.nom}, converti en €/t puis recalé sur le niveau d'Euronext des dernières séances (même tendance, écarts possibles entre les deux marchés) ; les moyennes mobiles portent sur cette série.`
              : null,
          });
        })(),
        h('p', { class: 'note', text: `Note technique : ${sgn(c.score_technique)} (de −2 à +2)` })
      )
    );
  }
  for (const o of Object.values(d.orges || {})) {
    const ble = (d.contrats || {}).EBM || {};
    orgGrid.append(
      h(
        'section',
        { class: 'card' },
        h('h3', { text: `🍺 ${o.nom}` }),
        h('p', {
          class: 'note',
          text: "Pas de marché à terme pour les orges : prix physique Creil FOB relevé chaque jour (terre-net) ; le moment de vendre suit le blé Euronext, la prime brassicole dit si l'orge est bien payée.",
        }),
        o.estime
          ? h('div', {
              class: 'alert info',
              text: `Pas encore d'historique de prix d'orge : courbe estimée = blé Euronext ${sgn(o.estime.ecart)} €/t (écart orge/blé du jour). Les points dorés sont les prix physiques réellement relevés ; ils s'accumulent chaque jour.`,
            })
          : null,
        o.estime
          ? periodPanel({
              nom: o.nom,
              graphique: o.estime.graphique,
              long: orgeLong(o, d.contrats.EBM),
              technique: o.estime.technique,
              series: o.estime.series,
              niveaux: o.estime.niveaux,
              mainColor: 'var(--muted)',
              longMain: 'var(--muted)',
              col4Dots: true,
              legend3m: h(
                'div',
                { class: 'legend' },
                h(
                  'span',
                  {},
                  h('i', { style: 'background:var(--muted)' }),
                  `Orge estimée (blé ${sgn(o.estime.ecart)} €/t)`
                ),
                h('span', {}, h('i', { style: 'background:var(--chart-1)' }), 'Prix physique relevé'),
                h('span', {}, h('i', { style: 'background:var(--chart-2)' }), 'MM20'),
                h('span', {}, h('i', { style: 'background:var(--chart-3)' }), 'MM50'),
                h('span', {}, h('i', { style: 'background:var(--channel)' }), 'Canal 3 mois'),
                h('span', {}, h('i', { class: 'cone' }), 'Fourchette probable 20 séances')
              ),
              legendLong: [
                ['var(--muted)', `Orge estimée (blé ${sgn(o.estime.ecart)} €/t)`],
                ['var(--chart-1)', 'Prix physique relevé'],
              ],
              noteLong: `Tendance longue de l'orge estimée à partir du blé (Euronext, puis ${(d.contrats.EBM.long || {}).nom || 'Chicago'} recalé) décalé de l'écart du jour : l'écart orge/blé varie dans le temps, ce n'est qu'un repère.`,
            })
          : h('p', { class: 'note', text: 'Graphique dès que plusieurs jours de prix sont relevés.' }),
        h(
          'table',
          {},
          h(
            'tr',
            {},
            h('td', { text: `Prix ${o.place} (${o.echeance || ''})` }),
            h('td', { class: 'n', text: `${fmt(o.prix)} €/t` })
          ),
          o.rouen_rendu
            ? h('tr', {}, h('td', { text: 'Rouen rendu' }), h('td', { class: 'n', text: `${fmt(o.rouen_rendu)} €/t` }))
            : null,
          h(
            'tr',
            {},
            h('td', { text: `Orge fourragère Creil FOB${o.fourragere_echeance ? ` (${o.fourragere_echeance})` : ''}` }),
            h('td', { class: 'n', text: o.fourragere ? `${fmt(o.fourragere)} €/t` : '—' })
          ),
          h(
            'tr',
            {},
            h('td', {
              text:
                'Prime brassicole' +
                (o.fourragere_echeance && o.fourragere_echeance !== o.echeance
                  ? ' (indicative : échéances différentes)'
                  : ''),
            }),
            h('td', { class: 'n ' + cls(o.prime), text: o.prime !== undefined ? `${sgn(o.prime)} €/t` : '—' })
          ),
          h(
            'tr',
            {},
            h('td', { text: 'Écart avec le blé Euronext' }),
            h('td', {
              class: 'n ' + cls(o.ecart_ble),
              text: o.ecart_ble !== undefined ? `${sgn(o.ecart_ble)} €/t` : '—',
            })
          ),
          h(
            'tr',
            {},
            h('td', { text: 'Variation 1 mois / 3 mois' }),
            h('td', { class: 'n', text: `${pct(o.var1m)} / ${pct(o.var3m)}` })
          ),
          h('tr', {}, h('td', { text: 'Cotation' }), h('td', { class: 'n', text: dfr(o.date) }))
        ),
        o.technique ? techTable(o.technique) : null,
        ble.feu ? h('div', { class: 'feu' }, h('b', { text: 'Timing (blé Euronext)' }), ble.feu.texte) : null
      )
    );
  }
  out.push(grid);
  if (orgGrid.children.length) out.push(h('h2', { text: '🍺 Orges brassicoles' }), orgGrid);
  out.push(h('h2', { text: '🌍 Marchés internationaux, énergie, change' }));
  const rows = Object.entries(d.international || {}).map(([tk, x]) => {
    const a = x.technique || {};
    return h(
      'tr',
      {},
      h('td', { text: x.nom }),
      h('td', { class: 'n', text: fmt(a.dernier, a.dernier < 10 ? 4 : 2) }),
      h('td', { class: 'n ' + cls(a.var1m), text: pct(a.var1m) }),
      h('td', { class: 'n ' + cls(a.ecart_mm50), text: pct(a.ecart_mm50) }),
      h('td', { class: 'n', text: fmt(a.rsi, 0) }),
      h('td', { class: 'n ' + cls(a.histo), text: sgn(a.histo) }),
      h('td', { class: 'n', text: sgn(x.score_technique) })
    );
  });
  out.push(
    h(
      'div',
      { class: 'card scroll' },
      h(
        'table',
        {},
        h(
          'tr',
          {},
          ['Marché', 'Dernier', '1 mois', 'vs MM50', 'RSI', 'Histo MACD', 'Note'].map((t, i) =>
            h('th', { class: i ? 'n' : '', text: t })
          )
        ),
        rows
      )
    )
  );
  out.push(h('h2', { text: '🏦 Positions des fonds (Euronext et CFTC)' }));
  const cot = Object.values(d.cot || {}).sort(
    (a, b) => (a.source === 'euronext' ? 0 : 1) - (b.source === 'euronext' ? 0 : 1)
  );
  out.push(
    cot.length
      ? h(
          'div',
          { class: 'card scroll' },
          h(
            'table',
            {},
            h(
              'tr',
              {},
              ['Marché', 'Rapport', 'Net', 'Semaine', 'Indice 3 ans', 'Lecture'].map((t, i) =>
                h('th', { class: i > 1 ? 'n' : '', text: t })
              )
            ),
            cot.map((c) =>
              h(
                'tr',
                {},
                h('td', { text: c.nom }),
                h('td', { text: dfr(c.date) }),
                h('td', { class: 'n', text: fmt(c.net, 0) }),
                h('td', { class: 'n ' + cls(c.variation), text: sgn(c.variation, 0) }),
                h('td', { class: 'n', text: fmt(c.indice, 0) }),
                h('td', {
                  class: 'n',
                  text:
                    c.indice === null || c.indice === undefined
                      ? `historique en constitution (${c.semaines || 0}/26 semaines)`
                      : c.indice <= 15
                        ? 'fonds très vendeurs : rachat possible'
                        : c.indice >= 85
                          ? 'fonds très acheteurs : liquidation possible'
                          : 'neutre',
                })
              )
            )
          ),
          h('p', {
            class: 'note',
            text: "Lecture à contre-courant : un positionnement extrême annonce souvent un retournement. Euronext : fonds d'investissement (rapport officiel du mercredi), compte pour 70 % de la note des fonds ; CFTC (managed money, États-Unis) pour 30 %.",
          })
        )
      : h('p', { class: 'muted', text: 'Positions des fonds non disponibles ce matin.' })
  );
  return out;
}

function vEngrais() {
  const e = GS.data.engrais || {};
  const out = [];
  out.push(
    h(
      'div',
      { class: 'grid' },
      h(
        'section',
        { class: 'card' },
        h('h3', { text: 'Décision du matin' }),
        h('div', { class: 'sig', text: e.libelle || '—' }),
        h('p', { text: 'À acheter maintenant : ' + (e.a_acheter || '—') }),
        h(
          'ul',
          { class: 'list note' },
          (e.notes || []).map((n) => h('li', { text: n }))
        )
      ),
      h(
        'section',
        { class: 'card' },
        h('h3', { text: 'Ratio urée / blé' }),
        h(
          'dl',
          { class: 'kv' },
          e.mondial
            ? [
                h('dt', { text: `Mondial (${e.mondial.mois})` }),
                h('dd', { text: `${fmt(e.mondial.ratio, 3)} — ${e.mondial.percentile}e percentile` }),
              ]
            : null,
          e.estimation
            ? [
                h('dt', { text: 'Estimé ce matin' }),
                h('dd', { text: `${fmt(e.estimation.ratio, 3)} — ${e.estimation.percentile}e percentile` }),
              ]
            : null,
          [
            h('dt', { text: 'Rattrapage' }),
            h('dd', { text: e.rattrapage !== undefined ? sgn(e.rattrapage, 0) + ' pts' : '—' }),
          ],
          [h('dt', { text: 'Saison' }), h('dd', { text: e.saison || '—' })]
        ),
        e.estimation ? h('p', { class: 'note', text: e.estimation.methode }) : null,
        h('p', {
          class: 'note',
          text: '≤ 20e percentile : acheter large · 20-60 : suivre le plan · 60-80 : fractionner · ≥ 80 : attendre. Rattrapage > +15 pts : avancer ; < −15 : retarder.',
        })
      ),
      e.ttf
        ? h(
            'section',
            { class: 'card' },
            h('h3', { text: 'Gaz TTF' }),
            h(
              'dl',
              { class: 'kv' },
              [h('dt', { text: 'Dernier' }), h('dd', { text: `${fmt(e.ttf.dernier)} €/MWh (${dfr(e.ttf.au)})` })],
              [
                h('dt', { text: '1 sem. / 1 mois / 3 mois' }),
                h('dd', { text: `${pct(e.ttf.var1s)} / ${pct(e.ttf.var1m)} / ${pct(e.ttf.var3m)}` }),
              ],
              [h('dt', { text: 'MM20 / MM50' }), h('dd', { text: `${fmt(e.ttf.mm20)} / ${fmt(e.ttf.mm50)}` })],
              [h('dt', { text: 'RSI / histo MACD' }), h('dd', { text: `${fmt(e.ttf.rsi, 0)} / ${sgn(e.ttf.histo)}` })],
              [
                h('dt', { text: 'Plus haut / bas 3 mois' }),
                h('dd', { text: `${fmt(e.ttf.haut3m)} / ${fmt(e.ttf.bas3m)}` }),
              ]
            )
          )
        : null
    )
  );
  const fr = Object.values(e.france || {});
  const tv = (e.ttf || {}).vues;
  if (tv && tv.graphique) {
    out.push(h('h2', { text: '⛽ Gaz TTF : graphique et indicateurs' }));
    out.push(
      h(
        'section',
        { class: 'card' },
        h('p', {
          class: 'note',
          text: "Le gaz fait le prix de l'azote avec environ 1 mois de décalage. Lecture acheteur : un gaz en survente ou au bas de son canal annonce un azote moins cher dans les semaines qui suivent.",
        }),
        periodPanel({
          nom: 'Gaz TTF',
          unite: '€/MWh',
          graphique: tv.graphique,
          long: tv.long,
          technique: tv.technique,
          series: tv.series,
          niveaux: null,
          mode: 'acheteur',
        })
      )
    );
  }
  if (e.histo_uree && e.histo_uree.length > 12) {
    out.push(h('h2', { text: '🧪 Urée et DAP sur 10 ans (Banque mondiale, mensuel, $/t)' }));
    out.push(
      h(
        'section',
        { class: 'card' },
        chart(e.histo_uree, { channel: false, cone: false, dot: false, label: 'Urée et DAP sur 10 ans' }),
        h(
          'div',
          { class: 'legend' },
          h('span', {}, h('i', { style: 'background:var(--chart-1)' }), 'Urée (Moyen-Orient)'),
          h('span', {}, h('i', { style: 'background:var(--chart-2)' }), 'Urée, moyenne 12 mois'),
          h('span', {}, h('i', { style: 'background:var(--chart-3)' }), 'DAP')
        ),
        h('p', {
          class: 'note',
          text: `Dernier mois publié : ${e.mondial ? e.mondial.mois : '—'}. Les prix France du jour sont dans le tableau plus bas.`,
        })
      )
    );
  }
  const hr = e.histo_ratio;
  if (hr && hr.points && hr.points.length > 12) {
    const lv = [
      { v: hr.seuils['20'], c: 'var(--good)', t: 'Acheter large (20e percentile)' },
      { v: hr.seuils['60'], c: 'var(--warn)', t: 'Fractionner (60e)' },
      { v: hr.seuils['80'], c: 'var(--bad)', t: 'Attendre (80e)' },
    ];
    if (hr.estimation) lv.push({ v: hr.estimation, c: 'var(--chart-1)', t: '● Estimé ce matin' });
    out.push(h('h2', { text: '⚖️ Ratio urée / blé sur 10 ans' }));
    out.push(
      h(
        'section',
        { class: 'card' },
        chart(
          hr.points.map((r) => [r[0], r[1], null, null]),
          { channel: false, cone: false, levels: lv, label: 'Ratio urée / blé sur 10 ans' }
        ),
        h('p', {
          class: 'note',
          text: "Prix de l'urée divisé par celui du blé (Banque mondiale, mensuel). Plus le ratio est bas, plus l'azote est bon marché par rapport à ce que rapporte le blé. Les seuils sont les percentiles des 10 années précédentes.",
        })
      )
    );
  }
  out.push(h('h2', { text: 'Prix France' }));
  out.push(
    h(
      'div',
      { class: 'card scroll' },
      h(
        'table',
        {},
        h(
          'tr',
          {},
          ['Produit', 'Prix €/t', '€/uN', '1 mois', '3 mois', 'Engrais / blé', 'Cotation'].map((t, i) =>
            h('th', { class: i ? 'n' : '', text: t })
          )
        ),
        fr.map((p) =>
          h(
            'tr',
            {},
            h('td', { text: p.nom }),
            h('td', { class: 'n', text: fmt(p.prix) }),
            h('td', { class: 'n', text: p.euro_un ? fmt(p.euro_un, 3) : '—' }),
            h('td', { class: 'n ' + cls(p.var1m), text: pct(p.var1m) }),
            h('td', { class: 'n ' + cls(p.var3m), text: pct(p.var3m) }),
            h('td', { class: 'n', text: p.ratio_ble ? fmt(p.ratio_ble) : '—' }),
            h('td', { class: 'n', text: dfr(p.date) })
          )
        )
      ),
      h('p', {
        class: 'note',
        text: "Prix départ (port, usine ou Rouen) relevés sur terre-net, pas des prix rendus ferme. €/uN avant pertes : l'urée perd une part de son azote par volatilisation ; vérifier le titre de la solution chez le fournisseur.",
      })
    )
  );
  out.push(
    h(
      'details',
      {},
      h('summary', { text: "Ce que dit l'historique (Banque mondiale, 2000-2024)" }),
      h(
        'ul',
        { class: 'list' },
        [
          'Gaz → urée : décalage d’environ 1 mois ; répercussion cumulée d’environ 0,3 sur 1 à 3 mois.',
          'Gaz plus haussier que l’urée sur 3 mois (quintile haut) : urée en moyenne +13 % les 3 mois suivants (66 % des cas).',
          'Ratio urée/blé ≤ 20e percentile (10 ans) : urée +22 % à 6 mois (86 % des cas) ; ≥ 80e : −11 %.',
          'Urée au plus bas en avril-juin, au plus haut en septembre-novembre.',
          'Engrais, gaz ou pétrole → blé : aucun pouvoir prédictif exploitable.',
        ].map((t) => h('li', { text: t }))
      )
    )
  );
  return out;
}

function cleanHtml(src) {
  const doc = new DOMParser().parseFromString('<div>' + (src || '') + '</div>', 'text/html');
  const ok = new Set([
    'P',
    'H1',
    'H2',
    'H3',
    'H4',
    'UL',
    'OL',
    'LI',
    'STRONG',
    'EM',
    'B',
    'I',
    'TABLE',
    'THEAD',
    'TBODY',
    'TR',
    'TH',
    'TD',
    'A',
    'BR',
    'HR',
    'CODE',
    'PRE',
    'BLOCKQUOTE',
    'DIV',
    'SPAN',
  ]);
  const walk = (node) => {
    [...node.children].forEach((el) => {
      if (!ok.has(el.tagName)) {
        el.replaceWith(document.createTextNode(el.textContent));
        return;
      }
      [...el.attributes].forEach((at) => {
        const keep =
          (el.tagName === 'A' && at.name === 'href' && /^https?:\/\//i.test(at.value)) ||
          (el.tagName === 'TD' && at.name === 'align') ||
          (el.tagName === 'TH' && at.name === 'align');
        if (!keep) el.removeAttribute(at.name);
      });
      if (el.tagName === 'A') {
        el.setAttribute('rel', 'noopener noreferrer');
        el.setAttribute('target', '_blank');
      }
      walk(el);
    });
  };
  const root = doc.body.firstChild;
  walk(root);
  return root;
}

function vComite() {
  const c = GS.comite || {};
  const out = [];
  if (!c.date) {
    out.push(
      h('div', {
        class: 'alert info',
        text:
          c.erreur ||
          "Aucun comité pour l'instant : il se réunit chaque lundi matin et quand un déclencheur important saute.",
      })
    );
    return out;
  }
  if (c.erreur) out.push(h('div', { class: 'alert', text: c.erreur }));
  out.push(
    h(
      'p',
      { class: 'note' },
      `Comité ${c.mode === 'alerte' ? "d'alerte" : 'complet'} du ${dfr(c.date)} — ${c.modele || ''}` +
        (c.usage ? ` — ${c.usage.searches || 0} recherches web` : '') +
        (c.cout_usd !== undefined ? `, ≈ ${fmt(c.cout_usd)} $` : '')
    )
  );
  if (c.consigne && c.mode === 'alerte') out.push(h('div', { class: 'alert', text: c.consigne }));
  out.push(h('article', { class: 'card rapport' }, cleanHtml(c.rapport_html)));
  if (c.sources && c.sources.length)
    out.push(
      h(
        'details',
        {},
        h('summary', { text: `Sources consultées (${c.sources.length})` }),
        h(
          'ul',
          { class: 'list' },
          c.sources
            .filter((s) => /^https?:\/\//i.test(s.url))
            .map((s) =>
              h('li', {}, h('a', { href: s.url, rel: 'noopener noreferrer', target: '_blank', text: s.titre || s.url }))
            )
        )
      )
    );
  if (GS.journal.length)
    out.push(
      h(
        'details',
        {},
        h('summary', { text: `Comités précédents (${GS.journal.length})` }),
        h(
          'ul',
          { class: 'list' },
          GS.journal.map((j) => h('li', {}, h('b', { text: `${dfr(j.date)} (${j.mode})` }), ' — ' + (j.resume || '')))
        )
      )
    );
  return out;
}

function vMethode() {
  const txt = [
    [
      'Chaque matin',
      "Grain Signal relève les cours Euronext (blé, colza, maïs) et leurs courbes, les marchés américains, le gaz TTF, le Brent, l'euro-dollar, les positions des fonds (rapport Euronext et CFTC), les prix des engrais en France et le Pink Sheet de la Banque mondiale. Il calcule la technique (RSI 14, MACD 12/26/9, moyennes mobiles 20/50/200, Bollinger 20/2, Fibonacci, divergences), le module engrais et les déclencheurs, puis envoie un email s'il se passe quelque chose.",
    ],
    [
      'Le comité',
      "Chaque lundi, et quand un déclencheur important saute (au plus deux fois par semaine), un comité de 10 experts (bilans, mer Noire, physique, macro, positions des fonds, météo, technique, risque, avocat du diable, achat d'engrais) est réuni par l'API Claude avec la recherche web. Il reçoit les chiffres du matin et cherche ce que l'outil ne mesure pas : bilans, mer Noire, météo, demande, actualité. Son avis fixe le signal de chaque culture pour 8 jours.",
    ],
    [
      'Entre deux comités',
      "Le score du comité est actualisé chaque matin par la variation de la technique, des fonds et de la macro (10 % chacun, comme dans la grille du comité). Si cela suffit à changer de case dans la matrice, la culture est marquée « à revoir » et un comité d'alerte est demandé.",
    ],
    [
      'Matrice',
      "Score ≤ −1 : vendre une tranche ou couvrir · entre −1 et +0,5 : tenir le plan · ≥ +0,5 : attendre ou stocker. Le timing technique décide du moment : pas de vente en survente ou au bas du range de 3 mois, accélération en surachat qui s'essouffle.",
    ],
    [
      'Limites',
      "Les historiques Euronext sont reconstitués chaque jour (indicateurs complets après 30 séances, MM200 après 200) ; avant, la technique s'appuie sur le marché américain correspondant. Les escourgeons et orges de printemps n'ont pas de marché à terme : ils suivent le blé, avec l'avis du comité sur les primes brassicoles. Les résultats historiques du module engrais portent sur l'urée mondiale et le blé US en dollars. L'outil ne connaît ni vos coûts ni vos volumes : il raisonne en pourcentages.",
    ],
  ];
  return [
    h(
      'div',
      { class: 'grid' },
      txt.map(([t, p]) => h('section', { class: 'card' }, h('h3', { text: t }), h('p', { text: p })))
    ),
    h('div', { style: 'margin-top:12px' }, calendarTable()),
    backtestSection(),
  ].concat(sources());
}

function sources() {
  const s = ((GS.data || {}).collecte || {}).sources || {};
  const rows = Object.entries(s).map(([k, v]) =>
    h(
      'tr',
      {},
      h('td', { text: k.replace(/_/g, ' ') }),
      h('td', { class: v.ok ? 'up' : 'down', text: v.ok ? 'lue' : 'en échec' }),
      h('td', { class: 'muted', text: v.detail || '' })
    )
  );
  return [
    h('h2', { text: 'Collecte du matin' }),
    h(
      'div',
      { class: 'card scroll' },
      h(
        'table',
        {},
        h(
          'tr',
          {},
          ['Source', 'État', 'Détail'].map((t) => h('th', { text: t }))
        ),
        rows
      )
    ),
  ];
}

function render() {
  const main = document.getElementById('main');
  main.textContent = '';
  if (!GS.data) {
    main.append(
      h('p', {
        class: 'pad muted',
        text: 'Données indisponibles pour le moment : le premier calcul du matin ne les a pas encore publiées.',
      })
    );
    return;
  }
  const v =
    { signaux: vSignaux, technique: vTechnique, engrais: vEngrais, comite: vComite, methode: vMethode }[GS.tab] ||
    vSignaux;
  main.append(...v());
  document
    .querySelectorAll('.tabs button')
    .forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === GS.tab)));
}

async function getJSON(path) {
  try {
    const r = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    return r.ok ? await r.json() : null;
  } catch (e) {
    return null;
  }
}

async function init() {
  const tab = (location.hash || '').slice(1);
  if (['signaux', 'technique', 'engrais', 'comite', 'methode'].includes(tab)) GS.tab = tab;
  document.querySelectorAll('.tabs button').forEach((b) =>
    b.addEventListener('click', () => {
      GS.tab = b.dataset.tab;
      history.replaceState(null, '', '#' + GS.tab);
      render();
      window.scrollTo({ top: 0 });
    })
  );
  window.addEventListener('hashchange', () => {
    const t = (location.hash || '').slice(1);
    if (['signaux', 'technique', 'engrais', 'comite', 'methode'].includes(t) && t !== GS.tab) {
      GS.tab = t;
      render();
    }
  });
  const [d, c, j, bt] = await Promise.all([
    getJSON('data/grain/grain-signal.json'),
    getJSON('data/grain/comite.json'),
    getJSON('data/grain/comites-journal.json'),
    getJSON('data/grain/backtest.json'),
  ]);
  GS.backtest = bt;
  GS.data = d;
  GS.comite = c || {};
  GS.journal = Array.isArray(j) ? j : [];
  const sub = document.getElementById('sub');
  if (d) {
    const s = Object.values((d.collecte || {}).sources || {});
    const ok = s.filter((x) => x.ok).length;
    sub.textContent =
      `Calcul du ${dfr(d.date)} · ${ok}/${s.length} sources lues` +
      (GS.comite.date ? ` · comité du ${dfr(GS.comite.date)}` : '');
  } else sub.textContent = 'Données indisponibles';
  render();
}

init();
