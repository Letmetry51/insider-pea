// Mini-interpréteur du sous-ensemble de ProBuilder (langage de ProRealTime) utilisé par prorealtime/euro-signal-screener.txt,
// pour vérifier dans les tests que le screener prend les mêmes décisions que le moteur (ProRealTime ne tourne pas ici).
// Pris en charge : affectations, IF / ELSE / ENDIF, AND / OR / NOT, comparaisons, + - * /, MIN MAX SQRT LOG EXP ROUND ABS,
// indicateurs [n](série) : Average, STD (écart type de population), Summation, Highest, Lowest, LinearRegressionSlope ;
// décalage x[k] ; close, volume, BarIndex ; TIMEFRAME(weekly / default) (barres déjà hebdomadaires) ;
// SCREENER[condition](expression AS "nom", …).
// Calcul barre par barre comme ProScreener ; seules les `tail` dernières barres sont calculées (fenêtres de 60 barres au plus).
'use strict';
const FN_P = new Set(['AVERAGE', 'STD', 'SUMMATION', 'HIGHEST', 'LOWEST', 'LINEARREGRESSIONSLOPE']);
const FN_0 = new Set(['MIN', 'MAX', 'SQRT', 'LOG', 'EXP', 'ROUND', 'ABS']);
const KW = new Set(['AND', 'OR', 'NOT', 'IF', 'THEN', 'ELSE', 'ENDIF', 'SCREENER', 'AS']);

