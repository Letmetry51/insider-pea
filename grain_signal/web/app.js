/* Grain Signal — page (lecture seule de data/grain/*.json, publiés chaque matin). Tout texte venu des données est inséré
   comme texte ; seul le rapport de la lecture hebdomadaire est du HTML, déjà nettoyé au calcul et nettoyé une seconde fois ici. */
'use strict';

const GS = { data: null, comite: null, journal: [], tab: 'marche' };
const ICON = { ble: '🌾', escourgeon: '🍺', orge_printemps: '🍺', colza: '🌼', mais: '🌽' };
const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const moisFr = (m) => (m && m.length >= 7 ? `${MOIS[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}` : m || '');

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

/* Graphique des cours : MM20, MM50, canal de tendance (3 mois), niveaux nommés (résistances, supports), fourchette
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
  // pastilles datées (facultatives) : couleur et détail au survol
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
   Couleurs de position, sans jugement : bas = bleu, moyenne = gris, haut = ambre. */
const SEGP = [
  [20, 'var(--info)'],
  [40, 'var(--info)'],
  [60, 'var(--neutral)'],
  [80, 'var(--warn)'],
  [100, 'var(--warn)'],
];
const T5 = [
  [20, '20'],
  [50, '50'],
  [80, '80'],
];
const lab5 = (v, t) => (v <= 20 ? t[0] : v <= 40 ? t[1] : v < 60 ? t[2] : v < 80 ? t[3] : t[4]);
const pos5 = (noms) => (v) =>
  lab5(
    v,
    noms.map((n, i) => [n, ['info', 'info', 'neutral', 'warn', 'warn'][i]])
  );
