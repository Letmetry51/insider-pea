/* Grain Signal — page (lecture seule de data/grain/*.json, publiés chaque matin). Tout texte venu des données est inséré
   comme texte ; seul le rapport du comité est du HTML, déjà nettoyé au calcul et nettoyé une seconde fois ici. */
'use strict';

const GS = { data: null, comite: null, journal: [], tab: 'signaux' };

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
function chart(rows, opts = {}) {
  const W = 640,
    H = opts.h || 200,
    P = { l: 44, r: 8, t: 10, b: 22 };
  const pts = rows.filter((r) => r[1] !== null && r[1] !== undefined);
  if (pts.length < 2) return h('p', { class: 'note', text: 'Historique trop court pour un graphique.' });
  const all = pts.flatMap((r) => r.slice(1).filter((v) => v !== null && v !== undefined));
  (opts.levels || []).forEach((l) => all.push(l.v));
  let lo = Math.min(...all),
    hi = Math.max(...all);
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad;
  hi += pad;
  const x = (i) => P.l + (i / (pts.length - 1)) * (W - P.l - P.r);
  const y = (v) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'chart');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', opts.label || 'Graphique des cours');
  const add = (tag, a) => {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(a)) el.setAttribute(k, v);
    svg.appendChild(el);
    return el;
  };
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4;
    add('line', { x1: P.l, x2: W - P.r, y1: y(v), y2: y(v), stroke: 'var(--line)', 'stroke-width': 1 });
    const t = add('text', { x: P.l - 6, y: y(v) + 4, 'text-anchor': 'end', 'font-size': 11, fill: 'var(--muted)' });
    t.textContent = fmt(v, v > 100 ? 0 : 1);
  }
  [0, Math.floor((pts.length - 1) / 2), pts.length - 1].forEach((i) => {
    const t = add('text', {
      x: x(i),
      y: H - 6,
      'text-anchor': i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle',
      'font-size': 11,
      fill: 'var(--muted)',
    });
    t.textContent = dfr(pts[i][0]);
  });
  const usedY = [];
  (opts.levels || []).forEach((l) => {
    add('line', {
      x1: P.l,
      x2: W - P.r,
      y1: y(l.v),
      y2: y(l.v),
      stroke: l.c,
      'stroke-width': 1.2,
      'stroke-dasharray': '5 4',
    });
    if (usedY.some((u) => Math.abs(u - y(l.v)) < 13)) return; // étiquettes trop proches : la ligne seule suffit
    usedY.push(y(l.v));
    const t = add('text', { x: W - P.r - 2, y: y(l.v) - 4, 'text-anchor': 'end', 'font-size': 11, fill: l.c });
    t.textContent = l.t + ' ' + fmt(l.v, 2);
  });
  const series = [
    [1, 'var(--chart-1)', 2.2],
    [2, 'var(--chart-2)', 1.4],
    [3, 'var(--chart-3)', 1.4],
  ];
  series.forEach(([col, color, w]) => {
    let d = '';
    pts.forEach((r, i) => {
      if (r[col] === null || r[col] === undefined) return;
      d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[col]).toFixed(1);
    });
    if (d) add('path', { d, fill: 'none', stroke: color, 'stroke-width': w, 'stroke-linejoin': 'round' });
  });
  return svg;
}