function tokenize(line) {
  const out = [];
  const re = /\s*(?:(\d+\.?\d*|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|("[^"]*")|(<=|>=|<>|[-+*/=<>()[\],]))/y;
  let m;
  re.lastIndex = 0;
  while (re.lastIndex < line.length) {
    const at = re.lastIndex;
    m = re.exec(line);
    if (!m) {
      if (/^\s*$/.test(line.slice(at))) break;
      throw new Error('jeton illisible : ' + line.slice(at, at + 20));
    }
    if (m[1]) out.push({ t: 'num', v: parseFloat(m[1]) });
    else if (m[2]) out.push({ t: KW.has(m[2].toUpperCase()) ? 'kw' : 'id', v: m[2].toUpperCase() });
    else if (m[3]) out.push({ t: 'str', v: m[3].slice(1, -1) });
    else if (m[4]) out.push({ t: 'op', v: m[4] });
  }
  return out;
}

function parser(toks) {
  let i = 0;
  const peek = () => toks[i];
  const is = (t, v) => toks[i] && toks[i].t === t && (v == null || toks[i].v === v);
  const eat = (t, v) => {
    if (!is(t, v)) throw new Error(`attendu ${v || t}, trouvé ${toks[i] ? toks[i].v : 'fin de ligne'}`);
    return toks[i++];
  };
  const expr = () => orE();
  const orE = () => {
    let a = andE();
    while (is('kw', 'OR')) {
      i++;
      a = { k: 'or', a, b: andE() };
    }
    return a;
  };
  const andE = () => {
    let a = notE();
    while (is('kw', 'AND')) {
      i++;
      a = { k: 'and', a, b: notE() };
    }
    return a;
  };
  const notE = () => (is('kw', 'NOT') ? (i++, { k: 'not', a: notE() }) : cmpE());
  const cmpE = () => {
    let a = addE();
    while (is('op') && ['=', '<>', '<', '>', '<=', '>='].includes(peek().v)) {
      const o = toks[i++].v;
      a = { k: 'cmp', o, a, b: addE() };
    }
    return a;
  };
  const addE = () => {
    let a = mulE();
    while (is('op', '+') || is('op', '-')) {
      const o = toks[i++].v;
      a = { k: 'bin', o, a, b: mulE() };
    }
    return a;
  };
  const mulE = () => {
    let a = unE();
    while (is('op', '*') || is('op', '/')) {
      const o = toks[i++].v;
      a = { k: 'bin', o, a, b: unE() };
    }
    return a;
  };
  const unE = () => (is('op', '-') ? (i++, { k: 'neg', a: unE() }) : postE());
  const postE = () => {
    let a = prim();
    while (is('op', '[')) {
      i++;
      const k = expr();
      eat('op', ']');
      a = { k: 'idx', a, n: k };
    }
    return a;
  };
  const prim = () => {
    if (is('num')) return { k: 'num', v: toks[i++].v };
    if (is('op', '(')) {
      i++;
      const e = expr();
      eat('op', ')');
      return e;
    }
    const id = eat('id').v;
    if (FN_P.has(id)) {
      eat('op', '[');
      const n = expr();
      eat('op', ']');
      eat('op', '(');
      const a = expr();
      eat('op', ')');
      return { k: 'fp', f: id, n, a };
    }
    if (FN_0.has(id)) {
      eat('op', '(');
      const args = [expr()];
      while (is('op', ',')) {
        i++;
        args.push(expr());
      }
      eat('op', ')');
      return { k: 'f0', f: id, args };
    }
    return { k: 'var', v: id };
  };
  return { expr, is, eat, end: () => i >= toks.length };
}

function compile(src) {
  const lines = src
    .split('\n')
    .map((l) => l.replace(/\/\/.*$/, '').trim())
    .filter(Boolean);
  const prog = [];
  const blocks = [prog]; // listes d'instructions ouvertes
  const ifs = []; // IF ouverts
  let screener = null;
  for (const line of lines) {
    const toks = tokenize(line);
    // TIMEFRAME(weekly) / TIMEFRAME(default) : les barres fournies sont déjà hebdomadaires
    if (toks.length && toks[0].t === 'id' && toks[0].v === 'TIMEFRAME') {
      if (!/^TIMEFRAME\((WEEKLY|DEFAULT)\)$/.test(toks.map((x) => String(x.v).toUpperCase()).join('')))
        throw new Error('unité de temps non prise en charge : ' + line);
      continue;
    }
    const P = parser(toks);
    const cur = blocks[blocks.length - 1];
    if (P.is('kw', 'IF')) {
      P.eat('kw', 'IF');
      const c = P.expr();
      P.eat('kw', 'THEN');
      if (!P.end()) throw new Error('IF sur une seule ligne : non pris en charge');
      const node = { k: 'if', c, th: [], el: [] };
      cur.push(node);
      ifs.push(node);
      blocks.push(node.th);
    } else if (P.is('kw', 'ELSE')) {
      if (!ifs.length) throw new Error('ELSE sans IF');
      blocks.pop();
      blocks.push(ifs[ifs.length - 1].el);
    } else if (P.is('kw', 'ENDIF')) {
      if (!ifs.length) throw new Error('ENDIF sans IF');
      blocks.pop();
      ifs.pop();
    } else if (P.is('kw', 'SCREENER')) {
      P.eat('kw', 'SCREENER');
      P.eat('op', '[');
      const c = P.expr();
      P.eat('op', ']');
      const cols = [];
      if (P.is('op', '(')) {
        P.eat('op', '(');
        for (;;) {
          const e = P.expr();
          P.eat('kw', 'AS');
          cols.push({ e, name: P.eat('str').v });
          if (!P.is('op', ',')) break;
          P.eat('op', ',');
        }
        P.eat('op', ')');
      }
      if (!P.end()) throw new Error('fin de SCREENER illisible');
      screener = { c, cols };
    } else {
      const name = P.eat('id').v;
      P.eat('op', '=');
      const e = P.expr();
      if (!P.end()) throw new Error('fin de ligne illisible : ' + line);
      cur.push({ k: 'set', name, e });
    }
  }
  if (ifs.length) throw new Error('IF sans ENDIF');
  if (!screener) throw new Error('pas d’instruction SCREENER');
  return { prog, screener };
}

function run(compiled, bars, tail = 120) {
  const n = bars.close.length,
    V = {};
  const t0 = Math.max(0, n - tail);
  const get = (name, t) => {
    if (name === 'CLOSE') return t >= 0 ? bars.close[t] : 0;
    if (name === 'VOLUME') return t >= 0 ? bars.volume[t] || 0 : 0;
    if (name === 'BARINDEX') return t;
    const a = V[name];
    if (!a) throw new Error('variable inconnue : ' + name);
    return t >= 0 && a[t] != null ? a[t] : 0;
  };
  const ev = (x, t) => {
    switch (x.k) {
      case 'num':
        return x.v;
      case 'var':
        return get(x.v, t);
      case 'idx':
        return ev(x.a, t - ev(x.n, t));
      case 'neg':
        return -ev(x.a, t);
      case 'not':
        return ev(x.a, t) ? 0 : 1;
      case 'and':
        return ev(x.a, t) && ev(x.b, t) ? 1 : 0;
      case 'or':
        return ev(x.a, t) || ev(x.b, t) ? 1 : 0;
      case 'cmp': {
        const a = ev(x.a, t),
          b = ev(x.b, t);
        return (
          x.o === '='
            ? a === b
            : x.o === '<>'
              ? a !== b
              : x.o === '<'
                ? a < b
                : x.o === '>'
                  ? a > b
                  : x.o === '<='
                    ? a <= b
                    : a >= b
        )
          ? 1
          : 0;
      }
      case 'bin': {
        const a = ev(x.a, t),
          b = ev(x.b, t);
        return x.o === '+' ? a + b : x.o === '-' ? a - b : x.o === '*' ? a * b : b === 0 ? 0 : a / b;
      }
      case 'f0': {
        const v = x.args.map((y) => ev(y, t));
        switch (x.f) {
          case 'MIN':
            return Math.min(...v);
          case 'MAX':
            return Math.max(...v);
          case 'SQRT':
            return Math.sqrt(v[0]);
          case 'LOG':
            return Math.log(v[0]);
          case 'EXP':
            return Math.exp(v[0]);
          case 'ROUND':
            return Math.round(v[0]);
          case 'ABS':
            return Math.abs(v[0]);
        }
        break;
      }
      case 'fp': {
        const L = Math.round(ev(x.n, t));
        const w = [];
        for (let k = L - 1; k >= 0; k--) w.push(ev(x.a, t - k));
        const m = w.reduce((s, y) => s + y, 0) / L;
        switch (x.f) {
          case 'AVERAGE':
            return m;
          case 'SUMMATION':
            return m * L;
          case 'STD':
            return Math.sqrt(w.reduce((s, y) => s + (y - m) * (y - m), 0) / L);
          case 'HIGHEST':
            return Math.max(...w);
          case 'LOWEST':
            return Math.min(...w);
          case 'LINEARREGRESSIONSLOPE': {
            const xm = (L - 1) / 2;
            let sxy = 0,
              sxx = 0;
            w.forEach((y, i) => {
              sxy += (i - xm) * (y - m);
              sxx += (i - xm) * (i - xm);
            });
            return sxy / sxx;
          }
        }
      }
    }
    throw new Error('nœud inconnu ' + x.k);
  };
  const exec = (list, t) => {
    for (const s of list) {
      if (s.k === 'set') {
        (V[s.name] = V[s.name] || [])[t] = ev(s.e, t);
      } else if (s.k === 'if') exec(ev(s.c, t) ? s.th : s.el, t);
    }
  };
  // déclare les variables (y compris celles d'une branche jamais prise)
  const declare = (list) =>
    list.forEach((s) => (s.k === 'set' ? (V[s.name] = V[s.name] || []) : (declare(s.th), declare(s.el))));
  declare(compiled.prog);
  for (let t = t0; t < n; t++) exec(compiled.prog, t);
  const t = n - 1;
  const out = { ok: !!ev(compiled.screener.c, t), vars: {} };
  compiled.screener.cols.forEach((c) => (out[c.name] = ev(c.e, t)));
  Object.keys(V).forEach((k) => (out.vars[k] = V[k][t]));
  return out;
}

module.exports = { compile, run, tokenize };
