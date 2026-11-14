/* Euro Signal — interface : outils, état de la page, stockage local.
   Scripts classiques chargés dans l'ordre par euro-signal.html (fonctions partagées entre fichiers) ; dépend de ES (euro_signal/core.js). */
'use strict';
var esc = ES.esc,
  pct = ES.fmtPct;
function $(s) {
  return document.querySelector(s);
}
function fmtN(v, d) {
  d = d == null ? 2 : d;
  return v == null || !isFinite(v)
    ? 'n.d.'
    : v.toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtInt(v) {
  return v == null || !isFinite(v) ? 'n.d.' : Math.round(v).toLocaleString('fr-FR');
}
function fmtMoney(v, cur) {
  if (v == null || !isFinite(v)) return 'n.d.';
  var s = v >= 1e6 ? fmtN(v / 1e6, 2) + ' M' : v >= 1e3 ? fmtN(v / 1e3, 1) + ' k' : fmtN(v, 0);
  return s + ' ' + ES.esc(ES.cleanCurrency(cur) || '?');
}
function todayIso() {
  var d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

var REGISTRIES = [
  { name: 'AMF', country: 'FR', official: true, label: 'AMF — base BDIF (France)', url: 'https://bdif.amf-france.org' },
  {
    name: 'BaFin',
    country: 'DE',
    official: true,
    label: "BaFin — Directors' Dealings (Allemagne)",
    url: 'https://portal.mvp.bafin.de/database/DealingsInfo/',
  },
  {
    name: 'FSMA',
    country: 'BE',
    official: true,
    label: 'FSMA — transactions de dirigeants (Belgique)',
    url: 'https://www.fsma.be',
  },
  {
    name: 'FI',
    country: 'SE',
    official: true,
    label: 'Finansinspektionen — registre Insynshandel (Suède)',
    url: 'https://marknadssok.fi.se',
  },
  {
    name: 'AFM',
    country: 'NL',
    official: true,
    label: 'AFM — registre MAR 19 (Pays-Bas)',
    url: 'https://www.afm.nl/en/sector/registers',
  },
  {
    name: 'CNMV',
    country: 'ES',
    official: true,
    label: 'CNMV — opérations des dirigeants (Espagne)',
    url: 'https://www.cnmv.es',
  },
  {
    name: 'CONSOB',
    country: 'IT',
    official: true,
    label: 'CONSOB / publications des émetteurs (Italie)',
    url: 'https://www.consob.it',
  },
  { name: 'Émetteur', country: null, official: true, label: "Communiqué de l'émetteur", url: '' },
  {
    name: 'Duceus',
    country: null,
    official: false,
    label: 'Duceus API (agrégateur)',
    url: 'https://duceusapi.com/docs',
  },
  {
    name: 'EODHD',
    country: null,
    official: false,
    label: 'EODHD (cours, fondamentaux)',
    url: 'https://eodhd.com/pricing',
  },
  { name: 'Autre', country: null, official: false, label: 'Autre source', url: '' },
];
var COUNTRIES = {
  FR: 'France',
  DE: 'Allemagne',
  IT: 'Italie',
  BE: 'Belgique',
  ES: 'Espagne',
  NL: 'Pays-Bas',
  PT: 'Portugal',
  IE: 'Irlande',
  AT: 'Autriche',
  FI: 'Finlande',
  LU: 'Luxembourg',
  DK: 'Danemark',
  SE: 'Suède',
  NO: 'Norvège',
  CH: 'Suisse',
  GB: 'Royaume-Uni',
};
var STAGES = {
  autorisation_ag: "Autorisation d'assemblée",
  annonce: 'Annonce du programme',
  debut: "Début d'exécution",
  execution: 'Rachats exécutés',
  suspension: 'Suspension',
  annulation: 'Annulation',
};
var ALERT_STATUS = {
  simulee: ['Simulée', 'neutral'],
  brouillon: ['Brouillon Gmail', 'good'],
  envoyee: ['Envoyée', 'good'],
  en_cours: ['Envoi non confirmé', 'warn'],
  incertain: ['Statut incertain', 'warn'],
  echec: ['Échec', 'bad'],
};

var S = {
  mode: 'chargement',
  db: null,
  mcp: null,
  dl: null,
  cfg: ES.mergeConfig(ES.DEFAULT_CONFIG, {}),
  inst: {},
  tx: {},
  ev: {},
  src: {},
  alerts: {},
  prices: {},
  refs: {},
  computed: {},
  range: (function () {
    try {
      return localStorage.getItem('es-range') === '5y' ? '5y' : '1y';
    } catch (e) {
      return '1y';
    }
  })(),
  view: 'classement',
  sel: null,
  filters: {
    q: '',
    country: '',
    status: '',
    signals: true,
    sort: 'advice',
    quick: ['buys'],
    figures: [],
    plans: [],
    timing: [],
  },
  txFilter: { type: 'achat', registry: '', country: '' },
  uniFilter: 'a_examiner',
  limit: 50,
  rankMode: (function () {
    try {
      return localStorage.getItem('es-rankmode') === 'ins' ? 'ins' : 'rank';
    } catch (e) {
      return 'rank';
    }
  })(),
  today: todayIso(),
  busy: null,
  imp: null,
  bt: null,
  restore: null,
  confirm: null,
  notice: null,
};
window.__ES_STATE = S; // pour le débogage dans la console

/* =========================== Stockage =========================== */
function boot() {
  render();
  tryRemote();
  var off = function () {
    document.body.classList.toggle('offline', !navigator.onLine);
  };
  try {
    window.addEventListener('online', off);
    window.addEventListener('offline', off);
    off();
  } catch (e) {}
  // Application installable : icône sur l'écran d'accueil, dernier classement consultable hors connexion
  try {
    if ('serviceWorker' in navigator && (/^https:$/.test(location.protocol) || location.hostname === 'localhost'))
      navigator.serviceWorker.register('sw.js').catch(function () {});
  } catch (e) {}
}
function defang(o) {
  if (typeof o === 'string')
    return o.indexOf('<') < 0 && o.indexOf('>') < 0 ? o : o.replace(/</g, '‹').replace(/>/g, '›');
  if (Array.isArray(o)) {
    for (var i = 0; i < o.length; i++) o[i] = defang(o[i]);
    return o;
  }
  if (o && typeof o === 'object') {
    Object.keys(o).forEach(function (k) {
      o[k] = defang(o[k]);
    });
    return o;
  }
  return o;
}
/** Empreintes des données publiées (data/version.json, écrit à la publication et relu à chaque ouverture) : chaque fichier est
 *  demandé en ?v=empreinte et servi par le cache du téléphone tant qu'il ne change pas (jusqu'au 23/10/2026, environ 1,7 Mo
 *  retéléchargés à chaque ouverture). Sans empreinte (première publication, fichier ouvert hors du site) : réseau, comme avant. */
S.ver = null;
function dataUrl(f) {
  var h = S.ver && S.ver[String(f).replace(/^data\//, '')];
  return h && /^[0-9a-f]{6,40}$/.test(h) ? f + '?v=' + h : f;
}
function getData(f) {
  var u = dataUrl(f);
  return fetch(u, { cache: u === f ? 'no-store' : 'default' });
}
function loadVersion() {
  return fetch('data/version.json?_=' + Date.now(), { cache: 'no-store' })
    .then(function (r) {
      return r.ok ? r.json() : null;
    })
    .then(function (v) {
      S.ver = v && v.format === 'euro-signal-version' && v.files && typeof v.files === 'object' ? v.files : null;
    })
    .catch(function () {
      S.ver = null;
    });
}
/** Mode automatique : la page est servie avec data/euro-signal.json (GitHub Pages), mis à jour chaque soir. */
function tryRemote() {
  busy('Chargement des données du jour…');
  loadVersion()
    .then(function () {
      return getData('data/euro-signal.json');
    })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      if (d.format !== 'euro-signal-snapshot') throw new Error('format inattendu');
      d = defang(d); // défense en profondeur : aucune balise HTML ne peut venir des sources
      S.mode = 'remote';
      S.ro = true;
      S.snapshot = d;
      ES.setFx(d.fx || {});
      S.cfg = ES.mergeConfig(ES.DEFAULT_CONFIG, d.cfg || {});
      S.today = d.today || S.today;
      S.inst = d.inst || {};
      S.aliases = d.aliases || {};
      S.tx = d.tx || {};
      S.ev = d.ev || {};
      S.src = d.src || {};
      S.alerts = d.alerts || {};
      S.prices = d.prices || {};
      S.refs = d.refs || {};
      S.detailFile = /^data\/[\w.-]+\.json$/.test(d.detailFile || '') ? d.detailFile : null;
      S.longFile = /^data\/[\w.-]+\.json$/.test(d.longFile || '') ? d.longFile : null;
      S.shards =
        d.detailShards && /^data\/[\w-]+$/.test(d.detailShards.dir || '') && d.detailShards.n > 0
          ? d.detailShards
          : null;
      S.shardLoaded = {};
      S.shardLoading = {};
      S.detailLoaded = !S.detailFile && !S.shards;
      Object.keys(S.prices).forEach(function (i) {
        var p = S.prices[i];
        if (p && p.closesOnly)
          p.rows = p.rows.map(function (r) {
            return [r[0], null, null, null, r[1], null];
          });
      });
      if (S.detailLoaded)
        Object.keys(S.inst).forEach(function (i) {
          if (!S.prices[i]) S.prices[i] = { rows: [], missing: true };
        });
      S.bt = { remote: true, res: d.backtest ? d.backtest.results : [], meta: d.backtest || {} };
      computeAll();
      idle();
      openFromHash();
      render();
    })
    .catch(function (e) {
      idle();
      S.mode = 'erreur';
      S.loadError = (e && e.message) || 'inconnue';
      render();
    });
}
/** Lien direct vers une fiche (…/euro-signal.html#ISIN), utilisé dans les emails d'alerte. */
/** Cours et historique complet : chargés une seule fois, à l'ouverture de la première fiche. */
/** Une partie des fiches (cours 1 an, déclarations, comptes) : intégrée à l'état, sociétés sans cours marquées. */
function mergeDetail(d, only) {
  d = defang(d);
  Object.keys(d.prices || {}).forEach(function (i) {
    var p = d.prices[i];
    if (p && p.closesOnly)
      p.rows = p.rows.map(function (r) {
        return [r[0], null, null, null, r[1], null];
      });
    S.prices[i] = p;
  });
  Object.keys(d.tx || {}).forEach(function (i) {
    S.tx[i] = d.tx[i];
  });
  Object.keys(d.refs || {}).forEach(function (i) {
    S.refs[i] = d.refs[i];
  });
  Object.keys(d.accounts || {}).forEach(function (i) {
    if (S.inst[i]) S.inst[i].accounts = d.accounts[i];
  });
  Object.keys(S.inst).forEach(function (i) {
    if (!S.prices[i] && (only == null || ES.shardOf(i, S.shards.n) === only)) S.prices[i] = { rows: [], missing: true };
  });
}
function hasDetail(i) {
  return S.detailLoaded || !!(S.shards && S.shardLoaded[ES.shardOf(i, S.shards.n)]);
}
/** Fiche d'une société : seul son petit fichier est téléchargé. */
function loadDetailFor(i) {
  if (!S.shards) {
    loadDetail();
    return;
  }
  var k = ES.shardOf(i, S.shards.n);
  if (S.detailLoaded || S.shardLoaded[k] || S.shardLoading[k]) return;
  S.shardLoading[k] = true;
  getData(S.shards.dir + '/' + k + '.json')
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      mergeDetail(d, k);
      S.shardLoaded[k] = true;
      S.shardLoading[k] = false;
      S.planCache = {};
      if (S.sel) computeOne(S.sel);
      render();
    })
    .catch(function () {
      S.shardLoading[k] = false;
      S.shardLoaded[k] = true;
      Object.keys(S.inst).forEach(function (j) {
        if (!S.prices[j] && ES.shardOf(j, S.shards.n) === k) S.prices[j] = { rows: [], missing: true };
      });
      render();
    });
}
function loadDetail() {
  if (S.detailLoading || S.detailLoaded) return;
  S.detailLoading = true;
  if (S.shards) {
    // toutes les fiches (calcul des tendances de toute la liste) : les fichiers sont lus en parallèle
    var todo = [];
    for (var k = 0; k < S.shards.n; k++) if (!S.shardLoaded[k]) todo.push(k);
    Promise.all(
      todo.map(function (k) {
        return getData(S.shards.dir + '/' + k + '.json')
          .then(function (r) {
            return r.ok ? r.json() : null;
          })
          .then(function (d) {
            if (d) mergeDetail(d, k);
            S.shardLoaded[k] = true;
          })
          .catch(function () {
            S.shardLoaded[k] = true;
          });
      })
    ).then(function () {
      Object.keys(S.inst).forEach(function (i) {
        if (!S.prices[i]) S.prices[i] = { rows: [], missing: true };
      });
      S.detailLoaded = true;
      S.detailLoading = false;
      S.planCache = {};
      if (S.sel) computeOne(S.sel);
      render();
    });
    return;
  }
  getData(S.detailFile)
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (d) {
      d = defang(d);
      Object.keys(d.prices || {}).forEach(function (i) {
        var p = d.prices[i];
        if (p && p.closesOnly)
          p.rows = p.rows.map(function (r) {
            return [r[0], null, null, null, r[1], null];
          });
        S.prices[i] = p;
      });
      Object.keys(d.tx || {}).forEach(function (i) {
        S.tx[i] = d.tx[i];
      });
      Object.keys(d.refs || {}).forEach(function (i) {
        S.refs[i] = d.refs[i];
      });
      Object.keys(d.accounts || {}).forEach(function (i) {
        if (S.inst[i]) S.inst[i].accounts = d.accounts[i];
      });
      Object.keys(S.inst).forEach(function (i) {
        if (!S.prices[i]) S.prices[i] = { rows: [], missing: true };
      });
      S.detailLoaded = true;
      S.detailLoading = false;
      if (S.sel) computeOne(S.sel);
      render();
    })
    .catch(function () {
      S.detailLoading = false;
      Object.keys(S.inst).forEach(function (i) {
        if (!S.prices[i]) S.prices[i] = { rows: [], missing: true };
      });
      S.detailLoaded = true;
      render();
    });
}
/** Actualiser la page ramène toujours à l'accueil : l'adresse d'une fiche (#ISIN, #co=…) ne sert qu'aux liens des emails. */
(function () {
  try {
    var nv = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
    if (nv && nv.type === 'reload' && location.hash && location.hash !== '#aide')
      history.replaceState(null, '', location.pathname + location.search);
  } catch (e) {}
})();
function openFromHash() {
  var m = (location.hash || '').match(/^#([A-Z]{2}[A-Z0-9]{9}[0-9])$/);
  var al = m && !S.inst[m[1]] && S.aliases && S.aliases[m[1]]; // ancien ISIN réuni à un autre dossier
  if (al && S.inst[al]) {
    S.sel = al;
    S.view = 'fiche';
  } else if (m && S.inst[m[1]]) {
    S.sel = m[1];
    S.view = 'fiche';
  } else if (location.hash === '#aide') S.view = 'aide';
  else {
    var co = (location.hash || '').match(/^#co=(.+)$/);
    if (co) {
      S.secSym = decodeURIComponent(co[1]);
      S.view = 'secco';
      S.secFrom = S.secFrom || 'classement';
    }
  }
}
window.addEventListener('hashchange', function () {
  var before = S.sel,
    v0 = S.view;
  openFromHash();
  // retour arrière du navigateur depuis une fiche : on revient à la liste d'origine, à la hauteur de la société
  if ((v0 === 'fiche' || v0 === 'secco') && !location.hash && S.back) {
    S.pushed = false;
    S.view = S.back.view;
    S.limit = Math.max(50, S.back.limit || 50);
    render();
    restoreBack();
    return;
  }
  if (S.sel !== before || S.view !== v0 || (S.view === 'secco' && location.hash)) {
    render();
    window.scrollTo(0, 0);
  }
});
/** Retour d'une fiche vers la liste : même hauteur qu'au départ, la société visible au milieu de l'écran et brièvement surlignée. */
function restoreBack() {
  var b = S.back;
  if (!b) {
    window.scrollTo(0, 0);
    return;
  }
  window.scrollTo(0, b.y || 0);
  var els = [].slice.call(
      document.querySelectorAll('[data-a="open"][data-i="' + b.i + '"], [data-a="secCo"][data-v="' + b.i + '"]')
    ),
    best = null,
    d0 = Infinity;
  els.forEach(function (e) {
    var y = e.getBoundingClientRect().top + window.scrollY,
      d = Math.abs(y - (b.y + window.innerHeight / 2));
    if (d < d0) {
      d0 = d;
      best = e;
    }
  }); // la ligne la plus proche de l'endroit quitté
  if (best) {
    var r = best.getBoundingClientRect();
    if (r.top < 60 || r.bottom > window.innerHeight)
      window.scrollTo(0, Math.max(0, r.top + window.scrollY - window.innerHeight / 3));
    best.classList.add('backflash');
    setTimeout(function () {
      best.classList.remove('backflash');
    }, 1600);
  }
}
function sentEventIds(isin) {
  var out = {};
  Object.keys(S.alerts).forEach(function (id) {
    var a = S.alerts[id];
    var counted = ['envoyee', 'brouillon', 'incertain', 'en_cours'].concat(
      S.mode === 'remote' && !(S.snapshot && S.snapshot.mail && S.snapshot.mail.ready) ? ['simulee'] : []
    );
    if (a.isin === isin && counted.indexOf(a.status) > -1)
      (a.eventIds || []).forEach(function (e) {
        out[e] = 1;
      });
  });
  return out;
}
function computeOne(isin) {
  var inst = S.inst[isin],
    ev = S.ev[isin] || { buybacks: [], results: [] },
    refs = S.refs[isin] || {};
  var uni = ES.universeStatus(inst, S.cfg);
  var score = ES.score({ inst: inst, tx: S.tx[isin] || [], events: ev, refs: refs, cfg: S.cfg, today: S.today });
  var q = ES.quality({ inst: inst, score: score, sources: S.src, events: ev, cfg: S.cfg, today: S.today });
  var oh = ES.overheat(inst, S.cfg);
  var dec = ES.alertDecision({
    inst: inst,
    score: score,
    quality: q,
    overheat: oh,
    universe: uni,
    cfg: S.cfg,
    today: S.today,
    sentEventIds: sentEventIds(isin),
  });
  S.computed[isin] = { uni: uni, score: score, q: q, oh: oh, dec: dec };
  return S.computed[isin];
}
function computeAll() {
  S.computed = {};
  Object.keys(S.inst).forEach(computeOne);
}