const PG = {
  prix: {
    segs: SEGP,
    ticks: T5,
    lab: pos5(['Bas sur 5 ans', 'Plutôt bas', 'Dans la moyenne', 'Plutôt haut', 'Haut sur 5 ans']),
  },
  prime: {
    segs: SEGP,
    ticks: T5,
    lab: pos5(['Prime faible', 'Prime plutôt faible', 'Prime normale', 'Prime plutôt forte', 'Prime forte']),
  },
  ratio: {
    segs: SEGP,
    ticks: T5,
    lab: pos5([
      'Azote bon marché / blé',
      'Azote plutôt bon marché',
      'Dans la moyenne',
      'Azote cher / blé',
      'Azote très cher / blé',
    ]),
  },
  stocks: {
    segs: SEGP,
    ticks: T5,
    lab: pos5([
      'Stocks très serrés',
      'Stocks plutôt serrés',
      'Stocks dans la moyenne',
      'Stocks plutôt confortables',
      'Stocks très confortables',
    ]),
  },
  cot: {
    segs: [
      [15, 'var(--info)'],
      [85, 'var(--neutral)'],
      [100, 'var(--warn)'],
    ],
    ticks: [
      [15, '15'],
      [85, '85'],
    ],
    lab: (v) =>
      v <= 15
        ? ['Fonds très vendeurs', 'info']
        : v >= 85
          ? ['Fonds très acheteurs', 'warn']
          : ['Position habituelle', 'neutral'],
  },
};
// humeur du marché (0 peur → 100 euphorie), pression de l'actualité (−2 → +2), risque géopolitique (percentile sur 10 ans)
const SEG_ACTU = [
  [25, 'var(--bad)'],
  [37.5, 'var(--bad)'],
  [62.5, 'var(--neutral)'],
  [75, 'var(--good)'],
  [100, 'var(--good)'],
];
// mêmes seuils que le calcul (±0,5 = 37,5 et 62,5 ; ±1 = 25 et 75)
const actuLab = (v, t) => (v <= 25 ? t[0] : v <= 37.5 ? t[1] : v < 62.5 ? t[2] : v < 75 ? t[3] : t[4]);
const T_ACTU = [
  [0, '−2'],
  [50, '0'],
  [100, '+2'],
];
Object.assign(PG, {
  psy: {
    segs: SEGP,
    ticks: T5,
    badge: (v) => String(Math.round(v)),
    lab: pos5(['Peur extrême', 'Peur', 'Humeur neutre', 'Optimisme', 'Euphorie']),
  },
  actu: {
    segs: SEG_ACTU,
    ticks: T_ACTU,
    map: (v) => Math.max(0, Math.min(100, ((v + 2) / 4) * 100)),
    badge: (v) => sgn(v, 1),
    lab: (v) =>
      actuLab(v, [
        ['Très baissière', 'bad'],
        ['Plutôt baissière', 'bad'],
        ['Équilibrée', 'neutral'],
        ['Plutôt haussière', 'good'],
        ['Très haussière', 'good'],
      ]),
  },
  actuEngrais: {
    segs: SEG_ACTU.map(([b], i) => [
      b,
      ['var(--info)', 'var(--info)', 'var(--neutral)', 'var(--warn)', 'var(--warn)'][i],
    ]),
    ticks: T_ACTU,
    map: (v) => Math.max(0, Math.min(100, ((v + 2) / 4) * 100)),
    badge: (v) => sgn(v, 1),
    lab: (v) =>
      actuLab(v, [
        ['Nettement moins cher', 'info'],
        ['Plutôt moins cher', 'info'],
        ['Équilibrée', 'neutral'],
        ['Plutôt plus cher', 'warn'],
        ['Nettement plus cher', 'warn'],
      ]),
  },
  geo: {
    segs: [
      [30, 'var(--neutral)'],
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
        ? ['Monde calme', 'neutral']
        : v < 70
          ? ['Tensions habituelles', 'neutral']
          : v < 90
            ? ['Tensions élevées', 'warn']
            : ['Tensions très élevées', 'bad'],
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

/* Graphique à périodes (3 mois, 1 an, 5 ans).
   p = { nom, graphique, long: { an, cinq_ans }, technique, niveaux, legendLong: [[couleur, libellé]], noteLong, legend3m, mainColor,
         col4Dots } */
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
  draw('3m');
  return h('div', {}, periods.length > 1 ? sw : null, box);
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

// résistances (au-dessus du cours) et supports (en dessous) de la lecture technique
function chartLevels(lec, a, u = '€/t') {
  const lv = [];
  ((lec && lec.resistances) || []).forEach((v) => lv.push({ v, c: 'var(--warn)', t: 'Résistance', u }));
  ((lec && lec.supports) || []).forEach((v) => lv.push({ v, c: 'var(--info)', t: 'Support', u }));
  if (!lv.length && a && a.bas3m) lv.push({ v: a.bas3m, c: 'var(--info)', t: 'Plus bas 3 mois', u });
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

function vEngrais() {
  const e = GS.data.engrais || {};
  const out = [];
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
          text: "Le gaz fait le prix de l'azote avec environ 1 mois de décalage.",
        }),
        periodPanel({
          nom: 'Gaz TTF',
          unite: '€/MWh',
          graphique: tv.graphique,
          long: tv.long,
          technique: tv.technique,
          series: tv.series,
          niveaux: null,
        }),
        tv.technique && !tv.technique.insuffisant ? techTable(tv.technique) : null
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
      { v: hr.seuils['20'], c: 'var(--info)', t: '20e percentile' },
      { v: hr.seuils['60'], c: 'var(--neutral)', t: '60e percentile' },
      { v: hr.seuils['80'], c: 'var(--warn)', t: '80e percentile' },
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

// la lecture technique annonce-t-elle la suite ? rendement moyen des 60 séances suivantes selon la lecture du jour
function techBt() {
  const bt = (GS.backtest || {}).technique || {};
  const rows = Object.entries(bt).filter(([, v]) => v && v['60']);
  if (!rows.length) return null;
  return h(
    'div',
    { class: 'card wide scroll' },
    h('h3', { text: 'La lecture technique annonce-t-elle la suite ? (60 séances après)' }),
    h(
      'table',
      {},
      h(
        'tr',
        {},
        [
          'Marché',
          'Verdict',
          'Après « hausse »',
          'Après « neutre »',
          'Après « baisse »',
          'Écart',
          'Hasard seul',
          'Depuis',
        ].map((t, i) => h('th', { class: i > 1 && i < 7 ? 'n' : '', text: t }))
      ),
      rows.map(([nom, v]) => {
        const o = v['60'];
        const g = o.groupes || {};
        const sig = o.ecart !== null && o.bruit !== null && Math.abs(o.ecart) > o.bruit;
        return h(
          'tr',
          {},
          h('td', { text: nom }),
          h('td', {
            class: sig ? '' : 'muted',
            text: !sig ? 'pas distinct du hasard' : o.ecart > 0 ? 'dans le sens de la lecture' : 'à contre-sens',
          }),
          ['haussière', 'neutre', 'baissière'].map((k) =>
            h('td', { class: 'n', text: g[k] ? `${pct(g[k].moyenne)} (${g[k].hausses} % ▲)` : '—' })
          ),
          h('td', { class: 'n', text: o.ecart !== null ? `${sgn(o.ecart, 1)} pt` : '—' }),
          h('td', { class: 'n', text: o.bruit !== null ? `±${fmt(o.bruit, 1)} pt` : '—' }),
          h('td', { text: String(v.depuis || '').slice(0, 4) })
        );
      })
    ),
    h('p', {
      class: 'note',
      text: 'Variation moyenne du cours dans les 60 séances qui suivent chaque jour, selon la lecture technique de ce jour-là (entre parenthèses : part des cas en hausse). « Écart » : après « hausse » moins après « baisse ». « Hasard seul » : écart atteint par pur hasard (90 % des cas) sur des cours tirés au sort de même longueur et de même nervosité. Une lecture qui ne bat pas le hasard décrit le marché ; elle ne le prédit pas.',
    })
  );
}

function vMethode() {
  const txt = [
    [
      'Chaque matin',
      "Grain Signal relève les cours Euronext (blé, colza, maïs) et leurs courbes, les prix physiques (Rouen, Creil, orges brassicoles), les marchés américains, le gaz TTF, le Brent, l'euro-dollar, les positions des fonds (Euronext et CFTC), les prix des engrais en France, le Pink Sheet de la Banque mondiale, la météo de 10 zones de production et une centaine de titres d'actualité. Il en tire une lecture par culture et envoie le rapport du matin vers 7 h 30, avec la synthèse PDF.",
    ],
    [
      'Lecture technique',
      'Note de −2 à +2 : position du cours par rapport à sa moyenne 50 séances et pente de celle-ci (sinon la moyenne 20 séances), élan du MACD 12/26/9 et son évolution sur 5 séances, excès du RSI 14 (survente sous 30, surachat au-dessus de 70), divergences RSI/prix. « Hausse » à partir de +0,75, « baisse » à partir de −0,75, « neutre » entre les deux. Résistances et supports : moyennes 20 et 50 séances, retracements de Fibonacci du dernier mouvement et extrêmes des 3 derniers mois, les deux plus proches de chaque côté. Escourgeon et orge de printemps n’ont pas de marché à terme : lecture du blé Euronext, niveaux ramenés au prix physique du jour.',
    ],
    [
      'Actualité',
      "Chaque titre est lu par l'IA d'après son seul titre : pertinent ou non, thème, fait ou rumeur, importance de 1 à 3, effet de −2 à +2 sur le prix de chaque culture et de l'azote, en une phrase sans conseil. La pression de l'actualité est la moyenne de ces effets sur 7 jours (un fait pèse plus qu'une rumeur, moitié du poids après 3 jours, comptes rendus de séance exclus car déjà dans les cours), ramenée vers 0 quand les nouvelles sont rares : elle donne le sens et la force de l'actualité, sans grimper avec le nombre de titres. Un fait majeur (importance 3, effet fort, moins de 72 h) part en alerte email.",
    ],
    [
      'Repères',
      "Prix sur 5 ans : percentile du cours du jour (10e = plus bas que 90 % des semaines passées). Plus haut de la campagne et écart depuis. Report : ce que paie la courbe Euronext entre l'échéance du jour et les plus lointaines de la même récolte, moins le stockage (0,6 €/t/mois et 4 %/an d'argent immobilisé, réglables). Prime locale : physique moins Euronext, sur un an. Saisonnalité : écart habituel de chaque mois au prix moyen de la campagne (plus de 20 campagnes). Bilans : stocks de fin / consommation de l'USDA, sur 20 campagnes. Azote : ratio urée/blé en percentile sur 10 ans, gaz, saison.",
    ],
    [
      'Lecture de la semaine',
      "Chaque lundi, l'API Claude, avec la recherche web, lit les chiffres du matin et cherche ce que l'outil ne mesure pas (bilans, mer Noire, météo, demande). Elle rend, par culture, les arguments haussiers et baissiers et la donnée à surveiller, avec un calendrier : jamais de consigne de vente ou d'achat.",
    ],
    [
      'Vos seuils',
      'Dans grain_signal/config.json (rubrique « seuils »), des prix au-dessus ou en dessous desquels être prévenu, par culture et pour l’urée. Le franchissement part en alerte et s’affiche sur la page.',
    ],
    [
      'Limites',
      "Les cours Euronext du jour viennent de terre-net (prix de compensation officiel) ; l'historique depuis novembre 2019 vient des fichiers statistiques publics d'Euronext. Tant que cet historique est trop court, la technique et les vues longues s'appuient sur le marché américain correspondant. L'outil ne connaît ni vos coûts, ni vos volumes, ni vos contrats : il décrit le marché, la décision vous appartient.",
    ],
  ];
  const pli = (titre, ...kids) => h('details', { class: 'acc' }, h('summary', { text: titre }), ...kids);
  const d = GS.data;
  const hist = d.historique_declencheurs || [];
  return [
    h('p', {
      class: 'note',
      text: 'Comment chaque lecture est calculée, ce qu’elle vaut sur l’historique, et d’où viennent les chiffres.',
    }),
    pli(
      'Comment l’outil lit le marché',
      ...txt.flatMap(([t, p]) => [h('h4', { class: 'ititle', text: t }), h('p', { text: p })])
    ),
    (() => {
      const bts = [techBt(), ...psySection()].filter(Boolean);
      return pli(
        'Ce que valent ces lectures (backtests)',
        ...(bts.length ? bts : [h('p', { class: 'note', text: 'Résultats au prochain calcul complet.' })])
      );
    })(),
    hist.length || GS.journal.length
      ? pli(
          'Historique des alertes et des lectures',
          hist.length ? h('h4', { class: 'ititle', text: 'Alertes' }) : null,
          hist.length
            ? h(
                'ul',
                { class: 'list' },
                hist.map((t) => h('li', { text: `${dfr(t.id.slice(0, 10))} — ${t.titre}` }))
              )
            : null,
          GS.journal.length ? h('h4', { class: 'ititle', text: 'Lectures de la semaine' }) : null,
          GS.journal.length
            ? h(
                'ul',
                { class: 'list' },
                GS.journal.map((j) => h('li', {}, h('b', { text: dfr(j.date) }), ' — ' + (j.resume || '')))
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

/* ---------------------------------------------------------------------------------------------- onglet Marché
   Une ligne par culture : cours, lecture technique, effet de l'actualité, repères ; le détail d'une culture au toucher.
   L'outil décrit le marché ; il ne dit jamais quoi vendre, ni quand, ni combien. */
const NOM_COURT = {
  ble: 'Blé',
  escourgeon: 'Escourgeon',
  orge_printemps: 'Orge de printemps',
  colza: 'Colza',
  mais: 'Maïs',
};
const BASE = { ble: 'ble', escourgeon: 'ble', orge_printemps: 'ble', colza: 'colza', mais: 'mais' };
const BASE_USDA = { ble: 'ble', escourgeon: 'orge', orge_printemps: 'orge', colza: 'colza', mais: 'mais' };
const SENS = {
  haussière: ['▲ hausse', 'good'],
  baissière: ['▼ baisse', 'bad'],
  neutre: ['● neutre', 'neutral'],
  équilibrée: ['● neutre', 'neutral'],
};
function sensBadge(s, azote, valeur) {
  if (!s) return h('span', { class: 'badge neutral', text: '—' });
  let [t, c] = SENS[s] || [s, 'neutral'];
  // azote : une hausse est un prix d'achat plus cher (couleurs de position, pas de jugement)
  if (azote && s === 'haussière') [t, c] = ['▲ plus cher', 'warn'];
  if (azote && s === 'baissière') [t, c] = ['▼ moins cher', 'info'];
  // valeur de la pression de l'actualité (−2 à +2), expliquée dans l'onglet Actualité
  return h('span', {
    class: 'badge ' + c,
    text: valeur !== undefined && valeur !== null ? `${t} · ${fmt(Math.abs(valeur), 1)} sur 2` : t,
  });
}
// une nouvelle en une ligne : titre — effet (sans tiret orphelin quand l'effet manque)
const ligneActu = (a) =>
  h('div', { class: 'dsous', text: (a.titre_fr || a.titre) + (a.impact ? ` — ${a.impact}` : '') });
const varSpan = (v, d = 2, suf = ' €', titre = 'Variation depuis la séance précédente') =>
  v === null || v === undefined || v === 0
    ? null
    : h('span', { class: 'mvar ' + cls(v), title: titre, text: sgn(v, d) + suf });
// date courte « 13 nov. » (l'année seulement si elle n'est pas l'année en cours)
const dcourt = (s) =>
  String(s).slice(0, 4) === String(new Date().getFullYear()) ? dfr(s).replace(/ \d{4}$/, '') : dfr(s);

// repères en une ligne : prix sur 5 ans, écart au plus haut de la campagne, seuils atteints
function reperesTxt(c) {
  const r = c.reperes || {};
  const out = [];
  if (r.ecart_plus_haut !== null && r.ecart_plus_haut !== undefined && !c.physique)
    out.push(
      r.ecart_plus_haut < -0.01
        ? `${fmt(-r.ecart_plus_haut)} € sous le plus haut de campagne`
        : 'au plus haut de la campagne'
    );
  for (const s of c.seuils || [])
    if (s.atteint) out.push(`🔔 votre seuil ${s.sens === '>' ? '≥' : '≤'} ${fmt(s.niveau)} €/t est atteint`);
  return out.join(' · ');
}

function marcheRow(href, nom, prix, tech, actu, note, jauge) {
  const paire = (lab, b) => h('span', { class: 'mpaire' }, h('span', { class: 'mlab', text: lab }), b);
  return h(
    'a',
    { class: 'mrow', href },
    h('span', { class: 'mname', text: nom }),
    h('span', { class: 'mprix' }, ...prix),
    h('span', { class: 'mbadges' }, tech ? paire(tech.lab || 'Technique', tech.b) : null, paire('Actualité', actu)),
    jauge ? h('span', { class: 'mjauge' }, jauge) : null,
    note ? h('span', { class: 'mnote', text: note }) : null,
    h('span', { class: 'dgo', 'aria-hidden': 'true', text: '›' })
  );
}

function alertes(d) {
  const ac = GS.actu || {};
  const out = (ac.articles || [])
    .filter((x) => (ac.majeurs || []).includes(x.id))
    .map((a) => `📰 ${a.titre_fr || a.titre}`);
  const ids = new Set((d.declencheurs || []).map((t) => t.id));
  for (const t of d.declencheurs || [])
    if (!(t.id.includes(':panne:') && ids.has(t.id.replace(':panne:', ':retablie:'))))
      out.push(`${t.grave ? '🔔 ' : ''}${t.titre}`);
  return out;
}

function agenda(d) {
  const cal = ((d.comite || {}).calendrier || [])
    .filter((x) => x.date >= d.date)
    .sort((a, b) => (a.date < b.date ? -1 : 1))
    .slice(0, 3);
  return cal.length
    ? h('p', {
        class: 'meta',
        text: '📅 À venir : ' + cal.map((x) => `${dcourt(x.date)} : ${x.evenement}`).join(' · '),
      })
    : null;
}

// la lecture de la semaine (lundi) : arguments haussiers et baissiers, ce qu'il faut surveiller ; jamais de consigne
function lectureCard(cc, titre) {
  if (!cc) return null;
  const liste = (xs, cl, t) =>
    xs && xs.length
      ? [
          h('h4', { class: 'ititle ' + cl, text: t }),
          h(
            'ul',
            { class: 'list' },
            xs.map((x) => h('li', { text: x }))
          ),
        ]
      : [];
  return h(
    'section',
    { class: 'card wide' },
    h('h3', { text: titre }),
    cc.lecture ? h('p', { text: cc.lecture }) : null,
    h(
      'div',
      { class: 'duo2' },
      h('div', {}, ...liste(cc.haussier, 'up', '▲ Ce qui pousse à la hausse')),
      h('div', {}, ...liste(cc.baissier, 'down', '▼ Ce qui pousse à la baisse'))
    ),
    cc.a_surveiller ? h('p', { class: 'note', text: `À surveiller : ${cc.a_surveiller}` }) : null
  );
}

// les nouvelles qui pèsent le plus sur une culture (ids calculés par actualites.py)
function principales(p) {
  const arts = (GS.actu || {}).articles || [];
  return ((p && p.principaux) || [])
    .map((id) => arts.find((a) => a.id === id))
    .filter(Boolean)
    .slice(0, 2);
}

// lecture du marché de la semaine (lundi), en bas de l'onglet Actualité : le résumé et une ligne par culture. Les arguments
// haussiers et baissiers sont dans le détail de chaque culture, le rapport complet dans l'email du lundi (pas de doublon ici).
function lectureSemaine(d) {
  const com = d.comite || {};
  if (!com.resume || !com.valide) return null;
  const lignes = [...Object.entries(d.cultures || {}), ['azote', { nom: 'Azote', comite: (d.engrais || {}).comite }]]
    .filter(([, c]) => c.comite && c.comite.lecture)
    .map(([k, c]) =>
      h(
        'li',
        {},
        h('a', { href: `#marche/${k}`, text: `${k === 'azote' ? '🧪' : ICON[k] || ''} ${NOM_COURT[k] || c.nom}` }),
        ` : ${c.comite.lecture}`
      )
    );
  return h(
    'details',
    { class: 'acc' },
    h('summary', { text: `Lecture du marché de la semaine (${dfr(com.date)})` }),
    h('p', { text: com.resume }),
    lignes.length ? h('ul', { class: 'list' }, lignes) : null,
    h('p', {
      class: 'note',
      text: 'Arguments à la hausse et à la baisse : dans le détail de chaque culture (onglet Marché).',
    })
  );
}

function navCultures(d, k) {
  const keys = Object.keys(d.cultures || {}).concat(['azote']);
  return h(
    'nav',
    { class: 'filters cnav', 'aria-label': 'Choisir une culture' },
    h('a', { class: 'filt', href: '#marche', text: '← Vue d’ensemble' }),
    keys.map((x) =>
      h('a', {
        class: 'filt',
        href: `#marche/${x}`,
        'aria-current': x === k ? 'page' : null,
        text: x === 'azote' ? '🧪 Azote' : `${ICON[x] || ''} ${NOM_COURT[x] || x}`,
      })
    )
  );
}

function vMarche() {
  const d = GS.data;
  const k = GS.cult;
  if (k && (k === 'azote' || (d.cultures || {})[k]))
    return [navCultures(d, k), ...(k === 'azote' ? azoteView(d) : cultureView(k, d))];
  const out = [h('p', { class: 'meta', text: `Séance du ${dfr((d.contrats.EBM || {}).seance || d.date)}` })];
  if (d.format !== 'grain-signal-2')
    out.push(
      h('div', {
        class: 'alert info',
        text: 'Données en cours de mise à jour : rechargez la page dans quelques minutes.',
      })
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
  out.push(h('h2', { text: 'Le marché ce matin' }));
  const rows = Object.entries(d.cultures || {}).map(([key, c]) =>
    marcheRow(
      `#marche/${key}`,
      `${ICON[key] || ''} ${NOM_COURT[key] || c.nom}`,
      [
        h('b', { text: c.cours ? `${fmt(c.cours)} €/t` : '—' }),
        varSpan(c.var1j, 2, c.physique ? ' € depuis le relevé précédent' : ' € sur la séance'),
        c.physique ? h('small', { text: 'physique' }) : null,
      ],
      { lab: c.proxy ? 'Technique (tendance du blé)' : 'Technique', b: sensBadge((c.technique || {}).sens) },
      sensBadge((c.actualite || {}).sens, false, (c.actualite || {}).valeur),
      reperesTxt(c),
      // escourgeon et orge de printemps : pas de jauge (ce serait celle du blé, déjà au-dessus)
      c.proxy ? null : pgauge((c.reperes || {}).percentile5, 'prix', 'Prix sur 5 ans', null, true)
    )
  );
  const e = d.engrais || {};
  const u = (e.france || {}).uree || {};
  rows.push(
    marcheRow(
      '#marche/azote',
      '🧪 Azote',
      [
        h('b', { text: u.prix ? `${fmt(u.prix)} €/t` : '—' }),
        varSpan(u.var1m, 1, ' % en 1 mois', 'Variation sur un mois'),
        h('small', { text: 'urée' }),
      ],
      null,
      sensBadge((e.actualite || {}).sens, true, (e.actualite || {}).valeur),
      (e.seuils || [])
        .filter((s) => s.atteint)
        .map((s) => `🔔 votre seuil ${s.sens === '>' ? '≥' : '≤'} ${fmt(s.niveau)} €/t est atteint`)
        .join(' · '),
      pgauge(e.percentile_retenu, 'ratio', 'Prix de l’azote face au blé (10 ans)', null, true)
    )
  );
  out.push(h('nav', { class: 'mrows', 'aria-label': 'Marché par culture' }, rows));
  out.push(
    h(
      'details',
      { class: 'aide' },
      h('summary', { text: 'Comment lire ce tableau' }),
      h(
        'ul',
        { class: 'list' },
        [
          'À côté du cours : variation en €/t sur la séance (orges : depuis le relevé de prix précédent ; azote : en % sur un mois).',
          'Technique : tendance des moyennes mobiles, élan (MACD) et excès (RSI). Escourgeon et orge de printemps n’ont pas de marché à terme coté chaque jour : le prix affiché est bien le leur (prix physique Creil), mais la technique est celle du blé Euronext, que l’orge suit de près.',
          'Actualité : effet moyen des nouvelles des 7 derniers jours sur le prix, sur une échelle de 0 à 2 dans le sens indiqué (« ▲ hausse · 1,5 sur 2 » = nettement haussière ; 0,5 = plutôt ; 1 et plus = très) ; azote : hausse = plus cher. Détail dans l’onglet Actualité.',
          'Prix sur 5 ans : le percentile place le cours du jour parmi les semaines des 5 dernières années. 50e = au milieu ; 20e = plus bas que 80 % d’entre elles ; 90e = plus haut que 90 %.',
          'Azote face au blé : même lecture pour le rapport prix de l’urée / prix du blé sur 10 ans (bas = azote bon marché par rapport au blé).',
          'Touchez une ligne pour le détail. L’outil décrit le marché ; la décision vous appartient.',
        ].map((t) => h('li', { text: t }))
      )
    )
  );
  out.push(agenda(d));
  out.push(autresMarches(d));
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
          'prix',
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
    con.psychologie ? pgauge(con.psychologie.indice, 'psy', '🧠 Humeur du marché', null, true) : null,
  ].filter(Boolean);
}

function cultureView(k, d) {
  const c = d.cultures[k];
  const con = (d.contrats || {})[c.contrat] || {};
  const tq = c.technique || {};
  const o = (d.orges || {})[k];
  const graph =
    o && o.estime
      ? periodPanel({
          nom: o.nom,
          graphique: o.estime.graphique,
          long: orgeLong(o, d.contrats.EBM),
          technique: o.estime.technique,
          niveaux: tq,
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
            h('span', {}, h('i', { style: 'background:var(--chart-1)' }), 'Prix physique relevé')
          ),
        })
      : !c.proxy
        ? periodPanel({
            nom: con.nom,
            graphique: (con.proxy && con.proxy.graphique ? con.proxy : con).graphique,
            long: con.long,
            technique: con.proxy && con.proxy.technique ? con.proxy.technique : con.technique,
            niveaux: tq,
            longMain: con.long && con.long.source === 'euronext' ? null : 'var(--muted)',
          })
        : null;
  const ta = con.proxy && con.proxy.technique ? con.proxy.technique : con.technique;
  const met = ((d.meteo || {}).cultures || {})[BASE[k]];
  const sa = (d.saison || {})[BASE[k]];
  const rp = c.reperes || {};
  const ceu = ((d.cot || {})['EURONEXT_' + c.contrat] || {}).indice;
  const pl = !c.proxy ? con.prime_locale : null;
  const ph = c.physique_detail || {};
  const ou = c.physique
    ? `prix physique ${ph.place || 'Creil FOB'}, ${dfr(c.date)}`
    : c.echeance
      ? `Euronext ${c.contrat} ${moisFr(c.echeance)}, séance du ${dfr(c.date)}`
      : '';
  const arts = principales(c.actualite);
  const kv = (t, ...v) => [h('dt', { text: t }), h('dd', {}, ...v)];
  return [
    h(
      'section',
      { class: 'card wide head' },
      h('h2', { text: `${ICON[k] || ''} ${c.nom}` }),
      h(
        'p',
        { class: 'mbig' },
        h('b', { text: c.cours ? `${fmt(c.cours)} €/t` : '—' }),
        varSpan(c.var1j, 2, c.physique ? ' € depuis le relevé précédent' : ' € sur la séance'),
        h('small', { text: ou })
      ),
      h(
        'dl',
        { class: 'kv' },
        kv(
          'Technique',
          sensBadge(tq.sens),
          ' ',
          tq.texte
            ? `${tq.sur_ble ? 'Tendance du blé Euronext, que l’orge suit : ' : ''}${tq.texte}`
            : 'historique trop court'
        ),
        kv('Actualité', sensBadge((c.actualite || {}).sens, false, (c.actualite || {}).valeur), ...arts.map(ligneActu))
      )
    ),
    graph ? h('section', { class: 'card wide' }, graph) : null,
    (() => {
      const g = reperes(k, c, con, d);
      return g.length
        ? h(
            'div',
            { class: 'card wide' },
            h('div', { class: 'pgrid tight' }, g),
            h('p', {
              class: 'note',
              text: 'Percentile : place du chiffre du jour dans son historique, de 0 (le plus bas) à 100 (le plus haut). Prix sur 5 ans au 70e : plus cher que 70 % des semaines des 5 dernières années. Stocks mondiaux au 30e : plus serrés que 70 % des 20 dernières campagnes. Humeur : de 0 (peur extrême) à 100 (euphorie).',
            })
          )
        : null;
    })(),
    lectureCard(c.comite, `Lecture de la semaine (${dfr((d.comite || {}).date)})`),
    h(
      'section',
      { class: 'card wide' },
      h(
        'dl',
        { class: 'kv' },
        rp.plus_haut !== undefined
          ? kv(
              '📈 Campagne',
              `plus haut ${fmt(rp.plus_haut)} €/t le ${dfr(rp.plus_haut_le)}${c.proxy ? ' (blé)' : ''}, ${sgn(rp.ecart_plus_haut)} €/t depuis`
            )
          : null,
        con.stockage && con.stockage.texte
          ? kv('📦 Stockage', (c.proxy ? 'Courbe du blé. ' : '') + con.stockage.texte)
          : null,
        pl && (pl.percentile !== undefined || pl.comparaison)
          ? kv(
              '📍 Prime locale',
              [pl.percentile !== undefined ? pl.texte : null, pl.comparaison].filter(Boolean).join(' · ')
            )
          : null,
        ph.prix
          ? kv(
              '🏭 Physique',
              `${fmt(ph.prix)} €/t ${ph.place || ''}${ph.prime !== undefined && ph.prime !== null ? `, prime brassicole ${sgn(ph.prime)} €/t sur la fourragère` : ''}`
            )
          : null,
        met
          ? kv(
              '🌦️ Météo',
              met.zones
                .filter((z) => z.etat !== 'normal' && z.saison)
                .map((z) => `${z.zone} ${z.etat}`)
                .join(', ') || 'rien d’anormal dans les zones en saison'
            )
          : null,
        sa
          ? kv(
              '📅 Saison',
              `mois habituellement chers : ${sa.plus_chers.map((m) => MOIS[m - 1]).join(', ')} ; moins chers : ${sa.moins_chers.map((m) => MOIS[m - 1]).join(', ')}`
            )
          : null,
        (c.seuils || []).length
          ? kv(
              '🔔 Vos seuils',
              c.seuils
                .map((s) => `${s.sens === '>' ? '≥' : '≤'} ${fmt(s.niveau)} €/t${s.atteint ? ' (atteint)' : ''}`)
                .join(' · ')
            )
          : null
      ),
      h(
        'details',
        {},
        h('summary', { text: 'Tous les indicateurs' }),
        con.psychologie
          ? h('p', {
              class: 'note',
              text: `🧠 Humeur ${con.psychologie.indice} (${con.psychologie.libelle}) : ${con.psychologie.lecture}. RSI ${con.psychologie.composantes.rsi}, écart MM200 ${con.psychologie.composantes.ecart200}, élan 20 j ${con.psychologie.composantes.elan20}${con.psychologie.composantes.fonds !== null && con.psychologie.composantes.fonds !== undefined ? `, fonds ${con.psychologie.composantes.fonds}` : ''} (percentiles sur 3 ans).`,
            })
          : null,
        h(
          'div',
          { class: 'pgrid' },
          ceu !== undefined && ceu !== null && !c.proxy
            ? pgauge(ceu, 'cot', '🏦 Fonds sur Euronext (3 ans)', null, true)
            : null,
          pl && pl.percentile !== undefined ? pgauge(pl.percentile, 'prime', '📍 Prime locale', null, true) : null
        ),
        ta && !ta.insuffisant ? techTable(ta) : null
      )
    ),
  ];
}

function azoteView(d) {
  const e = d.engrais || {};
  const u = (e.france || {}).uree || {};
  const kv = (t, ...v) => [h('dt', { text: t }), h('dd', {}, ...v)];
  return [
    h(
      'section',
      { class: 'card wide head' },
      h('h2', { text: '🧪 Azote' }),
      h(
        'p',
        { class: 'mbig' },
        h('b', { text: u.prix ? `${fmt(u.prix)} €/t` : '—' }),
        varSpan(u.var1m, 1, ' % en 1 mois'),
        h('small', { text: u.date ? `urée 46, ${dfr(u.date)}` : 'urée 46' })
      ),
      h(
        'dl',
        { class: 'kv' },
        kv(
          'Actualité',
          sensBadge((e.actualite || {}).sens, true, (e.actualite || {}).valeur),
          ...principales(e.actualite).map(ligneActu)
        ),
        e.saison ? kv('Saison', e.saison) : null,
        e.forme_moins_chere
          ? kv('Forme la moins chère', `${e.forme_moins_chere} (en €/unité d’azote, avant pertes)`)
          : null,
        (e.seuils || []).length
          ? kv(
              '🔔 Vos seuils',
              e.seuils
                .map((s) => `${s.sens === '>' ? '≥' : '≤'} ${fmt(s.niveau)} €/t${s.atteint ? ' (atteint)' : ''}`)
                .join(' · ')
            )
          : null
      ),
      e.notes && e.notes.length
        ? h(
            'ul',
            { class: 'list' },
            e.notes.map((n) => h('li', { text: n }))
          )
        : null
    ),
    h(
      'div',
      { class: 'card wide' },
      h(
        'div',
        { class: 'pgrid tight' },
        pgauge(e.percentile_retenu, 'ratio', '⚖️ Azote face au blé (10 ans)', null, true),
        e.ttf
          ? pgauge(e.ttf.percentile_5ans, 'prix', `⛽ Gaz sur 5 ans (${fmt(e.ttf.dernier)} €/MWh)`, null, true)
          : null
      )
    ),
    lectureCard(e.comite, `Lecture de la semaine (${dfr((d.comite || {}).date)})`),
    h('details', { class: 'acc' }, h('summary', { text: 'Gaz, urée, ratio et prix France' }), ...vEngrais()),
  ];
}

// contexte commun (marchés mondiaux, fonds, bilans, météo, saisons) : replié en bas de l'onglet Marché
function autresMarches(d) {
  const kids = [...stocksSection(d), ...saisonSection(d), ...meteoSection(d)];
  const inter = Object.entries(d.international || {});
  const cot = Object.values(d.cot || {}).filter((c) => c.indice !== null && c.indice !== undefined);
  return h(
    'details',
    { class: 'more-data', open: '' },
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
              ['Marché', 'Dernier', '1 mois', 'Technique'].map((t, i) =>
                h('th', { class: i && i < 3 ? 'n' : '', text: t })
              )
            ),
            inter.map(([, x]) => {
              const a = x.technique || {};
              return h(
                'tr',
                {},
                h('td', { text: x.nom }),
                h('td', { class: 'n', text: fmt(a.dernier, a.dernier < 10 ? 4 : 2) }),
                h('td', { class: 'n ' + cls(a.var1m), text: pct(a.var1m) }),
                h('td', {}, sensBadge((x.lecture || {}).sens))
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

// effet sur chaque prix : ↑ hausse, ↓ baisse (azote : ↑ = plus cher)
function impactChips(imp) {
  return Object.entries(imp || {})
    .filter(([, v]) => v)
    .map(([c, v]) => {
      const fl = v > 0 ? '↑'.repeat(Math.abs(v)) : '↓'.repeat(Math.abs(v));
      return h('span', {
        class: 'chip ' + (c === 'engrais' ? (v > 0 ? 'warn' : 'info') : v > 0 ? 'good' : 'bad'),
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
          ' Chaque événement se juge donc au cas par cas : c’est le rôle des actualités traduites ci-dessus et de la lecture de la semaine.',
      })
    ),
  ];
}

// ce que vaut l'humeur du marché sur l'historique (l'humeur du jour est sur chaque culture)
function psySection() {
  const bt = (GS.backtest || {}).psychologie || {};
  const evid = Object.entries(bt).filter(([, v]) => v && v['60']);
  return [
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
            text: 'Humeur de 0 (peur extrême) à 100 (euphorie) : moyenne des percentiles sur 3 ans du RSI, de l’écart à la moyenne 200 séances, de l’élan sur 20 séances et de la position des fonds. « Hasard seul » : corrélation atteinte par pur hasard (90 % des cas) sur des cours tirés au sort de même longueur et de même nervosité, car les périodes de 60 séances se chevauchent. Une humeur qui ne bat pas le hasard décrit l’ambiance du marché ; elle ne prédit pas la suite.',
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
        text: `Ce que l’actualité change pour les prix${ac.synthese_du && ac.synthese_du !== ac.date ? ` (${dfr(ac.synthese_du)})` : ''}`,
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
        text: `Comment lire le chiffre : chaque nouvelle des 7 derniers jours reçoit un effet de −2 (forte baisse du prix) à +2 (forte hausse), pondéré par son importance (1 à 3), sa nature (un fait pèse plus qu’une rumeur) et son âge (moitié du poids après 3 jours) ; le chiffre est la moyenne de ces effets, ramenée vers 0 quand il y a peu de nouvelles. Il ne grimpe donc pas avec le nombre de titres : il dit dans quel sens et avec quelle force l’actualité pousse. 0 : nouvelles sans effet ou qui s’équilibrent · ±0,5 : plutôt haussière ou baissière · ±1 et au-delà : très haussière ou baissière. Repères : des nouvelles modérées toutes dans le même sens donnent environ +0,8 ; un fait majeur du jour à effet fort, environ +1 ; +1,5 et au-delà demande plusieurs faits importants et concordants. Le chiffre mesure le sens et la force de l’actualité, pas une prévision de prix. Azote : + = plus cher. ${(ac.compte || {}).pertinents || 0} titres retenus sur ${(ac.compte || {}).lus || 0} ; les titres parlent plus des risques de hausse que d’une offre abondante : à lire avec les cours.`,
      })
    )
  );
  out.push(newsList(ac));
  const geo = geoSection(d).slice(1); // sans le titre : la section est repliée
  if (geo.length) out.push(h('details', { class: 'more-data' }, h('summary', { text: 'Risque géopolitique' }), ...geo));
  out.push(lectureSemaine(d));
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
  const v = { marche: vMarche, actualite: vActualite, methode: vMethode }[GS.tab] || vMarche;
  main.append(...v().filter(Boolean)); // une section absente (null) ne s'affiche pas « null »
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

// #marche, #marche/ble, #actualite, #methode ; anciens liens (#aujourdhui, #cultures/ble, #signaux, #engrais…) redirigés
const ANCIENS = {
  aujourdhui: 'marche',
  cultures: 'marche',
  signaux: 'marche',
  comite: 'marche',
  technique: 'marche',
  engrais: 'marche/azote',
};
function route() {
  let [t, x] = (location.hash || '').slice(1).split('/');
  if (ANCIENS[t]) [t, x] = [ANCIENS[t].split('/')[0], ANCIENS[t].split('/')[1] || x];
  GS.tab = ['marche', 'actualite', 'methode'].includes(t) ? t : 'marche';
  GS.cult = GS.tab === 'marche' ? x || null : GS.cult;
}

async function init() {
  // page installable sur le téléphone : même service worker qu'Euro Signal (réseau d'abord, copie locale hors connexion)
  if ('serviceWorker' in navigator && location.protocol === 'https:')
    navigator.serviceWorker.register('sw.js').catch(() => {});
  route();
  document.querySelectorAll('.tabs button').forEach((b) =>
    b.addEventListener('click', () => {
      location.hash = b.dataset.tab;
    })
  );
  window.addEventListener('hashchange', () => {
    const avant = GS.tab;
    route();
    render();
    if (avant !== GS.tab || GS.tab === 'marche') window.scrollTo({ top: 0 });
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
  GS.journal = (Array.isArray(j) ? j : []).filter((x) => x.mode === 'hebdo'); // lectures hebdomadaires seules (pas les anciens comités)
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