/* ---------------------------------------------------------------------------------------------- onglets */
function vSignaux() {
  const d = GS.data;
  const out = [];
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
  const grid = h('div', { class: 'grid' });
  for (const [, c] of Object.entries(d.cultures || {})) {
    const cc = c.comite || {};
    const niv = c.niveaux || {};
    // escourgeon et orge de printemps : pas de marché à terme, pas d'ordres techniques tirés du blé
    const ordres = (cc.ordres && cc.ordres.length ? cc.ordres : c.proxy ? [] : niv.ordres) || [];
    const revision = cc.revision_bas || (c.proxy ? null : niv.revision);
    const contrat = (d.contrats || {})[c.contrat] || {};
    grid.append(
      h(
        'section',
        { class: 'card' },
        h('h3', { text: c.nom }),
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
        c.a_revoir ? h('div', { class: 'alert', text: c.a_revoir }) : null,
        cc.texte ? h('p', { class: 'note', text: cc.texte }) : c.note ? h('p', { class: 'note', text: c.note }) : null,
        h(
          'dl',
          { class: 'kv' },
          cc.pct ? [h('dt', { text: 'À vendre' }), h('dd', { text: cc.pct })] : null,
          [
            h('dt', { text: 'Ordres' }),
            h('dd', { text: ordres.length ? ordres.map((v) => fmt(v)).join(' · ') + ' €/t' : '—' }),
          ],
          [h('dt', { text: 'Révision' }), h('dd', { text: revision ? '< ' + fmt(revision) : '—' })],
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
        c.feu ? h('div', { class: 'feu' }, h('b', { text: 'Timing technique' }), c.feu.texte) : null
      )
    );
  }
  const e = d.engrais || {};
  const ec = e.comite || {};
  grid.append(
    h(
      'section',
      { class: 'card' },
      h('h3', { text: 'Engrais azotés' }),
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
  const grid = h('div', { class: 'grid' });
  for (const [code, c] of Object.entries(d.contrats || {})) {
    const a = c.technique || {};
    const lv = [];
    ((c.niveaux || {}).ordres || []).forEach((v) => lv.push({ v, c: 'var(--good)', t: 'ordre' }));
    if ((c.niveaux || {}).revision) lv.push({ v: c.niveaux.revision, c: 'var(--bad)', t: 'révision' });
    grid.append(
      h(
        'section',
        { class: 'card' },
        h('h3', { text: `${c.nom} — Euronext ${code}` }),
        h('p', {
          class: 'note',
          text: `Série continue (échéance de référence ${c.echeance || '—'}), ${a.seances || 0} séances, dernière : ${dfr(c.seance)}`,
        }),
        c.alerte_raccord ? h('div', { class: 'alert', text: c.alerte_raccord }) : null,
        c.proxy ? h('div', { class: 'alert info', text: c.proxy.texte }) : null,
        c.proxy && c.proxy.graphique
          ? chart(c.proxy.graphique, { label: `${c.proxy.nom} en €/t : cours, MM20 et MM50` })
          : c.graphique
            ? chart(c.graphique, { levels: lv, label: `${c.nom} : cours, MM20 et MM50` })
            : null,
        h(
          'div',
          { class: 'legend' },
          h('span', {}, h('i', { style: 'background:var(--chart-1)' }), 'Cours'),
          h('span', {}, h('i', { style: 'background:var(--chart-2)' }), 'MM20'),
          h('span', {}, h('i', { style: 'background:var(--chart-3)' }), 'MM50')
        ),
        a.insuffisant && c.proxy && c.proxy.technique
          ? techTable(c.proxy.technique)
          : a.insuffisant
            ? h('p', { class: 'note', text: 'Indicateurs Euronext disponibles à partir de 30 séances.' })
            : techTable(a),
        h('p', { class: 'note', text: `Note technique : ${sgn(c.score_technique)} (de −2 à +2)` })
      )
    );
  }
  for (const o of Object.values(d.orges || {})) {
    const ble = (d.contrats || {}).EBM || {};
    grid.append(
      h(
        'section',
        { class: 'card' },
        h('h3', { text: o.nom }),
        h('p', {
          class: 'note',
          text: "Pas de marché à terme pour les orges : prix physique Creil FOB relevé chaque jour (terre-net) ; le moment de vendre suit le blé Euronext, la prime brassicole dit si l'orge est bien payée.",
        }),
        o.graphique && o.graphique.length >= 2
          ? chart(
              o.graphique.map((r) => [r[0], r[1], null, null]),
              { label: `${o.nom} : prix physique` }
            )
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
            h('td', { text: 'Orge fourragère Creil FOB' }),
            h('td', { class: 'n', text: o.fourragere ? `${fmt(o.fourragere)} €/t` : '—' })
          ),
          h(
            'tr',
            {},
            h('td', { text: 'Prime brassicole' }),
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
  out.push(h('h2', { text: 'Marchés internationaux, énergie, change' }));
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
  out.push(h('h2', { text: 'Positions des fonds (CFTC, managed money)' }));
  const cot = Object.values(d.cot || {});
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
                    c.indice <= 15
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
            text: 'Lecture à contre-courant : un positionnement extrême annonce souvent un retournement.',
          })
        )
      : h('p', { class: 'muted', text: 'Positions CFTC non disponibles ce matin.' })
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
      "Grain Signal relève les cours Euronext (blé, colza, maïs) et leurs courbes, les marchés américains, le gaz TTF, le Brent, l'euro-dollar, les positions des fonds (CFTC), les prix des engrais en France et le Pink Sheet de la Banque mondiale. Il calcule la technique (RSI 14, MACD 12/26/9, moyennes mobiles 20/50/200, Bollinger 20/2, Fibonacci, divergences), le module engrais et les déclencheurs, puis envoie un email s'il se passe quelque chose.",
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
  const [d, c, j] = await Promise.all([
    getJSON('data/grain/grain-signal.json'),
    getJSON('data/grain/comite.json'),
    getJSON('data/grain/comites-journal.json'),
  ]);
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
