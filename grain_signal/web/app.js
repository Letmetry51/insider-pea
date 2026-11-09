/* Grain Signal — page (lecture seule de data/grain/*.json, publiés chaque matin). Tout texte venu des données est inséré
   comme texte ; seul le rapport du comité est du HTML, déjà nettoyé au calcul et nettoyé une seconde fois ici. */
'use strict';

const GS = { data: null, comite: null, journal: [], tab: 'aujourdhui' };
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
  const fs = narrow ? 13 : 11; // textes du graphique (le repère du téléphone est réduit d'environ 15 % à l'écran)
  const tags = (opts.levels || []).length > 0 || opts.priceTag;
  const W = narrow ? 420 : 680,
    H = opts.h || (narrow ? 290 : 270),
    P = { l: narrow ? 44 : 40, r: tags ? (narrow ? 66 : 70) : 6, t: 22, b: 22 }; // marge droite : étiquettes de prix
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
      { x: P.l - 6, y: y(v) + 4, 'text-anchor': 'end', 'font-size': fs, fill: 'var(--muted)' },
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
          'font-size': fs,
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
        'stroke-width': k ? 1.3 : 1,
        'stroke-dasharray': k ? '7 5' : '2 4',
        opacity: k ? 0.75 : 0.5,
        'clip-path': clipUrl,
      });
    });
    const pctMonth = ((reg.slope * 21) / last) * 100;
    canal = { pente: pctMonth, sens: pctMonth > 0.8 ? 'haussier' : pctMonth < -0.8 ? 'baissier' : 'horizontal' };
    canal.position = (last - (yAt(li) - 2 * reg.sd)) / (4 * reg.sd);
    svgEl(
      svg,
      'text',
      { x: P.l + 6, y: P.t - 6, 'font-size': fs, 'font-weight': 700, fill: 'var(--channel)', class: 'halo' },
      `Canal ${canal.sens}`
    );
  }
  // niveaux nommés : ligne dans le graphique, prix dans une étiquette colorée à droite (hors du tracé), nom dans la liste
  // sous le graphique ; plus aucun texte posé sur les courbes
  const tagList = [];
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
        'stroke-width': 1.4,
        'stroke-dasharray': '4 3',
        opacity: 0.9,
      });
    }
    tagList.push({ v: l.v, c: l.c, ink: 'var(--tag-ink)' });
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
  // pastilles des avis passés (carnet de bord) : couleur du signal, détail au survol
  (opts.marks || []).forEach((m) => {
    const i = pts.findIndex((r) => r[0] >= m.d);
    if (i < 0) return;
    const cy = y(pts[i][1]);
    const g = svgEl(svg, 'g', { class: 'mark' });
    svgEl(g, 'title', {}, m.t);
    const k = cy - 25 >= P.t ? -1 : 1; // au-dessus du cours, en dessous s'il n'y a pas la place
    svgEl(g, 'line', { x1: x(i), x2: x(i), y1: cy + 7 * k, y2: cy + 19 * k, stroke: m.c, 'stroke-width': 1.5 });
    svgEl(g, 'circle', { cx: x(i), cy: cy + 25 * k, r: 6, fill: m.c, stroke: 'var(--surface)', 'stroke-width': 1.5 });
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
  // étiquettes de prix dans la marge droite, écartées les unes des autres (cours du jour compris)
  if (tags) {
    if (opts.dot !== false) tagList.push({ v: last, c: 'var(--ink)', ink: 'var(--surface)', cours: true }); // cours du jour : noir sur clair, blanc sur sombre
    const th = fs + 6,
      gap = th + 2;
    tagList.forEach((t) => (t.y = y(t.v)));
    tagList.sort((a, b) => a.y - b.y);
    for (let k = 1; k < tagList.length; k++) tagList[k].y = Math.max(tagList[k].y, tagList[k - 1].y + gap);
    const over = tagList.length ? tagList[tagList.length - 1].y - (H - P.b - th / 2) : 0;
    if (over > 0) tagList.forEach((t) => (t.y -= over));
    for (let k = tagList.length - 2; k >= 0; k--) tagList[k].y = Math.min(tagList[k].y, tagList[k + 1].y - gap);
    const x0 = W - P.r + 3,
      tw = P.r - 5;
    tagList.forEach((t) => {
      if (Math.abs(t.y - y(t.v)) > 1)
        svgEl(svg, 'line', { x1: W - P.r, x2: x0, y1: y(t.v), y2: t.y, stroke: t.c, 'stroke-width': 1.2 });
      svgEl(svg, 'rect', { x: x0, y: t.y - th / 2, width: tw, height: th, rx: 4, fill: t.c });
      svgEl(
        svg,
        'text',
        {
          x: x0 + tw / 2,
          y: t.y + fs / 2 - 1.5,
          'text-anchor': 'middle',
          'font-size': fs - 1,
          'font-weight': 700,
          fill: t.ink,
        },
        fmt(t.v, t.v >= 1000 ? 0 : t.v >= 100 ? 1 : 2)
      );
    });
  }
  const wrap = h('div', {}, svg);
  if ((opts.levels || []).length)
    wrap.appendChild(
      h(
        'div',
        { class: 'lvls' },
        opts.dot !== false
          ? h(
              'span',
              { class: 'lvl' },
              h('i', { class: 'now' }),
              'Cours du jour : ',
              h('b', { text: `${fmt(last, 2)}${opts.levels[0].u ? ' ' + opts.levels[0].u : ''}` })
            )
          : null,
        opts.levels.map((l) =>
          h(
            'span',
            { class: 'lvl' },
            h('i', { style: `color:${l.c}` }),
            `${l.t} : `,
            h('b', { text: `${fmt(l.v, 2)}${l.u ? ' ' + l.u : ''}` }),
            l.p ? h('span', { class: 'muted', text: ` · ${l.p}` }) : null
          )
        )
      )
    );
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

/* percentile en jauge (même forme que le RSI) : pastille chiffrée, libellé, barre colorée et curseur.
   vendeur / prime : vert = bon moment pour vendre ; ratio / acheteur : vert = bon moment pour acheter ; cot : lecture à contre-courant */
const SEG5V = [
  [20, 'var(--bad)'],
  [40, 'var(--warn)'],
  [60, 'var(--neutral)'],
  [80, 'var(--info)'],
  [100, 'var(--good)'],
];
const SEG5A = [
  [20, 'var(--good)'],
  [40, 'var(--info)'],
  [60, 'var(--neutral)'],
  [80, 'var(--warn)'],
  [100, 'var(--bad)'],
];
const T5 = [
  [20, '20'],
  [50, '50'],
  [80, '80'],
];
const lab5 = (v, t) => (v <= 20 ? t[0] : v <= 40 ? t[1] : v < 60 ? t[2] : v < 80 ? t[3] : t[4]);
const PG = {
  vendeur: {
    segs: SEG5V,
    ticks: T5,
    lab: (v) =>
      lab5(v, [
        ['Prix bas : ne pas brader', 'bad'],
        ['Plutôt bas', 'warn'],
        ['Dans la moyenne', 'neutral'],
        ['Plutôt haut', 'info'],
        ['Prix haut : bon pour vendre', 'good'],
      ]),
  },
  prime: {
    segs: SEG5V,
    ticks: T5,
    lab: (v) =>
      lab5(v, [
        ['Prime faible : vendre via Euronext', 'bad'],
        ['Prime plutôt faible', 'warn'],
        ['Prime normale', 'neutral'],
        ['Prime plutôt forte', 'info'],
        ['Prime forte : vendre au physique', 'good'],
      ]),
  },
  acheteur: {
    segs: SEG5A,
    ticks: T5,
    lab: (v) =>
      lab5(v, [
        ['Bas : bon prix d’achat', 'good'],
        ['Plutôt bas', 'info'],
        ['Dans la moyenne', 'neutral'],
        ['Plutôt cher', 'warn'],
        ['Cher : le minimum', 'bad'],
      ]),
  },
  ratio: {
    segs: [
      [20, 'var(--good)'],
      [60, 'var(--neutral)'],
      [80, 'var(--warn)'],
      [100, 'var(--bad)'],
    ],
    ticks: [
      [20, '20'],
      [60, '60'],
      [80, '80'],
    ],
    lab: (v) =>
      v <= 20
        ? ['Azote bon marché : acheter large', 'good']
        : v <= 60
          ? ['Normal : suivre le plan', 'neutral']
          : v <= 80
            ? ['Cher : fractionner', 'warn']
            : ['Très cher : attendre', 'bad'],
  },
  stocks: {
    segs: SEG5V,
    ticks: T5,
    lab: (v) =>
      lab5(v, [
        ['Stocks très serrés : risque de flambée', 'bad'],
        ['Stocks plutôt serrés', 'warn'],
        ['Stocks dans la moyenne', 'neutral'],
        ['Stocks plutôt confortables', 'info'],
        ['Stocks confortables : peu de risque de flambée', 'good'],
      ]),
  },
  cot: {
    segs: [
      [15, 'var(--bad)'],
      [85, 'var(--neutral)'],
      [100, 'var(--good)'],
    ],
    ticks: [
      [15, '15'],
      [85, '85'],
    ],
    lab: (v) =>
      v <= 15
        ? ['Fonds très vendeurs : rebond possible', 'bad']
        : v >= 85
          ? ['Fonds très acheteurs : vendre', 'good']
          : ['Neutre', 'neutral'],
  },
};
// humeur du marché (0 peur → 100 euphorie), pression de l'actualité (−2 → +2), risque géopolitique (percentile sur 10 ans)
const SEG_ACTU = [
  [25, 'var(--bad)'],
  [37.5, 'var(--warn)'],
  [62.5, 'var(--neutral)'],
  [75, 'var(--info)'],
  [100, 'var(--good)'],
];
// mêmes seuils que le calcul (±0,5 = 37,5 et 62,5 ; ±1 = 25 et 75)
const actuLab = (v, t) => (v <= 25 ? t[0] : v <= 37.5 ? t[1] : v < 62.5 ? t[2] : v < 75 ? t[3] : t[4]);
Object.assign(PG, {
  psy: {
    segs: SEG5V,
    ticks: T5,
    badge: (v) => String(Math.round(v)),
    lab: (v) =>
      lab5(v, [
        ['Peur extrême : ne pas vendre dans la panique', 'bad'],
        ['Peur : pas de vente forcée', 'warn'],
        ['Humeur neutre', 'neutral'],
        ['Optimisme : bonne fenêtre pour une tranche', 'info'],
        ['Euphorie : ne pas laisser passer une tranche', 'good'],
      ]),
  },
  actu: {
    segs: SEG_ACTU,
    ticks: [
      [0, '−2'],
      [50, '0'],
      [100, '+2'],
    ],
    map: (v) => Math.max(0, Math.min(100, ((v + 2) / 4) * 100)),
    badge: (v) => sgn(v, 1),
    lab: (v) =>
      actuLab(v, [
        ['Très baissière', 'bad'],
        ['Plutôt baissière', 'warn'],
        ['Équilibrée', 'neutral'],
        ['Plutôt haussière', 'info'],
        ['Très haussière', 'good'],
      ]),
  },
  actuEngrais: {
    segs: SEG_ACTU.map(([b], i) => [b, SEG_ACTU[SEG_ACTU.length - 1 - i][1]]),
    ticks: [
      [0, '−2'],
      [50, '0'],
      [100, '+2'],
    ],
    map: (v) => Math.max(0, Math.min(100, ((v + 2) / 4) * 100)),
    badge: (v) => sgn(v, 1),
    lab: (v) =>
      actuLab(v, [
        ['Nettement moins cher en vue', 'good'],
        ['Plutôt moins cher', 'info'],
        ['Équilibrée', 'neutral'],
        ['Plutôt plus cher', 'warn'],
        ['Nettement plus cher en vue', 'bad'],
      ]),
  },
  geo: {
    segs: [
      [30, 'var(--good)'],
      [70, 'var(--neutral)'],
      [90, 'var(--warn)'],
      [100, 'var(--bad)'],
    ],
    ticks: [
      [30, '30'],
      [70, '70'],
      [90, '90'],
    ],
    lab: (v) =>
      v <= 30
        ? ['Monde calme', 'good']
        : v < 70
          ? ['Tensions habituelles', 'neutral']
          : v < 90
            ? ['Tensions élevées : marchés nerveux', 'warn']
            : ['Tensions très élevées : risque de chocs', 'bad'],
  },
});
function pgauge(v, kind, title, note, compact) {
  if (v === null || v === undefined || Number.isNaN(v)) return null;
  const k = PG[kind];
  const raw = v;
  if (k.map) v = k.map(v); // échelle propre (pression de l'actualité de −2 à +2) ramenée sur 0-100
  const [lab, cl] = k.lab(v);
  const txt = k.badge ? k.badge(raw) : `${Math.round(v)}e`;
  return h(
    'div',
    { class: 'pg' + (compact ? ' compact' : '') },
    title ? h('div', { class: 'pg-t', text: title }) : null,
    h(
      'div',
      { class: 'ival' },
      h('span', { class: 'badge ' + cl, text: txt, title: k.badge ? txt : `${Math.round(v)}e percentile` }),
      h('span', { class: 'ilabel', text: lab })
    ),
    gauge(v, 0, 100, k.segs, compact ? [] : k.ticks),
    note ? h('div', { class: 'pg-n', text: note }) : null
  );
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
        marks: p.marks,
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
      marks: per === '1a' ? p.marks : null,
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
    p.simple
      ? null
      : ta && !ta.insuffisant
        ? indicatorCards(ta, p.series, p.niveaux, g.canal, p.mode)
        : h('p', { class: 'note', text: 'Indicateurs disponibles à partir de 30 séances.' }),
    !p.simple && ta && !ta.insuffisant
      ? h('details', {}, h('summary', { text: '📋 Tous les chiffres' }), techTable(ta))
      : null
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
  const pb = (niv && niv.probas) || {};
  const hz = pb.horizon ? ` d'ici le ${dfr(pb.horizon)}` : '';
  // « 1er ordre : 235,50 €/t » et non « Ordre 1 235,50 », qui se lisait 1 235,50 €
  (niv && niv.ordres ? niv.ordres : []).forEach((v, i) =>
    lv.push({
      v,
      c: 'var(--good)',
      t: `🎯 ${i === 0 ? '1er' : `${i + 1}e`} ordre`,
      u,
      p:
        (pb.ordres || [])[i] !== undefined && (pb.ordres || [])[i] !== null
          ? `${pb.ordres[i]} % de chances${hz}`
          : null,
    })
  );
  if (niv && niv.revision)
    lv.push({
      v: niv.revision,
      c: 'var(--bad)',
      t: '🛑 Révision',
      u,
      p: pb.revision !== undefined && pb.revision !== null ? `${pb.revision} % de risque${hz}` : null,
    });
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

const STRAT = {
  S0: 'Tout vendre à la moisson',
  S1: 'Même quantité chaque mois',
  S2: 'Calendrier Grain Signal',
  S3: 'Calendrier + timing technique',
  S4: 'Calendrier + timing + tendance',
  S5: 'Outil complet (sans comité)',
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
// bilan par décennie : une stratégie qui ne gagne que sur une période est fragile
function periodTable(per) {
  const P = Object.entries(per || {});
  if (!P.length) return null;
  const keys = Object.keys(P[0][1]).filter((k) => k !== 'S1');
  return h(
    'div',
    { class: 'scroll' },
    h(
      'table',
      {},
      h(
        'tr',
        {},
        h('th', { text: 'Gain / mensuel (€/t) par période' }),
        keys.map((k) => h('th', { class: 'n', text: STRAT[k] || k }))
      ),
      P.map(([lab, b]) =>
        h(
          'tr',
          {},
          h('td', { text: `${lab} (${b[keys[0]].campagnes} camp.)` }),
          keys.map((k) => h('td', { class: 'n ' + cls(b[k].ecart_moyen), text: sgn(b[k].ecart_moyen, 1) }))
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
        text: `Par rapport à une vente mensuelle régulière : calendrier ${g('S2')} ; avec le timing technique ${g('S3')} ; avec la tendance ${g('S4')}${b.S5 ? ` ; outil complet ${g('S5')}` : ''}.`,
      }),
      btTable(b, '€/t'),
      periodTable(v.periodes),
      h('p', {
        class: 'note',
        text: `Meilleur réglage du timing testé : RSI < ${v.variantes_timing[0].rsi} et bas du range ≤ ${v.variantes_timing[0].pos} % (${sgn(v.variantes_timing[0].ecart_moyen_vs_S2)} €/t par rapport au calendrier seul). Réglage actuel : RSI < 40 et ≤ 20 %.`,
      })
    );
  }
  const eu = Object.values(bt.ventes_euronext || {});
  if (eu.length) {
    parts.push(h('h4', { class: 'ititle', text: '🇪🇺 Sur les cours officiels Euronext (depuis novembre 2019)' }));
    for (const v of eu) {
      if (v.erreur) {
        parts.push(h('p', { class: 'note', text: `${v.nom} : ${v.erreur}` }));
        continue;
      }
      parts.push(
        h('p', { text: `${v.nom} — ${v.campagnes.length} campagnes depuis ${v.campagnes[0].recolte}` }),
        btTable(v.bilan_vs_S1, '€/t')
      );
    }
    const cmp = bt.comparaison || {};
    const lignes = Object.entries(cmp).flatMap(([cult, o]) =>
      Object.entries(o).map(
        ([k, x]) =>
          `${cult === 'ble' ? 'Blé' : 'Maïs'}, ${STRAT[k]} : Chicago ${sgn(x.chicago, 1)}, Euronext ${sgn(x.euronext, 1)} €/t (même sens ${x.meme_sens} fois sur ${x.campagnes})`
      )
    );
    if (lignes.length)
      parts.push(
        h('p', { class: 'note', text: 'Campagnes communes, écart par rapport à la vente mensuelle :' }),
        h(
          'ul',
          { class: 'list note' },
          lignes.map((t) => h('li', { text: t }))
        )
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
// résumé d'une tranche ; orges (sur = vendues selon le blé) : prix de l'orge = ordre sur le blé + écart orge/blé du jour
function court(p, sur, ecart) {
  if (!p) return '—';
  if (p.code === 'rien') return `Prochaine tranche : ${p.periode}`;
  const prix = !p.ordre
    ? ''
    : sur && ecart !== undefined && ecart !== null
      ? `à ≈ ${fmt(p.ordre + ecart)} €/t`
      : `${sur ? 'blé ≥ ' : 'à '}${fmt(p.ordre)} €/t`;
  if (p.code === 'ordre') return `${p.pct} % ${prix}`;
  if (p.code === 'executer') return `${p.pct} % ${prix || 'cette période'}`.trim();
  if (p.code === 'attendre') return `Décaler les ${p.pct} %`;
  if (p.code === 'patienter') return `${p.pct} % au prochain rebond`;
  if (p.code === 'couvrir') return `Couvrir ${p.pct} %`;
  return `${p.pct} %`;
}
const SIGC = { VENDRE: 'var(--good)', COUVRIR: 'var(--info)', TENIR: 'var(--warn)', ATTENDRE: 'var(--bad)' };
const SIGT = {
  VENDRE: 'vendre une tranche',
  COUVRIR: 'couvrir',
  TENIR: 'tenir le plan',
  ATTENDRE: 'attendre-stocker',
  ACHETER_LARGE: 'acheter large',
  SUIVRE: 'suivre le plan',
  FRACTIONNER: 'fractionner',
};
const BASE = { ble: 'ble', escourgeon: 'ble', orge_printemps: 'ble', colza: 'colza', mais: 'mais' };
const BASE_USDA = { ble: 'ble', escourgeon: 'orge', orge_printemps: 'orge', colza: 'colza', mais: 'mais' };
// « 1er ordre : 42 % de chances d'être touché d'ici le 30 nov. » (volatilité des 3 derniers mois, sans tendance)
function probaTxt(pb) {
  if (!pb || !pb.ordres || !pb.ordres.length) return '';
  const o = pb.ordres
    .map((p, i) => (p === null || p === undefined ? null : `${i === 0 ? '1er' : `${i + 1}e`} ordre ${p} %`))
    .filter(Boolean);
  const rv =
    pb.revision !== null && pb.revision !== undefined ? ` ; risque de passer sous la révision : ${pb.revision} %` : '';
  return o.length ? `${o.join(' · ')} de chances d'être touchés d'ici le ${dfr(pb.horizon)}${rv}` : '';
}
// résultat d'un avis du carnet à 4 ou 8 semaines : ✅ bon, ❌ mauvais, ➖ neutre, ⏳ pas encore jugé
function verdict(r, unite) {
  if (!r) return '—';
  if (r.variation === undefined) return `⏳ ${dfr(r.le)}`;
  const ic = { bon: '✅', mauvais: '❌' }[r.verdict] || '➖';
  if (r.gain === undefined) return `${ic} cours ${pct(r.pct)}`;
  return `${ic} ${fmt(Math.abs(r.gain))} ${unite} ${r.gain >= 0 ? 'gagnés' : 'perdus'}`;
}
function marksFor(cle) {
  return ((GS.data.carnet || {}).entrees || [])
    .filter((x) => x.cle === cle)
    .map((x) => ({
      d: x.date,
      c: SIGC[x.signal] || 'var(--muted)',
      t: `${dfr(x.date)} : comité « ${SIGT[x.signal] || x.signal} »${x.prix ? ` à ${fmt(x.prix)} €/t` : ''}${
        x.s8 && x.s8.variation !== undefined ? ` · 8 semaines après : ${verdict(x.s8, '€/t')}` : ''
      }`,
    }));
}

/* carnet de bord : chaque avis du comité, jugé 4 et 8 semaines plus tard sur le cours réel */
function carnetSection(d) {
  const cb = d.carnet || {};
  const rows = (cb.entrees || []).slice().reverse();
  if (!rows.length) return [];
  const b = cb.bilan || {};
  const noms = Object.fromEntries(
    Object.entries(d.cultures || {}).map(([k, c]) => [k, c.nom.replace(' brassicole', '')])
  );
  noms.engrais = 'Azote (urée)';
  const prochain = rows
    .map((x) => (x.s4 && x.s4.variation === undefined ? x.s4.le : null))
    .filter(Boolean)
    .sort()[0];
  return [
    h('h2', { text: '📓 Carnet de bord des avis' }),
    h(
      'div',
      { class: 'card scroll' },
      h('p', {
        class: 'cbilan',
        text: b.juges
          ? `Avis jugés à 8 semaines : ✅ ${b.bons} bon${b.bons > 1 ? 's' : ''} · ❌ ${b.mauvais} mauvais${
              b.gain_moyen !== null && b.gain_moyen !== undefined
                ? ` · gain moyen ${sgn(b.gain_moyen)} €/t par avis suivi`
                : ''
            }`
          : `Premiers résultats le ${dfr(prochain || d.date)} : chaque avis est jugé 4 et 8 semaines après, sur le cours réel.`,
      }),
      h(
        'table',
        {},
        h(
          'tr',
          {},
          ['Date', 'Culture', 'Avis du comité', 'Prix', '4 semaines', '8 semaines'].map((t, i) =>
            h('th', { class: i === 3 ? 'n' : '', text: t })
          )
        ),
        rows.map((x) => {
          const u = '€/t';
          return h(
            'tr',
            {},
            h('td', { text: dfr(x.date) }),
            h('td', { text: `${ICON[x.cle] || (x.cle === 'engrais' ? '🧪' : '')} ${noms[x.cle] || x.cle}` }),
            h(
              'td',
              {},
              h('span', { class: 'dot', style: `background:${SIGC[x.signal] || 'var(--muted)'}` }),
              SIGT[x.signal] || x.signal
            ),
            h('td', { class: 'n', text: x.prix ? fmt(x.prix) : '—' }),
            h('td', { text: verdict(x.s4, u) }),
            h('td', { text: verdict(x.s8, u) })
          );
        })
      ),
      h('p', {
        class: 'note',
        text: "Vendre (ou couvrir) est jugé bon si le cours a baissé ensuite, attendre si le cours a monté ; pour l'azote, acheter large est bon si l'urée a monté, attendre si elle a baissé. « Tenir le plan », « suivre » et « fractionner » ne parient pas sur un sens : seul le mouvement du cours est indiqué. Les orges sont jugées sur le blé Euronext. Écart de moins de 0,5 % : neutre (➖).",
      })
    ),
  ];
}

/* bilans mondiaux de l'USDA : le rapport stocks / consommation situe le niveau de prix par rapport aux fondamentaux */
function stocksSection(d) {
  const sm = d.stocks_mondiaux || {};
  const rows = ['ble', 'orge', 'mais', 'colza'].filter((k) => sm[k]);
  if (!rows.length) return [];
  const noms = { ble: '🌾 Blé', orge: '🍺 Orge', mais: '🌽 Maïs', colza: '🌼 Colza' };
  const maj = Object.values((sm._source || {}).dates || {}).filter(Boolean)[0];
  return [
    h('h2', { text: '🌍 Bilans mondiaux (USDA)' }),
    h(
      'div',
      { class: 'card scroll' },
      h(
        'table',
        {},
        h(
          'tr',
          {},
          ['Culture', 'Campagne', 'Production', 'Stocks de fin', 'Stocks / consommation', 'Révision', 'Sur 20 ans'].map(
            (t, i) => h('th', { class: i > 1 && i < 6 ? 'n' : '', text: t })
          )
        ),
        rows.map((k) => {
          const st = sm[k];
          return h(
            'tr',
            {},
            h('td', { text: noms[k] }),
            h('td', { text: st.campagne }),
            h('td', { class: 'n', text: `${fmt(st.prod, 0)} Mt` }),
            h('td', { class: 'n', text: `${fmt(st.stocks, 0)} Mt` }),
            h('td', { class: 'n', text: `${fmt(st.ratio, 1)} %${st.hors_chine ? ' hors Chine' : ''}` }),
            h('td', {
              class: 'n ' + (st.revision > 0 ? 'down' : st.revision < 0 ? 'up' : ''),
              text: st.revision !== undefined ? `${sgn(st.revision, 1)} pt` : '—',
            }),
            h('td', { class: 'pgcell' }, pgauge(st.percentile, 'stocks', null, null, true))
          );
        })
      ),
      h('p', {
        class: 'note',
        text: `Stocks de fin de campagne rapportés à la consommation de l'année, projection de l'USDA${maj ? ` (mise à jour du ${dfr(maj)})` : ''}. Hors Chine pour le blé et le maïs : la Chine détient environ la moitié des stocks mondiaux, peu accessibles au marché. Plus le rapport est bas, plus les prix sont hauts et nerveux ; il situe le niveau de prix, il ne dit pas quand il bougera. Une révision à la baisse des stocks (en vert) soutient les prix.`,
      })
    ),
  ];
}

/* profil saisonnier : écart habituel de chaque mois au prix moyen de la campagne */
function saisonSection(d) {
  const sa = d.saison || {};
  if (!Object.keys(sa).length) return [];
  const now = +d.date.slice(5, 7);
  const cards = Object.entries(sa).map(([k, p]) => {
    const order = Array.from({ length: 12 }, (_, i) => ((p.debut_campagne - 1 + i) % 12) + 1);
    const m = Math.max(...p.mois.map(Math.abs)) || 1;
    return h(
      'section',
      { class: 'card' },
      h('h3', { text: `${ICON[k] || ''} ${k === 'ble' ? 'Blé (et orges)' : 'Maïs'} : mois chers et mois bon marché` }),
      h(
        'div',
        { class: 'season' },
        order.map((mo) => {
          const v = p.mois[mo - 1];
          const a = Math.min(1, Math.abs(v) / m);
          return h(
            'div',
            {
              class: 'smonth' + (mo === now ? ' now' : ''),
              title: `${MOIS[mo - 1]} : ${pct(v)} par rapport à la moyenne de la campagne (médiane de ${p.campagnes} campagnes)`,
            },
            h('span', {
              class: 'sbar',
              style: `background:${v >= 0 ? 'var(--good)' : 'var(--bad)'};opacity:${(0.25 + 0.75 * a).toFixed(2)}`,
            }),
            h('span', { class: 'sm', text: MOIS[mo - 1].replace('.', '') }),
            h('span', { class: 'sv', text: (v > 0 ? '+' : '') + fmt(v, 1) })
          );
        })
      ),
      h('p', {
        class: 'note',
        text: `🟩 mois habituellement plus chers que la moyenne de la campagne, 🟥 moins chers (en %, médiane de ${p.campagnes} campagnes ; mois en cours encadré). Plus chers : ${p.plus_chers
          .map((x) => MOIS[x - 1])
          .join(
            ', '
          )} ; moins chers : ${p.moins_chers.map((x) => MOIS[x - 1]).join(', ')}. Source : ${p.source}. Une tendance, pas une règle : une année de crise l'efface.`,
      })
    );
  });
  return [h('h2', { text: '📅 Saisonnalité' }), h('div', { class: 'stack' }, cards)];
}

/* météo des zones de production : pluie des 60 derniers jours par rapport à la normale, chaleur prévue */
function meteoSection(d) {
  const m = d.meteo || {};
  const zs = Object.entries(m.zones || {});
  if (!zs.length) return [];
  const notes = Object.entries(m.cultures || {}).map(
    ([k, c]) => `${ICON[k] || ''} ${{ ble: 'blé', mais: 'maïs' }[k] || k} ${sgn(c.score)}`
  );
  return [
    h('h2', { text: '🌦️ Météo des zones de production' }),
    h(
      'div',
      { class: 'card scroll' },
      h('p', {
        class: 'cbilan',
        text: `Note météo (de −1 à +2, positive = risque de hausse des prix) : ${notes.join(' · ')}`,
      }),
      h(
        'table',
        {},
        h(
          'tr',
          {},
          ['Zone', 'État', 'Pluie 60 jours / normale', 'Pluie prévue 14 j', 'Jours ≥ 32 °C prévus'].map((t, i) =>
            h('th', { class: i > 2 ? 'n' : '', text: t })
          )
        ),
        zs.map(([zn, z]) =>
          h(
            'tr',
            {},
            h('td', { text: zn }),
            h('td', {
              text:
                ({ 'très sec': '🔥 ', sec: '🟠 ', 'un peu sec': '🟡 ', normal: '🟢 ', 'très humide': '💧 ' }[z.etat] ||
                  '') + z.etat,
            }),
            h(
              'td',
              { class: 'pgcell' },
              h(
                'div',
                { class: 'pg compact' },
                h(
                  'div',
                  { class: 'ival' },
                  h('span', {
                    class:
                      'badge ' + (z.ratio < 0.6 ? 'bad' : z.ratio < 0.8 ? 'warn' : z.ratio > 1.5 ? 'info' : 'good'),
                    text: `${Math.round(z.ratio * 100)} %`,
                  }),
                  h('span', { class: 'ilabel', text: `${z.pluie60} mm pour ${z.normale60} mm` })
                ),
                gauge(Math.min(z.ratio * 100, 200), 0, 200, [
                  [40, 'var(--bad)'],
                  [80, 'var(--warn)'],
                  [150, 'var(--good)'],
                  [200, 'var(--info)'],
                ])
              )
            ),
            h('td', { class: 'n', text: `${z.pluie14} mm` }),
            h('td', { class: 'n ' + (z.chaleur14 >= 3 ? 'down' : ''), text: String(z.chaleur14) })
          )
        )
      ),
      h('p', {
        class: 'note',
        text: `Normale : moyenne des 10 années précédentes sur la même fenêtre. Une sécheresse ou une vague de chaleur pendant la saison sensible d'une zone (semis, floraison, remplissage) peut faire monter les prix ; hors saison, elle compte pour un quart. Données ${m.source || 'Open-Meteo'}.`,
      })
    ),
  ];
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

const SIG_ENGRAIS_TXT = {
  ACHETER_LARGE: '🟢 ACHETER LARGE',
  SUIVRE: '🟡 SUIVRE LE PLAN',
  FRACTIONNER: '🟠 FRACTIONNER',
  ATTENDRE: '🔴 ATTENDRE',
};
function vEngrais(detail) {
  const e = GS.data.engrais || {};
  const out = [];
  if (!detail)
    out.push(
      h(
        'div',
        { class: 'grid' },
        h(
          'section',
          { class: 'card' },
          h('h3', { text: 'Décision du matin' }),
          // avis du comité d'abord (comme l'onglet Signaux, l'email et le PDF), règles chiffrées en second
          h('div', {
            class: 'sig',
            text: (e.comite && e.comite.signal && SIG_ENGRAIS_TXT[e.comite.signal]) || e.libelle || '—',
          }),
          e.comite && e.comite.signal
            ? h(
                'div',
                {},
                h('span', { class: 'chip good', text: 'Avis du comité' }),
                e.comite.signal !== e.signal
                  ? h('span', { class: 'chip', text: 'Règles du matin : ' + e.libelle })
                  : null
              )
            : null,
          h('p', {
            text:
              'À acheter maintenant : ' +
              ((e.comite && e.comite.pct) || e.a_acheter || '—') +
              (e.comite && e.comite.prix_plafond ? ` (plafond ${fmt(e.comite.prix_plafond, 0)} €/t)` : ''),
          }),
          e.comite && e.comite.texte ? h('p', { class: 'note', text: e.comite.texte }) : null,
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
            'div',
            { class: 'pgrid' },
            e.estimation
              ? pgauge(e.estimation.percentile, 'ratio', `Estimé ce matin : ${fmt(e.estimation.ratio, 3)}`)
              : null,
            e.mondial
              ? pgauge(
                  e.mondial.percentile,
                  'ratio',
                  `Mondial (${moisFr(e.mondial.mois)}) : ${fmt(e.mondial.ratio, 3)}`
                )
              : null,
            e.mondial
              ? pgauge(
                  e.mondial.uree_percentile,
                  'acheteur',
                  `Urée mondiale seule sur 10 ans : ${fmt(e.mondial.uree, 0)} $/t`
                )
              : null
          ),
          h(
            'dl',
            { class: 'kv' },
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
              pgauge(e.ttf.percentile_5ans, 'acheteur', `Prix sur 5 ans : ${fmt(e.ttf.dernier)} €/MWh`),
              h(
                'dl',
                { class: 'kv' },
                [h('dt', { text: 'Dernier' }), h('dd', { text: `${fmt(e.ttf.dernier)} €/MWh (${dfr(e.ttf.au)})` })],
                [
                  h('dt', { text: '1 sem. / 1 mois / 3 mois' }),
                  h('dd', { text: `${pct(e.ttf.var1s)} / ${pct(e.ttf.var1m)} / ${pct(e.ttf.var3m)}` }),
                ],
                [h('dt', { text: 'MM20 / MM50' }), h('dd', { text: `${fmt(e.ttf.mm20)} / ${fmt(e.ttf.mm50)}` })],
                [
                  h('dt', { text: 'RSI / histo MACD' }),
                  h('dd', { text: `${fmt(e.ttf.rsi, 0)} / ${sgn(e.ttf.histo)}` }),
                ],
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

function vMethode() {
  const txt = [
    [
      'Chaque matin',
      "Grain Signal relève les cours Euronext (blé, colza, maïs) et leurs courbes, les marchés américains, le gaz TTF, le Brent, l'euro-dollar, les positions des fonds (rapport Euronext et CFTC), les prix des engrais en France, le Pink Sheet de la Banque mondiale et la météo de 10 zones de production. Il calcule la technique (RSI 14, MACD 12/26/9, moyennes mobiles 20/50/200, Bollinger 20/2, Fibonacci, divergences), le module engrais et les déclencheurs, puis envoie un email s'il se passe quelque chose.",
    ],
    [
      'Le comité',
      "Chaque lundi, et quand un déclencheur important saute ou qu'un fait majeur tombe dans l'actualité (au plus deux fois par semaine), un comité de 11 experts (bilans, mer Noire, physique, macro, positions des fonds, météo, technique, risque, avocat du diable, achat d'engrais, psychologie des marchés) est réuni par l'API Claude avec la recherche web. Il reçoit les chiffres du matin et cherche ce que l'outil ne mesure pas : bilans, mer Noire, météo, demande, actualité. Son avis fixe le signal de chaque culture pour 8 jours.",
    ],
    [
      'Entre deux comités',
      "Le score du comité est actualisé chaque matin par la variation de la technique, des fonds, de la macro et de la météo (10 % chacun, comme dans la grille du comité). Si cela suffit à changer de case dans la matrice, la culture est marquée « à revoir » et un comité d'alerte est demandé.",
    ],
    [
      'Matrice',
      "Score ≤ −1 : vendre une tranche ou couvrir · entre −1 et +0,5 : tenir le plan · ≥ +0,5 : attendre ou stocker. Le timing technique décide du moment : pas de vente en survente ou au bas du range de 3 mois, accélération en surachat qui s'essouffle.",
    ],
    [
      'Jauges en percentile',
      'Un percentile situe le chiffre du jour dans son histoire : 10e = plus bas que 90 % des valeurs passées, 90e = plus haut. Prix sur 5 ans (cours officiels Euronext de l’échéance la plus proche ; marché mondial en €/t tant que cet historique est trop court), ratio azote/blé et urée sur 10 ans, gaz sur 5 ans, positions des fonds sur 3 ans, prime locale sur un an. Vert = bon moment pour vendre (céréales) ou pour acheter (azote).',
    ],
    [
      'Stocker ou vendre',
      "Écart entre l'échéance Euronext de référence et chaque échéance plus lointaine de la même récolte, moins le coût du stockage (0,6 €/t/mois de frais et 4 %/an pour l'argent immobilisé, réglables). Gain net ≥ 3 €/t : stocker ; négatif : vendre plutôt que stocker.",
    ],
    [
      'Prime locale, saisonnalité, météo',
      "Prime locale : prix physique (Rouen, Moselle, Creil, Rhin) moins l'échéance Euronext du même jour, situé sur son historique après 40 relevés. Saisonnalité : écart habituel de chaque mois au prix moyen de la campagne, médiane de plus de 20 campagnes à Chicago. Météo : pluie des 60 derniers jours par rapport à la normale sur 10 ans et chaleur prévue à 14 jours, notée de −1 à +2 et comptée pour 15 % de la lecture de marché.",
    ],
    [
      'Bilans mondiaux et chances d’atteindre un ordre',
      "Bilans : rapport stocks de fin / consommation de l'USDA (rapport mensuel WASDE, fichiers PSD publics), hors Chine pour le blé et le maïs, situé sur les 20 campagnes précédentes. Chances : probabilité que le cours touche chaque ordre (ou le seuil de révision) au moins une fois d'ici la fin de la tranche, d'après la volatilité des 3 derniers mois et sans supposer de tendance ; une probabilité faible signale un ordre trop ambitieux pour la période.",
    ],
    [
      'Actualité, géopolitique et psychologie',
      "Chaque matin, une centaine de titres (Google Actualités en français et en anglais, presse agricole) sont lus par l'IA d'après leur seul titre : pertinent ou non, thème, fait ou rumeur, importance de 1 à 3, effet de −2 à +2 sur le prix de chaque culture et de l'azote, et ce que cela change pour vous. La pression de l'actualité additionne ces effets sur 7 jours (un fait pèse plus qu'une rumeur, moitié du poids après 3 jours, comptes rendus de séance exclus car déjà dans les cours). Un fait majeur (importance 3, effet fort, moins de 36 h) envoie une alerte et convoque le comité, qui vérifie le fait sur le web. Géopolitique : indice de risque de Caldara et Iacoviello (presse mondiale, quotidien et par pays). Psychologie : humeur de 0 (peur) à 100 (euphorie) à partir du RSI, de l'écart à la moyenne 200 séances, de l'élan sur 20 séances et des fonds. Ni l'indice géopolitique ni l'humeur n'ont annoncé les prix mieux que le hasard sur l'historique : ils éclairent le comité et le rythme des ventes, sans entrer dans la note de marché.",
    ],
    [
      'Carnet de bord',
      "Chaque avis du comité est noté avec le cours du jour, puis jugé 4 et 8 semaines plus tard : vendre est bon si le cours a baissé, attendre s'il a monté ; pour l'azote, acheter large est bon si l'urée a monté. Les pastilles de couleur sur les graphiques montrent où les avis ont été donnés.",
    ],
    [
      'Limites',
      "Les cours Euronext du jour viennent de terre-net (prix de compensation officiel) ; l'historique depuis novembre 2019 est repris des fichiers statistiques publics d'Euronext, et chaque séance commune sert de contrôle croisé avec terre-net. Tant que cet historique est trop court, la technique et les vues longues s'appuient sur le marché américain correspondant. Les escourgeons et orges de printemps n'ont pas de marché à terme : ils suivent le blé, avec l'avis du comité sur les primes brassicoles. Les résultats historiques du module engrais portent sur l'urée mondiale et le blé US en dollars. L'outil ne connaît ni vos coûts ni vos volumes : il raisonne en pourcentages.",
    ],
  ];
  const pli = (titre, ...kids) => h('details', { class: 'acc' }, h('summary', { text: titre }), ...kids);
  const d = GS.data;
  const hist = d.historique_declencheurs || [];
  return [
    h('p', { class: 'note', text: 'Comment l’outil décide, ce qu’il aurait rapporté, et d’où viennent les chiffres.' }),
    pli(
      'Comment l’outil décide',
      ...txt
        .filter(([t]) => t !== 'Carnet de bord')
        .flatMap(([t, p]) => [h('h4', { class: 'ititle', text: t }), h('p', { text: p })])
    ),
    pli('Calendrier des tranches de vente', calendarTable()),
    pli('Backtest : ce que les règles auraient rapporté', backtestSection()),
    pli(
      'Carnet de bord des avis du comité',
      h('p', { class: 'note', text: (txt.find(([t]) => t === 'Carnet de bord') || [])[1] || '' }),
      ...carnetSection(d).slice(1)
    ),
    hist.length || GS.journal.length
      ? pli(
          'Historique des alertes et des comités',
          hist.length ? h('h4', { class: 'ititle', text: 'Alertes' }) : null,
          hist.length
            ? h(
                'ul',
                { class: 'list' },
                hist.map((t) => h('li', { text: `${dfr(t.id.slice(0, 10))} — ${t.titre}` }))
              )
            : null,
          GS.journal.length ? h('h4', { class: 'ititle', text: 'Comités' }) : null,
          GS.journal.length
            ? h(
                'ul',
                { class: 'list' },
                GS.journal.map((j) =>
                  h('li', {}, h('b', { text: `${dfr(j.date)} (${j.mode})` }), ' — ' + (j.resume || ''))
                )
              )
            : null
        )
      : null,
    pli('Collecte du matin (sources)', ...sources().slice(1)),
  ];
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

/* ---------------------------------------------------------------------------------------------- vue simplifiée
   Aujourd'hui : une ligne par culture (que faire, combien, à quel prix) ; Cultures : une culture à la fois, le détail replié. */
const ED = {
  ACHETER_LARGE: ['🟢', 'ACHETER', 'good'],
  SUIVRE: ['🟡', 'SUIVRE LE PLAN', 'info'],
  FRACTIONNER: ['🟠', 'FRACTIONNER', 'warn'],
  ATTENDRE: ['🔴', 'ATTENDRE', 'bad'],
};
const NOM_COURT = {
  ble: 'Blé',
  escourgeon: 'Escourgeon',
  orge_printemps: 'Orge de printemps',
  colza: 'Colza',
  mais: 'Maïs',
};

function duePlan(c) {
  const plan = c.plan || [];
  return plan.find((p) => p.statut === 'due' && !p.avant_moisson) || plan.find((p) => p.statut === 'due') || plan[0];
}

// ce que la page dit de chaque culture, calculé une fois : action, quantité, prix, cours du jour, chances
function resumeCulture(k, d) {
  const c = d.cultures[k];
  const due = duePlan(c);
  const [ic, lab, cl] = DECISION[(due || {}).code] || ['❔', '—', 'neutral'];
  const con = (d.contrats || {})[c.contrat] || {};
  const nr = c.niveaux_retenus || {};
  const gap = nr.sur_ble ? ((d.orges || {})[k] || {}).ecart_ble : null;
  const phys = c.physique || {};
  const cours = phys.prix ? phys.prix : con.dernier_reel;
  const v1 = (con.technique || {}).var1s;
  const pb = nr.probas || {};
  const ch = due && due.code === 'ordre' && pb.ordres && pb.ordres[0] !== undefined ? pb.ordres[0] : null;
  // consigne exacte du comité d'abord : elle peut préciser le plan (« 7,5 % maintenant + 7,5 % par ordre »)
  const cc = c.source === 'comite' ? c.comite || {} : {};
  const sous = [
    cours
      ? `${phys.prix ? 'Prix physique' : 'Cours'} ${fmt(cours)} €/t` +
        (!c.proxy && v1 !== undefined ? ` (${pct(v1)} en 1 sem.)` : '')
      : null,
    ch !== null ? `${ch} % de chances d’atteindre l’ordre d’ici le ${dfr(pb.horizon)}` : null,
    due && due.ordre && nr.sur_ble ? `ordre déclenché par le blé Euronext à ${fmt(due.ordre)} €/t` : null,
  ].filter(Boolean);
  return {
    c,
    due,
    ic,
    lab,
    cl,
    quoi: court(due, nr.sur_ble, gap),
    com: cc.pct ? `Comité : ${cc.pct}` : '',
    sous: sous.join(' · '),
    con,
    nr,
    gap,
  };
}

function resumeAzote(d) {
  const e = d.engrais || {};
  const ec = e.comite || {};
  const [ic, lab, cl] = ED[ec.signal || e.signal] || ['❔', '—', 'neutral'];
  const ur = (e.france || {}).uree || {};
  const sous = [
    ur.prix ? `Urée ${fmt(ur.prix)} €/t` + (ur.var1m !== undefined ? ` (${pct(ur.var1m)} en 1 mois)` : '') : null,
    ec.prix_plafond ? `plafond d’achat ${fmt(ec.prix_plafond, 0)} €/t` : null,
  ].filter(Boolean);
  return { e, ec, ic, lab, cl, quoi: ec.pct ? ec.pct.split('(')[0].trim() : e.a_acheter || '', sous: sous.join(' · ') };
}

function decisionRow(href, nom, r) {
  return h(
    'a',
    { class: 'drow d-' + r.cl, href },
    h('span', { class: 'dname', text: nom }),
    h(
      'span',
      { class: 'dmain' },
      h('span', { class: 'badge ' + r.cl, text: `${r.ic} ${r.lab}` }),
      h('span', { class: 'dquoi', text: r.quoi })
    ),
    r.com ? h('span', { class: 'dcom', text: r.com }) : null,
    r.sous ? h('span', { class: 'dsous', text: r.sous }) : null,
    h('span', { class: 'dgo', 'aria-hidden': 'true', text: '›' })
  );
}

function alertes(d) {
  const out = [];
  const com = d.comite || {};
  const cj = GS.comite || {};
  if (cj.erreur && com.valide)
    out.push(`Le dernier comité n’a pas abouti : l’avis du ${dfr(com.date)} reste appliqué.`);
  else if (!com.valide) out.push('Pas d’avis du comité de moins de 8 jours : plan de vente par défaut.');
  for (const a of ((GS.actu || {}).articles || []).filter((x) => ((GS.actu || {}).majeurs || []).includes(x.id)))
    out.push(`📰 ${a.titre_fr || a.titre}`);
  for (const t of d.declencheurs || []) out.push(`${t.grave ? '⚠️ ' : ''}${t.titre}`);
  return out;
}

function vAujourdhui() {
  const d = GS.data;
  const com = d.comite || {};
  const out = [];
  const cal = ((com.calendrier || []).filter((x) => x.date >= d.date) || []).sort((a, b) => (a.date < b.date ? -1 : 1));
  out.push(
    h(
      'p',
      { class: 'meta' },
      `Séance du ${dfr((d.contrats.EBM || {}).seance || d.date)}`,
      cal.length ? ` · prochain rendez-vous : ${cal[0].evenement} (${dfr(cal[0].date)})` : ''
    )
  );
  const al = alertes(d);
  if (al.length)
    out.push(
      h(
        'div',
        { class: 'alert' },
        h(
          'ul',
          { class: 'alist' },
          al.slice(0, 5).map((t) => h('li', { text: t }))
        )
      )
    );
  out.push(h('h2', { text: 'Que faire aujourd’hui' }));
  const rows = Object.keys(d.cultures || {}).map((k) =>
    decisionRow(`#cultures/${k}`, `${ICON[k] || ''} ${NOM_COURT[k] || d.cultures[k].nom}`, resumeCulture(k, d))
  );
  rows.push(decisionRow('#cultures/azote', '🧪 Azote', resumeAzote(d)));
  out.push(h('nav', { class: 'drows', 'aria-label': 'Décisions par culture' }, rows));
  out.push(
    h('p', {
      class: 'note',
      text: '🎯 ORDRE : placer un ordre de vente à ce prix, pas au prix du jour · ⏸️ PATIENTER : attendre un rebond · ✅ VENDRE : la tranche peut partir · 🔴 ATTENDRE : décaler · 💤 RIEN : pas de tranche maintenant. Touchez une ligne pour le détail.',
    })
  );
  const cj = GS.comite || {};
  if (com.resume) {
    out.push(
      h(
        'section',
        { class: 'card wide' },
        h('h3', { text: `L’avis du comité (${dfr(com.date)})` }),
        h('p', { text: com.resume }),
        cj.rapport_html
          ? h(
              'details',
              {},
              h('summary', { text: 'Lire le rapport complet' }),
              h('article', { class: 'rapport' }, cleanHtml(cj.rapport_html)),
              cj.sources && cj.sources.length
                ? h(
                    'p',
                    { class: 'note' },
                    `Sources consultées : ${cj.sources.filter((x) => /^https?:\/\//i.test(x.url)).length} pages · ${cj.modele || ''}${
                      cj.cout_usd !== undefined ? ` · ≈ ${fmt(cj.cout_usd)} $` : ''
                    }`
                  )
                : null
            )
          : null
      )
    );
  }
  return out;
}

// une jauge résumée par sujet, 4 au plus : prix sur 5 ans, stocks mondiaux, actualité, humeur
function reperes(k, c, con, d) {
  const th = con.thermo;
  const st = (d.stocks_mondiaux || {})[BASE_USDA[k]];
  return [
    th
      ? pgauge(
          th.percentile,
          'vendeur',
          `🌡️ Prix sur 5 ans${c.proxy ? ' (blé)' : ''}`,
          th.euronext ? `Habituel ${fmt(th.p20, 0)}–${fmt(th.p80, 0)} €/t` : null,
          true
        )
      : null,
    st
      ? pgauge(
          st.percentile,
          'stocks',
          '🌍 Stocks mondiaux',
          `${fmt(st.ratio, 1)} % de la consommation${st.hors_chine ? ' hors Chine' : ''}`,
          true
        )
      : null,
    c.actualite ? pgauge(c.actualite.valeur, 'actu', '📰 Actualité (7 jours)', null, true) : null,
    con.psychologie ? pgauge(con.psychologie.indice, 'psy', '🧠 Humeur du marché', null, true) : null,
  ].filter(Boolean);
}

function cultureView(k, d) {
  const r = resumeCulture(k, d);
  const { c, con, nr } = r;
  const cc = c.comite || {};
  const ech = nr.echeance ? ` (${c.contrat} ${moisFr(nr.echeance)})` : '';
  const ordres = nr.ordres || [];
  const o = (d.orges || {})[k];
  const plan = (c.plan || []).map((p) => `Récolte ${p.recolte} : ${court(p, nr.sur_ble, r.gap)} (${p.periode})`);
  const graph =
    o && o.estime
      ? periodPanel({
          nom: o.nom,
          graphique: o.estime.graphique,
          long: orgeLong(o, d.contrats.EBM),
          technique: o.estime.technique,
          niveaux: o.estime.niveaux,
          mainColor: 'var(--muted)',
          longMain: 'var(--muted)',
          col4Dots: true,
          simple: true,
          legend3m: h(
            'div',
            { class: 'legend' },
            h(
              'span',
              {},
              h('i', { style: 'background:var(--muted)' }),
              `Orge estimée (blé ${sgn(o.estime.ecart)} €/t)`
            ),
            h('span', {}, h('i', { style: 'background:var(--chart-1)' }), 'Prix physique relevé')
          ),
        })
      : !c.proxy
        ? periodPanel({
            nom: con.nom,
            graphique: (con.proxy && con.proxy.graphique ? con.proxy : con).graphique,
            long: con.long,
            technique: con.proxy && con.proxy.technique ? con.proxy.technique : con.technique,
            niveaux: con.niveaux_retenus || con.niveaux,
            marks: marksFor(k),
            longMain: con.long && con.long.source === 'euronext' ? null : 'var(--muted)',
            simple: true,
          })
        : null;
  const ta = con.proxy && con.proxy.technique ? con.proxy.technique : con.technique;
  const met = ((d.meteo || {}).cultures || {})[BASE[k]];
  const sa = (d.saison || {})[BASE[k]];
  const b = c.biais;
  const ceu = ((d.cot || {})['EURONEXT_' + c.contrat] || {}).indice;
  const pl = !c.proxy ? con.prime_locale : null;
  return [
    h(
      'section',
      { class: 'card wide head d-' + r.cl },
      h('h2', { text: `${ICON[k] || ''} ${c.nom}` }),
      h(
        'div',
        { class: 'dmain' },
        h('span', { class: 'badge ' + r.cl, text: `${r.ic} ${r.lab}` }),
        h('span', { class: 'dquoi', text: r.quoi })
      ),
      r.com ? h('p', { class: 'dcom', text: r.com }) : null,
      r.sous ? h('p', { class: 'dsous', text: r.sous }) : null,
      cc.texte ? h('p', { text: cc.texte }) : c.note ? h('p', { class: 'note', text: c.note }) : null,
      c.a_revoir ? h('div', { class: 'alert', text: c.a_revoir }) : null
    ),
    graph ? h('section', { class: 'card wide' }, graph) : null,
    (() => {
      const g = reperes(k, c, con, d);
      return g.length ? h('div', { class: 'card wide' }, h('div', { class: 'pgrid tight' }, g)) : null;
    })(),
    h(
      'section',
      { class: 'card wide' },
      h(
        'dl',
        { class: 'kv' },
        ordres.length && (nr.sur_ble || !graph)
          ? [
              h('dt', { text: '🎯 Ordres' }),
              h('dd', {
                text: nr.sur_ble
                  ? `${nr.equivalent_orge && nr.equivalent_orge.ordres.length ? `≈ ${nr.equivalent_orge.ordres.map((v) => fmt(v)).join(' · ')} €/t d’orge, ` : ''}quand le blé Euronext atteint ${ordres.map((v) => fmt(v)).join(' · ')} €/t${ech}`
                  : `${ordres.map((v) => fmt(v)).join(' · ')} €/t${ech}`,
              }),
            ]
          : null,
        probaTxt(nr.probas) && (nr.sur_ble || !graph)
          ? [h('dt', { text: '🎲 Chances' }), h('dd', { text: probaTxt(nr.probas) })]
          : null,
        nr.revision && (nr.sur_ble || !graph)
          ? [h('dt', { text: '🛑 Révision' }), h('dd', { text: `sous ${fmt(nr.revision)} €/t${ech}` })]
          : null,
        plan.length
          ? [
              h('dt', { text: '📅 Plan' }),
              h(
                'dd',
                {},
                plan.map((t) => h('div', { text: t }))
              ),
            ]
          : null,
        c.feu ? [h('dt', { text: `${FEU[c.feu.code] || ''} Timing` }), h('dd', { text: c.feu.texte })] : null,
        con.stockage && con.stockage.texte
          ? [
              h('dt', { text: '📦 Stocker ?' }),
              h('dd', { text: (c.proxy ? 'Selon le blé : ' : '') + con.stockage.texte }),
            ]
          : null
      ),
      h(
        'details',
        {},
        h('summary', { text: 'Tous les détails' }),
        h(
          'dl',
          { class: 'kv' },
          cc.signal
            ? [
                h('dt', { text: 'Avis du comité' }),
                h('dd', {
                  text: `${c.libelle || ''}${cc.pct ? ` · ${cc.pct}` : ''}${c.score_actualise !== undefined ? ` · score ${sgn(cc.score)} au comité, ${sgn(c.score_actualise)} ce matin` : ''}`,
                }),
              ]
            : null,
          c.physique && c.physique.prix
            ? [
                h('dt', { text: 'Physique' }),
                h('dd', {
                  text: `${fmt(c.physique.prix)} €/t ${c.physique.place || ''}${c.physique.prime !== undefined && c.physique.prime !== null ? `, prime brassicole ${sgn(c.physique.prime)} €/t` : ''}, ${dfr(c.physique.date)}`,
                }),
              ]
            : null,
          met
            ? [
                h('dt', { text: '🌦️ Météo' }),
                h('dd', {
                  text: `Note ${sgn(met.score)} : ${
                    met.zones
                      .filter((z) => z.etat !== 'normal' && z.saison)
                      .map((z) => `${z.zone} ${z.etat}`)
                      .join(', ') || 'rien à signaler en saison'
                  }`,
                }),
              ]
            : null,
          sa
            ? [
                h('dt', { text: '📅 Mois chers' }),
                h('dd', {
                  text: `${sa.plus_chers.map((m) => MOIS[m - 1]).join(', ')} (moins chers : ${sa.moins_chers.map((m) => MOIS[m - 1]).join(', ')})`,
                }),
              ]
            : null,
          b
            ? [
                h('dt', { text: '🪞 Vos biais' }),
                h('dd', {
                  text:
                    (b.chance_plus_haut !== null && b.chance_plus_haut !== undefined
                      ? `Plus haut de la campagne ${fmt(b.plus_haut)} €/t le ${dfr(b.plus_haut_le)} : ${b.chance_plus_haut} % de chances de le revoir d’ici le ${dfr(b.horizon)}. `
                      : '') +
                    `Attendre encore 5 € : ${b.gagner5} % de chances de les voir, ${b.perdre5} % de risque de reculer de 5 €.`,
                }),
              ]
            : null
        ),
        h(
          'div',
          { class: 'pgrid' },
          ceu !== undefined && ceu !== null && !c.proxy
            ? pgauge(ceu, 'cot', '🏦 Fonds sur Euronext (3 ans)', null, true)
            : null,
          pl && pl.percentile !== undefined ? pgauge(pl.percentile, 'prime', '📍 Prime locale', null, true) : null
        ),
        ta && !ta.insuffisant ? indicatorCards(ta, con.series, nr, null) : null,
        ta && !ta.insuffisant ? techTable(ta) : null
      )
    ),
  ];
}

function azoteView(d) {
  const r = resumeAzote(d);
  const e = r.e;
  return [
    h(
      'section',
      { class: 'card wide head d-' + r.cl },
      h('h2', { text: '🧪 Azote' }),
      h(
        'div',
        { class: 'dmain' },
        h('span', { class: 'badge ' + r.cl, text: `${r.ic} ${r.lab}` }),
        h('span', { class: 'dquoi', text: r.quoi })
      ),
      r.sous ? h('p', { class: 'dsous', text: r.sous }) : null,
      r.ec.texte ? h('p', { text: r.ec.texte }) : null
    ),
    h(
      'div',
      { class: 'card wide' },
      h(
        'div',
        { class: 'pgrid tight' },
        pgauge(e.percentile_retenu, 'ratio', '⚖️ Azote face au blé (10 ans)', null, true),
        e.ttf
          ? pgauge(e.ttf.percentile_5ans, 'acheteur', `⛽ Gaz sur 5 ans (${fmt(e.ttf.dernier)} €/MWh)`, null, true)
          : null
      )
    ),
    h(
      'section',
      { class: 'card wide' },
      h(
        'dl',
        { class: 'kv' },
        e.forme_moins_chere
          ? [h('dt', { text: 'Forme la moins chère' }), h('dd', { text: e.forme_moins_chere })]
          : null,
        e.saison ? [h('dt', { text: 'Saison' }), h('dd', { text: e.saison })] : null,
        r.ec.signal && r.ec.signal !== e.signal
          ? [h('dt', { text: 'Règles chiffrées' }), h('dd', { text: e.libelle || '—' })]
          : null
      ),
      h(
        'details',
        {},
        h('summary', { text: 'Tous les détails' }),
        e.notes && e.notes.length
          ? h(
              'ul',
              { class: 'list note' },
              e.notes.map((n) => h('li', { text: n }))
            )
          : null,
        ...vEngrais(true)
      )
    ),
  ];
}

// contexte commun (marchés mondiaux, fonds, bilans, météo, saisons) : replié en bas de l'onglet Cultures
function autresMarches(d) {
  const kids = [...stocksSection(d), ...saisonSection(d), ...meteoSection(d)];
  const inter = Object.entries(d.international || {});
  const cot = Object.values(d.cot || {}).filter((c) => c.indice !== null && c.indice !== undefined);
  return h(
    'details',
    { class: 'more-data' },
    h('summary', { text: 'Marchés mondiaux, fonds, bilans, météo' }),
    inter.length
      ? h(
          'div',
          { class: 'card scroll' },
          h(
            'table',
            {},
            h(
              'tr',
              {},
              ['Marché', 'Dernier', '1 mois', 'RSI'].map((t, i) => h('th', { class: i ? 'n' : '', text: t }))
            ),
            inter.map(([, x]) => {
              const a = x.technique || {};
              return h(
                'tr',
                {},
                h('td', { text: x.nom }),
                h('td', { class: 'n', text: fmt(a.dernier, a.dernier < 10 ? 4 : 2) }),
                h('td', { class: 'n ' + cls(a.var1m), text: pct(a.var1m) }),
                h('td', { class: 'n', text: fmt(a.rsi, 0) })
              );
            })
          )
        )
      : null,
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
              ['Fonds', 'Positionnement sur 3 ans'].map((t) => h('th', { text: t }))
            ),
            cot.map((c) =>
              h(
                'tr',
                {},
                h('td', { text: c.nom }),
                h('td', { class: 'pgcell' }, pgauge(c.indice, 'cot', null, null, true))
              )
            )
          )
        )
      : null,
    kids
  );
}

function vCultures() {
  const d = GS.data;
  const keys = Object.keys(d.cultures || {}).concat(['azote']);
  const k = keys.includes(GS.cult) ? GS.cult : keys[0];
  const nav = h(
    'nav',
    { class: 'filters cnav', 'aria-label': 'Choisir une culture' },
    keys.map((x) =>
      h('a', {
        class: 'filt',
        href: `#cultures/${x}`,
        'aria-current': x === k ? 'page' : null,
        text: x === 'azote' ? '🧪 Azote' : `${ICON[x] || ''} ${NOM_COURT[x] || x}`,
      })
    )
  );
  return [nav, ...(k === 'azote' ? azoteView(d) : cultureView(k, d)), autresMarches(d)];
}

/* ---------------------------------------------------------------------------------------------- onglet Actualité */
const THEME = {
  geopolitique: ['🌐', 'Géopolitique'],
  meteo: ['🌦️', 'Météo'],
  offre: ['📦', 'Offre'],
  demande: ['🛒', 'Demande'],
  politique: ['🏛️', 'Politique'],
  macro: ['💱', 'Macro'],
  engrais: ['🧪', 'Engrais'],
  logistique: ['🚢', 'Logistique'],
  psychologie: ['🧠', 'Psychologie'],
  marche: ['📈', 'Séance'],
};
const NATURE = { fait: 'Fait', prevision: 'Prévision', rumeur: 'Rumeur', opinion: 'Avis' };
const ACTU_NOM = { ble: '🌾 Blé', orge: '🍺 Orges', colza: '🌼 Colza', mais: '🌽 Maïs', engrais: '🧪 Azote' };
const FILTRES = [
  ['tout', 'Tout'],
  ['ble', '🌾 Blé'],
  ['orge', '🍺 Orges'],
  ['colza', '🌼 Colza'],
  ['mais', '🌽 Maïs'],
  ['engrais', '🧪 Azote'],
  ['geopolitique', '🌐 Géopolitique'],
];

function ilya(iso) {
  const t = Date.parse(iso);
  if (!t) return '';
  const hrs = (Date.now() - t) / 3600000;
  if (hrs < 1) return 'il y a moins d’une heure';
  if (hrs < 24) return `il y a ${Math.round(hrs)} h`;
  const j = Math.round(hrs / 24);
  return `il y a ${j} jour${j > 1 ? 's' : ''}`;
}

// effet sur chaque prix : vert = favorable à l'exploitation (grain plus cher à la vente, azote moins cher à l'achat)
function impactChips(imp) {
  return Object.entries(imp || {})
    .filter(([, v]) => v)
    .map(([c, v]) => {
      const fav = c === 'engrais' ? v < 0 : v > 0;
      const fl = v > 0 ? '↑'.repeat(Math.abs(v)) : '↓'.repeat(Math.abs(v));
      return h('span', {
        class: 'chip ' + (fav ? 'good' : 'bad'),
        title:
          c === 'engrais'
            ? v > 0
              ? 'azote plus cher'
              : 'azote moins cher'
            : v > 0
              ? 'prix en hausse'
              : 'prix en baisse',
        text: `${ACTU_NOM[c] || c} ${fl}`,
      });
    });
}

function articleRow(a) {
  const th = THEME[a.theme] || ['📰', 'Actualité'];
  const imp = Math.max(1, Math.min(3, a.importance || 1));
  const majeur = ((GS.actu || {}).majeurs || []).includes(a.id);
  return h(
    'article',
    { class: 'news' + (majeur ? ' major' : '') + (a.non_classe ? ' raw' : '') },
    h(
      'div',
      { class: 'news-h' },
      h('span', { class: 'news-th', text: `${th[0]} ${th[1]}` }),
      a.non_classe
        ? null
        : h('span', {
            class: 'news-imp',
            title: `Importance ${imp} sur 3`,
            text: '●'.repeat(imp) + '○'.repeat(3 - imp),
          }),
      a.nature ? h('span', { class: 'chip', text: NATURE[a.nature] || a.nature }) : null,
      majeur ? h('span', { class: 'chip bad', text: '⚠️ Majeur' }) : null,
      h('span', {
        class: 'news-src',
        text: `${a.source || ''}${a.autres_sources && a.autres_sources.length ? ` + ${a.autres_sources.length} autre${a.autres_sources.length > 1 ? 's' : ''}` : ''} · ${ilya(a.date)}`,
      })
    ),
    h(
      'a',
      {
        class: 'news-t',
        href: /^https?:\/\//.test(a.url || '') ? a.url : null,
        target: '_blank',
        rel: 'noopener noreferrer',
        title: a.titre_fr && a.titre_fr !== a.titre ? `Titre d’origine : ${a.titre}` : null,
      },
      a.titre_fr || a.titre
    ),
    a.impact ? h('p', { class: 'news-i', text: a.impact }) : null,
    a.impacts ? h('div', { class: 'news-c' }, impactChips(a.impacts)) : null
  );
}

function newsList(ac) {
  const f = GS.actuFiltre || 'tout';
  const all = (ac.articles || []).filter((a) => !a.doublon_de);
  const keep = all.filter((a) =>
    f === 'tout'
      ? true
      : f === 'geopolitique'
        ? a.theme === 'geopolitique' || a.theme === 'politique'
        : a.impacts && a.impacts[f]
  );
  // le plus important d'abord, puis le plus récent ; comptes rendus de séance en dernier
  keep.sort(
    (a, b) =>
      (b.theme !== 'marche') - (a.theme !== 'marche') ||
      (b.importance || 0) - (a.importance || 0) ||
      String(b.date).localeCompare(String(a.date))
  );
  const n = GS.actuTout ? keep.length : 6;
  const bar = h(
    'div',
    { class: 'filters', role: 'group', 'aria-label': 'Filtrer les actualités' },
    FILTRES.map(([k, t]) => {
      const b = h('button', { class: 'filt', 'aria-pressed': String(k === f), text: t });
      b.addEventListener('click', () => {
        GS.actuFiltre = k;
        GS.actuTout = false;
        render();
      });
      return b;
    })
  );
  const more =
    keep.length > n
      ? (() => {
          const b = h('button', { class: 'more', text: `Afficher les ${keep.length} titres` });
          b.addEventListener('click', () => {
            GS.actuTout = true;
            render();
          });
          return b;
        })()
      : null;
  return h(
    'div',
    { class: 'card wide' },
    bar,
    keep.length ? keep.slice(0, n).map(articleRow) : h('p', { class: 'muted', text: 'Aucun titre pour ce filtre.' }),
    more
  );
}

// ce que l'indice a annoncé sur le blé (Chicago) : comparé à des cours tirés au sort de même nervosité
function geoBt(bt) {
  const r = [
    ['20', 'un mois'],
    ['60', 'trois mois'],
  ]
    .filter(([k]) => bt[k])
    .map(([k, t]) => {
      const o = bt[k];
      const ec = o.tendu - o.moyenne;
      const sig = o.bruit_tendu !== undefined && o.bruit_tendu !== null && Math.abs(ec) > o.bruit_tendu;
      return `à ${t}, après les 10 % de jours les plus tendus, ${pct(o.tendu)} contre ${pct(o.moyenne)} d’habitude (${
        sig ? 'écart plus grand que le hasard' : `écart à la portée du hasard, ±${fmt(o.bruit_tendu, 1)} pt`
      })`;
    });
  return r.length ? ` : depuis ${String(bt.depuis || '').slice(0, 4)}, sur le blé de Chicago, ${r.join(' ; ')}.` : '.';
}

function geoSection(d) {
  const g = d.geopolitique;
  if (!g) return [];
  const bt = (GS.backtest || {}).geopolitique || {};
  return [
    h('h2', { text: '🌐 Risque géopolitique' }),
    h(
      'div',
      { class: 'card wide' },
      h(
        'div',
        { class: 'pgrid' },
        pgauge(
          g.percentile,
          'geo',
          '🌍 Monde (moyenne 30 jours, sur 10 ans)',
          `Indice ${g.mois} (100 = moyenne 1985-2019) · il y a 30 jours ${g.il_y_a_30j ?? '—'} · cette semaine ${g.semaine} · au ${dfr(g.au)}`
        )
      ),
      g.pays && g.pays.length
        ? h(
            'table',
            { class: 'geo' },
            h(
              'tr',
              {},
              ['Pays', 'Mois', 'Sur 10 ans'].map((t) => h('th', { text: t }))
            ),
            g.pays.map((p) =>
              h(
                'tr',
                {},
                h('td', { text: p.nom }),
                h('td', { text: moisFr(p.mois) }),
                h('td', { class: 'pgcell' }, pgauge(p.percentile, 'geo', null, null, true))
              )
            )
          )
        : null,
      g.evenements && g.evenements.length
        ? h(
            'p',
            { class: 'note' },
            'Pics récents notés par les auteurs : ',
            g.evenements.map((e) => `${dfr(e.date)} ${e.texte}`).join(' · ')
          )
        : null,
      h('p', {
        class: 'note',
        text:
          'Indice de risque géopolitique de Caldara et Iacoviello (Réserve fédérale) : part des articles de grands journaux qui parlent de guerre, de menace militaire ou de terrorisme, chaque jour et par pays. Il mesure la tension, pas son effet sur les grains' +
          geoBt(bt) +
          ' Chaque événement se juge donc au cas par cas : c’est le rôle des actualités traduites ci-dessus et de l’expert géopolitique du comité.',
      })
    ),
  ];
}

function psySection(d) {
  const noms = { EBM: '🌾 Blé (et orges)', ECO: '🌼 Colza', EMA: '🌽 Maïs' };
  const rows = Object.entries(d.contrats || {}).filter(([, c]) => c.psychologie);
  if (!rows.length) return [];
  const CMP = [
    ['rsi', 'RSI'],
    ['ecart200', 'Écart MM200'],
    ['elan20', 'Élan 20 j'],
    ['fonds', 'Fonds'],
  ];
  const bt = (GS.backtest || {}).psychologie || {};
  const evid = Object.entries(bt).filter(([, v]) => v && v['60']);
  return [
    h('h2', { text: '🧠 Psychologie des marchés' }),
    h(
      'div',
      { class: 'grid' },
      rows.map(([k, c]) => {
        const ps = c.psychologie;
        return h(
          'section',
          { class: 'card' },
          h('h3', { text: noms[k] || c.nom }),
          pgauge(ps.indice, 'psy', null, ps.lecture),
          h(
            'div',
            { class: 'minis' },
            CMP.filter(([ck]) => ps.composantes[ck] !== null && ps.composantes[ck] !== undefined).map(([ck, t]) =>
              h('span', {
                class: 'mini ' + (ps.composantes[ck] <= 20 ? 'bad' : ps.composantes[ck] >= 80 ? 'good' : ''),
                title:
                  ck === 'fonds'
                    ? `Position nette des ${ps.fonds_source || 'fonds'} sur 3 ans`
                    : ck === 'rsi'
                      ? `RSI ${fmt(ps.valeurs.rsi, 0)}, situé sur 3 ans`
                      : ck === 'ecart200'
                        ? `${pct(ps.valeurs.ecart200)} par rapport à la moyenne 200 séances, situé sur 3 ans`
                        : `${pct(ps.valeurs.elan20)} en 20 séances, situé sur 3 ans`,
                text: `${t} ${ps.composantes[ck]}`,
              })
            )
          )
        );
      })
    ),
    evid.length
      ? h(
          'div',
          { class: 'card wide scroll' },
          h('h3', { text: 'L’humeur annonce-t-elle la suite ? (60 séances après)' }),
          h(
            'table',
            {},
            h(
              'tr',
              {},
              ['Marché', 'Verdict', 'Corrélation', 'Hasard seul', 'Après peur extrême', 'Après euphorie', 'Depuis'].map(
                (t, i) => h('th', { class: i > 1 && i < 6 ? 'n' : '', text: t })
              )
            ),
            evid.map(([nom, v]) => {
              const o = v['60'];
              const br = (v.bruit || {})['60'];
              const tr = o.tranches || {};
              const sig = br !== undefined && o.correlation !== null && Math.abs(o.correlation) > br;
              return h(
                'tr',
                {},
                h('td', { text: nom }),
                h('td', {
                  class: sig ? '' : 'muted',
                  text: !sig
                    ? 'pas distinct du hasard'
                    : o.correlation < 0
                      ? 'à contre-courant'
                      : 'dans le sens de la tendance',
                }),
                h('td', { class: 'n', text: sgn(o.correlation, 2) }),
                h('td', { class: 'n', text: br !== undefined ? `±${fmt(br, 2)}` : '—' }),
                h('td', { class: 'n', text: tr.peur_extreme ? pct(tr.peur_extreme.moyenne) : '—' }),
                h('td', { class: 'n', text: tr.euphorie ? pct(tr.euphorie.moyenne) : '—' }),
                h('td', { text: String(v.depuis || '').slice(0, 4) })
              );
            })
          ),
          h('p', {
            class: 'note',
            text: 'Humeur de 0 (peur extrême) à 100 (euphorie) : moyenne des percentiles sur 3 ans du RSI, de l’écart à la moyenne 200 séances, de l’élan sur 20 séances et de la position des fonds. « Hasard seul » : corrélation atteinte par pur hasard (90 % des cas) sur des cours tirés au sort de même longueur et de même nervosité, car les périodes de 60 séances se chevauchent. Une humeur qui ne bat pas le hasard n’entre pas dans la note de marché : elle sert à ne pas vendre dans la panique et à ne pas laisser passer une tranche dans l’euphorie.',
          })
        )
      : null,
  ];
}

function vActualite() {
  const d = GS.data;
  const ac = GS.actu || {};
  const ad = d.actualites || {};
  const out = [];
  const pr = ad.pression || ac.pression;
  if (!ac.date)
    return [h('div', { class: 'alert info', text: 'Première revue de presse au prochain calcul du matin.' })];
  if (ac.sans_ia)
    out.push(h('div', { class: 'alert info', text: 'Titres non traduits : le secret ANTHROPIC_API_KEY manque.' }));
  if (ac.erreur) out.push(h('div', { class: 'alert', text: ac.erreur }));
  out.push(
    h(
      'section',
      { class: 'card wide' },
      h('h3', {
        text: `Ce que l’actualité change pour vous${ac.synthese_du && ac.synthese_du !== ac.date ? ` (${dfr(ac.synthese_du)})` : ''}`,
      }),
      ac.synthese ? h('p', { text: ac.synthese }) : null,
      pr
        ? h(
            'div',
            { class: 'pgrid tight' },
            ['ble', 'orge', 'colza', 'mais', 'engrais']
              .filter((c) => pr[c])
              .map((c) => pgauge(pr[c].valeur, c === 'engrais' ? 'actuEngrais' : 'actu', ACTU_NOM[c], null, true))
          )
        : null,
      h('p', {
        class: 'note',
        text: `Effet des nouvelles des 7 derniers jours sur chaque prix (azote : + = plus cher). ${(ac.compte || {}).pertinents || 0} titres retenus sur ${(ac.compte || {}).lus || 0}. Les titres parlent plus des risques de hausse que d’une offre abondante : à lire avec les cours.`,
      })
    )
  );
  out.push(newsList(ac));
  const geo = geoSection(d).slice(1); // sans le titre : la section est repliée
  const psy = psySection(d);
  const ev = psy.length ? psy[psy.length - 1] : null; // tableau « l'humeur annonce-t-elle la suite ? »
  if (geo.length || ev)
    out.push(
      h(
        'details',
        { class: 'more-data' },
        h('summary', { text: 'Géopolitique et psychologie des marchés' }),
        ...geo,
        ev
      )
    );
  return out;
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
    { aujourdhui: vAujourdhui, cultures: vCultures, actualite: vActualite, methode: vMethode }[GS.tab] || vAujourdhui;
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

// #aujourdhui, #cultures/ble, #actualite, #methode ; anciens liens (#signaux, #technique, #engrais, #comite) redirigés
const ANCIENS = { signaux: 'aujourdhui', comite: 'aujourdhui', technique: 'cultures', engrais: 'cultures/azote' };
function route() {
  let [t, x] = (location.hash || '').slice(1).split('/');
  if (ANCIENS[t]) [t, x] = ANCIENS[t].split('/');
  GS.tab = ['aujourdhui', 'cultures', 'actualite', 'methode'].includes(t) ? t : 'aujourdhui';
  if (GS.tab === 'cultures' && x) GS.cult = x;
}

async function init() {
  // page installable sur le téléphone : même service worker qu'Euro Signal (réseau d'abord, copie locale hors connexion)
  if ('serviceWorker' in navigator && location.protocol === 'https:')
    navigator.serviceWorker.register('sw.js').catch(() => {});
  route();
  document.querySelectorAll('.tabs button').forEach((b) =>
    b.addEventListener('click', () => {
      location.hash = b.dataset.tab === 'cultures' && GS.cult ? `cultures/${GS.cult}` : b.dataset.tab;
    })
  );
  window.addEventListener('hashchange', () => {
    const avant = GS.tab;
    route();
    render();
    if (avant !== GS.tab || GS.tab === 'cultures') window.scrollTo({ top: 0 });
  });
  const [d, c, j, bt, ac] = await Promise.all([
    getJSON('data/grain/grain-signal.json'),
    getJSON('data/grain/comite.json'),
    getJSON('data/grain/comites-journal.json'),
    getJSON('data/grain/backtest.json'),
    getJSON('data/grain/actualites.json'),
  ]);
  GS.backtest = bt;
  GS.actu = ac;
  GS.data = d;
  GS.comite = c || {};
  GS.journal = Array.isArray(j) ? j : [];
  const sub = document.getElementById('sub');
  if (d) {
    const s = Object.values((d.collecte || {}).sources || {});
    const ok = s.filter((x) => x.ok).length;
    // une source en panne se signale ; sinon, seulement la date (le détail est dans Méthode)
    sub.textContent =
      `Mis à jour le ${dfr(d.date)}` +
      (ok < s.length ? ` · ${s.length - ok} source${s.length - ok > 1 ? 's' : ''} en panne` : '');
  } else sub.textContent = 'Données indisponibles';
  render();
}

init();
