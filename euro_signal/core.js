/* Euro Signal — moteur de calcul (fonctions pures, sans accès réseau ni DOM).
 * Testé avec Node (tests.js) puis intégré tel quel dans la page HTML.
 * Conventions :
 *  - dates ISO "AAAA-MM-JJ" (UTC, sans fuseau) ; heures "HH:MM" séparées.
 *  - pourcentages exprimés en points (12.5 = 12,5 %).
 *  - une valeur inconnue vaut null : jamais 0, jamais "vrai" par défaut.
 */
(function (root) {
  'use strict';
  var ES = {};
  ES.ENGINE_VERSION = '1.0.0';

  /* ============================== Dates ============================== */
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function toDate(iso) { var p = iso.split('-'); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); }
  ES.isoDate = function (d) { return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()); };
  function mk(y, mo, d) {
    if (!(y > 1900 && y < 2200) || mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    var dt = new Date(Date.UTC(y, mo - 1, d));
    if (dt.getUTCMonth() !== mo - 1) return null; // 31 février, etc.
    return ES.isoDate(dt);
  }
  /** Interprète AAAA-MM-JJ, JJ/MM/AAAA, JJ.MM.AAAA, AAAAMMJJ. Les formats ambigus M/J/A ne sont pas acceptés. */
  ES.parseDate = function (v) {
    if (v == null) return null;
    var s = String(v).trim(), m;
    if (!s) return null;
    if ((m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/))) return mk(+m[1], +m[2], +m[3]);
    if ((m = s.match(/^(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{4})/))) return mk(+m[3], +m[2], +m[1]);
    if ((m = s.match(/^(\d{4})(\d{2})(\d{2})$/))) return mk(+m[1], +m[2], +m[3]);
    return null;
  };
  /** Date + heure éventuelle, avec la précision réellement connue. */
  ES.parseDateTime = function (v) {
    var d = ES.parseDate(v);
    if (!d) return null;
    var m = String(v).match(/[ T](\d{1,2}):(\d{2})/);
    if (m && +m[1] < 24 && +m[2] < 60) return { date: d, time: pad(+m[1]) + ':' + m[2], precision: 'minute' };
    return { date: d, time: null, precision: 'jour' };
  };
  ES.addDays = function (iso, n) { var d = toDate(iso); d.setUTCDate(d.getUTCDate() + n); return ES.isoDate(d); };
  /** Mois calendaires : 31 mai - 3 mois = 28/29 février (jour borné à la fin du mois). */
  ES.addMonths = function (iso, n) {
    var p = iso.split('-'), y = +p[0], m = +p[1] - 1 + n, d = +p[2];
    y += Math.floor(m / 12); m = ((m % 12) + 12) % 12;
    var last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
    return ES.isoDate(new Date(Date.UTC(y, m, Math.min(d, last))));
  };
  ES.daysBetween = function (a, b) { return Math.round((toDate(b) - toDate(a)) / 864e5); };
  /** Jours ouvrés (lundi-vendredi) strictement après a et jusqu'à b inclus. Les jours fériés ne sont pas déduits. */
  ES.businessDaysBetween = function (a, b) {
    if (b <= a) return 0;
    var n = 0, d = toDate(a), end = toDate(b);
    while (d < end) { d.setUTCDate(d.getUTCDate() + 1); var w = d.getUTCDay(); if (w !== 0 && w !== 6) n++; }
    return n;
  };

  /* ============================= Nombres ============================= */
  /** locale : 'auto' | 'eu' (1.234,56) | 'en' (1,234.56). Retourne null si invalide. */
  ES.parseNumber = function (v, locale) {
    if (v == null) return null;
    if (typeof v === 'number') return isFinite(v) ? v : null;
    var s = String(v).trim().replace(/[  \s']/g, '').replace(/(EUR|CHF|GBP|USD|SEK|DKK|NOK|PLN|€|\$|£)/gi, '');
    if (!s || /^(-|—|n\/?a|nan|null|none|\?)$/i.test(s)) return null;
    var neg = false;
    if (/^\(.*\)$/.test(s)) { neg = true; s = s.slice(1, -1); }
    locale = locale || 'auto';
    var c = s.lastIndexOf(','), d = s.lastIndexOf('.');
    if (locale === 'eu') s = s.replace(/\./g, '').replace(',', '.');
    else if (locale === 'en') s = s.replace(/,/g, '');
    else if (c > -1 && d > -1) s = c > d ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
    else if (c > -1) s = s.split(',').length > 2 ? s.replace(/,/g, '') : s.replace(',', '.');
    else if (d > -1 && s.split('.').length > 2) s = s.replace(/\./g, '');
    if (!/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(s)) return null;
    var n = parseFloat(s);
    if (!isFinite(n)) return null;
    return neg ? -n : n;
  };

  /* ============================== Texte ============================== */
  ES.norm = function (s) {
    return String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, ' ').trim();
  };
  /** Clé de personne insensible à l'ordre "Nom Prénom" / "Prénom Nom" et aux civilités. */
  ES.personKey = function (name) {
    var t = ES.norm(name).split(' ').filter(function (w) {
      return w && ['m', 'mme', 'mr', 'mrs', 'ms', 'dr', 'herr', 'frau', 'sig', 'sr', 'sra', 'de', 'la', 'le', 'van', 'von', 'der', 'den'].indexOf(w) < 0;
    });
    return t.sort().join(' ');
  };
  ES.hash = function (s) { // FNV-1a 32 bits, suffisant pour des identifiants internes
    var h = 0x811c9dc5;
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0; }
    return ('0000000' + h.toString(16)).slice(-8);
  };
  ES.safeId = function (s) { return String(s).replace(/[^A-Za-z0-9_\-.~:@+]/g, '_').slice(0, 180); };

  /** Contrôle de format + clé de contrôle ISIN (Luhn sur la conversion lettres → chiffres). */
  ES.isValidIsin = function (isin) {
    if (!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin || '')) return false;
    var digits = '';
    for (var i = 0; i < 11; i++) { var ch = isin[i]; digits += /[0-9]/.test(ch) ? ch : String(ch.charCodeAt(0) - 55); }
    var sum = 0, dbl = true;
    for (var j = digits.length - 1; j >= 0; j--) {
      var n = +digits[j];
      if (dbl) { n *= 2; if (n > 9) n -= 9; }
      sum += n; dbl = !dbl;
    }
    return (10 - (sum % 10)) % 10 === +isin[11];
  };

  /* ============================ CSV / JSON =========================== */
  ES.parseCSV = function (text) {
    text = String(text || '').replace(/^﻿/, '');
    var first = text.split(/\r?\n/)[0] || '', best = ',', bestN = -1;
    [';', ',', '\t', '|'].forEach(function (dl) {
      var n = 0, q = false;
      for (var i = 0; i < first.length; i++) { var ch = first[i]; if (ch === '"') q = !q; else if (!q && ch === dl) n++; }
      if (n > bestN) { bestN = n; best = dl; }
    });
    var rows = [], row = [], f = '', q = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (q) {
        if (ch === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; }
        else f += ch;
      } else if (ch === '"') q = true;
      else if (ch === best) { row.push(f); f = ''; }
      else if (ch === '\n' || ch === '\r') {
        if (ch === '\r' && text[i + 1] === '\n') i++;
        row.push(f); f = '';
        if (row.length > 1 || row[0] !== '') rows.push(row);
        row = [];
      } else f += ch;
    }
    if (f !== '' || row.length) { row.push(f); if (row.length > 1 || row[0] !== '') rows.push(row); }
    if (!rows.length) return { headers: [], rows: [], delimiter: best, truncated: false };
    var headers = rows[0].map(function (h) { return String(h).trim(); });
    var out = [], truncated = false;
    for (var r = 1; r < rows.length; r++) {
      if (rows[r].length < headers.length && r === rows.length - 1) { truncated = true; continue; } // dernière ligne coupée
      var o = {};
      headers.forEach(function (h, k) { o[h] = rows[r][k] != null ? String(rows[r][k]).trim() : ''; });
      out.push(o);
    }
    return { headers: headers, rows: out, delimiter: best, truncated: truncated || q };
  };
  /** Aplatit un JSON (tableau ou {data|results|items:[...]}) en lignes clé→valeur ("a.b" pour les objets imbriqués). */
  ES.parseJSONRows = function (text) {
    var data = JSON.parse(text);
    if (!Array.isArray(data)) {
      var k = ['data', 'results', 'items', 'transactions', 'rows', 'records'].filter(function (x) { return data && Array.isArray(data[x]); })[0];
      if (!k) throw new Error('JSON sans tableau de lignes reconnaissable');
      data = data[k];
    }
    var headers = {}, rows = data.map(function (obj) {
      var o = {};
      (function walk(v, p) {
        if (v && typeof v === 'object' && !Array.isArray(v)) Object.keys(v).forEach(function (kk) { walk(v[kk], p ? p + '.' + kk : kk); });
        else { o[p] = v == null ? '' : Array.isArray(v) ? v.join(' | ') : String(v); headers[p] = 1; }
      })(obj, '');
      return o;
    });
    return { headers: Object.keys(headers), rows: rows, delimiter: 'json', truncated: false };
  };
  ES.parseTable = function (text) {
    var t = String(text || '').trim();
    if (t[0] === '[' || t[0] === '{') return ES.parseJSONRows(t);
    return ES.parseCSV(text);
  };

  /* ===================== Correspondance des colonnes ===================== */
  ES.FIELDS = {
    tx: {
      isin: ['isin', 'code isin', 'isin code', 'codice isin', 'instrument isin', 'issuer isin'],
      issuer: ['emetteur', 'issuer', 'societe', 'company', 'emittent', 'nom de la societe', 'emisor', 'emittente', 'company name', 'issuer name', 'uitgevende instelling'],
      ticker: ['ticker', 'symbol', 'symbole', 'mnemo', 'mnemonique'],
      person: ['declarant', 'nom du declarant', 'insider', 'insider name', 'person', 'person name', 'meldepflichtiger', 'meldepflichtige person', 'nome', 'persona', 'nombre', 'pdmr', 'personne', 'name of person', 'notifying person'],
      role: ['fonction', 'position', 'role', 'position status', 'funktion', 'position status funktion', 'qualita', 'cargo', 'title', 'position title', 'statut du declarant'],
      linkedTo: ['personne liee a', 'lie a', 'linked to', 'related to', 'associated pdmr', 'pdmr lie', 'verbunden mit'],
      associated: ['personne etroitement liee', 'closely associated', 'closely associated person', 'pca', 'eng verbundene person', 'persona strettamente legata'],
      nature: ['nature', 'nature de l operation', 'nature de la transaction', 'transaction type', 'type', 'type d operation', 'art des geschafts', 'art des geschaefts', 'geschaftsart', 'tipo operazione', 'naturaleza', 'soort transactie', 'transaction nature'],
      txDate: ['date de l operation', 'date de la transaction', 'date de transaction', 'transaction date', 'trade date', 'datum des geschafts', 'datum des geschaefts', 'geschaftsdatum', 'data operazione', 'fecha de la operacion', 'datum transactie', 'date'],
      pubDate: ['date de publication', 'publication date', 'published', 'published at', 'publication', 'mitteilungsdatum', 'datum der veroffentlichung', 'veroffentlichungsdatum', 'date de reception', 'filing date', 'data pubblicazione', 'fecha de publicacion', 'datum publicatie', 'disclosure date'],
      qty: ['quantite', 'quantity', 'nombre de titres', 'number of shares', 'shares', 'stuckzahl', 'stueckzahl', 'anzahl', 'quantita', 'numero de acciones', 'aantal', 'qty', 'units'],
      price: ['prix', 'prix unitaire', 'prix moyen', 'prix moyen pondere', 'price', 'unit price', 'average price', 'durchschnittspreis', 'preis', 'prezzo', 'prezzo medio', 'precio', 'precio medio', 'prijs'],
      currency: ['devise', 'currency', 'wahrung', 'waehrung', 'valuta', 'moneda'],
      amount: ['montant', 'montant total', 'amount', 'value', 'valeur', 'total value', 'aggregiertes volumen', 'gesamtvolumen', 'controvalore', 'importe', 'importe total', 'bedrag', 'transaction value'],
      venue: ['lieu', 'lieu de l operation', 'venue', 'place', 'ort des geschafts', 'handelsplatz', 'sede', 'mercado', 'trading venue', 'place of transaction'],
      sourceUrl: ['lien', 'url', 'link', 'source url', 'document', 'pdf', 'lien vers la declaration', 'document url'],
      registryId: ['id', 'reference', 'numero', 'id declaration', 'numero de declaration', 'bafin id', 'referenz', 'document id', 'filing id', 'notification id'],
      version: ['version', 'revision'],
      status: ['statut', 'status', 'correction', 'rectificatif', 'annulation', 'berichtigung', 'stornierung', 'amendment'],
      planned: ['planifie', 'operation planifiee', 'planned', 'programmed', 'plan', 'mandat'],
      holding: ['detention', 'direct indirect', 'holding type', 'direct or indirect'],
      stakeAfter: ['participation apres', 'detention apres', 'holding after', 'stake after', 'shares held after', 'post transaction holding']
    },
    price: {
      ticker: ['code', 'ticker', 'symbol'], isin: ['isin'], date: ['date', 'datum', 'trade date'],
      open: ['open', 'ouverture'], high: ['high', 'plus haut', 'haut'], low: ['low', 'plus bas', 'bas'],
      close: ['close', 'cloture', 'dernier'], volume: ['volume', 'titres echanges', 'volume titres'],
      adjClose: ['adjusted close', 'adjusted_close', 'adj close']
    },
    instrument: {
      isin: ['isin'], name: ['nom', 'name', 'societe', 'company'], ticker: ['ticker', 'code', 'symbol'],
      venue: ['place', 'place de cotation', 'exchange', 'venue', 'marche'], mic: ['mic'],
      currency: ['devise', 'currency'], country: ['pays de domiciliation', 'domicile', 'country', 'pays'],
      sector: ['secteur', 'sector', 'industry'], shareType: ['type de titre', 'share type', 'type', 'security type'],
      reference: ['cotation de reference', 'reference', 'primary', 'is primary'],
      peaStatus: ['pea', 'statut pea', 'eligible pea', 'pea status'], peaSource: ['source pea', 'pea source'], peaDate: ['date pea', 'pea date']
    },
    buyback: {
      isin: ['isin'], stage: ['etape', 'stage', 'type', 'statut'], date: ['date', 'date de publication'],
      amount: ['montant', 'amount'], pctCapital: ['pourcentage du capital', 'capital', 'pct capital', '% capital'],
      sourceUrl: ['lien', 'url', 'source'], confirmed: ['confirme', 'confirmed', 'officiel'], note: ['modalites', 'note', 'commentaire']
    },
    results: {
      isin: ['isin'], pubDate: ['date de publication', 'date', 'publication date'], period: ['periode', 'period'],
      epsActual: ['bpa publie', 'bpa', 'eps actual', 'eps'], epsConsensus: ['bpa consensus', 'eps consensus', 'eps estimate'],
      revActual: ['ca publie', 'chiffre d affaires', 'revenue actual', 'revenue'], revConsensus: ['ca consensus', 'revenue consensus', 'revenue estimate'],
      consensusDate: ['date du consensus', 'consensus date'], guidance: ['perspectives', 'guidance', 'outlook'],
      comparable: ['comparable', 'comparabilite', 'valide'], currency: ['devise', 'currency'], sourceUrl: ['lien', 'url', 'source']
    },
    split: { isin: ['isin'], date: ['date', 'date d effet'], ratio: ['ratio', 'parite', 'facteur'], from: ['old', 'avant', 'de'], to: ['new', 'apres', 'a'] }
  };
  /** En-têtes volontairement ambigus : jamais mappés automatiquement. */
  ES.AMBIGUOUS_HEADERS = { volume: 'quantité ou montant ?', 'volume eur': 'montant en euros ?', 'aggregated volume': 'quantité ou montant ?' };

  ES.autoMap = function (kind, headers) {
    var fields = ES.FIELDS[kind], map = {}, used = {}, warnings = [];
    var nh = headers.map(function (h) { return { raw: h, n: ES.norm(h) }; });
    nh.forEach(function (h) { if (kind === 'tx' && ES.AMBIGUOUS_HEADERS[h.n]) warnings.push('Colonne « ' + h.raw + ' » ambiguë (' + ES.AMBIGUOUS_HEADERS[h.n] + ') : indiquez-la vous-même.'); });
    // 1) correspondances exactes, 2) correspondances partielles (le synonyme est contenu dans l'en-tête).
    [true, false].forEach(function (exact) {
      Object.keys(fields).forEach(function (f) {
        if (map[f]) return;
        var syn = fields[f];
        for (var i = 0; i < nh.length; i++) {
          var h = nh[i];
          if (used[h.raw] || (kind === 'tx' && ES.AMBIGUOUS_HEADERS[h.n])) continue;
          var ok = syn.some(function (s) {
            if (exact) return h.n === s;
            if (s.length < 4) return false;
            return (' ' + h.n + ' ').indexOf(' ' + s + ' ') > -1;
          });
          if (ok) { map[f] = h.raw; used[h.raw] = 1; break; }
        }
      });
    });
    return { map: map, warnings: warnings };
  };

  /* ===================== Classification des opérations ===================== */
  ES.TX_TYPES = {
    achat: 'Achat', vente: 'Vente', attribution: 'Attribution gratuite', option: "Exercice d'options",
    souscription: 'Souscription', transfert: 'Transfert', don: 'Don / succession', nantissement: 'Nantissement / prêt',
    dividende: 'Dividende en actions', instrument: 'Autre instrument (FCPE, options, dette…)', autre_nv: 'Autre opération (non comptée)',
    autre: 'Autre (nature ambiguë)', inconnu: 'Type non déterminé'
  };
  var TYPE_RULES = [
    ['attribution', /(attribution gratuite|actions? gratuites?|actions? de performance|performance share|free share|grant|award|vesting|acquisition definitive|zuteilung|assegnazione gratuita|entrega gratuita|toekenning)/],
    ['option', /(exercice|exercise|option|ausubung|ausuebung|esercizio|ejercicio|warrant|bsa|stock option)/],
    ['souscription', /(souscription|subscription|zeichnung|sottoscrizione|suscripcion|inschrijving|augmentation de capital|capital increase|kapitalerhohung|ampliacion)/],
    ['nantissement', /(nantissement|pledge|verpfandung|pegno|prenda|pret de titres|securities lending)/],
    ['don', /(\bdon\b|donation|gift|schenkung|erbschaft|succession|heritage|inheritance|donazione|herencia)/],
    ['transfert', /(transfert|transfer|ubertragung|uebertragung|trasferimento|traspaso|apport)/],
    ['vente', /(cession|vente|verkauf|\bsale\b|\bsell\b|\bsold\b|disposal|vendita|venta|verkoop|^s$|^v$)/],
    ['achat', /(acquisition|achat|\bkauf\b|purchase|\bbuy\b|\bbought\b|acquisto|compra|aankoop|^p$|^a$|^k$)/]
  ];
  ES.classifyType = function (text) {
    var t = ES.norm(text);
    if (!t) return 'inconnu';
    for (var i = 0; i < TYPE_RULES.length; i++) if (TYPE_RULES[i][1].test(t)) return TYPE_RULES[i][0];
    return 'autre';
  };
  ES.classifyRole = function (text) {
    var t = ES.norm(text);
    var r = { ceo: false, cfo: false, board: false, associated: false, label: text || '' };
    if (/(directeur general|president directeur|\bpdg\b|\bceo\b|chief executive|vorstandsvorsitz|vorsitzender des vorstands|amministratore delegato|consejero delegado|ceo|managing director|algemeen directeur|chief exec)/.test(t)) r.ceo = true;
    if (/(directeur financier|\bdaf\b|\bcfo\b|chief financial|finanzvorstand|finanzchef|direttore finanziario|director financiero|financieel directeur)/.test(t)) r.cfo = true;
    // fonctions qui ne sont pas celles du DG ou du DAF de l'émetteur lui-même
    if (/(filiale|subsidiary|adjoint|division|deputy|head of|des fonctions|en charge|business unit)/.test(t)) { r.ceo = false; r.cfo = false; }
    if (/(administrateur|conseil|board|aufsichtsrat|vorstand|consigliere|consejero|bestuurder|commissaris|director)/.test(t)) r.board = true;
    if (/(personne liee|etroitement liee|closely associated|eng verbundene|strettamente legat|estrechamente vinculad|nauw gelieerd|\bpca\b|personne morale liee|related person|related party)/.test(t)) r.associated = true;
    return r;
  };
  function statusFrom(text) {
    var t = ES.norm(text);
    if (!t) return 'active';
    if (/(annul|storn|cancel|revoc|withdraw|ritir)/.test(t)) return 'annulee';
    if (/(correct|rectif|berichtig|amend|rettific|modif)/.test(t)) return 'corrigee';
    return 'active';
  }
  function boolFrom(text) {
    var t = ES.norm(text);
    if (!t) return null;
    if (/^(oui|yes|ja|si|true|1|vrai|x)$/.test(t)) return true;
    if (/^(non|no|nein|false|0|faux)$/.test(t)) return false;
    return null;
  }

  /* ================== Normalisation d'une déclaration ================== */
  /** opts: { map, registry, country, today, locale, defaultCurrency } → { ok, rec, errors, warnings } */
  ES.normalizeTx = function (row, opts) {
    var m = opts.map, g = function (f) { return m[f] ? row[m[f]] : undefined; };
    var errors = [], warnings = [], loc = opts.locale || 'auto';
    var isin = String(g('isin') || '').trim().toUpperCase().replace(/\s/g, '');
    if (!isin) errors.push('ISIN absent');
    else if (!ES.isValidIsin(isin)) errors.push('ISIN invalide (' + isin + ')');
    var txDate = ES.parseDate(g('txDate'));
    if (!txDate) errors.push('date de transaction absente ou illisible');
    else if (txDate > opts.today) errors.push('date de transaction dans le futur (' + txDate + ')');
    var pub = g('pubDate') != null && g('pubDate') !== '' ? ES.parseDateTime(g('pubDate')) : null;
    if (g('pubDate') && !pub) errors.push('date de publication illisible');
    if (pub && pub.date > opts.today) errors.push('date de publication dans le futur (' + pub.date + ')');
    if (pub && txDate && pub.date < txDate) errors.push('publication antérieure à la transaction');
    if (!pub) warnings.push('date de publication inconnue : la disponibilité de l\'information n\'est pas datée');

    function num(f, label, positive) {
      var raw = g(f);
      if (raw == null || String(raw).trim() === '') return null;
      var n = ES.parseNumber(raw, loc);
      if (n == null) { errors.push(label + ' illisible (« ' + raw + ' »)'); return null; }
      if (positive && n <= 0) { errors.push(label + ' négatif ou nul'); return null; }
      return n;
    }
    var qty = num('qty', 'quantité', true), price = num('price', 'prix', true), amount = num('amount', 'montant', true);
    var amountComputed = false;
    if (amount == null && qty != null && price != null) { amount = qty * price; amountComputed = true; }
    if (qty == null) warnings.push(amount != null ? 'quantité non publiée (non déduite du montant)' : 'quantité et montant inconnus');
    if (price == null) warnings.push('prix inconnu');
    var currency = String(g('currency') || opts.defaultCurrency || '').trim().toUpperCase() || null;
    if (!currency) warnings.push('devise inconnue');
    var natureText = g('nature') || '';
    var type = ES.classifyType(natureText);
    if (type === 'inconnu' || type === 'autre') warnings.push('nature de l\'opération ambiguë (« ' + natureText + ' »)');
    var person = String(g('person') || '').trim();
    if (!person) warnings.push('nom du déclarant absent');
    var role = ES.classifyRole(g('role'));
    var assocFlag = boolFrom(g('associated'));
    var associated = assocFlag === true || role.associated;
    var linkedTo = String(g('linkedTo') || '').trim() || null;
    if (associated && !linkedTo) warnings.push('personne liée sans dirigeant de rattachement : non comptée comme acheteur indépendant');
    var status = statusFrom(g('status'));
    var regId = String(g('registryId') || '').trim();
    var version = ES.parseNumber(g('version')) || 1;
    var rec = {
      isin: isin, issuer: String(g('issuer') || '').trim() || null, ticker: String(g('ticker') || '').trim() || null,
      registry: opts.registry, registryCountry: opts.country || null,
      person: person || null, role: role.label || null, ceo: role.ceo, cfo: role.cfo, board: role.board,
      associated: associated, linkedTo: linkedTo,
      type: type, natureText: natureText || null,
      txDate: txDate, pubDate: pub ? pub.date : null, pubTime: pub ? pub.time : null, pubPrecision: pub ? pub.precision : 'inconnue',
      qty: qty, price: price, currency: currency, amount: amount, amountComputed: amountComputed,
      venue: String(g('venue') || '').trim() || null, sourceUrl: String(g('sourceUrl') || '').trim() || null,
      registryId: regId || null, version: version, status: status,
      planned: boolFrom(g('planned')), holding: String(g('holding') || '').trim() || null,
      stakeAfter: g('stakeAfter') ? ES.parseNumber(g('stakeAfter'), loc) : null
    };
    rec.personKey = ES.personKey(person);
    rec.dedupKey = ES.dedupKey(rec);
    rec.id = regId ? ES.safeId(opts.registry + ':' + regId) : 'h' + ES.hash(rec.dedupKey + '|' + opts.registry);
    return { ok: errors.length === 0, rec: rec, errors: errors, warnings: warnings };
  };
  ES.dedupKey = function (r) {
    var size = r.qty != null ? 'q' + Math.round(r.qty) : r.amount != null ? 'm' + Math.round(r.amount) : '?';
    return [r.isin, r.txDate, r.personKey, r.type, r.price != null ? r.price.toFixed(2) : '?', size].join('|');
  };
  ES.OFFICIAL = { AMF: 1, BaFin: 1, FSMA: 1, AFM: 1, CNMV: 1, CONSOB: 1, 'Émetteur': 1 };

  /** Fusionne de nouvelles déclarations avec l'existant (même ISIN ou non). Ne perd jamais l'historique. */
  ES.mergeTransactions = function (existing, incoming, nowIso) {
    var byId = {}, byKey = {}, out = existing.map(function (r) { return Object.assign({}, r); });
    var looseKey = function (r) { return [r.isin, r.txDate, r.type, r.price != null ? r.price.toFixed(2) : '?', r.qty != null ? 'q' + Math.round(r.qty) : r.amount != null ? 'm' + Math.round(r.amount) : '?'].join('|'); };
    var corrKey = function (r) { return [r.registry, r.isin, r.personKey, r.txDate, r.type].join('|'); };
    var byLoose = {}, byCorr = {};
    out.forEach(function (r, i) { byId[r.id] = i; if (r.status !== 'remplacee') { byKey[r.dedupKey] = i; byLoose[looseKey(r)] = i; byCorr[corrKey(r)] = i; } });
    var stats = { added: 0, duplicates: 0, corrected: 0, cancelled: 0, crossSource: 0 };
    incoming.forEach(function (inc) {
      inc = Object.assign({}, inc);
      var i = byId[inc.id];
      if (i != null) {
        var cur = out[i];
        var incSt = inc.status === 'corrigee' ? 'active' : inc.status;
        var changed = inc.qty !== cur.qty || inc.price !== cur.price || inc.txDate !== cur.txDate || inc.type !== cur.type || inc.amount !== cur.amount;
        var newer = inc.version > cur.version || incSt !== cur.status || (inc.status === 'corrigee' && (!cur.corrected || changed)) || inc.type !== cur.type;
        if (cur.status === 'annulee' && incSt === 'active' && !(inc.version > cur.version)) newer = false; // une annulation n'est pas défaite par la republication de l'original
        if (!newer) { stats.duplicates++; return; }
        inc.firstSeen = cur.firstSeen; inc.history = (cur.history || []).concat([{ version: cur.version, status: cur.status, replacedOn: nowIso, snapshot: { qty: cur.qty, price: cur.price, amount: cur.amount, txDate: cur.txDate, type: cur.type } }]).slice(-5);
        inc.alsoSeenIn = cur.alsoSeenIn || [];
        if (inc.status === 'annulee') stats.cancelled++; else stats.corrected++;
        if (inc.status === 'corrigee') inc.status = 'active', inc.corrected = true;
        out[i] = inc;
        return;
      }
      // correction publiée sous un nouvel identifiant : remplace la déclaration d'origine
      var ck = inc.status === 'corrigee' ? byCorr[corrKey(inc)] : null;
      if (ck != null && out[ck].status === 'active' && out[ck].id !== inc.id) {
        var orig = out[ck];
        if (orig.qty === inc.qty && orig.price === inc.price && orig.amount === inc.amount) { stats.duplicates++; byId[inc.id] = ck; return; }
        inc.firstSeen = orig.firstSeen; inc.status = 'active'; inc.corrected = true; inc.replaces = orig.id;
        inc.history = (orig.history || []).concat([{ version: orig.version, status: orig.status, replacedOn: nowIso, snapshot: { qty: orig.qty, price: orig.price, amount: orig.amount, txDate: orig.txDate, type: orig.type } }]).slice(-5);
        out[ck] = inc; byId[inc.id] = ck; byKey[inc.dedupKey] = ck; stats.corrected++;
        return;
      }
      var k = byKey[inc.dedupKey];
      if (k == null) { var lk = byLoose[looseKey(inc)]; if (lk != null && out[lk].registry !== inc.registry) k = lk; } // même opération déclarée dans deux registres, nom différent (dirigeant / sa société)
      if (k != null) {
        var ex = out[k];
        if (ex.registry === inc.registry) { stats.duplicates++; return; }
        stats.crossSource++;
        if (!ES.OFFICIAL[ex.registry] && ES.OFFICIAL[inc.registry]) { // la source officielle prend le dessus
          inc.firstSeen = ex.firstSeen; inc.alsoSeenIn = (ex.alsoSeenIn || []).concat([{ registry: ex.registry, id: ex.id, sourceUrl: ex.sourceUrl }]);
          out[k] = inc; byId[inc.id] = k;
        } else {
          ex.alsoSeenIn = (ex.alsoSeenIn || []).concat([{ registry: inc.registry, id: inc.id, sourceUrl: inc.sourceUrl }]);
          if (inc.firstSeen && (!ex.firstSeen || inc.firstSeen < ex.firstSeen)) ex.firstSeen = inc.firstSeen;
        }
        return;
      }
      inc.firstSeen = inc.firstSeen || nowIso;
      if (inc.status === 'corrigee') { inc.status = 'active'; inc.corrected = true; }
      out.push(inc); byId[inc.id] = out.length - 1; byKey[inc.dedupKey] = out.length - 1; byLoose[looseKey(inc)] = out.length - 1; byCorr[corrKey(inc)] = out.length - 1; stats.added++;
    });
    return { list: out, stats: stats };
  };

  /* ===================== Séries de cours et splits ===================== */
  /** rows : [[date, open, high, low, close, volume], ...] cours bruts non ajustés.
   *  splits : [{date, ratio}] ; ratio = nombre de nouvelles actions pour une ancienne (division par 2 → 2). */
  ES.normalizeSeries = function (rows) {
    var seen = {}, out = [];
    rows.forEach(function (r) {
      if (!r || !r[0] || typeof r[4] !== 'number' || !isFinite(r[4]) || !(r[4] > 0)) return;
      for (var k = 1; k < 6; k++) if (r[k] != null && (typeof r[k] !== 'number' || !isFinite(r[k]))) { r = r.slice(); r[k] = null; }
      if (seen[r[0]] != null) { out[seen[r[0]]] = r; return; } // dernière valeur gagne (pagination répétée)
      seen[r[0]] = out.length; out.push(r);
    });
    out.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; });
    return out;
  };
  /** Facteur qui ramène un prix brut de la date d au même nombre d'actions qu'aujourd'hui. */
  ES.splitFactor = function (splits, d) {
    var f = 1;
    (splits || []).forEach(function (s) { if (s && s.date > d && typeof s.ratio === 'number' && isFinite(s.ratio) && s.ratio > 0 && s.ratio < 1e4) f *= s.ratio; });
    return f;
  };
  /**
   * Dividendes → facteurs d'ajustement, traités comme des divisions : cours d'avant le détachement × (1 − D / clôture veille).
   * rows bruts [[date, o, h, l, c, v]], dividends [{ date, amount }] → [{ date, ratio, dividend: true }].
   */
  ES.dividendSplits = function (rows, dividends) {
    var out = [];
    (Array.isArray(dividends) ? dividends : []).forEach(function (dv) {
      var amt = dv && +dv.amount, d = dv && dv.date;
      if (!(amt > 0) || typeof d !== 'string') return;
      var prev = null;
      for (var k = 0; k < rows.length; k++) { if (rows[k] && rows[k][0] < d && rows[k][4] > 0) prev = rows[k][4]; else if (rows[k] && rows[k][0] >= d) break; }
      if (!prev || amt >= prev * 0.9) return; // incohérent : ignoré
      out.push({ date: d, ratio: prev / (prev - amt), dividend: true, amount: amt });
    });
    return out;
  };
  ES.adjustedSeries = function (rows, splits) {
    return rows.map(function (r) {
      var f = ES.splitFactor(splits, r[0]);
      return [r[0], r[1] != null ? r[1] / f : null, r[2] != null ? r[2] / f : null, r[3] != null ? r[3] / f : null, r[4] / f, r[5] != null ? r[5] * f : null];
    });
  };
  function mean(a) { return a.length ? a.reduce(function (s, x) { return s + x; }, 0) / a.length : null; }
  function sma(closes, n) { return closes.length >= n ? mean(closes.slice(-n)) : null; }
  function rsi(closes, n) {
    if (closes.length < n + 1) return null;
    var g = 0, l = 0;
    for (var i = closes.length - n; i < closes.length; i++) { var d = closes[i] - closes[i - 1]; if (d > 0) g += d; else l -= d; }
    if (l === 0) return 100;
    return 100 - 100 / (1 + g / l);
  }
  /** Extrêmes sur une fenêtre ; utilise les plus hauts/bas intrajournaliers s'ils existent pour toutes les lignes. */
  ES.extremes = function (adj, fromDate, toDate) {
    var sub = adj.filter(function (r) { return (!fromDate || r[0] >= fromDate) && r[0] <= toDate; });
    if (!sub.length) return null;
    var intraday = sub.every(function (r) { return r[2] != null && r[3] != null && r[2] >= r[3]; });
    var hi = -Infinity, lo = Infinity, hiD, loD;
    sub.forEach(function (r) {
      var h = intraday ? r[2] : r[4], l = intraday ? r[3] : r[4];
      if (h > hi) { hi = h; hiD = r[0]; }
      if (l < lo) { lo = l; loD = r[0]; }
    });
    return { high: hi, low: lo, highDate: hiD, lowDate: loD, basis: intraday ? 'intrajournalier' : 'clôtures', from: sub[0][0], to: sub[sub.length - 1][0], sessions: sub.length };
  };
  ES.rangePosition = function (p, ex) {
    if (!ex || p == null || !(ex.high > ex.low)) return null;
    return (p - ex.low) / (ex.high - ex.low) * 100;
  };

  /** Statistiques d'admissibilité et de marché, calculées à l'import et stockées avec l'instrument. */
  ES.computeStats = function (rawRows, splits, today, cfg, currency) {
    var rows = ES.normalizeSeries(rawRows || []);
    var u = cfg.universe;
    if (!rows.length) return { sessions: 0, empty: true };
    var adj = ES.adjustedSeries(rows, splits);
    var closes = adj.map(function (r) { return r[4]; });
    var last = rows[rows.length - 1];
    var s = { sessions: rows.length, firstDate: rows[0][0], lastDate: last[0], lastClose: last[4], currency: currency || null };
    s.staleBusinessDays = ES.businessDaysBetween(last[0], today);
    var l20 = rows.slice(-20).filter(function (r) { return r[5] != null; });
    s.adv20 = l20.length >= 10 ? mean(l20.map(function (r) { return r[4] * r[5]; })) : null;
    if (s.adv20 != null && !isFinite(s.adv20)) s.adv20 = null;
    s.adv20Eur = currency === 'EUR' ? s.adv20 : null;
    // anomalies : variations quotidiennes extrêmes (sur cours ajustés), éventuels splits non déclarés
    var anomalies = [], recent = adj.slice(-261);
    for (var i = 1; i < recent.length; i++) {
      var ch = (recent[i][4] / recent[i - 1][4] - 1) * 100;
      if (Math.abs(ch) >= u.maxDailyMovePct) {
        var inv = recent[i - 1][4] / recent[i][4], near = [2, 3, 4, 5, 10, 0.5, 1 / 3, 0.25, 0.2, 0.1].some(function (k) { return Math.abs(inv - k) / k < 0.04; });
        anomalies.push({ date: recent[i][0], changePct: ch, possibleSplit: near });
      }
    }
    s.anomalies = anomalies.slice(-5);
    var zeroStreak = 0, maxZero = 0;
    rows.slice(-20).forEach(function (r) { if (r[5] === 0) { zeroStreak++; maxZero = Math.max(maxZero, zeroStreak); } else zeroStreak = 0; });
    s.zeroVolumeStreak = maxZero;
    var rets = [];
    for (var j = Math.max(1, closes.length - 60); j < closes.length; j++) rets.push(Math.log(closes[j] / closes[j - 1]));
    var mu = mean(rets);
    s.volAnnPct = rets.length >= 20 ? Math.sqrt(rets.reduce(function (a, x) { return a + (x - mu) * (x - mu); }, 0) / (rets.length - 1)) * Math.sqrt(252) * 100 : null;
    s.sma50 = sma(closes, 50); s.sma200 = sma(closes, 200);
    // Dernier croisement MM50 / MM200 (moyennes glissantes calculées en une passe)
    s.goldenCrossDate = null; s.deathCrossDate = null;
    if (closes.length >= 201) {
      var s50 = 0, s200 = 0, prev = null;
      for (var q = 0; q < closes.length; q++) {
        s50 += closes[q]; s200 += closes[q];
        if (q >= 50) s50 -= closes[q - 50];
        if (q >= 200) s200 -= closes[q - 200];
        if (q < 199) continue;
        var above = s50 / 50 > s200 / 200;
        if (prev !== null && above !== prev) { if (above) s.goldenCrossDate = adj[q][0]; else s.deathCrossDate = adj[q][0]; }
        prev = above;
      }
    }
    var c = closes[closes.length - 1];
    s.ret1m = closes.length > 21 ? (c / closes[closes.length - 22] - 1) * 100 : null;
    s.ret3m = closes.length > 63 ? (c / closes[closes.length - 64] - 1) * 100 : null;
    // 6 mois hors dernier mois (mesure classique du momentum, moins sensible aux retournements de court terme)
    s.ret6m1 = closes.length > 127 ? (closes[closes.length - 22] / closes[closes.length - 127] - 1) * 100 : null;
    s.rsi14 = rsi(closes, 14);
    s.distSma50 = s.sma50 ? (c / s.sma50 - 1) * 100 : null;
    var vols = adj.map(function (r) { return r[5]; }).filter(function (v) { return v != null; });
    var v60 = vols.length >= 60 ? mean(vols.slice(-60)) : null, v5 = vols.length >= 5 ? mean(vols.slice(-5)) : null;
    s.volRatio5_60 = v60 ? v5 / v60 : null;
    s.upVolumeSpike = false;
    if (v60) for (var k = Math.max(1, adj.length - 5); k < adj.length; k++) if (adj[k][5] > 3 * v60 && adj[k][4] > adj[k - 1][4]) s.upVolumeSpike = true;
    s.ex52 = ES.extremes(adj, ES.addDays(last[0], -365), last[0]);
    s.exAll = ES.extremes(adj, null, last[0]);
    s.lastCloseAdj = c;
    return s;
  };

  /** Comparaisons d'un achat d'initié au cours (sur base ajustée des splits). */
  ES.priceRefs = function (tx, rawRows, splits, today, seriesCurrency) {
    var rows = ES.normalizeSeries(rawRows || []);
    var res = { available: false, notes: [] };
    if (!rows.length) { res.notes.push('aucun historique de cours importé'); return res; }
    if (tx.price == null || typeof tx.price !== 'number' || !isFinite(tx.price) || tx.price <= 0) { res.notes.push('prix payé inconnu'); return res; }
    var unit = 1, tc = String(tx.currency || '').trim().toUpperCase(), sc = String(seriesCurrency || '').trim();
    var minor = { GBp: 'GBP', GBX: 'GBP', ZAc: 'ZAR', ZAC: 'ZAR', ILA: 'ILS' }[sc]; // cotations en centimes / pence
    if (tc && sc && String(tx.currency).trim() !== sc) {
      if (minor) { if (tc === minor) unit = 100; else if (tc !== sc.toUpperCase()) { res.notes.push('devise du prix payé (' + tc + ') différente de la cotation suivie (' + sc + ') : comparaison impossible'); res.currencyMismatch = true; return res; } }
      else if (tc !== sc.toUpperCase()) { res.notes.push('devise du prix payé (' + tc + ') différente de la cotation suivie (' + sc + ') : comparaison impossible'); res.currencyMismatch = true; return res; }
    }
    var adj = ES.adjustedSeries(rows, splits);
    var f = ES.splitFactor(splits, tx.txDate);
    var paid = tx.price * unit / f;
    res.available = true;
    res.paidAdj = paid; res.splitFactor = f;
    if (f !== 1) res.notes.push('prix payé ajusté des opérations sur titres postérieures (facteur ' + f + ')');
    var last = adj[adj.length - 1];
    res.lastDate = last[0]; res.lastClose = last[4];
    res.currentVsPaidPct = (last[4] / paid - 1) * 100;
    // références connues à la date de l'achat (aucune donnée postérieure)
    if (rows[0][0] > tx.txDate) {
      res.atPurchase = null; res.notes.push('historique commençant après l\'achat : références à la date d\'achat indisponibles');
    } else {
      var ex52 = ES.extremes(adj, ES.addDays(tx.txDate, -365), tx.txDate), exAll = ES.extremes(adj, null, tx.txDate);
      res.atPurchase = {
        ex52: ex52, exAll: exAll,
        full52: ex52 && ex52.from <= ES.addDays(tx.txDate, -358),
        paidVsHigh52Pct: ex52 ? (paid / ex52.high - 1) * 100 : null, paidVsLow52Pct: ex52 ? (paid / ex52.low - 1) * 100 : null,
        paidPos52: ES.rangePosition(paid, ex52),
        paidVsHighAllPct: exAll ? (paid / exAll.high - 1) * 100 : null, paidVsLowAllPct: exAll ? (paid / exAll.low - 1) * 100 : null,
        paidPosAll: ES.rangePosition(paid, exAll)
      };
      // Psychologie du marché au moment de l'achat : chute récente et survente (RSI 14)
      var upto = adj.filter(function (r) { return r[0] <= tx.txDate; }).map(function (r) { return r[4]; });
      if (upto.length > 11) { var mx = Math.max.apply(null, upto.slice(-11)); res.atPurchase.drop10 = (upto[upto.length - 1] / mx - 1) * 100; }
      res.atPurchase.rsi14 = rsi(upto, 14);
      if (ex52 && !res.atPurchase.full52) res.notes.push('fenêtre 52 semaines incomplète à la date d\'achat (début ' + ex52.from + ')');
      var day = ES.extremes(adj, tx.txDate, tx.txDate);
      if (day) { res.dayLow = day.low; res.dayHigh = day.high; }
      if (day && (paid > day.high * 1.02 || paid < day.low * 0.98)) { res.outOfRange = true; if (paid < day.low * 0.8) res.belowMarket = true; if (paid > day.high * 3) { res.belowMarket = true; res.priceSuspect = true; res.notes.push('prix déclaré plus de 3 fois supérieur au cours du jour : déclaration probablement mal saisie (virgule, unité), ignorée dans les calculs'); } res.notes.push('prix payé hors de la fourchette du jour (' + day.low.toFixed(2) + '–' + day.high.toFixed(2) + ') : vérifier la déclaration ou une opération sur titres'); }
    }
    var t52 = ES.extremes(adj, ES.addDays(last[0], -365), last[0]), tAll = ES.extremes(adj, null, last[0]);
    res.today = {
      ex52: t52, exAll: tAll,
      paidVsHigh52Pct: t52 ? (paid / t52.high - 1) * 100 : null, paidVsLow52Pct: t52 ? (paid / t52.low - 1) * 100 : null,
      paidPos52: ES.rangePosition(paid, t52), currentPos52: ES.rangePosition(last[4], t52),
      paidPosAll: ES.rangePosition(paid, tAll), currentPosAll: ES.rangePosition(last[4], tAll)
    };
    if (ES.businessDaysBetween(last[0], today) > 3) res.notes.push('dernier cours daté du ' + last[0] + ' : comparaison possiblement périmée');
    return res;
  };

  /* ============================ Configuration ============================ */
  ES.DEFAULT_CONFIG = {
    scoringVersion: '2.3.0',
    universe: { minAdv20Eur: 1000000, minSessions: 200, maxStaleBusinessDays: 3, maxDailyMovePct: 40, suspensionZeroVolumeDays: 5, maxAnnualVolPct: 120, requireOrdinaryShares: true, requireReferenceListing: true },
    insiders: { windowMonths: 3, clusterMinBuyers: 3, clusterWindowDays: 14, bigAmountEur: 500000, nearLowPct: 25, excludePlanned: true, excludeLegalEntities: true, fallingKnifeNote: true, maxFilingLagDays: 30, minBuyerEur: 100000 },
    pea: { strict: true },
    sources: { maxRegistryAgeDays: 7, registryByCountry: { FR: 'AMF', DE: 'BaFin', BE: 'FSMA', NL: 'AFM', ES: 'CNMV', IT: 'CONSOB' }, acceptAggregatorsAsCoverage: true },
    weights: {
      insiders: { cap: 40, floor: -10, anyBuy: 10, amountBig: 10, cluster: 12, pair: 5, coordinatedCluster: -6, ceoCfo: 6, repeat: 4, discountBig: 5, discountBigPct: 40, discountMedium: 3, discountMediumPct: 25, panicBuy: 2, panicDropPct: 15, panicRsi: 30, netSeller: -10, ceoCfoSale: -5 },
      buyback: { cap: 15, floor: -5, announced: 8, executing: 4, largeSize: 3, largeSizePct: 2, suspended: -5 },
      results: { cap: 25, floor: -10, epsStrong: 8, epsMild: 4, epsStrongPct: 5, epsMildPct: 2, epsMiss: -6, revStrong: 7, revMild: 3, revStrongPct: 2, revMildPct: 0, guidanceRaised: 10, guidanceLowered: -10 },
      market: { cap: 20, floor: 0, trend: 6, volume: 6, volumeRatio: 1.5, liquidity: 4, liquidityEur: 5000000, goldenCrossAfterBuy: 4, relStrength: 4, relStrengthPts: 10, relWeakPts: 20 }
    },
    quality: { minForAlert: 60 },
    display: { scoreCeiling: 60 },
    valuation: { cheapPct: 20, richPct: 30 },
    accounts: { fscoreGood: 7, fscoreBad: 3 }, // F-score de Piotroski : 7 à 9 = comptes solides, 0 à 3 = comptes en dégradation // décote / prime de valorisation par rapport aux pairs jugée nette // note /100 affichée : 100 = maximum réaliste (initiés + marché au plafond = 60 points bruts)
    overheat: { rsiHigh: 75, rsiExtreme: 82, distSma50Pct: 20, ret1mPct: 25, blockAlertsAbove: null },
    alerts: { minScore: 45, minFamilies: 2, recentEventDays: 14, mode: 'simulation', recipient: '', enabled: false, blockFragile: true, earningsWarnDays: 21, buyEmails: true },
    selection: { enabled: true, size: 5, minScore: 30, recentDays: 30, weekday: 1, peaOnly: true },
    exits: { enabled: true, followDays: 365, belowInsiderPricePct: 10, drawdownFromPeakPct: 20 },
    learning: { mode: 'auto', minCases: 60, minT: 2, maxStep: 1, horizon: 60 },
    backtest: { costRoundTripPct: 0.5, horizons: [20, 60], oosStart: '' }
  };
  ES.mergeConfig = function (base, over) {
    var out = JSON.parse(JSON.stringify(base));
    (function rec(a, b) {
      Object.keys(b || {}).forEach(function (k) {
        if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object') rec(a[k], b[k]);
        else a[k] = b[k];
      });
    })(out, over);
    return out;
  };
  ES.validateConfig = function (c) {
    var e = [];
    function pos(v, n) { if (!(typeof v === 'number' && v >= 0)) e.push(n + ' doit être un nombre positif'); }
    pos(c.universe.minAdv20Eur, 'universe.minAdv20Eur'); pos(c.universe.minSessions, 'universe.minSessions');
    pos(c.insiders.clusterMinBuyers, 'insiders.clusterMinBuyers'); pos(c.insiders.clusterWindowDays, 'insiders.clusterWindowDays');
    if (!(c.insiders.windowMonths >= 1 && c.insiders.windowMonths <= 24)) e.push('insiders.windowMonths entre 1 et 24');
    if (!(c.alerts.minScore >= 0 && c.alerts.minScore <= 100)) e.push('alerts.minScore entre 0 et 100');
    if (['simulation', 'brouillon', 'envoi'].indexOf(c.alerts.mode) < 0) e.push('alerts.mode : simulation, brouillon ou envoi');
    if (c.alerts.recipient && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.alerts.recipient)) e.push('alerts.recipient : adresse email invalide');
    var caps = ['insiders', 'buyback', 'results', 'market'].reduce(function (s, k) { return s + (c.weights[k].cap || 0); }, 0);
    if (caps !== 100) e.push('la somme des plafonds des familles vaut ' + caps + ' au lieu de 100');
    if (!c.scoringVersion) e.push('scoringVersion obligatoire');
    return e;
  };

  /* ============================== Univers ============================== */
  /** Statut : 'retenu' | 'rejete' | 'a_examiner' avec motifs. */
  ES.universeStatus = function (inst, cfg) {
    var u = cfg.universe, s = inst.stats || { sessions: 0, empty: true }, rej = [], exam = [], warn = [];
    if (u.requireOrdinaryShares && inst.shareType && !/ordinaire|ordinary|common|stamm|ordinari|ordinaria|gewone/i.test(inst.shareType)) rej.push('type de titre : ' + inst.shareType);
    if (u.requireOrdinaryShares && !inst.shareType) exam.push('type de titre non renseigné (action ordinaire ?)');
    if (u.requireReferenceListing && inst.isReference === false) rej.push('cotation secondaire (une autre cotation fait référence)');
    if (s.empty || !s.sessions) exam.push('aucun cours importé');
    else {
      if (s.sessions < u.minSessions) exam.push('historique insuffisant : ' + s.sessions + ' séances < ' + u.minSessions + ' (cotation récente ou import partiel ?)');
      if (s.staleBusinessDays > u.maxStaleBusinessDays) exam.push('cours périmé : dernier cours le ' + s.lastDate + ' (' + s.staleBusinessDays + ' jours ouvrés)');
      if (s.adv20Eur == null) exam.push(s.currency && s.currency !== 'EUR' ? 'devise ' + s.currency + ' : liquidité en euros non calculée' : 'liquidité moyenne sur 20 séances incalculable');
      else if (s.adv20Eur < u.minAdv20Eur) rej.push('liquidité ' + fmtEur(s.adv20Eur) + '/jour < ' + fmtEur(u.minAdv20Eur));
      if (s.zeroVolumeStreak >= u.suspensionZeroVolumeDays) exam.push('suspension possible : ' + s.zeroVolumeStreak + ' séances sans volume');
      if (s.anomalies && s.anomalies.length) exam.push('variation anormale le ' + s.anomalies[s.anomalies.length - 1].date + (s.anomalies[s.anomalies.length - 1].possibleSplit ? ' (split non déclaré ?)' : ''));
      if (s.volAnnPct != null && s.volAnnPct > u.maxAnnualVolPct) exam.push('volatilité annualisée ' + Math.round(s.volAnnPct) + ' % > ' + u.maxAnnualVolPct + ' %');
    }
    var status = rej.length ? 'rejete' : exam.length ? 'a_examiner' : 'retenu';
    return { status: status, reasons: rej.concat(exam), warnings: warn };
  };
  /** « 2026-08-06 » → « 06/08/2026 » (affichage). */
  ES.frDate = function (d) { return typeof d === 'string' && /^\d{4}-\d{2}-\d{2}/.test(d) ? d.slice(8, 10) + '/' + d.slice(5, 7) + '/' + d.slice(0, 4) : d; };
  ES.frText = function (txt) {
    return String(txt).replace(/entre le (\d{4}-\d{2}-\d{2}) et le \1/g, 'le $1').replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, '$3/$2/$1')
      .replace(/(\d)\.(\d+)(?=\s?(?:%|point|fois|séance))/g, '$1,$2').replace(/(\d) %/g, '$1\u00a0%'); // virgule décimale, espace insécable avant %
  };
  function fmtEur(n) { return n >= 1e6 ? (n / 1e6).toFixed(1).replace('.', ',') + ' M€' : Math.round(n / 1e3) + ' k€'; }
  ES.fmtEur = fmtEur;

  /* ========================= Signaux d'initiés ========================= */
  ES.windowStart = function (today, months) { return ES.addMonths(today, -months); };
  /** Date de disponibilité de l'information : publication si connue, sinon transaction (signalé). */
  ES.availDate = function (t) { return t.pubDate || t.txDate; };
  ES.activeTx = function (list) { return (list || []).filter(function (t) { return t.status !== 'annulee' && t.status !== 'remplacee'; }); };
  /** Clé d'acheteur indépendant ; null si personne liée sans rattachement (non comptée). */
  ES.buyerKey = function (t) {
    if (t.associated) return t.linkedTo ? ES.personKey(t.linkedTo) : null;
    return t.personKey || null;
  };
  /** Déclarant personne morale (holding, société, fonds, fondation…) d'après son nom, toutes langues du périmètre. */
  var LEGAL_FORM_SET = {};
  'ab ag aktieselskabet aps bv bvba commv corp cv eurl ev fcp fcpe gbr gie gmbh inc kg kgaa lda limited llc llp lp ltd ltda nv ohg oy oyj plc sa sapa sarl sas sasu sau sc sca sccl sci scp scpi scrl scs se selarl sgr sicar sicav sim sl slu snc spa sprl srl srls ss ug vof'.split(' ').forEach(function (f) { LEGAL_FORM_SET[f] = 1; });
  // formes courtes qui sont aussi des noms de famille (Sá, Sim, Se…) : retenues seulement en majuscules ou avec des points
  var AMBIG_FORMS = { sa: 1, se: 1, sc: 1, ss: 1, sim: 1, ab: 1, as: 1, ag: 1, kg: 1, nv: 1, bv: 1, sl: 1, lp: 1, cv: 1, ev: 1, ug: 1, oy: 1, gie: 1, inc: 0 };
  var LEGAL_WORDS = /(^| )(holding|holdings|participations?|participaciones|partecipazioni|deelnemingen|beteiligungs?\w*|invest|investissements?|investments?|investment|inversiones|inversora|investimenti|capital|partners|management|gestion|gestora|gestioni|family office|familienstiftung|stiftung|stichting|fondation|foundation|fondazione|fundacion|fonds|fund|funds|trust|beheer|verwaltungs?\w*|vermogensverwaltung|patrimoine|patrimonial|patrimoniale|societe|societa|sociedad|company|compagnie|groupe|group|gruppo|grupo|finanziaria|fiduciaria|immobiliare|cartera|consulting|conseil|ventures|equity|asset|assets|family|familie|famiglia|familia|croissance|gestao|investimentos|administracao|participacoes|sociedade|holdco|maatschap|financiere|finance|industries|industrie|beteiligung)( |$)/;
  ES.isLegalEntity = function (name, issuer) {
    if (!name) return false;
    var raw = String(name), t = raw.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\./g, '').replace(/[^a-z0-9]+/g, ' ').trim();
    var toks = raw.split(/[\s,;()]+/).filter(Boolean);
    for (var x = 0; x < toks.length; x++) {
      var tk = toks[x], nk = tk.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
      if (!LEGAL_FORM_SET[nk]) continue;
      if (AMBIG_FORMS[nk] && !(/\./.test(tk) || (tk === tk.toUpperCase() && /[A-Z]{2}/.test(tk)))) continue;
      return true;
    }
    if (/(^| )a s( |$)/.test(t) && /A\/S/.test(raw)) return true;
    if (LEGAL_WORDS.test(t)) return true;
    // Un seul mot (« VALSEBA », « ALTAFI 2 ») : une personne physique a au moins un prénom et un nom
    var words = t.split(' ').filter(function (w) { return /[a-z]/.test(w); });
    if (words.length === 1 && words[0].length >= 3 && !/[a-z\u00e0-\u00ff][A-Z\u00c0-\u00dd]/.test(raw)) return true; // « DominiqueFOUGERAT » : prénom et nom collés
    // Le déclarant est l'émetteur lui-même (rachat d'actions déclaré comme une opération d'initié)
    if (issuer) {
      var i = String(issuer).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\./g, '').replace(/[^a-z0-9]+/g, ' ').trim();
      if (i && (t === i || (i.length >= 4 && t.indexOf(i) === 0))) return true;
    }
    return false;
  };
  /** Société exclue du comptage : par défaut, seules les sociétés qui ne sont pas la holding personnelle d'un dirigeant
   *  (fonds, investisseur, l'émetteur lui-même). Mode « strict » : toutes les sociétés. */
  ES.excludedEntity = function (t, cfg) {
    var m = cfg.insiders.excludeLegalEntities;
    if (!m || !ES.isLegalEntity(t.person, t.issuer)) return false;
    return m === 'strict' || !t.associated;
  };
  ES.isPanic = function (a, wi) { return !!a && ((a.drop10 != null && a.drop10 <= -wi.panicDropPct) || (a.rsi14 != null && a.rsi14 <= wi.panicRsi)); };
  /** Argumentaire en tête d'email : principe, chiffres académiques, et nos propres mesures pour le profil de signal le plus proche. */
  /** Secteur d'activité en français (classification Yahoo Finance). */
  var SECTORS_FR = { 'Basic Materials': 'Matériaux de base', 'Communication Services': 'Médias et télécoms', 'Consumer Cyclical': 'Consommation cyclique',
    'Consumer Defensive': 'Consommation courante', 'Energy': 'Énergie', 'Financial Services': 'Finance', 'Healthcare': 'Santé', 'Industrials': 'Industrie',
    'Real Estate': 'Immobilier', 'Technology': 'Technologie', 'Utilities': 'Services aux collectivités' };
  ES.INDUSTRIES_FR = {"Advertising Agencies": "Agences de publicité", "Aerospace & Defense": "Aéronautique et défense", "Agricultural Inputs": "Intrants agricoles", "Airlines": "Compagnies aériennes", "Apparel Manufacturing": "Fabrication de vêtements", "Apparel Retail": "Distribution de vêtements", "Asset Management": "Gestion d'actifs", "Auto & Truck Dealerships": "Concessionnaires automobiles", "Auto Manufacturers": "Constructeurs automobiles", "Auto Parts": "Équipementiers automobiles", "Banks - Diversified": "Banques diversifiées", "Banks - Regional": "Banques régionales", "Beverages - Brewers": "Brasseurs", "Beverages - Non-Alcoholic": "Boissons sans alcool", "Beverages - Wineries & Distilleries": "Vins et spiritueux", "Biotechnology": "Biotechnologies", "Broadcasting": "Télévision et radio", "Building Materials": "Matériaux de construction", "Building Products & Equipment": "Produits et équipements du bâtiment", "Business Equipment & Supplies": "Équipements de bureau", "Capital Markets": "Marchés de capitaux", "Chemicals": "Chimie", "Communication Equipment": "Équipements de communication", "Computer Hardware": "Matériel informatique", "Conglomerates": "Conglomérats", "Consulting Services": "Conseil", "Consumer Electronics": "Électronique grand public", "Credit Services": "Services de crédit", "Department Stores": "Grands magasins", "Diagnostics & Research": "Diagnostic et recherche", "Drug Manufacturers - General": "Laboratoires pharmaceutiques", "Drug Manufacturers - Specialty & Generic": "Pharmacie de spécialité et génériques", "Electrical Equipment & Parts": "Équipements électriques", "Electronic Components": "Composants électroniques", "Electronic Gaming & Multimedia": "Jeux vidéo et multimédia", "Electronics & Computer Distribution": "Distribution électronique et informatique", "Engineering & Construction": "Ingénierie et construction", "Entertainment": "Divertissement", "Farm & Heavy Construction Machinery": "Machines agricoles et de chantier", "Farm Products": "Produits agricoles", "Financial Conglomerates": "Conglomérats financiers", "Financial Data & Stock Exchanges": "Données financières et Bourses", "Food Distribution": "Distribution alimentaire", "Footwear & Accessories": "Chaussures et accessoires", "Furnishings, Fixtures & Appliances": "Ameublement et électroménager", "Gambling": "Jeux d'argent", "Grocery Stores": "Supermarchés", "Health Information Services": "Informatique de santé", "Home Improvement Retail": "Bricolage", "Household & Personal Products": "Produits ménagers et d'hygiène", "Industrial Distribution": "Distribution industrielle", "Information Technology Services": "Services informatiques", "Insurance - Diversified": "Assurance diversifiée", "Insurance - Property & Casualty": "Assurance dommages", "Insurance - Reinsurance": "Réassurance", "Integrated Freight & Logistics": "Transport et logistique", "Internet Content & Information": "Contenus internet", "Internet Retail": "Commerce en ligne", "Leisure": "Loisirs", "Lodging": "Hôtellerie", "Luxury Goods": "Luxe", "Medical Care Facilities": "Établissements de santé", "Medical Devices": "Dispositifs médicaux", "Medical Distribution": "Distribution médicale", "Medical Instruments & Supplies": "Instruments et fournitures médicales", "Metal Fabrication": "Métallurgie", "Oil & Gas E&P": "Exploration-production pétrolière", "Oil & Gas Equipment & Services": "Services pétroliers", "Oil & Gas Integrated": "Pétrole et gaz intégrés", "Oil & Gas Midstream": "Transport de pétrole et gaz", "Oil & Gas Refining & Marketing": "Raffinage et distribution pétrolière", "Other Precious Metals & Mining": "Métaux précieux et mines", "Packaged Foods": "Agroalimentaire", "Packaging & Containers": "Emballages", "Paper & Paper Products": "Papier", "Personal Services": "Services aux particuliers", "Pharmaceutical Retailers": "Pharmacies", "Pollution & Treatment Controls": "Traitement et dépollution", "Publishing": "Édition", "REIT - Diversified": "Foncière diversifiée", "REIT - Industrial": "Foncière logistique et industrielle", "REIT - Office": "Foncière de bureaux", "REIT - Residential": "Foncière résidentielle", "REIT - Retail": "Foncière commerciale", "Railroads": "Ferroviaire", "Real Estate - Development": "Promotion immobilière", "Real Estate - Diversified": "Immobilier diversifié", "Real Estate Services": "Services immobiliers", "Recreational Vehicles": "Véhicules de loisirs", "Rental & Leasing Services": "Location et crédit-bail", "Resorts & Casinos": "Complexes de loisirs et casinos", "Restaurants": "Restauration", "Scientific & Technical Instruments": "Instruments scientifiques et techniques", "Security & Protection Services": "Sécurité et protection", "Semiconductor Equipment & Materials": "Équipements pour semi-conducteurs", "Semiconductors": "Semi-conducteurs", "Software - Application": "Logiciels applicatifs", "Software - Infrastructure": "Logiciels d'infrastructure", "Solar": "Solaire", "Specialty Business Services": "Services aux entreprises", "Specialty Chemicals": "Chimie de spécialité", "Specialty Industrial Machinery": "Machines industrielles spécialisées", "Specialty Retail": "Distribution spécialisée", "Staffing & Employment Services": "Travail temporaire et recrutement", "Steel": "Acier", "Telecom Services": "Télécommunications", "Textile Manufacturing": "Textile", "Tools & Accessories": "Outillage", "Travel Services": "Services de voyage", "Utilities - Diversified": "Services aux collectivités diversifiés", "Utilities - Regulated Electric": "Électricité réglementée", "Utilities - Regulated Gas": "Gaz réglementé", "Utilities - Renewable": "Énergies renouvelables", "Waste Management": "Gestion des déchets", "Gold": "Or", "Copper": "Cuivre", "Aluminum": "Aluminium", "Coking Coal": "Charbon", "Thermal Coal": "Charbon", "Uranium": "Uranium", "Silver": "Argent", "Lumber & Wood Production": "Bois", "Tobacco": "Tabac", "Confectioners": "Confiserie", "Discount Stores": "Distribution discount", "Education & Training Services": "Éducation et formation", "Insurance - Life": "Assurance vie", "Insurance Brokers": "Courtage en assurance", "Insurance - Specialty": "Assurance spécialisée", "Marine Shipping": "Transport maritime", "Trucking": "Transport routier", "Airports & Air Services": "Aéroports", "Infrastructure Operations": "Exploitation d'infrastructures", "Utilities - Independent Power Producers": "Producteurs d'électricité indépendants", "Utilities - Regulated Water": "Eau", "Real Estate - Specialty": "Immobilier spécialisé", "REIT - Healthcare Facilities": "Foncière de santé", "REIT - Hotel & Motel": "Foncière hôtelière", "REIT - Specialty": "Foncière spécialisée", "Mortgage Finance": "Crédit immobilier", "Banks - Diversified ": "Banques diversifiées", "Shell Companies": "Sociétés coquilles", "Oil & Gas Drilling": "Forage pétrolier", "Electronics & Computer Distribution ": "Distribution électronique", "Computer Distribution": "Distribution informatique", "Semiconductor Memory": "Mémoires", "Scientific Instruments": "Instruments scientifiques"};
  ES.industryFr = function (s) { return s ? ES.INDUSTRIES_FR[s] || String(s) : null; };
  ES.sectorFr = function (s) { return s ? SECTORS_FR[s] || String(s) : null; };
  /** Résultat mesuré d'un groupe de signaux, échantillon et hors échantillon réunis. */
  ES.groupOutcome = function (results, group, horizon) {
    var o = { n: 0, up: 0, mean: 0, nEx: 0, beat: 0, meanEx: 0 };
    (results || []).filter(function (r) { return r.group === group && r.horizon === horizon; }).forEach(function (r) {
      o.n += r.n; o.up += r.hit * r.n; o.mean += r.mean * r.n;
      if (r.nExcess) { o.nEx += r.nExcess; o.beat += r.hitExcess * r.nExcess; o.meanEx += r.meanExcess * r.nExcess; }
    });
    if (o.n) { o.up /= o.n; o.mean /= o.n; }
    if (o.nEx) { o.beat /= o.nEx; o.meanEx /= o.nEx; }
    return o;
  };
  /** « Pourquoi cette méthode » : fondement académique + ce que nos propres données mesurent, sans enjoliver. */
  ES.methodRationale = function (results, cfg, since) {
    var H = 60, pc = function (v) { return (v >= 0 ? '+' : '') + v.toFixed(1).replace('.', ',') + ' %'; };
    var p1 = 'Pourquoi cette méthode ? Un dirigeant qui achète des actions de sa propre société avec son argent connaît mieux que personne ses perspectives : il ne le fait que s\'il juge le cours trop bas. ' +
      'Les études académiques mesurent une surperformance d\'environ 0,4 % par mois après ces achats (Jeng, Metrick et Zeckhauser, marché américain), plus nette sur les petites et moyennes valeurs, ' +
      'quand l\'achat est important, quand plusieurs dirigeants achètent ensemble ou après une forte baisse. D\'où nos filtres : au moins ' + fmtEur(cfg.insiders.minBuyerEur) +
      ' par dirigeant, décote par rapport au plus haut de l\'année, achat du DG ou du DAF, cluster, société financièrement solide.';
    var lines = [], labels = [['Achat volontaire', 'achat de dirigeant d\'au moins ' + fmtEur(cfg.insiders.minBuyerEur)], ['Décote ≥ ' + cfg.weights.insiders.discountMediumPct + ' %', 'même achat, payé au moins ' + cfg.weights.insiders.discountMediumPct + ' % sous le plus haut 52 semaines'], ['Achat DG ou DAF', 'achat du DG ou du DAF']];
    var total = 0, best = 0;
    labels.forEach(function (l) {
      var o = ES.groupOutcome(results, l[0], H);
      if (!o.n) return;
      total = Math.max(total, o.n); best = Math.max(best, o.nEx ? o.beat : 0);
      lines.push('• ' + l[1] + ' : le cours était plus haut ' + H + ' séances plus tard (environ 3 mois) dans ' + Math.round(o.up) + ' % des cas, variation moyenne ' + pc(o.mean) +
        (o.nEx ? ', mieux que le CAC 40 dans ' + Math.round(o.beat) + ' % des cas' : '') + ' (' + o.n + ' cas).');
    });
    var p2 = 'Ce que mesurent nos propres données européennes' + (since ? ' (déclarations depuis le ' + since + ')' : '') + ', coûts de transaction déduits :';
    var p3 = !lines.length ? 'Pas encore assez de recul pour mesurer : les premiers résultats à 3 mois arrivent avec le temps.'
      : (total < 100 ? 'Recul encore court (moins de 100 cas) : ces chiffres se précisent chaque soir. ' : '') +
        (best < 55 ? 'Pour l\'instant, nos données ne montrent pas d\'avantage net : cette liste sert à étudier des dossiers, pas à acheter les yeux fermés.' : 'Le signal se confirme sur nos données, sans garantie pour l\'avenir.');
    var text = p1 + '\n\n' + p2 + '\n' + (lines.length ? lines.join('\n') + '\n' : '') + p3;
    var html = '<div style="background:#EEF6F2;border-left:4px solid #0D6A56;padding:10px 14px;margin:0 0 14px;font-size:13px;line-height:1.45"><b>Pourquoi cette méthode ?</b><br>' + esc(p1.replace(/^Pourquoi cette méthode \? /, '')) +
      '<br><br>' + esc(p2) + (lines.length ? '<ul style="margin:6px 0 6px 18px;padding:0">' + lines.map(function (l) { return '<li>' + esc(l.replace(/^• /, '')) + '</li>'; }).join('') + '</ul>' : '<br>') + '<i>' + esc(p3) + '</i></div>';
    return { text: text, html: html };
  };
  ES.emailRationale = function (results, group, horizon) {
    var rows = (results || []).filter(function (r) { return r.group === group && r.horizon === horizon && r.nExcess; });
    var n = 0, hit = 0, mean = 0;
    rows.forEach(function (r) { n += r.nExcess; hit += r.hitExcess * r.nExcess; mean += r.meanExcess * r.nExcess; });
    var p1 = 'Quand un dirigeant achète des actions de sa société avec son propre argent, il signale qu\'il juge le cours trop bas. Les études académiques mesurent en moyenne environ +0,4 % par mois de surperformance après ces achats (Jeng, Metrick et Zeckhauser, marché américain 1975-1996) ; l\'effet est plus net quand plusieurs dirigeants achètent ensemble ou après une forte baisse.';
    var p2;
    if (!n) p2 = 'Nos propres mesures sur ce type de signal (« ' + group + ' ») ne sont pas encore disponibles.';
    else {
      hit /= n; mean /= n;
      var o = ES.groupOutcome(results, group, horizon);
      p2 = 'Sur les ' + n + ' cas « ' + group + ' » que nous avons suivis, le cours était plus haut ' + horizon + ' séances plus tard (environ 3 mois) dans ' + Math.round(o.up) + ' % des cas et a battu le CAC 40 dans ' + Math.round(hit) + ' % des cas à ' + horizon + ' séances, avec un écart moyen de ' + (mean >= 0 ? '+' : '') + mean.toFixed(1).replace('.', ',') + ' point' + (Math.abs(mean) >= 2 ? 's' : '') + ', frais compris.';
      if (n < 30) p2 += ' Échantillon encore trop petit pour conclure.';
      else if (mean < 0) p2 += ' Sur la période récente, ce signal seul n\'a pas battu le marché : ce sont les combinaisons (décote, tendance, plusieurs signaux) qui font le tri.';
    }
    return { text: p1 + '\n' + p2, html: '<div style="background:#EEF6F2;border-left:4px solid #0D6A56;padding:10px 14px;margin:0 0 14px;font-size:13px;line-height:1.45"><b>Pourquoi cette alerte ?</b><br>' + esc(p1) + '<br><br>' + esc(p2) + '</div>' };
  };
  /** Solidité financière (dernières données publiées, non historisées) : solide / fragile / inconnu. */
  ES.financialHealth = function (f) {
    if (!f || typeof f !== 'object') return { status: 'inconnu', reasons: ['données financières indisponibles'], notes: [] };
    var sec = String(f.sector || '') + ' ' + String(f.industry || '');
    // Dette non comparable : banques, assurances, foncières (jugées sur la valeur des actifs) et constructeurs automobiles (dette de leur banque captive)
    var fin = /financial|bank|insurance|banque|assurance|real estate|reit|auto manufacturers|rental & leasing|asset management/i.test(sec);
    var maxLev = /utilit|waste|infrastructure|telecom|toll|railroad/i.test(sec) ? 7 : 4.5; // dette Yahoo y compris loyers (IFRS 16) ; secteurs régulés : endettement plus élevé normal
    var reasons = [], notes = [];
    var debt = f.totalDebt, cash = f.totalCash, ebitda = f.ebitda, net = debt != null && cash != null ? debt - cash : null;
    if (!fin && net != null) {
      if (ebitda != null && ebitda > 0) {
        var lev = net / ebitda;
        if (lev > maxLev) reasons.push('dette nette (loyers compris) égale à ' + lev.toFixed(1).replace('.', ',') + ' fois l\'EBITDA');
        else if (lev < 0) notes.push('trésorerie nette positive');
        else notes.push('dette nette ' + lev.toFixed(1).replace('.', ',') + ' fois l\'EBITDA');
      } else if (ebitda != null && ebitda <= 0 && net > 0) reasons.push('EBITDA négatif avec une dette nette');
    }
    if (!fin && f.freeCashflow != null && f.freeCashflow < 0 && (ebitda == null || ebitda <= 0) && cash != null) {
      var runway = cash / -f.freeCashflow;
      if (runway < 2) reasons.push('trésorerie couvrant environ ' + (runway < 1 ? 'moins d\'un an' : Math.round(runway * 10) / 10 + ' an(s)').replace('.', ',') + ' de consommation au rythme actuel');
    }
    if (f.profitMargins != null && f.profitMargins < -0.15) reasons.push('pertes importantes (marge nette ' + Math.round(f.profitMargins * 100) + ' %)');
    if (!fin && f.freeCashflow != null && f.operatingCashflow != null && f.freeCashflow < 0 && f.operatingCashflow < 0 && (f.profitMargins == null || f.profitMargins < 0)) reasons.push('l\'activité consomme de la trésorerie et perd de l\'argent');
    if (!fin && f.currentRatio != null && f.currentRatio < 0.8) notes.push('liquidité de court terme tendue (ratio ' + f.currentRatio.toFixed(2).replace('.', ',') + ')');
    if (f.freeCashflow != null && f.freeCashflow > 0) notes.push('flux de trésorerie disponible positif');
    var known = [debt, cash, ebitda, f.profitMargins, f.freeCashflow].filter(function (v) { return v != null; }).length;
    if (!reasons.length && (known < 2 || (!fin && debt == null && cash == null))) return { status: 'inconnu', reasons: ['données financières trop incomplètes (dette et trésorerie inconnues)'], notes: notes };
    return { status: reasons.length ? 'fragile' : 'solide', reasons: reasons, notes: notes, asOf: f.asOf || null, financial: fin };
  };
  ES.significantBuys = function (buys, cfg) {
    var min = cfg.insiders.minBuyerEur || 0, w = cfg.insiders.clusterWindowDays;
    if (!min) return { kept: buys, small: [] };
    var kept = [], small = [];
    buys.forEach(function (t) {
      var e = ES.toEur(t.amount, t.currency);
      if (e == null) { kept.push(t); return; } // montant inconnu ou hors euro : non filtrable, conservé
      var k = ES.buyerKey(t) || t.personKey, from = ES.addDays(t.txDate, -(w - 1)), pub = ES.availDate(t), tot = 0;
      buys.forEach(function (b) { if ((ES.buyerKey(b) || b.personKey) === k && b.txDate >= from && b.txDate <= t.txDate && ES.availDate(b) <= pub) tot += ES.toEur(b.amount, b.currency) || 0; });
      (tot >= min ? kept : small).push(t);
    });
    return { kept: kept, small: small };
  };
  /** Numéro de semaine ISO (« 2026-W41 »). */
  ES.isoWeek = function (day) {
    var d = new Date(day + 'T12:00:00Z'), wd = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - wd + 3);
    var y = d.getUTCFullYear(), j4 = new Date(Date.UTC(y, 0, 4)), w = 1 + Math.round(((d - j4) / 864e5 - 3 + ((j4.getUTCDay() + 6) % 7)) / 7);
    return y + '-W' + (w < 10 ? '0' : '') + w;
  };
  /**
   * Sélection courte : les N meilleurs dossiers parmi les sociétés achetées récemment par un dirigeant.
   * Filtres durs : titre retenu, données fiables, pas de fragilité financière, achat significatif publié depuis
   * moins de recentDays jours, score ≥ minScore. Tri : score, puis décote.
   * cands : [{ isin, inst, score, quality, universe }]
   */
  /** Raisons pour lesquelles une société ne peut pas entrer dans la sélection de la semaine (liste vide = éligible). */
  ES.selectionBlockers = function (c, cfg, today) {
    var S = cfg.selection, sc = c.score, out = [], health = ES.financialHealth(c.inst.fund);
    if (!sc || !sc.buys.length) return ['aucun achat significatif de dirigeant (au moins ' + fmtEur(cfg.insiders.minBuyerEur) + ') sur ' + cfg.insiders.windowMonths + ' mois'];
    if (c.universe && c.universe.status !== 'retenu') out.push('titre non retenu : ' + ((c.universe.reasons || [])[0] || 'liquidité ou historique de cours insuffisant'));
    if (health.status === 'fragile') out.push('solidité financière fragile : ' + health.reasons.join(', '));
    if (S.peaOnly !== false && c.inst.peaStatus === 'non_eligible') out.push('non éligible au PEA' + (c.inst.peaSource ? ' (' + c.inst.peaSource + ')' : ''));
    if (c.quality && (c.quality.total < cfg.quality.minForAlert || (c.quality.coverage && !c.quality.coverage.ok))) out.push('données incomplètes (qualité ' + c.quality.total + '/100)');
    if (sc.ambiguousCount) out.push('déclaration ambiguë à vérifier');
    if (sc.total < S.minScore) out.push('note ' + ES.note(sc.total, cfg) + '/100, sous le seuil de ' + ES.note(S.minScore, cfg));
    var from = ES.addDays(today, -S.recentDays);
    if (!sc.buys.some(function (t) { return ES.availDate(t) >= from; })) out.push('dernier achat significatif publié il y a plus de ' + S.recentDays + ' jours');
    return out;
  };
  /**
   * Signaux croisés, lisibles d'un coup d'œil : { k, icon, text, tone: good | warn | bad | info }.
   * Ventes à découvert : avertissement rouge ; face à des achats forts de dirigeants, « duel » (issue binaire, risque élevé).
   */
  ES.crossSignals = function (inst, sc, cfg) {
    var out = [], push = function (k, icon, text, tone) { out.push({ k: k, icon: icon, text: text, tone: tone }); };
    if (!sc) return out;
    var ceo = sc.buys.some(function (t) { return t.ceo || t.cfo; }), big = sc.buyEur >= cfg.insiders.bigAmountEur, cl = sc.cluster && sc.cluster.count >= cfg.insiders.clusterMinBuyers;
    var strongInsider = sc.buys.length && (ceo || big || cl);
    if (ceo) push('ceo', '👔', 'le DG ou le DAF achète', 'good');
    if (cl) push('cluster', '👥', sc.cluster.count + ' dirigeants achètent', 'good');
    if (big) push('big', '💰', fmtEur(sc.buyEur) + ' achetés', 'good');
    if (sc.discount && sc.discount.pct >= cfg.weights.insiders.discountMediumPct) push('disc', '🏷️', 'payé ' + Math.round(sc.discount.pct) + ' % sous le plus haut', 'good');
    if (sc.panicBuy) push('panic', '😱', 'achat dans la panique', 'good');
    if (sc.trendUp) push('trend', '📈', 'tendance de fond haussière', 'good');
    if (sc.fallingKnife) push('knife', '🔻', 'cours en repli', 'warn');
    var p = inst.peer;
    if (p && p.discountPct >= cfg.valuation.cheapPct) push('cheap', '💶', Math.round(p.discountPct) + ' % moins chère que ses pairs', 'good');
    else if (p && p.discountPct <= -cfg.valuation.richPct) push('rich', '💸', Math.round(-p.discountPct) + ' % plus chère que ses pairs', 'warn');
    var pos = inst.position;
    if (pos && (pos.key === 'leader' || pos.key === 'challenger')) push('pos', '🏆', (pos.key === 'leader' ? 'leader' : 'challenger') + ' de son industrie', 'good');
    var sh = inst.shorts;
    if (sh && sh.totalPct >= 2) {
      if (strongInsider) push('duel', '⚡', 'duel : ' + String(sh.totalPct).replace('.', ',') + ' % vendus à découvert contre des achats forts de dirigeants', 'warn');
      push('short', '⚠️', String(sh.totalPct).replace('.', ',') + ' % du capital vendu à découvert (' + sh.holders + ' fonds)', sh.totalPct >= 5 ? 'bad' : 'warn');
    } else if (sh) push('short', '⚠️', String(sh.totalPct).replace('.', ',') + ' % vendu à découvert', 'warn');
    var bp = inst.buyerProfiles || {}, bpl = Object.keys(bp).map(function (k) { return bp[k]; });
    if (bpl.length && bpl.some(function (b) { return b.routine === 'inhabituel'; })) push('opportunistic', '🧭', 'achat inhabituel pour ce dirigeant', 'good');
    else if (bpl.length && bpl.every(function (b) { return b.routine === 'habituel'; })) push('routine', '🔁', 'achat habituel (même période chaque année ou achats en continu) : peu informatif', 'warn');
    var tr = bpl.filter(function (b) { return b.track && b.track.n >= 2; }).sort(function (a, b) { return b.track.n - a.track.n; })[0];
    if (tr) push('track', '🏅', 'palmarès du dirigeant : ' + tr.track.beat + ' de ses ' + tr.track.n + ' achats passés ' + (tr.track.beat > 1 ? 'ont' : 'a') + ' battu le CAC 40', tr.track.beat / tr.track.n >= 0.6 ? 'good' : tr.track.beat / tr.track.n <= 0.34 ? 'bad' : 'info');
    if (bpl.some(function (b) { return b.record; })) push('record', '💪', 'achat record pour ce dirigeant', 'good');
    var acc = inst.accounts, fs = acc && acc.fscore && !acc.fscore.na ? acc.fscore.f9 : null;
    if (fs != null) push('fscore', '📊', 'comptes ' + (fs >= cfg.accounts.fscoreGood ? 'solides' : fs <= cfg.accounts.fscoreBad ? 'en dégradation' : 'mitigés') + ' (F-score ' + fs + '/9)', fs >= cfg.accounts.fscoreGood ? 'good' : fs <= cfg.accounts.fscoreBad ? 'bad' : 'info');
    var h = ES.financialHealth(inst.fund);
    if (h.status === 'fragile') push('fragile', '🩺', 'solidité financière fragile', 'bad');
    if (inst.peaStatus === 'non_eligible') push('pea', '🚫', 'hors PEA', 'bad');
    if (sc.sellEur > sc.buyEur && sc.sellEur > 0) push('sellers', '🔴', 'dirigeants vendeurs nets', 'bad');
    if (inst.nextEarnings) push('earn', '📅', 'résultats le ' + ES.frDate(inst.nextEarnings), 'info');
    return out;
  };
  /**
   * Avis croisé (aide à la décision, jamais un ordre) : priority | watch | wait | avoid, avec ses raisons.
   * Croise la note, le repère historique, la solidité, la valorisation, les ventes à découvert, la tendance et le calendrier.
   */
  ES.advice = function (inst, sc, cfg, opts) {
    opts = opts || {};
    var sig = ES.crossSignals(inst, sc, cfg), has = function (k) { return sig.some(function (x) { return x.k === k; }); };
    var why = [], A = { priority: { icon: '🟢', label: 'À étudier en priorité' }, watch: { icon: '🟡', label: 'À surveiller' }, wait: { icon: '⚪', label: 'Attendre' }, avoid: { icon: '🔴', label: 'Éviter pour l\'instant' } };
    var mk = function (k) { return { key: k, icon: A[k].icon, label: A[k].label, why: why, signals: sig }; };
    if (!sc || !sc.buys.length) { why.push('aucun achat significatif de dirigeant récent'); return mk('wait'); }
    if (has('fragile')) why.push('solidité financière fragile : la baisse du cours peut être justifiée');
    if (has('pea') && cfg.selection.peaOnly !== false) why.push('non éligible au PEA');
    if (has('sellers')) why.push('les dirigeants vendent plus qu\'ils n\'achètent');
    var accF = inst.accounts && inst.accounts.fscore && !inst.accounts.fscore.na ? inst.accounts.fscore.f9 : null;
    if (accF != null && accF <= 1) why.push('comptes en forte dégradation (F-score ' + accF + '/9)');
    if (opts.universe && opts.universe.status === 'rejete') why.push('titre peu liquide ou historique insuffisant');
    if (why.length) return mk('avoid');
    var lab = ES.scoreLabel(sc.total, cfg).key, hist = opts.histKey, caution = [];
    if (has('knife')) caution.push('cours encore en repli : entrer en plusieurs fois');
    if (has('rich')) caution.push('valorisation au-dessus des pairs');
    if (accF != null && accF <= cfg.accounts.fscoreBad) caution.push('comptes en dégradation (F-score ' + accF + '/9)');
    if (inst.shorts && inst.shorts.totalPct >= 5) caution.push(has('duel') ? 'duel avec des vendeurs à découvert : issue binaire, position réduite' : 'fonds fortement vendeurs à découvert');
    if (inst.nextEarnings && opts.today && inst.nextEarnings >= opts.today && ES.daysBetween(opts.today, inst.nextEarnings) <= cfg.alerts.earningsWarnDays) caution.push('résultats dans moins de ' + cfg.alerts.earningsWarnDays + ' jours');
    if (sc.marketDown) caution.push('marché européen baissier');
    if (has('routine')) caution.push('achats habituels de ce dirigeant, peu informatifs');
    if (opts.mood && opts.mood.key === 'greed') caution.push('marché européen euphorique');
    var accTxt = accF != null && accF >= cfg.accounts.fscoreGood ? 'comptes solides et en amélioration (F-score ' + accF + '/9)' : null;
    var extra = [];
    if (has('opportunistic')) extra.push('achat inhabituel pour ce dirigeant');
    var trk = sig.filter(function (x) { return x.k === 'track' && x.tone === 'good'; })[0]; if (trk) extra.push(trk.text);
    if (has('record')) extra.push('achat record pour ce dirigeant');
    if (opts.mood && opts.mood.key === 'fear') extra.push('achat pendant la peur du marché (comportement contrarien)');
    if (accTxt) extra.unshift(accTxt); accTxt = extra.length ? extra.join(' ; ') : null;
    if (lab === 'top' && hist !== 'wait' && caution.length <= 1) { why.push('note très forte' + (hist === 'rare' ? ', remarquable dans l\'historique' : '')); if (accTxt) why.push(accTxt); caution.forEach(function (c) { why.push('vigilance : ' + c); }); return mk('priority'); }
    if (lab === 'top' || lab === 'strong') { why.push(lab === 'top' ? 'note très forte' : 'note forte'); if (accTxt) why.push(accTxt); caution.forEach(function (c) { why.push('vigilance : ' + c); }); if (hist === 'wait') why.push('ordinaire par rapport aux sélections passées'); return mk('watch'); }
    why.push('signal encore modeste (note ' + ES.note(sc.total, cfg) + '/100)');
    return mk('wait');
  };
  ES.weeklySelection = function (cands, cfg, today) {
    var S = cfg.selection || {}, from = ES.addDays(today, -(S.recentDays || 30)), out = [];
    (cands || []).forEach(function (c) {
      if (ES.selectionBlockers(c, cfg, today).length) return;
      var sc = c.score, health = ES.financialHealth(c.inst.fund);
      var recent = sc.buys.filter(function (t) { return ES.availDate(t) >= from; });
      var d = sc.discount, eur = sc.buyEur;
      out.push({ isin: c.isin, name: c.inst.name || c.isin, country: c.inst.country || null, sector: ES.sectorFr(c.inst.sector || (c.inst.fund && c.inst.fund.sector)), score: sc.total,
        discountPct: d ? d.pct : null, buyer: d ? d.person : recent[0].person, ceo: sc.buys.some(function (t) { return t.ceo || t.cfo; }),
        buyDate: d ? d.date : recent[0].txDate, lastPub: recent.map(function (t) { return ES.availDate(t); }).sort().pop(), buyEur: eur || null,
        buyers: sc.cluster ? sc.cluster.count : 1, clusterFrom: sc.cluster ? sc.cluster.from : null, clusterTo: sc.cluster ? sc.cluster.to : null, trendUp: sc.trendUp, fallingKnife: sc.fallingKnife, panic: !!sc.panicBuy,
        health: health.status, nextEarnings: c.inst.nextEarnings || null,
        accounts: c.inst.accounts && c.inst.accounts.verdict ? { f9: c.inst.accounts.fscore && !c.inst.accounts.fscore.na ? c.inst.accounts.fscore.f9 : null, key: c.inst.accounts.verdict.key, text: c.inst.accounts.verdict.text, good: c.inst.accounts.verdict.good, bad: c.inst.accounts.verdict.bad } : null,
        peer: c.inst.peer || null, position: c.inst.position ? { label: c.inst.position.label, key: c.inst.position.key, rank: c.inst.position.rank, of: c.inst.position.of, industry: c.inst.position.industry } : null, shorts: c.inst.shorts ? { totalPct: c.inst.shorts.totalPct, holders: c.inst.shorts.holders } : null });
    });
    out.sort(function (a, b) { return b.score - a.score || (b.discountPct || 0) - (a.discountPct || 0); });
    return out.slice(0, S.size || 5);
  };
  /** Email « Sélection de la semaine » : une liste courte à étudier, jamais un ordre d'achat. */
  ES.buildSelectionEmail = function (sel, week, cfg, dashUrl, today, rationale, track, verdict, replayStats) {
    var n = sel.length, S = cfg.selection || {};
    var subject = '[Euro Signal] Sélection de la semaine (' + week + ') : ' + (n ? n + ' dossier' + (n > 1 ? 's' : '') + ' à étudier' : 'aucun dossier');
    var A = cfg.alerts.minScore, M = S.minScore;
    var intro = 'Sociétés où un dirigeant a acheté au moins ' + fmtEur(cfg.insiders.minBuyerEur) + ' ces ' + S.recentDays + ' derniers jours, solides et liquides' + (S.peaOnly !== false ? ', éligibles au PEA' : '') + '. Note sur 100 : ' + ES.note(A, cfg) + ' et plus = très fort, ' + ES.note(M, cfg) + ' à ' + (ES.note(A, cfg) - 1) + ' = fort.';
    // Repli quand l'avis croisé n'est pas fourni (tests, anciennes données) : faits bruts
    var why = function (x) {
      var w = [];
      if (x.discountPct != null) w.push('payé ' + Math.round(x.discountPct) + ' % sous le plus haut 52 semaines' + (x.buyDate ? ' (achat du ' + ES.frDate(x.buyDate) + ')' : ''));
      w.push(x.ceo ? 'achat du DG ou du DAF' : 'achat d\'un dirigeant');
      if (x.buyers >= cfg.insiders.clusterMinBuyers) w.push(x.buyers + ' dirigeants acheteurs');
      if (x.peer && x.peer.discountPct >= cfg.valuation.cheapPct) w.push(Math.round(x.peer.discountPct) + ' % sous ses pairs (' + x.peer.metric + ')');
      if (x.trendUp) w.push('tendance de fond haussière');
      if (x.buyEur) w.push(fmtEur(x.buyEur) + ' achetés par les dirigeants');
      return w.map(function (t) { return t.charAt(0).toUpperCase() + t.slice(1); });
    };
    var care = function (x) {
      var c = [];
      if (x.shorts) c.push('⚠️ ' + x.shorts.holders + ' fonds parie' + (x.shorts.holders > 1 ? 'nt' : '') + ' à la baisse (' + String(x.shorts.totalPct).replace('.', ',') + ' % du capital)');
      if (x.fallingKnife) c.push('🔻 Cours en repli : entrer en plusieurs fois');
      if (x.peer && x.peer.discountPct <= -cfg.valuation.richPct) c.push('💸 ' + Math.round(-x.peer.discountPct) + ' % plus chère que ses pairs');
      if (x.nextEarnings && (!today || (x.nextEarnings >= today && ES.daysBetween(today, x.nextEarnings) <= 30))) c.push('📅 Résultats le ' + ES.frDate(x.nextEarnings));
      if (x.health === 'inconnu') c.push('Solidité financière non vérifiable');
      return c;
    };
    var sumOf = function (x) {
      if (x.advice) { var s = ES.adviceSummary(x.advice); if (s.pros.length || s.cons.length) return s; }
      return { pros: why(x).slice(0, 3), cons: care(x).slice(0, 2) };
    };
    var pcs = function (v) { return (v >= 0 ? '+' : '') + v.toFixed(1).replace('.', ',') + ' %'; };
    var tr = track && track.weeks ? 'Sélections déjà envoyées (' + track.n + ' dossiers) : ' + pcs(track.avg) + ' en moyenne depuis l\'envoi' + (track.bench != null ? ', CAC 40 ' + pcs(track.bench) : '') + '.' : null;
    var rel = ES.reliabilityText(replayStats);
    var why1 = rationale ? 'Pourquoi cette méthode ? Un dirigeant qui achète avec son propre argent connaît mieux que personne sa société ; les études mesurent environ +0,4 % par mois de surperformance après ces achats.' : null;
    var head = function (x) { return ES.stars(x.score, cfg, x.hist && x.hist.key).text + ' ' + ES.note(x.score, cfg) + '/100' + (x.advice ? ' · ' + x.advice.icon + ' ' + x.advice.label : ''); };
    var text = (verdict && verdict.text ? (verdict.icon ? verdict.icon + ' ' : '') + verdict.text + '\n\n' : '') + (rel ? rel + '\n' : '') + (tr ? tr + '\n' : '') + (rel || tr ? '\n' : '') + (n ? sel.map(function (x, k) {
      var s = sumOf(x);
      return (k + 1) + '. ' + (x.isNew ? '[NOUVEAU] ' : '') + x.name + (x.sector ? ' (' + x.sector + ')' : '') + ' — ' + head(x) +
        (x.hist && x.hist.key !== 'na' ? '\n   ' + x.hist.icon + ' ' + x.hist.label : '') +
        (s.pros.length ? '\n   Pourquoi : ' + s.pros.join(' · ') : '') + (s.cons.length ? '\n   Attention : ' + s.cons.join(' · ') : '') + (dashUrl ? '\n   Fiche : ' + dashUrl + '#' + x.isin : '');
    }).join('\n\n') : 'Aucune société ne remplit tous les critères cette semaine. Mieux vaut ne rien faire que forcer un choix.') +
      '\n\n' + intro + (why1 ? '\n' + why1 : '') + '\nÀ étudier, pas un ordre d\'achat. Éligibilité PEA à vérifier.' + (dashUrl ? '\nTableau de bord : ' + dashUrl : '');
    var btn = function (href, label) { return '<a href="' + ES.esc(href) + '" style="display:inline-block;background:#0D6A56;color:#ffffff;text-decoration:none;font-weight:bold;padding:8px 14px;border-radius:6px;font-size:13px">' + label + '</a>'; };
    var advStyle = { priority: 'background:#E3F3E8;color:#1F5F35', watch: 'background:#FFF6DC;color:#7A5600', wait: 'background:#F1F2F1;color:#3D4641', avoid: 'background:#FBE6E3;color:#8E2219' };
    var html = '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.45;max-width:640px;color:#1b2420"><h2 style="margin:0 0 8px">Sélection de la semaine</h2>' +
      (verdict && verdict.text ? '<div style="border-radius:8px;padding:10px 14px;margin:0 0 10px;' + ({ strong: 'background:#E3F3E8;border:1px solid #1F7A3E', normal: 'background:#FFF6DC;border:1px solid #B38600', weak: 'background:#F1F2F1;border:1px solid #9AA39E' }[verdict.key] || 'background:#F1F2F1;border:1px solid #CBD3CD') + '"><b>' + (verdict.icon ? verdict.icon + ' ' : '') + ES.esc(verdict.text.split(' : ')[0]) + '</b>' + (verdict.text.indexOf(' : ') > -1 ? ' : ' + ES.esc(verdict.text.slice(verdict.text.indexOf(' : ') + 3)) : '') + '</div>' : '') +
      (rel || tr ? '<p style="margin:0 0 12px;font-size:13px;color:#3D4641">' + (rel ? '🎯 ' + ES.esc(rel) : '') + (rel && tr ? '<br>' : '') + (tr ? '📈 ' + ES.esc(tr) : '') + '</p>' : '') +
      (n ? sel.map(function (x, k) {
        var s = sumOf(x);
        return '<div style="border:1px solid #dfe5e1;border-radius:8px;padding:12px 14px;margin:0 0 10px">' +
          '<div style="font-size:16px;font-weight:bold">' + (k + 1) + '. ' + ES.esc(x.name) + (x.isNew ? ' <span style="background:#B0281F;color:#ffffff;font-size:11px;padding:2px 6px;border-radius:4px;vertical-align:middle">NOUVEAU</span>' : '') + '</div>' +
          '<div style="color:#55615c;font-size:13px">' + ES.esc([x.country, x.sector].filter(Boolean).join(' · ')) + '</div>' +
          '<div style="margin:6px 0"><span style="color:#E0A800;font-size:18px;letter-spacing:1px">' + ES.stars(x.score, cfg, x.hist && x.hist.key).text + '</span> <b>' + ES.note(x.score, cfg) + '/100</b>' +
          (x.advice ? ' <span style="display:inline-block;margin-left:4px;padding:2px 8px;border-radius:10px;font-size:13px;font-weight:bold;' + advStyle[x.advice.key] + '">' + x.advice.icon + ' ' + ES.esc(x.advice.label) + '</span>' : '') + '</div>' +
          (x.hist && x.hist.key !== 'na' ? '<div style="font-size:13px;color:' + ({ rare: '#1F7A3E', good: '#8a6400', wait: '#55615c' }[x.hist.key]) + '">' + x.hist.icon + ' ' + ES.esc(x.hist.label) + '</div>' : '') +
          (s.pros.length ? '<div style="margin:8px 0 0"><b>Pourquoi</b><ul style="margin:2px 0 0 18px;padding:0">' + s.pros.map(function (w) { return '<li>' + ES.esc(w) + '</li>'; }).join('') + '</ul></div>' : '') +
          (s.cons.length ? '<div style="margin:6px 0 0;color:#8a3a00"><b>Attention</b><ul style="margin:2px 0 0 18px;padding:0">' + s.cons.map(function (w) { return '<li>' + ES.esc(w) + '</li>'; }).join('') + '</ul></div>' : '') +
          (dashUrl ? '<div style="margin-top:10px">' + btn(dashUrl + '#' + x.isin, 'Voir la fiche') + '</div>' : '') + '</div>';
      }).join('') : '<p><b>Aucune société ne remplit tous les critères cette semaine.</b> Mieux vaut ne rien faire que forcer un choix.</p>') +
      '<p style="color:#55615c;font-size:12px;margin-top:14px">' + ES.esc(intro) + (why1 ? '<br><b>Pourquoi cette méthode ?</b> ' + ES.esc(why1.replace(/^Pourquoi cette méthode \? /, '')) : '') + '<br>À étudier, pas un ordre d\'achat. Éligibilité PEA à vérifier.</p>' +
      (dashUrl ? '<p>' + btn(dashUrl, 'Ouvrir le tableau de bord') + ' &nbsp;<a href="' + ES.esc(dashUrl) + '#aide" style="color:#0D6A56;font-size:13px">Méthode et preuves</a></p>' : '') + '</div>';
    return { subject: subject, text: text, html: html };
  };
  /** Note sur 100 affichée : points bruts rapportés au maximum réaliste (display.scoreCeiling), plafonnée à 100. Le calcul, les seuils et l'apprentissage restent en points bruts. */
  ES.note = function (total, cfg) {
    var c = (cfg && cfg.display && cfg.display.scoreCeiling) || 60;
    return Math.max(0, Math.min(100, Math.round((total || 0) * 100 / c)));
  };
  /** Lecture du score : 100 est un maximum théorique (tous les signaux à la fois) ; repères calés sur les seuils d'alerte et de sélection. */
  ES.scoreLabel = function (total, cfg) {
    var a = cfg.alerts.minScore, s = cfg.selection.minScore;
    var N = function (v) { return ES.note(v, cfg); };
    if (total >= a) return { key: 'top', label: 'très fort', hint: 'note ' + N(a) + ' et plus' };
    if (total >= s) return { key: 'strong', label: 'fort', hint: 'note ' + N(s) + ' à ' + (N(a) - 1) };
    if (total >= Math.round(s / 2)) return { key: 'mid', label: 'moyen', hint: 'note ' + N(Math.round(s / 2)) + ' à ' + (N(s) - 1) };
    return { key: 'low', label: 'faible', hint: 'note inférieure à ' + N(Math.round(s / 2)) };
  };
  /** Bilan des sélections passées : performance moyenne de chaque dossier depuis l'envoi, comparée au CAC 40. */
  ES.selectionTrackSummary = function (track) {
    var items = [], beat = 0, nb = 0, sb = 0, weeks = 0;
    (track || []).forEach(function (w) {
      var any = false;
      (w.items || []).forEach(function (x) { if (x.perf == null) return; any = true; items.push(x.perf); if (w.bench != null) { nb++; sb += w.bench; if (x.perf > w.bench) beat++; } });
      if (any) weeks++;
    });
    if (!items.length) return null;
    return { weeks: weeks, n: items.length, avg: items.reduce(function (a, b) { return a + b; }, 0) / items.length, bench: nb ? sb / nb : null, beatPct: nb ? beat / nb * 100 : null };
  };
  /**
   * Valorisation par rapport aux pairs : multiple de la société comparé à la médiane des sociétés de la même industrie
   * (au moins 5 pairs), sinon du même secteur. Banques, assurances, foncières : cours / actif net ; autres : VE / EBITDA,
   * à défaut PER prévisionnel. discountPct > 0 = moins chère que ses pairs. Données récentes, non historisées.
   */
  ES.peerValuation = function (inst) {
    var FIN = /financial|bank|insurance|real estate|reit/i;
    var num = function (v) { v = +v; return Number.isFinite(v) ? v : null; };
    var metricOf = function (f0) {
      if (!f0 || typeof f0 !== 'object') return null;
      var f = { sector: f0.sector, industry: f0.industry, priceToBook: num(f0.priceToBook), evToEbitda: num(f0.evToEbitda), forwardPE: num(f0.forwardPE) };
      var sec = String(f.sector || '') + ' ' + String(f.industry || '');
      if (FIN.test(sec)) return f.priceToBook > 0 && f.priceToBook < 20 ? { key: 'pb', label: 'cours / actif net', v: f.priceToBook } : null;
      if (f.evToEbitda > 0 && f.evToEbitda < 60) return { key: 'ev', label: 'VE / EBITDA', v: f.evToEbitda };
      if (f.forwardPE > 0 && f.forwardPE < 100) return { key: 'pe', label: 'PER prévisionnel', v: f.forwardPE };
      return null;
    };
    var rows = [];
    Object.keys(inst || {}).forEach(function (isin) {
      var f = inst[isin] && inst[isin].fund, m = metricOf(f);
      if (m) rows.push({ isin: isin, m: m, sector: f.sector || null, industry: f.industry || null, cap: +f.marketCap > 0 ? +f.marketCap : null });
    });
    var med = function (a) { a = a.slice().sort(function (x, y) { return x - y; }); var n = a.length; return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2; };
    var out = {};
    rows.forEach(function (r) {
      var pick = function (lvl) {
        var all = rows.filter(function (o) { return o.isin !== r.isin && o.m.key === r.m.key && o[lvl] && o[lvl] === r[lvl] && o.m.v > 0.5; });
        var near = r.cap ? all.filter(function (o) { return o.cap && o.cap >= r.cap / 10 && o.cap <= r.cap * 10; }) : [];
        var peers = (near.length >= 5 ? near : all).map(function (o) { return o.m.v; }); // taille comparable (×10 au plus) quand c'est possible
        return peers.length >= 5 ? { lvl: lvl, vals: peers } : null;
      };
      var p = pick('industry') || pick('sector');
      if (!p) return;
      var m = med(p.vals);
      if (!(m > 0) || r.m.v < m / 4 || r.m.v > m * 4) return; // multiple aberrant par rapport aux pairs (donnée suspecte) : pas de comparaison
      out[r.isin] = { metric: r.m.label, value: +r.m.v.toFixed(2), peerMedian: +m.toFixed(2), peers: p.vals.length, level: p.lvl === 'industry' ? 'industrie' : 'secteur',
        group: p.lvl === 'industry' ? ES.industryFr(r.industry) : ES.sectorFr(r.sector), discountPct: +((1 - r.m.v / m) * 100).toFixed(1) };
    });
    return out;
  };
  /**
   * Position concurrentielle : rang par chiffre d'affaires dans l'industrie (au moins 4 sociétés), parmi les sociétés suivies
   * par Euro Signal (cotées en France, Allemagne, Italie, Espagne, Pays-Bas, Belgique). Conversion approximative en euros.
   */
  ES.FX_EUR = { EUR: 1, USD: 0.92, GBP: 1.17, CHF: 1.06, SEK: 0.087, DKK: 0.134, NOK: 0.085, PLN: 0.23 };
  ES.marketPosition = function (inst) {
    var groups = {};
    Object.keys(inst || {}).forEach(function (isin) {
      var f = inst[isin] && inst[isin].fund, rev = f ? +f.revenue : NaN;
      if (!f || !(rev > 0) || !f.industry) return;
      var fx = ES.FX_EUR[f.currency || inst[isin].currency || '']; if (!fx) return; // devise inconnue : pas de comparaison
      var g = groups[f.industry] = groups[f.industry] || [];
      if (g.some(function (o) { return o.raw === rev; })) return; // même chiffre d'affaires = autre classe d'actions de la même société
      g.push({ isin: isin, rev: rev * fx, raw: rev });
    });
    var out = {};
    Object.keys(groups).forEach(function (ind) {
      var g = groups[ind].sort(function (a, b) { return b.rev - a.rev; });
      if (g.length < 5) return;
      var tot = g.reduce(function (a, x) { return a + x.rev; }, 0);
      g.forEach(function (x, k) {
        var share = x.rev / tot * 100;
        var big = x.rev >= 5e8; // moins de 500 M€ de chiffre d'affaires : jamais « leader » d'une industrie européenne
        var key = k === 0 && big ? 'leader' : k <= 2 && big ? 'challenger' : share < 3 || !big ? 'niche' : 'follower';
        out[x.isin] = { key: key, label: { leader: 'Leader', challenger: 'Challenger', follower: 'Suiveur', niche: 'Acteur de niche' }[key], rank: k + 1, of: g.length, industry: ES.industryFr(ind), sharePct: +share.toFixed(1), revenueEur: Math.round(x.rev) };
      });
    });
    return out;
  };
  /** Étoiles d'un coup d'œil : 5 = très fort et remarquable dans l'historique, 4 = très fort, 3 = fort, 2 = moyen, 1 = faible. */
  ES.stars = function (total, cfg, histKey) {
    var k = ES.scoreLabel(total, cfg).key;
    var n = k === 'top' ? (histKey === 'rare' ? 5 : 4) : k === 'strong' ? 3 : k === 'mid' ? 2 : 1;
    return { n: n, text: '★★★★★'.slice(0, n) + '☆☆☆☆☆'.slice(0, 5 - n) };
  };
  /**
   * Analyse des comptes annuels : tendances sur les derniers exercices et F-score de Piotroski (0 à 9).
   * fin : { years: [{ date, revenue, grossProfit, operatingIncome, netIncome, ebitda, interestExpense, totalAssets, currentAssets,
   *   currentLiabilities, totalDebt, longTermDebt, cash, equity, shares, cfo, capex, fcf }], currency }
   * opts.asOf : date d'analyse ; seuls les exercices clos au moins 120 jours avant sont utilisés (comptes publiés à cette date).
   * opts.sector / opts.industry : banques et assurances → F-score non applicable.
   */
  ES.accountsAnalysis = function (fin, opts) {
    opts = opts || {};
    var n = function (v) { v = +v; return Number.isFinite(v) ? v : null; };
    var limit = opts.asOf ? ES.addDays(opts.asOf, -120) : null;
    var Y = (fin && Array.isArray(fin.years) ? fin.years : []).filter(function (y) { return y && typeof y.date === 'string' && (!limit || y.date <= limit); })
      .sort(function (a, b) { return a.date < b.date ? -1 : 1; }).slice(-4).map(function (y) {
        var o = { date: y.date };
        ['revenue', 'grossProfit', 'operatingIncome', 'netIncome', 'ebitda', 'interestExpense', 'totalAssets', 'currentAssets', 'currentLiabilities', 'totalDebt', 'longTermDebt', 'cash', 'equity', 'shares', 'cfo', 'capex', 'fcf'].forEach(function (k) { o[k] = n(y[k]); });
        if (o.fcf == null && o.cfo != null && o.capex != null) o.fcf = o.cfo + o.capex; // capex négatif chez Yahoo
        return o;
      });
    if (!Y.length) return null;
    var sec = String(opts.sector || '') + ' ' + String(opts.industry || '');
    var fin_ = /financial|bank|insurance|banque|assurance|capital markets|asset management|credit services/i.test(sec);
    var div = function (a, b) { return a != null && b != null && b !== 0 ? a / b : null; };
    var rows = Y.map(function (y) {
      var nd = y.totalDebt != null && y.cash != null ? y.totalDebt - y.cash : null;
      return { date: y.date, year: y.date.slice(0, 4), revenue: y.revenue, opMargin: div(y.operatingIncome, y.revenue) != null ? div(y.operatingIncome, y.revenue) * 100 : null,
        netIncome: y.netIncome, netMargin: div(y.netIncome, y.revenue) != null ? div(y.netIncome, y.revenue) * 100 : null, fcf: y.fcf,
        netDebtEbitda: fin_ ? null : (y.ebitda > 0 && nd != null ? nd / y.ebitda : null), netCash: nd != null && nd < 0,
        roe: y.equity > 0 && y.netIncome != null ? y.netIncome / y.equity * 100 : null, equityRatio: div(y.equity, y.totalAssets) != null ? div(y.equity, y.totalAssets) * 100 : null };
    });
    var first = Y[0], last = Y[Y.length - 1], prev = Y.length > 1 ? Y[Y.length - 2] : null, out = { years: rows, n: Y.length, currency: (fin && fin.currency) || null, notes: [] };
    // Tendances lisibles
    var nyr = Y.length - 1;
    if (nyr >= 1 && first.revenue > 0 && last.revenue > 0) out.revenueCagr = (Math.pow(last.revenue / first.revenue, 1 / nyr) - 1) * 100;
    var r0 = rows[0], r1 = rows[rows.length - 1];
    if (nyr >= 1 && r0.opMargin != null && r1.opMargin != null) out.opMarginDelta = r1.opMargin - r0.opMargin;
    out.fcfPositiveYears = Y.filter(function (y) { return y.fcf != null && y.fcf > 0; }).length;
    out.fcfKnownYears = Y.filter(function (y) { return y.fcf != null; }).length;
    if (nyr >= 1 && first.shares > 0 && last.shares > 0) out.dilutionPct = (last.shares / first.shares - 1) * 100;
    if (last.interestExpense && last.operatingIncome != null) out.interestCover = last.operatingIncome / Math.abs(last.interestExpense);
    // F-score de Piotroski (Piotroski, 2000) : 9 critères binaires sur les deux derniers exercices
    if (fin_) out.fscore = { na: true, reason: 'non applicable aux banques, assurances et sociétés financières (comptes d\'une autre nature)' };
    else if (!prev) out.fscore = { na: true, reason: 'un seul exercice disponible' };
    else {
      var roa = function (y) { return div(y.netIncome, y.totalAssets); }, cr = function (y) { return div(y.currentAssets, y.currentLiabilities); };
      var lev = function (y) { return y.totalAssets ? (y.longTermDebt != null ? y.longTermDebt : y.totalDebt) / y.totalAssets : null; };
      var gm = function (y) { return div(y.grossProfit, y.revenue); }, ato = function (y) { return div(y.revenue, y.totalAssets); };
      var cmp = function (a, b, better) { return a == null || b == null ? null : better === 'up' ? a > b : a < b; };
      var crit = [
        ['roa', 'Bénéfice positif (rentabilité des actifs > 0)', roa(last) == null ? null : roa(last) > 0],
        ['cfo', 'Flux de trésorerie d\'exploitation positif', last.cfo == null ? null : last.cfo > 0],
        ['droa', 'Rentabilité des actifs en hausse sur un an', cmp(roa(last), roa(prev), 'up')],
        ['accrual', 'Trésorerie d\'exploitation supérieure au bénéfice (bénéfice de qualité)', last.cfo == null || last.netIncome == null ? null : last.cfo > last.netIncome],
        ['lev', 'Endettement à long terme en baisse (rapporté aux actifs)', lev(last) == null || lev(prev) == null ? null : lev(last) < lev(prev) || (lev(last) === 0 && lev(prev) === 0)],
        ['liq', 'Liquidité à court terme en hausse', cmp(cr(last), cr(prev), 'up')],
        ['shares', 'Pas de nouvelles actions émises (pas de dilution)', last.shares == null || prev.shares == null ? null : last.shares <= prev.shares * 1.01],
        ['gm', 'Marge brute en hausse', cmp(gm(last), gm(prev), 'up')],
        ['ato', 'Rotation des actifs en hausse (plus de ventes par euro d\'actif)', cmp(ato(last), ato(prev), 'up')]
      ].map(function (c) { return { k: c[0], label: c[1], ok: c[2] }; });
      var known = crit.filter(function (c) { return c.ok != null; }), pts = known.filter(function (c) { return c.ok; }).length;
      out.fscore = known.length >= 7 ? { score: pts, avail: known.length, f9: Math.round(pts * 9 / known.length), items: crit, year: last.date.slice(0, 4) }
        : { na: true, reason: 'comptes trop incomplets (' + known.length + ' critères sur 9 calculables)', items: crit };
    }
    // Verdict en une phrase
    var f = out.fscore && !out.fscore.na ? out.fscore.f9 : null, good = [], bad = [];
    if (out.revenueCagr != null) (out.revenueCagr >= 3 ? good : out.revenueCagr <= -3 ? bad : []).push('chiffre d\'affaires ' + (out.revenueCagr >= 0 ? '+' : '') + out.revenueCagr.toFixed(1).replace('.', ',') + ' % par an');
    if (out.opMarginDelta != null) (out.opMarginDelta >= 1 ? good : out.opMarginDelta <= -1 ? bad : []).push('marge opérationnelle ' + (out.opMarginDelta >= 0 ? '+' : '') + out.opMarginDelta.toFixed(1).replace('.', ',') + ' point' + (Math.abs(out.opMarginDelta) >= 2 ? 's' : ''));
    if (out.fcfKnownYears >= 2) (out.fcfPositiveYears === out.fcfKnownYears ? good : out.fcfPositiveYears === 0 ? bad : []).push('trésorerie disponible ' + (out.fcfPositiveYears === out.fcfKnownYears ? 'positive chaque année' : out.fcfPositiveYears === 0 ? 'négative chaque année' : 'irrégulière'));
    if (out.dilutionPct != null && out.dilutionPct >= 5) bad.push('dilution de ' + Math.round(out.dilutionPct) + ' % (nouvelles actions)');
    if (out.interestCover != null && out.interestCover < 2 && !fin_) bad.push(out.interestCover <= 0 ? 'résultat d\'exploitation négatif : intérêts non couverts' : 'intérêts peu couverts (résultat d\'exploitation = ' + out.interestCover.toFixed(1).replace('.', ',') + ' fois les intérêts)');
    var key = f == null ? (bad.length > good.length ? 'bad' : good.length > bad.length ? 'good' : 'mixed') : f >= 7 ? 'good' : f <= 3 ? 'bad' : 'mixed';
    if (f == null && !good.length && !bad.length) key = 'na';
    out.verdict = { key: key, good: good, bad: bad, text: ({ good: 'Comptes solides et en amélioration', mixed: 'Comptes mitigés', bad: 'Comptes en dégradation', na: 'Comptes insuffisants pour conclure' }[key]) + (f != null ? ' (F-score ' + f + '/9)' : '') };
    return out;
  };
  /**
   * Profil d'un acheteur au moment d'un achat (aucune donnée postérieure) :
   * - habituel ou inhabituel (Cohen, Malloy et Pomorski, 2012 : les achats « de routine », au même mois chaque année,
   *   n'annoncent rien ; les achats inhabituels sont ceux qui ont battu le marché) ;
   * - palmarès : ses achats passés (toutes sociétés), résultat 60 séances plus tard, comparé au CAC 40 ;
   * - conviction : montant record par rapport à ses propres achats passés.
   * hist : [{ date, eur, ret, excess }] achats significatifs passés de la même personne ; t : { date, eur } ; archiveFrom : début de l'archive.
   */
  ES.buyerProfile = function (hist, t, archiveFrom) {
    var d = t.date, before = (hist || []).filter(function (h) { return h && h.date < d && ES.daysBetween(h.date, d) > 20; });
    var month = d.slice(5, 7), y = +d.slice(0, 4), years = 0, seen = 0;
    for (var k = 1; k <= 3; k++) {
      var yy = String(y - k);
      if (archiveFrom && archiveFrom > yy + '-' + month + '-28') break; // ce mois-là n'est pas couvert par l'archive
      seen++;
      if (before.some(function (h) { return h.date.slice(0, 4) === yy && h.date.slice(5, 7) === month; })) years++;
    }
    // Acheteur en série : achats dans au moins 6 mois différents sur les 12 derniers = habituel, quel que soit le mois
    var y1 = {}; before.forEach(function (h) { if (ES.daysBetween(h.date, d) <= 365) y1[h.date.slice(0, 7)] = 1; });
    var monthsActive = Object.keys(y1).length;
    var routine = monthsActive >= 6 ? 'habituel' : !seen ? 'inconnu' : years >= 2 || (years >= 1 && seen === 1) ? 'habituel' : 'inhabituel';
    var done = before.filter(function (h) { return h.excess != null && ES.daysBetween(h.date, d) >= 90; });
    var track = done.length ? { n: done.length, up: done.filter(function (h) { return h.ret > 0; }).length, beat: done.filter(function (h) { return h.excess > 0; }).length,
      avgExcess: done.reduce(function (a, h) { return a + h.excess; }, 0) / done.length * 100 } : null;
    var amounts = before.map(function (h) { return h.eur; }).filter(function (v) { return v > 0; });
    var record = amounts.length >= 2 && t.eur > 0 ? t.eur >= 2 * Math.max.apply(null, amounts) : null;
    return { routine: routine, monthsActive: monthsActive, sameMonthYears: years, yearsSeen: seen, track: track, record: record, pastBuys: before.length, firstBuy: !before.length && !!archiveFrom && ES.daysBetween(archiveFrom, d) >= 365 };
  };
  /**
   * Humeur du marché (aspect psychologique) à une date : volatilité sur 20 séances comparée à l'année écoulée et recul
   * depuis le plus haut 52 semaines de l'indice européen. rows : séries ajustées [[date, o, h, l, c, v]].
   */
  ES.marketMood = function (rows, d) {
    if (!Array.isArray(rows) || rows.length < 260) return null;
    var k = -1; for (var q = rows.length - 1; q >= 0; q--) if (rows[q][0] <= d) { k = q; break; }
    if (k < 260) return null;
    var vol = function (e) { var r = []; for (var i = e - 19; i <= e; i++) r.push(Math.log(rows[i][4] / rows[i - 1][4])); var m = r.reduce(function (a, x) { return a + x; }, 0) / r.length; return Math.sqrt(r.reduce(function (a, x) { return a + (x - m) * (x - m); }, 0) / (r.length - 1)) * Math.sqrt(252) * 100; };
    var v = vol(k), past = []; for (var e = Math.max(21, k - 250); e < k; e += 5) past.push(vol(e));
    var pct = Math.round(past.filter(function (x) { return x < v; }).length / past.length * 100);
    var hi = Math.max.apply(null, rows.slice(k - 251, k + 1).map(function (r) { return r[4]; })), dd = (rows[k][4] / hi - 1) * 100;
    var r6 = (rows[k][4] / rows[k - 126][4] - 1) * 100;
    var key = pct >= 80 || dd <= -10 ? 'fear' : pct <= 20 && dd > -3 && r6 >= 12 ? 'greed' : 'neutral';
    return { key: key, volPct: Math.round(v * 10) / 10, volRank: pct, drawdownPct: Math.round(dd * 10) / 10, ret6m: Math.round(r6 * 10) / 10,
      icon: { fear: '😨', greed: '🤩', neutral: '😐' }[key], label: { fear: 'peur', greed: 'euphorie', neutral: 'calme' }[key],
      text: { fear: 'Marché européen dans la peur (volatilité plus forte que ' + pct + ' % de l\'année écoulée, ' + (Math.round(dd * 10) / 10).toString().replace('.', ',') + ' % sous son plus haut). Historiquement, les achats de dirigeants pendant les paniques de marché ont souvent été bien placés, mais la baisse peut durer.',
        greed: 'Marché européen euphorique (volatilité au plus bas, ' + (Math.round(r6 * 10) / 10).toString().replace('.', ',') + ' % en 6 mois, proche de ses plus hauts) : prudence, c\'est souvent le moment où les bonnes nouvelles sont déjà dans les cours.',
        neutral: 'Marché européen calme : ni peur ni euphorie.' }[key] };
  };
  /** Statistiques de résultats : [{ ret, excess }] (fractions) → probabilité de hausse, gain médian, fourchette, % battant le CAC 40. */
  /** Fonction d'un dirigeant publiée par Yahoo (« Chief Executive Officer », « CFO & Member of Management Board »…) → 'ceo' | 'cfo' | null. Adjoints exclus. */
  ES.officerRole = function (title) {
    var t = ES.norm(title || '');
    if (!t || /\b(deputy|vice|adjoint|delegue|stellvertret|interim|former|ancien|advisor|adviser|censor|conseiller|consultant)\b/.test(t)) return null;
    // « CEO of Orange France », « Division CEO of … », « Managing Director of Client » : dirigeant d'une filiale ou d'une division, pas du groupe
    t = t.replace(/\b(division|regional|country|segment|business unit)\s+(ceo|chief executive officer|cfo|managing director)\b[^&,]*/g, ' ')
      .replace(/\b(chief executive officer|ceo|managing director|executive managing director|md|cfo|chief financial officer|directeur general|directeur financier)\s+(of|de|du|des|d)\s+[^&,]*/g, ' ');
    if (/\b(ceo|chief executive|president directeur general|directeur general|directrice generale|vorstandsvorsitzende|vorsitzender des vorstands|chairman of the (management|executive) board|chair of the (management|executive) board|managing director|consejero delegado|amministratore delegato|chief executive officer)\b/.test(t)) return 'ceo';
    if (/\b(cfo|chief financial|finance director|financial director|directeur financier|directrice financiere|finanzvorstand|director financiero|direttore finanziario)\b/.test(t)) return 'cfo';
    return null;
  };
  /** Le déclarant (personne physique) figure-t-il parmi les dirigeants publiés comme DG ou DAF ? Tous les mots du nom le plus court (initiales exclues) doivent se retrouver dans l'autre, deux mots au moins. */
  ES.officerMatch = function (person, officers) {
    if (!person || !Array.isArray(officers)) return null;
    var toks = function (n) { return ES.personKey(n).split(' ').filter(function (w) { return w.length >= 2 && ['prof', 'ing', 'mag', 'phd', 'mba', 'jr', 'sir', 'dott', 'ir'].indexOf(w) < 0; }); };
    var a = toks(person);
    if (a.length < 2) return null;
    for (var k = 0; k < officers.length; k++) {
      var o = officers[k], role = o && ES.officerRole(o.title);
      if (!role) continue;
      var b = toks(o.name);
      if (b.length < 2) continue;
      var sm = a.length <= b.length ? a : b, lg = a.length <= b.length ? b : a;
      if (sm.every(function (w) { return lg.indexOf(w) > -1; })) return role;
    }
    return null;
  };
  /** Euro Signal ne suit que des sociétés européennes : un ISIN américain ou canadien sur une déclaration européenne trahit une confusion de société (ex. « CEG NV » rattaché à Constellation Energy). */
  ES.EUROPE_ISIN = 'AT BE BG CH CY CZ DE DK EE ES FI FO FR GB GG GI GR HR HU IE IM IS IT JE LI LT LU LV MC MT NL NO PL PT RO SE SI SK'.split(' ');
  ES.isEuropeanIsin = function (isin) { return typeof isin === 'string' && ES.EUROPE_ISIN.indexOf(isin.slice(0, 2).toUpperCase()) > -1; };
  ES.outcomeStats = function (list) {
    var r = (list || []).filter(function (x) { return x && x.ret != null && isFinite(x.ret); });
    if (!r.length) return null;
    var v = r.map(function (x) { return x.ret * 100; }).sort(function (a, b) { return a - b; });
    var q = function (p) { var i = (v.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return v[lo] + (v[hi] - v[lo]) * (i - lo); };
    var ex = r.filter(function (x) { return x.excess != null && isFinite(x.excess); });
    return { n: r.length, upPct: Math.round(r.filter(function (x) { return x.ret > 0; }).length / r.length * 100), mean: v.reduce(function (a, x) { return a + x; }, 0) / v.length,
      median: q(0.5), p25: q(0.25), p75: q(0.75), beatPct: ex.length ? Math.round(ex.filter(function (x) { return x.excess > 0; }).length / ex.length * 100) : null,
      meanExcess: ex.length ? ex.reduce(function (a, x) { return a + x.excess * 100; }, 0) / ex.length : null };
  };
  function pcS(v) { return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1).replace('.', ',') + ' %'; }
  /**
   * Fiabilité mesurée pour une note : résultats, 3 mois plus tard, des dossiers comparables des sélections passées rejouées.
   * rs : selection.replayStats. Rien si la note est sous le seuil de sélection ou si moins de 10 cas.
   */
  ES.comparables = function (rs, note, cfg) {
    if (!rs || note == null) return null;
    var top = ES.note(cfg.alerts.minScore, cfg), strong = ES.note(cfg.selection.minScore, cfg);
    if (note < strong) return null;
    var b = note >= top ? rs.top : rs.strong, scope = note >= top ? 'notes de ' + top + ' et plus' : 'notes de ' + strong + ' à ' + (top - 1);
    if (!b || b.n < 10) { b = rs.all; scope = 'toutes les sélections'; }
    if (!b || b.n < 10) return null;
    if (b.n < 30) return { n: b.n, upPct: b.upPct, median: b.median, p25: b.p25, p75: b.p75, beatPct: b.beatPct, scope: scope, few: true,
      text: 'seulement ' + b.n + ' dossiers passés mesurés, trop peu pour conclure (' + b.upPct + ' % en hausse à 3 mois, gain médian ' + pcS(b.median) + ')' };
    return { n: b.n, upPct: b.upPct, median: b.median, p25: b.p25, p75: b.p75, beatPct: b.beatPct, scope: scope,
      text: b.upPct + ' % en hausse 3 mois plus tard, gain médian ' + pcS(b.median) + ' (la moitié des cas entre ' + pcS(b.p25) + ' et ' + pcS(b.p75) + ')' + (b.beatPct != null ? ', ' + b.beatPct + ' % ont battu le CAC 40' : '') + ' — ' + b.n + ' dossiers passés, ' + scope };
  };
  /** Résumé de fiabilité pour l'email et la page « Méthode » : une ligne, chiffres réels, ou null s'il manque du recul. */
  ES.reliabilityText = function (rs) {
    var a = rs && rs.all;
    if (!a || a.n < 10) return null;
    return 'Fiabilité mesurée : sur ' + a.n + ' dossiers des sélections passées (rejouées' + (rs.from ? ' depuis le ' + ES.frDate(rs.from) : '') + '), ' + a.upPct + ' % étaient en hausse 3 mois plus tard, gain médian ' + pcS(a.median) +
      (a.beatPct != null ? ', ' + a.beatPct + ' % ont fait mieux que le CAC 40' : '') + ' (frais déduits). ' + (a.n < 30 ? 'Trop peu de cas pour conclure. ' : '') + (a.beatPct != null && a.beatPct >= 55 ? 'Encourageant, sans garantie.' : 'Pas encore d\'avantage net : à étudier, pas à acheter les yeux fermés.');
  };
  /**
   * Avis résumé pour une lecture rapide : au plus 3 raisons (signaux favorables) et 2 points d'attention (3 si « éviter »).
   * a : résultat de ES.advice.
   */
  ES.adviceSummary = function (a) {
    var pros = [], cons = [];
    if (!a) return { pros: pros, cons: cons };
    var sig = a.signals || [], has = {}, cap = function (s) { return s.charAt(0).toUpperCase() + s.slice(1); };
    var ICON = { '⚡': 'duel', '⚠️': 'short', '🔻': 'knife', '💸': 'rich', '🔁': 'routine', '🩺': 'fragile', '🚫': 'pea', '🔴': 'sellers', '📊': 'fscore', '👥': 'cluster', '👔': 'ceo', '🏷️': 'disc', '🧭': 'opportunistic', '💪': 'record', '😱': 'panic', '💶': 'cheap', '💰': 'big', '🏆': 'pos', '🏅': 'track', '📈': 'trend' };
    sig = sig.map(function (g) { return g.k ? g : Object.assign({ k: ICON[g.icon] || '' }, g); });
    sig.forEach(function (g) { has[g.k] = 1; });
    var PRI = ['cluster', 'ceo', 'disc', 'opportunistic', 'record', 'panic', 'cheap', 'fscore', 'big', 'pos', 'track', 'trend'];
    sig.filter(function (g) { return g.tone === 'good'; }).sort(function (x, y) { return PRI.indexOf(x.k) - PRI.indexOf(y.k); }).forEach(function (g) { pros.push(g.icon + ' ' + cap(g.text)); });
    var covered = /repli|valorisation|découvert|habituels|F-score/, ico = function (t) { return /résultats/.test(t) ? '📅 ' : /baissier/.test(t) ? '📉 ' : /euphorique/.test(t) ? '🤩 ' : /ordinaire|modeste|aucun achat/.test(t) ? '⚪ ' : ''; };
    var bad = sig.filter(function (g) { return g.tone === 'bad' && !(a.key === 'avoid' && /^(fragile|pea|sellers|fscore)$/.test(g.k)); }).map(function (g) { return g.icon + ' ' + cap(g.text); });
    var warn = sig.filter(function (g) { return g.tone === 'warn' && !(g.k === 'short' && has.duel); }).map(function (g) { return g.icon + ' ' + cap(g.text); });
    var other = [];
    a.why.forEach(function (w) {
      if (a.key === 'avoid') { other.push('🔴 ' + cap(w)); return; }
      if (/^vigilance : /.test(w)) { var t = w.slice(12); if (!covered.test(t)) other.push(ico(t) + cap(t)); }
      else if (/^(signal encore modeste|aucun achat)/.test(w)) other.push(ico(w) + cap(w)); // « ordinaire » : déjà dit par le repère historique affiché à côté
    });
    cons = a.key === 'avoid' ? other.concat(bad, warn) : bad.concat(warn.slice(0, 1), other, warn.slice(1));
    var seen = {};
    cons = cons.filter(function (c) { if (seen[c]) return false; seen[c] = 1; return true; });
    return { pros: pros.slice(0, 3), cons: cons.slice(0, a.key === 'avoid' ? 3 : 2), morePros: Math.max(0, pros.length - 3), moreCons: Math.max(0, cons.length - (a.key === 'avoid' ? 3 : 2)) };
  };
  /** Positions vendeuses nettes publiées (≥ 0,5 % du capital) en vigueur à une date. list : [{ holder, pct, from, to, country }] */
  ES.shortInfo = function (list, day) {
    var cur = (Array.isArray(list) ? list : []).filter(function (p) { return p && typeof p === 'object' && +p.pct >= 0.5 && +p.pct <= 25 && (!p.from || p.from <= day) && (!p.to || p.to > day); }).map(function (p) { return { holder: p.holder, pct: +p.pct, from: p.from, to: p.to }; });
    if (!cur.length) return null;
    var byHolder = {};
    cur.forEach(function (p) { var k = String(p.holder || '?').toLowerCase(); if (!byHolder[k] || p.from > byHolder[k].from) byHolder[k] = p; });
    var pos = Object.keys(byHolder).map(function (k) { return byHolder[k]; }).sort(function (a, b) { return b.pct - a.pct; });
    return { holders: pos.length, totalPct: +pos.reduce(function (a, p) { return a + p.pct; }, 0).toFixed(2), maxPct: pos[0].pct, top: pos.slice(0, 3).map(function (p) { return { holder: p.holder, pct: p.pct, from: p.from }; }) };
  };
  /** Critères mesurés sans poids dans le score (« en observation ») : promus seulement s'ils font leurs preuves. */
  ES.OBSERVE_FEATURES = [
    ['sectorStrong', 'Secteur plus fort que le marché sur 6 mois (rotation sectorielle)'],
    ['sectorBreadth', 'Achats de dirigeants dans 3 sociétés ou plus du même secteur (30 jours)'],
    ['smallMid', 'Petite ou moyenne valeur (capitalisation < 2 Md€)'],
    ['bigVsCap', 'Achat ≥ 0,05 % de la capitalisation'],
    ['peerCheap', 'Valorisation ≥ 20 % sous ses pairs'],
    ['shorted', 'Achat pendant que des fonds parient à la baisse (≥ 0,5 % du capital)'],
    ['fscoreHigh', 'Comptes solides : F-score de Piotroski ≥ 7 (comptes publiés à la date de l\'achat)'],
    ['opportunistic', 'Achat inhabituel pour ce dirigeant (pas au même mois les années précédentes)'],
    ['trackGood', 'Dirigeant dont les achats passés ont battu le CAC 40 au moins 2 fois sur 3'],
    ['personalRecord', 'Achat record pour ce dirigeant (au moins 2 fois son plus gros achat passé)'],
    ['marketFear', 'Achat pendant la peur du marché européen (volatilité dans les 20 % les plus hautes de l\'année ou recul de 10 %)']
  ];
  ES.observeStats = function (samples, cfg) {
    var L = cfg.learning, ok = (samples || []).filter(function (s) { return s.excess != null && isFinite(s.excess); });
    return ES.OBSERVE_FEATURES.map(function (f) {
      var w = ok.filter(function (s) { return s.f[f[0]] === true; }).map(function (s) { return s.excess * 100; });
      var wo = ok.filter(function (s) { return s.f[f[0]] === false; }).map(function (s) { return s.excess * 100; });
      var st = { feature: f[0], label: f[1], nWith: w.length, nWithout: wo.length, meanWith: w.length ? mean(w) : null, meanWithout: wo.length ? mean(wo) : null, t: null };
      if (w.length >= 2 && wo.length >= 2) {
        var v = function (a, m) { return a.reduce(function (x, y) { return x + (y - m) * (y - m); }, 0) / (a.length - 1); };
        var se = Math.sqrt(v(w, st.meanWith) / w.length + v(wo, st.meanWithout) / wo.length);
        st.t = se > 0 ? +((st.meanWith - st.meanWithout) / se).toFixed(2) : null;
      }
      st.action = w.length < L.minCases || wo.length < L.minCases ? 'en observation (' + w.length + ' / ' + L.minCases + ' cas)'
        : st.t != null && st.t >= L.minT ? 'apporte un avantage net : candidat à l\'entrée dans le score (revue de janvier)'
        : st.t != null && st.t <= -L.minT ? 'pénalisant sur nos données' : 'pas d\'écart net pour l\'instant';
      return st;
    });
  };
  /**
   * Repère historique : situe une note par rapport aux sélections passées rejouées (meilleurs dossiers de chaque semaine).
   * hist : notes des dossiers sélectionnés les semaines précédentes ; weekBest : meilleure note de chaque semaine.
   */
  ES.historicRank = function (note, hist) {
    var h = (hist || []).filter(function (x) { return x != null; });
    if (h.length < 10) return { key: 'na', label: 'repère historique en construction', pct: null };
    var below = h.filter(function (x) { return x < note; }).length, eq = h.filter(function (x) { return x === note; }).length;
    var pct = Math.round((below + eq / 2) / h.length * 100);
    if (pct >= 90) return { key: 'rare', icon: '🟢', label: 'remarquable : parmi les 10 % meilleurs dossiers des sélections passées', short: 'Remarquable', pct: pct };
    if (pct >= 60) return { key: 'good', icon: '🟡', label: 'bon dossier : au-dessus de la moyenne des sélections passées', short: 'Bon', pct: pct };
    return { key: 'wait', icon: '⚪', label: 'ordinaire : sous la moyenne des sélections passées, rien ne presse', short: 'Ordinaire', pct: pct };
  };
  ES.weekVerdict = function (items, weekBest) {
    var notes = (items || []).map(function (x) { return x.note; }).filter(function (x) { return x != null; });
    var wb = (weekBest || []).filter(function (x) { return x != null; });
    if (!notes.length) return { key: 'empty', text: 'Aucun dossier cette semaine : rien à faire.' };
    if (wb.length < 6) return { key: 'na', text: 'Repère historique en construction (' + wb.length + ' semaine' + (wb.length > 1 ? 's' : '') + ' rejouée' + (wb.length > 1 ? 's' : '') + ').' };
    var best = Math.max.apply(null, notes), rk = { pct: Math.round((wb.filter(function (x) { return x < best; }).length + wb.filter(function (x) { return x === best; }).length / 2) / wb.length * 100) };
    var rare = items.filter(function (x) { return x.hist && x.hist.key === 'rare'; }).length;
    if (rk.pct >= 80) return { key: 'strong', icon: '🟢', text: 'Semaine exceptionnelle : le signal le plus fort de la semaine dépasse celui de ' + rk.pct + ' % des ' + wb.length + ' semaines précédentes. Une semaine qui mérite un examen attentif des dossiers ; la force du signal n\'est pas une promesse de gain.' };
    if (rk.pct >= 40) return { key: 'normal', icon: '🟡', text: 'Semaine dans la moyenne (' + rk.pct + 'e centile sur ' + wb.length + ' semaines)' + (rare ? ' ; ' + rare + ' dossier' + (rare > 1 ? 's' : '') + ' remarquable' + (rare > 1 ? 's' : '') : '') + '. Acheter n\'a rien d\'urgent : une meilleure occasion peut venir.' };
    return { key: 'weak', icon: '⚪', text: 'Semaine faible (' + rk.pct + 'e centile sur ' + wb.length + ' semaines) : mieux vaut attendre les prochaines sélections.' };
  };
  ES.isVoluntaryBuy = function (t, cfg) {
    return t.type === 'achat' && !(cfg.insiders.excludePlanned && t.planned === true) && !ES.excludedEntity(t, cfg);
  };
  /** Nombre maximal d'acheteurs indépendants distincts dans une fenêtre glissante de N jours (dates de transaction). */
  ES.clusterInfo = function (buys, days) {
    var pts = buys.map(function (t) { return { d: t.txDate, k: ES.buyerKey(t) }; }).filter(function (p) { return p.k; })
      .sort(function (a, b) { return a.d < b.d ? -1 : 1; });
    var best = { count: 0, from: null, to: null, buyers: [] };
    for (var i = 0; i < pts.length; i++) {
      var end = ES.addDays(pts[i].d, days - 1), set = {}, lastD = pts[i].d;
      for (var j = i; j < pts.length && pts[j].d <= end; j++) { set[pts[j].k] = pts[j].d; lastD = pts[j].d; }
      var n = Object.keys(set).length;
      if (n > best.count) best = { count: n, from: pts[i].d, to: lastD, buyers: Object.keys(set) };
    }
    return best;
  };
  ES.toEur = function (amount, currency) { return amount != null && currency === 'EUR' ? amount : null; };

  /* =============================== Score =============================== */
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  /**
   * ctx: { inst, tx[], events{buybacks[], results[]}, refs{txId: priceRefs}, cfg, today }
   * Retour : familles détaillées, total, blocages, événements contributifs.
   */
  ES.score = function (ctx) {
    var cfg = ctx.cfg, W = cfg.weights, today = ctx.today, from = ES.windowStart(today, cfg.insiders.windowMonths);
    var fam = {}, contributing = [];
    function F(key, label) { fam[key] = { key: key, label: label, items: [], raw: 0, points: 0, cap: W[key].cap }; return fam[key]; }
    function add(f, label, pts, ev) { f.items.push({ label: label, points: pts }); f.raw += pts; if (ev) contributing.push(ev); }

    // --- Initiés
    var fi = F('insiders', 'Initiés'), wi = W.insiders;
    var inWin = ES.activeTx(ctx.tx).filter(function (t) { return ES.availDate(t) >= from && ES.availDate(t) <= today; });
    var belowMkt = function (t) { var r = ctx.refs && ctx.refs[t.id]; return !!(r && r.belowMarket); };
    var lateDays = function (t) { return t.pubDate && t.txDate ? ES.daysBetween(t.txDate, t.pubDate) : 0; };
    var cand = inWin.filter(function (t) { return ES.isVoluntaryBuy(t, cfg); });
    var sig = ES.significantBuys(cand.filter(function (t) { return !belowMkt(t) && lateDays(t) <= cfg.insiders.maxFilingLagDays; }), cfg);
    var buys = sig.kept, nSmall = sig.small.length;
    var nBelow = cand.filter(belowMkt).length, nLate = cand.filter(function (t) { return !belowMkt(t) && lateDays(t) > cfg.insiders.maxFilingLagDays; }).length;
    var sells = inWin.filter(function (t) { return t.type === 'vente'; });
    var corpBuys = inWin.filter(function (t) { return t.type === 'achat' && ES.excludedEntity(t, cfg); }).length;
    var holdBuys = buys.filter(function (t) { return t.associated && ES.isLegalEntity(t.person, t.issuer); }).length;
    var buyEur = 0, buyUnknown = 0, discount = null, panic = null, clusterOut = null;
    buys.forEach(function (t) { var e = ES.toEur(t.amount, t.currency); if (e == null) buyUnknown++; else buyEur += e; });
    var sellEur = sells.reduce(function (s, t) { return s + (ES.toEur(t.amount, t.currency) || 0); }, 0);
    if (buys.length) {
      add(fi, buys.length + ' achat(s) volontaire(s) publiés depuis le ' + from, wi.anyBuy);
      buys.forEach(function (t) { contributing.push({ id: 'tx:' + t.id, date: ES.availDate(t), kind: 'initie', ambiguous: false }); });
      if (buyEur >= cfg.insiders.bigAmountEur) add(fi, 'montant cumulé ' + fmtEur(buyEur) + ' ≥ ' + fmtEur(cfg.insiders.bigAmountEur), wi.amountBig);
      if (buyUnknown) add(fi, buyUnknown + ' achat(s) au montant en euros inconnu : non comptés dans le montant', 0);
      var cl = ES.clusterInfo(buys, cfg.insiders.clusterWindowDays);
      if (cl.count >= 2) {
        // Regroupement des achats du cluster : un acheteur = une ligne (proches rattachés à leur dirigeant)
        var inCl = buys.filter(function (t) { return t.txDate >= cl.from && t.txDate <= cl.to && ES.buyerKey(t); }), per = {};
        inCl.forEach(function (t) {
          var k = ES.buyerKey(t), p = per[k] = per[k] || { name: t.associated ? (t.linkedTo || t.person) : t.person, role: t.associated ? null : t.role, ceo: false, eur: 0, n: 0, dates: {} };
          if (!t.associated) { p.name = t.person; p.role = t.role; }
          p.ceo = p.ceo || !!(t.ceo || t.cfo); p.eur += ES.toEur(t.amount, t.currency) || 0; p.n++; p.dates[t.txDate] = 1;
        });
        var buyers = Object.keys(per).map(function (k) { return per[k]; }).sort(function (a, b) { return b.eur - a.eur; });
        var total = buyers.reduce(function (x, b) { return x + b.eur; }, 0), amts = buyers.map(function (b) { return b.eur; }).filter(function (v) { return v > 0; });
        var spanDays = ES.daysBetween(cl.from, cl.to), m = amts.length ? amts.reduce(function (x, y) { return x + y; }, 0) / amts.length : 0;
        var cv = amts.length > 2 && m > 0 ? Math.sqrt(amts.reduce(function (x, y) { return x + (y - m) * (y - m); }, 0) / amts.length) / m : null;
        // Tous le même jour (ou presque) avec des montants proches : souvent un programme collectif organisé plutôt que des convictions indépendantes
        var coordinated = buyers.length >= cfg.insiders.clusterMinBuyers && spanDays <= 2 && cv != null && cv < 0.35;
        clusterOut = { count: cl.count, from: cl.from, to: cl.to, totalEur: total, buyers: buyers.map(function (b) { return { name: b.name, role: b.role, ceo: b.ceo, eur: b.eur, n: b.n }; }), coordinated: coordinated };
        var names = buyers.slice(0, 4).map(function (b) { return (b.name || '?') + (b.ceo ? ' (DG/DAF)' : ''); }).join(', ') + (buyers.length > 4 ? ' et ' + (buyers.length - 4) + ' autre(s)' : '');
        if (cl.count >= cfg.insiders.clusterMinBuyers) add(fi, 'cluster : ' + cl.count + ' dirigeants indépendants entre le ' + cl.from + ' et le ' + cl.to + (total ? ' (' + fmtEur(total) + ' au total)' : '') + ' : ' + names, wi.cluster);
        else add(fi, '2 dirigeants indépendants sur ' + cfg.insiders.clusterWindowDays + ' jours : ' + names, wi.pair);
        if (coordinated) add(fi, 'achats groupés sur ' + (spanDays + 1) + ' jour(s) avec des montants proches : possible programme collectif organisé par la société, signal moins fort qu\'il n\'y paraît', wi.coordinatedCluster);
      }
      var unattached = buys.filter(function (t) { return t.associated && !t.linkedTo; }).length;
      if (unattached) add(fi, unattached + ' achat(s) de personnes liées sans dirigeant identifié : exclus du comptage des acheteurs', 0);
      if (buys.some(function (t) { return t.ceo || t.cfo; })) add(fi, 'achat du directeur général ou du directeur financier', wi.ceoCfo);
      var per = {};
      buys.forEach(function (t) { var k = ES.buyerKey(t); if (k) (per[k] = per[k] || {})[t.txDate] = 1; });
      if (Object.keys(per).some(function (k) { return Object.keys(per[k]).length >= 2; })) add(fi, 'achats répétés par un même dirigeant (dates distinctes)', wi.repeat);
      buys.forEach(function (t) {
        var r = ctx.refs && ctx.refs[t.id], a = r && r.atPurchase;
        if (!a || a.paidVsHigh52Pct == null || r.outOfRange) return; // prix payé incohérent avec les cours (mauvaise cotation, devise, opération sur titres)
        var d = -a.paidVsHigh52Pct;
        if (!discount || d > discount.pct) discount = { pct: d, pos52: a.paidPos52, high52: a.ex52 && a.ex52.high, high52Date: a.ex52 && a.ex52.highDate, paid: r.paidAdj, date: t.txDate, person: t.person, ceo: t.ceo || t.cfo, amount: t.amount, currency: t.currency, id: t.id, full52: a.full52 };
      });
      if (discount && discount.pct >= wi.discountBigPct) add(fi, 'prix payé ' + Math.round(discount.pct) + ' % sous le plus haut 52 semaines (' + discount.date + ')' + (discount.pos52 != null && discount.pos52 <= cfg.insiders.nearLowPct ? ', près du plus bas' : ''), wi.discountBig);
      else if (discount && discount.pct >= wi.discountMediumPct) add(fi, 'prix payé ' + Math.round(discount.pct) + ' % sous le plus haut 52 semaines (' + discount.date + ')', wi.discountMedium);
      buys.forEach(function (t) {
        var r = ctx.refs && ctx.refs[t.id], a = r && !r.outOfRange && r.atPurchase;
        if (a && ES.isPanic(a, wi) && !panic) panic = { date: t.txDate, drop10: a.drop10, rsi14: a.rsi14 };
      });
      if (panic) add(fi, 'achat pendant une vente panique (' + [panic.drop10 != null && panic.drop10 <= -wi.panicDropPct ? 'chute de ' + Math.round(-panic.drop10) + ' % en 10 séances' : null, panic.rsi14 != null && panic.rsi14 <= wi.panicRsi ? 'RSI ' + Math.round(panic.rsi14) : null].filter(Boolean).join(', ') + ', le ' + panic.date + ')', wi.panicBuy);
      // « achat près du plus bas » : fusionné dans la décote (les deux mesuraient presque la même chose)
    }
    if (sells.length) {
      if (sellEur > buyEur && sellEur > 0) add(fi, 'ventes d\'initiés (' + fmtEur(sellEur) + ') supérieures aux achats', wi.netSeller);
      if (sells.some(function (t) { return t.ceo || t.cfo; })) add(fi, 'vente du directeur général ou du directeur financier', wi.ceoCfoSale);
    }
    if (nSmall) add(fi, nSmall + ' petit(s) achat(s) (moins de ' + fmtEur(cfg.insiders.minBuyerEur) + ' investis par le dirigeant sur ' + cfg.insiders.clusterWindowDays + ' jours) : ignorés', 0);
    if (nBelow) add(fi, nBelow + ' achat(s) à un prix très inférieur au cours du jour (exercice d\'options, plan, livraison) : exclus', 0);
    if (nLate) add(fi, nLate + ' achat(s) déclaré(s) plus de ' + cfg.insiders.maxFilingLagDays + ' jours après l\'opération : information ancienne, exclus', 0);
    if (corpBuys) add(fi, corpBuys + ' achat(s) par une société qui n\'est pas la holding d\'un dirigeant (fonds, investisseur, émetteur) : exclus', 0);
    if (holdBuys) add(fi, holdBuys + ' achat(s) via la holding personnelle d\'un dirigeant : comptés comme les siens', 0);
    var nonVol = inWin.filter(function (t) { return ['attribution', 'option', 'souscription', 'transfert', 'don', 'nantissement', 'dividende', 'instrument', 'autre_nv'].indexOf(t.type) > -1; }).length;
    if (nonVol) add(fi, nonVol + ' opération(s) non volontaire(s) (attributions, options, souscriptions…) : ignorées', 0);
    var ambiguous = inWin.filter(function (t) { return t.type === 'inconnu' || t.type === 'autre'; });
    if (ambiguous.length) add(fi, ambiguous.length + ' déclaration(s) ambiguë(s) : à vérifier manuellement', 0);

    // --- Rachats
    var fb = F('buyback', 'Rachats d\'actions'), wb = W.buyback;
    var bbs = (ctx.events && ctx.events.buybacks || []).filter(function (e) { return e.date >= from && e.date <= today; });
    var conf = bbs.filter(function (e) { return e.confirmed; });
    var cand = bbs.filter(function (e) { return !e.confirmed; });
    var ann = conf.filter(function (e) { return e.stage === 'annonce' || e.stage === 'debut'; });
    if (ann.length) {
      add(fb, 'programme de rachat annoncé (' + ann[ann.length - 1].date + ')', wb.announced, { id: 'bb:' + ann[ann.length - 1].id, date: ann[ann.length - 1].date, kind: 'rachat' });
      if (ann.some(function (e) { return e.pctCapital != null && e.pctCapital >= wb.largeSizePct; })) add(fb, 'taille ≥ ' + wb.largeSizePct + ' % du capital', wb.largeSize);
    }
    var exe = conf.filter(function (e) { return e.stage === 'execution'; });
    if (exe.length) add(fb, 'rachats effectivement exécutés (' + exe[exe.length - 1].date + ')', wb.executing, { id: 'bb:' + exe[exe.length - 1].id, date: exe[exe.length - 1].date, kind: 'rachat' });
    if (conf.some(function (e) { return e.stage === 'autorisation_ag'; }) && !ann.length) add(fb, 'autorisation d\'assemblée seule (routine, non comptée)', 0);
    if (conf.some(function (e) { return e.stage === 'suspension' || e.stage === 'annulation'; })) add(fb, 'programme suspendu ou annulé', wb.suspended);
    if (cand.length) add(fb, cand.length + ' mention(s) non confirmée(s) : candidat à vérifier', 0);

    // --- Résultats
    var fr = F('results', 'Résultats et perspectives'), wr = W.results;
    var res = (ctx.events && ctx.events.results || []).filter(function (e) { return e.pubDate >= from && e.pubDate <= today; })
      .sort(function (a, b) { return a.pubDate < b.pubDate ? -1 : 1; });
    var lastRes = res[res.length - 1];
    if (lastRes) {
      var ev = { id: 'res:' + lastRes.id, date: lastRes.pubDate, kind: 'resultats' }, used = false;
      var consOk = lastRes.consensusDate && lastRes.consensusDate < lastRes.pubDate && lastRes.comparable === true;
      if (!consOk) add(fr, 'consensus non validé (antériorité ou comparabilité) : surprise non comptée, validation manuelle requise', 0);
      else {
        var eps = ES.surprise(lastRes.epsActual, lastRes.epsConsensus), rev = ES.surprise(lastRes.revActual, lastRes.revConsensus);
        if (eps != null) {
          if (eps >= wr.epsStrongPct) { add(fr, 'BPA supérieur au consensus de ' + eps.toFixed(1) + ' %', wr.epsStrong); used = true; }
          else if (eps >= wr.epsMildPct) { add(fr, 'BPA supérieur au consensus de ' + eps.toFixed(1) + ' %', wr.epsMild); used = true; }
          else if (eps < 0) add(fr, 'BPA inférieur au consensus de ' + Math.abs(eps).toFixed(1) + ' %', wr.epsMiss);
        }
        if (rev != null) {
          if (rev >= wr.revStrongPct) { add(fr, 'chiffre d\'affaires supérieur au consensus de ' + rev.toFixed(1) + ' %', wr.revStrong); used = true; }
          else if (rev > wr.revMildPct) { add(fr, 'chiffre d\'affaires supérieur au consensus de ' + rev.toFixed(1) + ' %', wr.revMild); used = true; }
        }
      }
      if (lastRes.guidance === 'relevee') { add(fr, 'perspectives relevées', wr.guidanceRaised); used = true; }
      else if (lastRes.guidance === 'abaissee') add(fr, 'perspectives abaissées', wr.guidanceLowered);
      else if (lastRes.guidance === 'maintenue') add(fr, 'perspectives maintenues', 0);
      if (used) contributing.push(ev);
    }

    // --- Confirmation de marché
    var fm = F('market', 'Confirmation de marché'), wm = W.market, s = ctx.inst.stats || {};
    if (s.sessions) {
      var firstBuy = buys.length ? buys.map(function (t) { return t.txDate; }).sort()[0] : null;
      if (s.sma50 && s.sma200 && s.sma50 > s.sma200) {
        add(fm, 'tendance de fond haussière (MM50 au-dessus de la MM200)', wm.trend);
        if (firstBuy && s.goldenCrossDate && s.goldenCrossDate >= firstBuy) add(fm, 'croisement survenu le ' + s.goldenCrossDate + ', après l\'achat d\'un dirigeant (' + firstBuy + ')', wm.goldenCrossAfterBuy);
      }
      if (s.volRatio5_60 != null && s.volRatio5_60 >= wm.volumeRatio && s.ret1m > 0) add(fm, 'volumes 5 j = ' + s.volRatio5_60.toFixed(1) + '× la moyenne 60 j, en hausse', wm.volume);
      // performance 3 mois : fusionnée dans la force relative 6 mois
      if (s.adv20Eur != null && s.adv20Eur >= wm.liquidityEur) add(fm, 'liquidité ' + fmtEur(s.adv20Eur) + '/jour', wm.liquidity);
      if (s.rel6m != null && isFinite(s.rel6m)) {
        if (s.rel6m >= wm.relStrengthPts) add(fm, 'plus fort que le marché européen sur 6 mois (' + (s.rel6m > 0 ? '+' : '') + s.rel6m.toFixed(0) + ' points, hors dernier mois)', wm.relStrength);
        else if (s.rel6m <= -wm.relWeakPts) add(fm, 'nettement plus faible que le marché européen sur 6 mois (' + s.rel6m.toFixed(0) + ' points)', 0);
      }
      if (s.marketAbove200 === false) add(fm, 'marché européen sous sa moyenne 200 séances : environnement baissier, prudence', 0);
      // Leçon Rheinmetall 2026 : un dirigeant qui achète en pleine baisse n'indique pas le point bas
      var knife = cfg.insiders.fallingKnifeNote && buys.length && s.sma50 && s.sma200 && s.lastCloseAdj < s.sma50 && s.lastCloseAdj < s.sma200;
      if (knife) add(fm, 'cours en repli (passé sous ses moyennes 50 et 200 séances) : un achat de dirigeant ne marque pas forcément le point bas, entrer en plusieurs fois', 0);
    }

    var total = 0, families = 0;
    Object.keys(fam).forEach(function (k) {
      var f = fam[k]; f.points = clamp(f.raw, W[k].floor || 0, W[k].cap); total += f.points;
      f.capped = f.raw > W[k].cap;
    });
    ['insiders', 'buyback', 'results'].forEach(function (k) { if (fam[k].points > 0) families++; });
    var marketFamily = fam.market.points > 0;
    total = clamp(Math.round(total), 0, 100);
    contributing.sort(function (a, b) { return a.date < b.date ? 1 : -1; });
    // Libellés affichés : dates à la française, « entre le X et le X » → « le X »
    Object.keys(fam).forEach(function (k) { fam[k].items.forEach(function (it) { it.label = ES.frText(it.label); }); });
    return {
      version: cfg.scoringVersion, total: total, families: fam,
      eventFamilies: families, independentFamilies: families + (marketFamily ? 1 : 0),
      contributing: contributing, lastEventDate: contributing.length ? contributing[0].date : null,
      ambiguousCount: ambiguous.length, windowFrom: from,
      txInWindow: inWin, buys: buys, sells: sells, buyEur: buyEur, sellEur: sellEur, discount: discount,
      fallingKnife: !!(buys.length && s.sma50 && s.sma200 && s.lastCloseAdj < s.sma50 && s.lastCloseAdj < s.sma200),
      panicBuy: panic, cluster: clusterOut,
      trendUp: !!(s.sma50 && s.sma200 && s.sma50 > s.sma200), marketDown: s.marketAbove200 === false, rel6m: s.rel6m != null ? s.rel6m : null, goldenCrossAfterBuy: !!(buys.length && s.sma50 > s.sma200 && s.goldenCrossDate && s.goldenCrossDate >= buys.map(function (t) { return t.txDate; }).sort()[0])
    };
  };
  ES.surprise = function (actual, consensus) {
    if (actual == null || consensus == null || consensus === 0) return null;
    return (actual - consensus) / Math.abs(consensus) * 100;
  };

  /* ===================== Qualité et couverture ===================== */
  ES.quality = function (ctx) {
    var cfg = ctx.cfg, s = ctx.inst.stats || {}, items = [], total = 0;
    function add(label, pts, max, ok) { items.push({ label: label, points: pts, max: max, ok: ok }); total += pts; }
    var sess = s.sessions || 0;
    add('Historique : ' + sess + ' séances (' + cfg.universe.minSessions + ' attendues)', Math.round(20 * Math.min(1, sess / cfg.universe.minSessions)), 20, sess >= cfg.universe.minSessions);
    var fresh = sess && s.staleBusinessDays <= cfg.universe.maxStaleBusinessDays;
    add(fresh ? 'Cours à jour (' + s.lastDate + ')' : sess ? 'Cours périmé (' + s.lastDate + ')' : 'Aucun cours', fresh ? 20 : 0, 20, !!fresh);
    var cov = ES.coverage(ctx.inst, ctx.sources, cfg, ctx.today);
    add(cov.label, cov.ok ? 20 : 0, 20, cov.ok);
    var tw = ctx.score ? ctx.score.txInWindow : [];
    if (tw.length) {
      var complete = tw.filter(function (t) { return t.price != null && (t.qty != null || t.amount != null) && t.sourceUrl && t.pubDate; }).length;
      add('Déclarations complètes (prix, taille, date de publication, lien) : ' + complete + '/' + tw.length, Math.round(15 * complete / tw.length), 15, complete === tw.length);
    } else add('Aucune déclaration dans la fenêtre (rien à contrôler)', 15, 15, true);
    var pea = ctx.inst.peaStatus;
    var peaOk = (pea === 'eligible' || pea === 'non_eligible') && ctx.inst.peaSource && ctx.inst.peaDate;
    add(peaOk ? 'Éligibilité PEA documentée (' + ctx.inst.peaSource + ', ' + ctx.inst.peaDate + ')' : 'Éligibilité PEA à vérifier', peaOk ? 10 : 0, 10, !!peaOk);
    var res = (ctx.events && ctx.events.results || []).filter(function (e) { return e.pubDate >= ES.addMonths(ctx.today, -4); });
    var valid = res.filter(function (e) { return e.comparable === true && e.consensusDate && e.consensusDate < e.pubDate; });
    add(valid.length ? 'Résultats récents avec consensus validé' : res.length ? 'Résultats récents sans consensus validé' : 'Aucun résultat récent renseigné', valid.length ? 15 : res.length ? 7 : 0, 15, valid.length > 0);
    return { total: total, items: items, coverage: cov };
  };
  /** Couverture des déclarations d'initiés pour le pays de domiciliation de l'émetteur. */
  ES.coverage = function (inst, sources, cfg, today) {
    var home = inst.country && cfg.sources.registryByCountry[inst.country];
    if (inst.registry && home && home !== inst.registry) { // ex. société allemande dont les déclarations viennent de l'AMF : la BaFin doit aussi être à jour
      var a = ES.coverage(Object.assign({}, inst, { registry: null }), sources, cfg, today);
      if (!a.ok) return a;
    }
    var country = inst.country, reg = inst.registry || cfg.sources.registryByCountry[country];
    if (inst.registry) {
      var rs = sources && sources[inst.registry];
      if (!rs || rs.status === 'echec' || !rs.lastSuccess) return { ok: false, label: 'Registre ' + inst.registry + ' : collecte en échec ou jamais réussie' };
      if (rs.status === 'absent') return { ok: false, label: 'Registre ' + inst.registry + ' : source non configurée' + (rs.note ? ' (' + rs.note + ')' : '') };
      if (rs.status === 'partiel') return { ok: false, label: 'Registre ' + inst.registry + ' : collecte partielle' + (rs.note ? ' (' + rs.note + ')' : '') };
      var rage = ES.daysBetween(rs.lastSuccess, today);
      if (rage > cfg.sources.maxRegistryAgeDays) return { ok: false, label: 'Registre ' + inst.registry + ' : dernière collecte réussie il y a ' + rage + ' jours' };
      return { ok: true, label: 'Déclarations collectées via ' + inst.registry + (rs.via ? ' (' + rs.via + ')' : '') + ' le ' + rs.lastSuccess, source: inst.registry };
    }
    if (!country) return { ok: false, label: 'Pays de domiciliation inconnu : registre compétent indéterminé' };
    var cands = [];
    if (reg) cands.push(reg);
    if (cfg.sources.acceptAggregatorsAsCoverage) cands.push('Insider Screener', 'Duceus');
    var best = null;
    cands.forEach(function (n) {
      var src = sources && sources[n];
      if (!src || src.status === 'echec' || !src.lastSuccess) return;
      var cov = src.countries ? src.countries.indexOf(country) > -1 : n === reg;
      if (!cov) return;
      var age = ES.daysBetween(src.lastSuccess, today);
      if (age <= cfg.sources.maxRegistryAgeDays && (!best || src.lastSuccess > best.lastSuccess)) best = { name: n, lastSuccess: src.lastSuccess, age: age };
    });
    if (!best) return { ok: false, label: 'Couverture des initiés ' + country + ' non à jour (' + (reg || 'registre non défini') + ' : aucune collecte réussie depuis ' + cfg.sources.maxRegistryAgeDays + ' jours)' };
    return { ok: true, label: 'Initiés ' + country + ' collectés via ' + best.name + ' le ' + best.lastSuccess, source: best.name };
  };

  /* ================= Sentiment et surchauffe (expérimental) ================= */
  ES.overheat = function (inst, cfg) {
    var s = inst.stats || {}, o = cfg.overheat, items = [], total = 0;
    function add(l, p) { items.push({ label: l, points: p }); total += p; }
    if (s.rsi14 != null) { if (s.rsi14 >= o.rsiExtreme) add('RSI 14 = ' + Math.round(s.rsi14) + ' (extrême)', 35); else if (s.rsi14 >= o.rsiHigh) add('RSI 14 = ' + Math.round(s.rsi14), 25); }
    if (s.distSma50 != null && s.distSma50 >= o.distSma50Pct) add('cours ' + Math.round(s.distSma50) + ' % au-dessus de la moyenne 50 séances', 20);
    if (s.ret1m != null && s.ret1m >= o.ret1mPct) add('hausse de ' + Math.round(s.ret1m) + ' % en un mois', 20);
    if (s.upVolumeSpike) add('séance de hausse avec volume > 3× la moyenne', 15);
    if (inst.shorts) add('positions vendeuses publiées : ' + String(inst.shorts.totalPct).replace('.', ',') + ' % du capital (' + inst.shorts.holders + ' fonds), information non notée', 0);
    if (inst.revision30d != null && isFinite(inst.revision30d)) add('révision du BPA annuel estimé par les analystes sur 30 jours : ' + (inst.revision30d > 0 ? '+' : '') + inst.revision30d.toFixed(1) + ' % (information, non notée)', 0);
    var unavailable = ['recherches Google (non accessibles)', 'tonalité des actualités (non mesurée)', 'flux institutionnels (non observables de façon fiable)'].concat(inst.revision30d == null ? ['révisions d\'analystes (non disponibles pour ce titre)'] : []);
    return { total: Math.min(100, total), items: items, unavailable: unavailable, experimental: true };
  };

  /* ============================ Alertes ============================ */
  /**
   * Décision d'envoi. Toutes les conditions sont listées, réussies ou non.
   * sentEventIds : identifiants d'événements déjà inclus dans une alerte envoyée ou à l'état incertain.
   */
  ES.alertDecision = function (a) {
    var cfg = a.cfg, c = [], blocks = [];
    function cond(label, ok, blocking) { c.push({ label: label, ok: ok }); if (!ok) blocks.push(label); }
    var uni = a.universe;
    cond('Titre admissible dans l\'univers' + (uni.status !== 'retenu' ? ' (' + uni.reasons.join(' ; ') + ')' : ''), uni.status === 'retenu');
    if (cfg.pea.strict) cond('Éligibilité PEA confirmée (mode strict)', a.inst.peaStatus === 'eligible' && !!a.inst.peaSource && !!a.inst.peaDate);
    cond('Qualité des données ≥ ' + cfg.quality.minForAlert + ' (' + a.quality.total + ')', a.quality.total >= cfg.quality.minForAlert);
    cond('Couverture des initiés à jour pour le pays', a.quality.coverage.ok);
    cond('Score ≥ ' + cfg.alerts.minScore + ' (' + a.score.total + ')', a.score.total >= cfg.alerts.minScore);
    cond('Au moins ' + cfg.alerts.minFamilies + ' familles de signaux indépendantes (' + a.score.independentFamilies + ', dont au moins une famille d\'événement)', a.score.independentFamilies >= cfg.alerts.minFamilies && a.score.eventFamilies >= 1);
    var recentFrom = ES.addDays(a.today, -cfg.alerts.recentEventDays);
    cond('Événement publié depuis le ' + recentFrom + (a.score.lastEventDate ? ' (dernier : ' + a.score.lastEventDate + ')' : ' (aucun)'), !!a.score.lastEventDate && a.score.lastEventDate >= recentFrom);
    cond('Aucune déclaration ambiguë dans la fenêtre', a.score.ambiguousCount === 0);
    var health = ES.financialHealth(a.inst.fund);
    if (cfg.alerts.blockFragile) cond('Solidité financière non fragile' + (health.status === 'fragile' ? ' (' + health.reasons.join(' ; ') + ')' : health.status === 'inconnu' ? ' (données indisponibles : à vérifier)' : ''), health.status !== 'fragile');
    if (cfg.overheat.blockAlertsAbove != null) cond('Surchauffe < ' + cfg.overheat.blockAlertsAbove, a.overheat.total < cfg.overheat.blockAlertsAbove);
    var ids = a.score.contributing.map(function (e) { return e.id; });
    var fresh = ids.filter(function (id) { return !(a.sentEventIds || {})[id]; });
    cond('Information nouvelle, non encore signalée (' + fresh.length + ' événement(s) nouveau(x))', fresh.length > 0);
    var fp = ES.hash(a.inst.isin + '|' + ids.slice().sort().join(','));
    return { send: blocks.length === 0, conditions: c, blocking: blocks, fingerprint: fp, eventIds: ids, newEventIds: fresh };
  };

  /* ========================= Validation statistique ========================= */
  /**
   * Étude d'événements point-in-time : entrée à l'ouverture (ou clôture) de la première séance
   * STRICTEMENT postérieure à la date de publication ; sortie à la clôture h séances plus tard.
   * events : [{isin, date, group}] ; series : {isin: {rows, splits}} ; bench : {rows, splits} | null
   */
  ES.forwardExcess = function (adj, benchAdj, benchIdx, date, h, cost) {
    var i = 0; while (i < adj.length && adj[i][0] <= date) i++;
    if (i >= adj.length || i + h >= adj.length || !benchAdj) return null;
    var j = i + h, entry = adj[i][1] != null ? adj[i][1] : adj[i][4];
    if (benchIdx[adj[i][0]] == null || benchIdx[adj[j][0]] == null) return null;
    var b0 = benchAdj[benchIdx[adj[i][0]]], b1 = benchAdj[benchIdx[adj[j][0]]];
    return (adj[j][4] / entry - 1 - cost) - (b1[4] / (b0[1] != null ? b0[1] : b0[4]) - 1);
  };
  /**
   * Auto-apprentissage encadré : chaque mois, chaque composante est comparée sur les résultats réels
   * (achats avec / sans la composante, rendement en excès à h séances). Un poids ne bouge que d'un pas,
   * seulement si l'écart est net (|t| ≥ minT) sur au moins minCases cas de chaque côté, et reste entre 0 et 2 fois sa valeur d'origine.
   */
  ES.LEARN_FEATURES = [
    ['discountBig', 'insiders', 'discountBig', 'Décote ≥ 40 %'], ['discountMedium', 'insiders', 'discountMedium', 'Décote 25 à 40 %'],
    ['panic', 'insiders', 'panicBuy', 'Achat dans la panique'],
    ['ceo', 'insiders', 'ceoCfo', 'Achat du DG ou du DAF'], ['cluster', 'insiders', 'cluster', 'Cluster de dirigeants'],
    ['trend', 'market', 'trend', 'Tendance de fond haussière (MM50 > MM200)'], ['relStrong', 'market', 'relStrength', 'Plus fort que le marché sur 6 mois']
  ];
  ES.calibrate = function (samples, cfg, prev, today) {
    var L = cfg.learning, month = today.slice(0, 7), base = ES.DEFAULT_CONFIG.weights;
    var out = { month: month, weights: JSON.parse(JSON.stringify((prev && prev.weights) || {})), log: ((prev && prev.log) || []).slice(-60), stats: [], changed: [] , version: (prev && prev.version) || 0 };
    if (prev && prev.month === month) { out.stats = prev.stats || []; out.changed = []; out.skipped = 'déjà calibré ce mois-ci'; return out; }
    var ok = samples.filter(function (s) { return s.excess != null && isFinite(s.excess); });
    ES.LEARN_FEATURES.forEach(function (f) {
      var w = ok.filter(function (s) { return s.f[f[0]] === true; }).map(function (s) { return s.excess * 100; });
      var wo = ok.filter(function (s) { return s.f[f[0]] === false; }).map(function (s) { return s.excess * 100; });
      var st = { feature: f[0], label: f[3], nWith: w.length, nWithout: wo.length, meanWith: w.length ? mean(w) : null, meanWithout: wo.length ? mean(wo) : null, t: null, action: 'aucune' };
      if (w.length >= 2 && wo.length >= 2) {
        var v = function (a, m) { return a.reduce(function (x, y) { return x + (y - m) * (y - m); }, 0) / (a.length - 1); };
        var se = Math.sqrt(v(w, st.meanWith) / w.length + v(wo, st.meanWithout) / wo.length);
        st.t = se > 0 ? (st.meanWith - st.meanWithout) / se : null;
      }
      var cur = out.weights[f[1]] && out.weights[f[1]][f[2]] != null ? out.weights[f[1]][f[2]] : cfg.weights[f[1]][f[2]];
      var orig = base[f[1]][f[2]], next = cur;
      if (w.length < L.minCases || wo.length < L.minCases) st.action = 'pas assez de cas (' + w.length + ' / ' + L.minCases + ' requis)';
      else if (st.t != null && st.t >= L.minT) next = Math.min(cur + L.maxStep, 2 * orig);
      else if (st.t != null && st.t <= -L.minT) next = Math.max(cur - L.maxStep, 0);
      else st.action = 'écart non significatif';
      if (next !== cur) {
        st.action = (next > cur ? 'hausse ' : 'baisse ') + cur + ' → ' + next;
        (out.weights[f[1]] = out.weights[f[1]] || {})[f[2]] = next;
        var e = { month: month, feature: f[0], label: f[3], from: cur, to: next, nWith: w.length, effect: +(st.meanWith - st.meanWithout).toFixed(2), t: +st.t.toFixed(2) };
        out.log.push(e); out.changed.push(e);
      }
      out.stats.push(st);
    });
    if (out.changed.length) out.version++;
    return out;
  };
  ES.eventStudy = function (events, series, bench, opts) {
    var cost = (opts.costRoundTripPct || 0) / 100, horizons = opts.horizons || [20, 60], oos = opts.oosStart || null;
    var benchAdj = bench ? ES.adjustedSeries(ES.normalizeSeries(bench.rows), bench.splits) : null;
    var benchIdx = {}; if (benchAdj) benchAdj.forEach(function (r, i) { benchIdx[r[0]] = i; });
    var groups = {};
    events.forEach(function (ev) {
      var s = series[ev.isin]; if (!s) return;
      var adj = ES.adjustedSeries(ES.normalizeSeries(s.rows), s.splits);
      var i = 0; while (i < adj.length && adj[i][0] <= ev.date) i++;
      if (i >= adj.length) return;
      var entry = adj[i][1] != null ? adj[i][1] : adj[i][4];
      horizons.forEach(function (h) {
        var j = i + h; if (j >= adj.length) return;
        var r = adj[j][4] / entry - 1 - cost, ex = null;
        if (benchAdj && benchIdx[adj[i][0]] != null && benchIdx[adj[j][0]] != null) {
          var b0 = benchAdj[benchIdx[adj[i][0]]], b1 = benchAdj[benchIdx[adj[j][0]]];
          ex = r - (b1[4] / (b0[1] != null ? b0[1] : b0[4]) - 1);
        }
        var sample = oos && ev.date >= oos ? 'hors échantillon' : 'échantillon';
        var k = ev.group + '|' + h + '|' + sample;
        (groups[k] = groups[k] || { group: ev.group, horizon: h, sample: sample, rets: [], excess: [] }).rets.push(r);
        if (ex != null) groups[k].excess.push(ex);
      });
    });
    return Object.keys(groups).map(function (k) {
      var g = groups[k], s = g.rets.slice().sort(function (a, b) { return a - b; });
      var ex = g.excess.slice().sort(function (a, b) { return a - b; });
      return {
        group: g.group, horizon: g.horizon, sample: g.sample, n: s.length,
        mean: mean(s) * 100, median: s[Math.floor(s.length / 2)] * 100, hit: s.filter(function (x) { return x > 0; }).length / s.length * 100,
        nExcess: ex.length, meanExcess: ex.length ? mean(ex) * 100 : null, hitExcess: ex.length ? ex.filter(function (x) { return x > 0; }).length / ex.length * 100 : null
      };
    }).sort(function (a, b) { return (a.group + a.horizon + a.sample) < (b.group + b.horizon + b.sample) ? -1 : 1; });
  };

  /* ============================ Email ============================ */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function pct(v) { return v == null ? 'n.d.' : (v > 0 ? '+' : '') + v.toFixed(1).replace('.', ',') + ' %'; }
  function num2(v) { return v == null ? 'n.d.' : v.toFixed(2).replace('.', ','); }
  ES.fmtPct = pct; ES.esc = esc;
  ES.buildEmail = function (a) {
    var i = a.inst, s = a.score, subj = '[Euro Signal] ' + ES.stars(s.total, a.cfg || ES.DEFAULT_CONFIG).text + ' ' + (i.name || i.isin) + ' — note ' + ES.note(s.total, a.cfg) + '/100 (barème ' + s.version + ')';
    var h = [], t = [];
    h.push('<div style="font-family:Arial,sans-serif;font-size:14px;color:#1c2321;max-width:680px">');
    h.push('<h2 style="margin:0 0 4px">' + esc(i.name || i.isin) + '</h2>');
    var secFr = ES.sectorFr(i.sector || (i.fund && i.fund.sector));
    h.push('<p style="margin:0 0 12px;color:#55615c">' + esc([secFr ? 'Secteur : ' + secFr + (i.fund && i.fund.industry ? ' (' + ES.industryFr(i.fund.industry) + ')' : '') : null, i.isin, i.ticker, i.venue, 'domicile ' + (i.country || '?'), 'PEA : ' + ES.PEA_LABEL[i.peaStatus || 'a_verifier']].filter(Boolean).join(' · ')) + '</p>');
    t.push((i.name || i.isin) + ' (' + i.isin + ')' + (secFr ? ' — secteur : ' + secFr : ''), 'Note d\'opportunité ' + ES.note(s.total, a.cfg) + '/100 (' + s.total + ' points) — barème ' + s.version, '');
    h.push('<p><b>Note d\'opportunité : ' + ES.note(s.total, a.cfg) + '/100</b> (' + s.total + ' points bruts) · qualité des données ' + a.quality.total + '/100 · surchauffe (expérimental) ' + a.overheat.total + '/100</p>');
    h.push('<p style="color:#55615c;font-size:12px">Ce score classe des dossiers à examiner. Ce n\'est pas une probabilité de hausse : il n\'a pas été validé statistiquement. Aucun ordre n\'est passé.</p>');
    h.push('<table style="border-collapse:collapse;width:100%">');
    Object.keys(s.families).forEach(function (k) {
      var f = s.families[k];
      h.push('<tr><td colspan="2" style="padding:8px 0 2px;border-bottom:1px solid #ccd3cf"><b>' + esc(f.label) + ' : ' + f.points + '/' + f.cap + '</b></td></tr>');
      t.push(f.label + ' : ' + f.points + '/' + f.cap);
      f.items.forEach(function (it) {
        h.push('<tr><td style="padding:2px 8px 2px 0">' + esc(it.label) + '</td><td style="text-align:right;white-space:nowrap">' + (it.points > 0 ? '+' : '') + it.points + '</td></tr>');
        t.push('  ' + (it.points > 0 ? '+' : '') + it.points + '  ' + it.label);
      });
    });
    h.push('</table>');
    if (s.buys.length || s.sells.length) {
      h.push('<h3 style="margin:16px 0 4px">Opérations d\'initiés (fenêtre depuis le ' + s.windowFrom + ')</h3><table style="border-collapse:collapse;width:100%;font-size:13px">');
      h.push('<tr style="text-align:left"><th>Date</th><th>Déclarant</th><th>Nature</th><th>Prix</th><th>Montant</th><th>Cours actuel / prix payé</th><th>Source</th></tr>');
      t.push('', 'Opérations d\'initiés :');
      s.buys.concat(s.sells).forEach(function (x) {
        var r = a.refs && a.refs[x.id];
        h.push('<tr><td>' + x.txDate + '</td><td>' + esc(x.person || 'n.d.') + '<br><span style="color:#55615c">' + esc(x.role || '') + (x.associated ? ' (personne liée' + (x.linkedTo ? ' à ' + esc(x.linkedTo) : '') + ')' : '') + '</span></td><td>' + ES.TX_TYPES[x.type] + '</td><td>' + num2(x.price) + ' ' + esc(x.currency || '') + '</td><td>' + (x.amount != null ? ES.fmtEur(x.amount).replace('€', esc(x.currency || '?')) : 'n.d.') + '</td><td>' + (r && r.available ? pct(r.currentVsPaidPct) : 'n.d.') + '</td><td>' + (ES.safeUrl(x.sourceUrl) ? '<a href="' + esc(ES.safeUrl(x.sourceUrl)) + '">' + esc(x.registry) + '</a>' : esc(x.registry)) + '</td></tr>');
        t.push('- ' + x.txDate + ' ' + (x.person || 'n.d.') + ' (' + (x.role || '') + ') ' + ES.TX_TYPES[x.type] + ' ' + num2(x.price) + ' ' + (x.currency || '') + ' ; cours/prix payé ' + (r && r.available ? pct(r.currentVsPaidPct) : 'n.d.') + ' ; ' + (x.sourceUrl || x.registry));
        if (r && r.available && r.atPurchase && r.atPurchase.ex52) {
          var p = r.atPurchase;
          h.push('<tr><td></td><td colspan="6" style="color:#55615c;font-size:12px;padding-bottom:6px">À l\'achat : ' + pct(p.paidVsLow52Pct) + ' au-dessus du plus bas 52 sem., ' + pct(p.paidVsHigh52Pct) + ' sous le plus haut (' + p.ex52.basis + ', depuis ' + p.ex52.from + '). Aujourd\'hui le cours est à ' + (r.today.currentPos52 != null ? Math.round(r.today.currentPos52) + ' %' : 'n.d.') + ' de son intervalle 52 semaines.</td></tr>');
        }
      });
      h.push('</table>');
    }
    var risks = a.overheat.items.map(function (x) { return x.label; }).concat(a.universeWarnings || []);
    if (s.sells.length) risks.push('ventes d\'initiés dans la fenêtre');
    h.push('<h3 style="margin:16px 0 4px">Risques et limites</h3><ul>' + (risks.length ? risks.map(function (r) { return '<li>' + esc(r) + '</li>'; }).join('') : '<li>Aucun signal de surchauffe relevé par les indicateurs disponibles.</li>') + '<li>Couverture : ' + esc(a.quality.coverage.label) + '</li></ul>');
    t.push('', 'Risques : ' + (risks.join(' ; ') || 'aucun signal de surchauffe relevé'), 'Couverture : ' + a.quality.coverage.label);
    var links = [];
    (a.events.buybacks || []).concat(a.events.results || []).forEach(function (e) { if (e.sourceUrl) links.push(e.sourceUrl); });
    if (links.length) { h.push('<h3 style="margin:16px 0 4px">Autres sources</h3><ul>' + links.filter(ES.safeUrl).map(function (l) { return '<li><a href="' + esc(l) + '">' + esc(l) + '</a></li>'; }).join('') + '</ul>'); t.push('Sources : ' + links.join(' ; ')); }
    h.push('<p style="color:#55615c;font-size:12px">Empreinte ' + a.decision.fingerprint + ' · généré le ' + a.today + ' · Euro Signal ' + ES.ENGINE_VERSION + '</p></div>');
    t.push('', 'Score non probabiliste. Aide à l\'analyse ; aucun ordre passé. Empreinte ' + a.decision.fingerprint);
    return { subject: subj, html: h.join(''), text: t.join('\n') };
  };
  ES.PEA_LABEL = { eligible: 'confirmé éligible', non_eligible: 'confirmé non éligible', a_verifier: 'à vérifier' };

  /* =============== Collecteur insider-pea (AMF via transactions-amf.swaoo.com) =============== */
  /** Natures AMF, y compris tronquées par la source (« ATTRIBUTION GRA... »). L'ordre compte. */
  var AMF_NATURES = [
    ['achat', /^acquisition$/], ['vente', /^cession$/],
    ['attribution', /^(attribution|livraison d|acquisition def|acquisition definitive|vesting|remise d actions)/],
    ['option', /^(exercice|levee d option)/], ['souscription', /^souscription/],
    ['dividende', /^(paiement du div|dividende)/], ['don', /^(donation|don |don$|succession|heritage)/],
    ['transfert', /^(apport|transfert|reception d|retour|reclassement|assignment)/], ['nantissement', /^(nantissement|pret|emprunt)/]
  ];
  ES.classifyAmfNature = function (nature, instrument) {
    var ins = ES.norm(instrument);
    if (ins && ins !== 'action' && ins !== 'actions') return 'instrument'; // FCPE, options, préférence, ADR, dette…
    var n = ES.norm(nature);
    if (!n) return 'inconnu';
    for (var i = 0; i < AMF_NATURES.length; i++) if (AMF_NATURES[i][1].test(n)) return AMF_NATURES[i][0];
    return 'autre'; // ex. « Acquisition d'a... » tronqué : actions achetées ou actions gratuites ? ambigu
  };
  /** Dirigeant de rattachement d'une personne étroitement liée, extrait du texte de fonction. */
  ES.extractLinkedTo = function (role) {
    var m = String(role || '').match(/(?:li[ée]e?s?\s+(?:à|a)|associated with)\s+(.+)/i);
    if (!m) return null;
    var s = m[1].replace(/\b(MR|MME)(?=[A-Z]{3})/g, '').replace(/(^|\s)(m\.|mr\.?|mme\.?|monsieur|madame|mrs\.?)\s*/gi, ' ').replace(/\s+or\b.*$/i, '').trim();
    s = s.split(/,|\s+(?:membres?|pr[ée]sident|directeur|directrice|administrat|g[ée]rant|ceo|cfo|dirigeant|vice|censeur|directeur)\b/i)[0];
    s = s.replace(/\s+/g, ' ').trim();
    return s.length >= 3 ? s.slice(0, 120) : null;
  };
  /** Convertit une ligne du collecteur en déclaration normalisée. Montant ou prix à 0 = inconnu. */
  ES.fromAmfCollector = function (t, opts) {
    var errors = [], warnings = [], today = opts.today;
    var isin = String(t.isin || '').trim().toUpperCase();
    var type = ES.classifyAmfNature(t.nature, t.instrument);
    if ((type === 'achat' || type === 'vente') && (Number(t.price) === 0 || NON_VOLUNTARY.test(String(t.nature || '')))) type = 'autre_nv'; // actions gratuites, plan, prix nul
    if (type !== 'instrument' && !ES.isValidIsin(isin)) errors.push('ISIN invalide (' + isin + ')');
    var txDate = ES.parseDate(t.date), pub = ES.parseDate(t.date_published);
    if (!txDate) errors.push('date de transaction illisible');
    else if (txDate > today) errors.push('date de transaction dans le futur');
    if (pub && pub > today) errors.push('date de publication dans le futur');
    if (pub && txDate && pub < txDate) errors.push('publication antérieure à la transaction');
    var pos = function (v) { var n = typeof v === 'number' ? v : ES.parseNumber(v); return n != null && n > 0 && isFinite(n) ? n : null; };
    var qty = pos(t.quantity), price = pos(t.price), amount = pos(t.amount);
    if (amount == null) warnings.push('montant non publié par la source');
    if (/\.\.\.$|…$/.test(String(t.nature || '')) && type === 'autre') warnings.push('nature tronquée par la source : ambiguë');
    var role = String(t.role || '').trim(); if (role === 'N/D') role = '';
    var who = String(t.insider || '').replace(/\s+/g, ' ').trim();
    // Le collecteur écrit « X personne liée à Y » dans le nom ; la fonction est alors celle du dirigeant Y.
    var mm = who.match(/^(.+?)\s+personne (?:morale |physique )?(?:étroitement )?li[ée]e à\s+(.+)$/i);
    var linkedTo = null, associated = false;
    if (mm) { who = mm[1].trim(); linkedTo = ES.extractLinkedTo('liée à ' + mm[2]); associated = true; }
    var r = ES.classifyRole(role);
    if (!associated) { associated = r.associated || /li[ée]e?s?\s+(?:à|a)\s|closely associated/i.test(role); if (associated) linkedTo = ES.extractLinkedTo(role); }
    if (associated) { r.ceo = false; r.cfo = false; } // l'achat d'un proche n'est pas l'achat du DG lui-même
    var rec = {
      isin: isin, issuer: t.company_name || null, ticker: null, registry: 'AMF', registryCountry: 'FR',
      person: who || null, role: (associated && role ? 'proche de ' + (linkedTo || 'un dirigeant') + ' (' + role + ')' : role) || null,
      ceo: r.ceo, cfo: r.cfo, board: r.board, associated: associated, linkedTo: linkedTo,
      type: type, natureText: (t.nature || '') + (type === 'instrument' ? ' — ' + (t.instrument || '') : ''),
      txDate: txDate, pubDate: pub, pubTime: null, pubPrecision: pub ? 'jour' : 'inconnue',
      qty: qty, price: price, currency: ES.cleanCurrency(t.currency), amount: amount, amountComputed: false,
      venue: null, sourceUrl: t.reference_url || null, registryId: t.declaration_number || null, version: 1, status: 'active',
      planned: null, holding: null, stakeAfter: null, via: opts.via || null
    };
    rec.personKey = ES.personKey(rec.person);
    rec.dedupKey = ES.dedupKey(rec);
    rec.id = rec.registryId ? ES.safeId('AMF:' + rec.registryId) : 'h' + ES.hash(rec.dedupKey + '|AMF');
    return { ok: errors.length === 0, rec: rec, errors: errors, warnings: warnings };
  };

  /* =============== Collecteurs européens (format commun) =============== */
  var SHARE_WORDS = /^(action|actions|share|shares|ordinary shares?|aandeel|aandelen|gewone aandelen|aktie|aktien|azione|azioni|azioni ordinarie|accion|acciones|equity)$/;
  /** Déclaration issue d'un collecteur de registre (FSMA, AFM…). Valeurs brutes en texte, parsées ici. */
  /** Lien sûr : http(s) uniquement (pas de javascript:, data:…). */
  ES.safeUrl = function (u) { u = String(u == null ? '' : u).trim(); return /^https?:\/\/[^\s"'<>]+$/i.test(u) ? u : ''; };
  ES.cleanCurrency = function (c) { c = String(c == null ? '' : c).trim(); return /^[A-Za-z]{3}$/.test(c) ? (c === 'GBp' || c === 'GBX' ? 'GBp' : c.toUpperCase()) : null; };
  var NON_VOLUNTARY = /\b(free (allocation|shares?|grant)|gratuit|gratis|gratuito|grant(ed)?|awards?|vesting|vested|attribu(tion|zione)|assegnazione|toekenning|zuteilung|sell[- ]to[- ]cover|incentive plan|piano di incentivazione|plan de incentivos|stock option|exercise of options?)\b/i;
  ES.fromCollectorRecord = function (r, opts) {
    var errors = [], warnings = [], today = opts.today, loc = r.numberLocale || 'auto';
    var isin = String(r.isin || '').trim().toUpperCase().replace(/\s/g, '');
    var ins = ES.norm(r.instrument);
    var type;
    if (ins && !SHARE_WORDS.test(ins)) type = 'instrument';
    else {
      type = ES.classifyAmfNature(r.nature, 'action');
      if (type === 'autre' || type === 'inconnu') type = ES.classifyType(r.nature);
      // Codes normalisés d'agrégateur (Insider Screener : BUY / SELL / OO) quand le libellé d'origine est absent ou ambigu
      var code = ES.norm(r.natureCode);
      if ((type === 'autre' || type === 'inconnu') && code) type = code === 'buy' ? 'achat' : code === 'sell' ? 'vente' : code === 'oo' ? 'autre_nv' : type;
      if (ES.norm(r.nature) === 'oo') type = 'autre_nv';
      // Attribution gratuite, plan d'actionnariat, vente pour couvrir l'impôt, prix nul : pas une décision d'investissement
      if ((type === 'achat' || type === 'vente') && (NON_VOLUNTARY.test(String(r.nature || '')) || ES.parseNumber(r.price, loc) === 0)) type = 'autre_nv';
    }
    if (type !== 'instrument' && !ES.isValidIsin(isin)) errors.push(isin ? 'ISIN invalide (' + isin + ')' : 'ISIN absent');
    var txDate = ES.parseDate(r.txDate), pub = ES.parseDate(r.published);
    if (!txDate) errors.push('date de transaction illisible');
    else if (txDate > today) errors.push('date de transaction dans le futur');
    if (pub && pub > today) errors.push('date de publication dans le futur');
    if (pub && txDate && pub < txDate) errors.push('publication antérieure à la transaction');
    var num = function (v) { var n = ES.parseNumber(v, loc); return n != null && isFinite(n) && n > 0 && n < 1e13 ? n : null; };
    var qty = num(r.quantity), price = num(r.price), amount = num(r.amount);
    if (amount == null && qty != null && price != null && isFinite(qty * price) && qty * price < 1e13) amount = qty * price;
    if (amount == null) warnings.push('montant non publié');
    var role = String(r.role || '').trim();
    var rr = ES.classifyRole(role);
    var associated = rr.associated || /closely associated|personne .*li[ée]e|nauw gelieerd|eng verbunden|strettamente/i.test(role);
    var linkedTo = associated ? ES.extractLinkedTo(r.linkedTo ? 'liée à ' + r.linkedTo : role) : null;
    if (associated) { rr.ceo = false; rr.cfo = false; }
    var rec = {
      isin: isin, issuer: r.issuer || null, ticker: null, registry: r.registry, registryCountry: r.country || null,
      person: String(r.person || '').replace(/\s+/g, ' ').trim() || null, role: role || null,
      ceo: rr.ceo, cfo: rr.cfo, board: rr.board, associated: associated, linkedTo: linkedTo,
      type: type, natureText: (r.nature || '') + (type === 'instrument' ? ' — ' + (r.instrument || '') : ''),
      txDate: txDate, pubDate: pub, pubTime: null, pubPrecision: pub ? 'jour' : 'inconnue',
      qty: qty, price: price, currency: ES.cleanCurrency(r.currency), amount: amount, amountComputed: ES.parseNumber(r.amount, loc) == null && amount != null,
      venue: r.place || null, sourceUrl: r.url || null, registryId: r.id ? String(r.id) : null, version: 1,
      status: /amend|correct|rectif|wijzig/i.test(String(r.status || '')) ? 'corrigee' : 'active',
      planned: null, holding: null, stakeAfter: null, via: r.via || null
    };
    if (!rec.currency) warnings.push('devise inconnue');
    rec.personKey = ES.personKey(rec.person);
    rec.dedupKey = ES.dedupKey(rec);
    rec.id = rec.registryId ? ES.safeId(r.registry + ':' + rec.registryId) : 'h' + ES.hash(rec.dedupKey + '|' + r.registry);
    return { ok: errors.length === 0, rec: rec, errors: errors, warnings: warnings };
  };

  /* =============== Communiqués des émetteurs : rachats, perspectives =============== */
  // Lecture automatique des TITRES de communiqués (FR, EN, DE, NL, ES, IT). Détection, pas compréhension.
  var PR_RULES = [
    ['buyback', 'annulation', /(cancel(?:s|led|lation)? (?:of )?(?:the )?(?:share )?buy-?back|annul\w* (?:du |le )?programme de rachat|beendigung des aktienr|stopzetting .*inkoop)/],
    ['buyback', 'suspension', /(suspen\w* (?:of )?(?:the |its )?(?:share )?buy-?back|suspen\w* (?:du |le |son )?programme de rachat|aussetzung des aktienr)/],
    ['buyback', 'execution', /(transactions? (?:in|on) own shares|purchase of own shares|declaration des transactions sur actions propres|operations sur actions propres|rachats? d actions? propres? effectu|zwischenmeldung.*(aktienr|r.ckkauf)|r.ckkauf eigener aktien.*(woche|meldung)|inkoop (?:van )?eigen aandelen|acquisto di azioni proprie|compra de acciones propias|operaciones (?:sobre|con) acciones propias|weekly report on share buy-?back|transactions under (?:its |the )?(?:current |ongoing )?(?:share )?buy-?back|share buy-?back (?:programme|program)?\s*[-–:]?\s*(?:weekly|update|transactions))/],
    ['buyback', 'annonce', /(launch\w* (?:of )?(?:a |an |its |the )?(?:new )?(?:share )?(?:buy-?back|repurchase)|announce\w* (?:a |an |its )?(?:new )?(?:share )?(?:buy-?back|repurchase)|(?:share )?buy-?back (?:programme|program) of|lance\w* (?:un |son |d un )?(?:nouveau )?programme de rachat|mise en (?:oeuvre|œuvre) (?:d un |du )?programme de rachat|aktienr.ckkaufprogramm|beschlie\w* .*aktienr.ckkauf|start\w* .*inkoopprogramma|inkoopprogramma|programa de recompra|programma di (?:acquisto|riacquisto) di azioni proprie|avvio .*buy-?back)/],
    ['guidance', 'relevee', /(raises? (?:its |full year |fy |annual |2\d{3} )*(?:guidance|outlook|forecast|targets?)|upgrades? (?:its )?(?:guidance|outlook)|rel[eè]ve\w* (?:ses |son |sa |l )?(?:objectifs?|previsions?|perspectives?|guidance)|hebt (?:die |seine |ihre )?(?:prognose|jahresprognose|ausblick)|prognoseerh.hung|verhoogt (?:de |haar |zijn )?(?:verwachting|outlook|prognose)|eleva (?:la |le )?(?:guidance|previsioni|stime)|alza (?:la |le )?(?:guidance|previsioni)|eleva (?:sus )?previsiones)/],
    ['guidance', 'abaissee', /(lowers? (?:its |full year |fy |annual |2\d{3} )*(?:guidance|outlook|forecast|targets?)|cuts? (?:its )?(?:guidance|outlook|forecast)|profit warning|abaiss\w* (?:ses |son |sa |l )?(?:objectifs?|previsions?|perspectives?|guidance)|revoit a la baisse|senkt (?:die |seine |ihre )?(?:prognose|jahresprognose|ausblick)|gewinnwarnung|prognosesenkung|verlaagt (?:de |haar |zijn )?(?:verwachting|outlook)|winstwaarschuwing|taglia (?:la |le )?(?:guidance|previsioni|stime)|rebaja (?:sus )?previsiones)/],
    ['guidance', 'maintenue', /(confirms? (?:its |full year |annual |2\d{3} )*(?:guidance|outlook|targets?)|reaffirms? (?:its )?(?:guidance|outlook)|confirme (?:ses |son |sa )?(?:objectifs?|perspectives?|guidance)|bestatigt (?:die |seine |ihre )?(?:prognose|ausblick)|bevestigt (?:de |haar |zijn )?(?:verwachting|outlook))/]
  ];
  ES.classifyPressTitle = function (title) {
    var t = ES.norm(title);
    if (!t) return null;
    for (var i = 0; i < PR_RULES.length; i++) if (PR_RULES[i][2].test(t)) {
      var v = PR_RULES[i][1];
      // « avvio / lancement / launch … » d'un programme : annonce, pas exécution
      if (v === 'execution' && /\b(avvio|launch\w*|lance\w*|lancement|lanza\w*|beginn\w*|initiat\w*|start\w*)\b/.test(t)) v = 'annonce';
      return { kind: PR_RULES[i][0], value: v };
    }
    return null;
  };
  /** Pourcentage du capital mentionné dans un titre de rachat (« up to 10% of share capital »), sinon null. */
  ES.pctFromTitle = function (title) {
    var m = String(title || '').match(/(\d{1,2}(?:[.,]\d{1,2})?)\s?%\s*(?:of|du|des|des actions|van|del|des titres|of the|de son)?\s*(?:its |the |le |son )?(?:share capital|capital|issued|aandelenkapitaal|grundkapital|capitale)/i);
    return m ? ES.parseNumber(m[1]) : null;
  };
  /**
   * Événements à partir des données Yahoo collectées par GitHub Actions :
   * raw = { ticker, earnings:[{date, epsEstimate, epsActual}], press:[{title, date, provider, url}], epsTrend:{current, d30} }
   * Le consensus Yahoo d'un trimestre passé est l'estimation figée au moment de la publication.
   */
  ES.eventsFromYahoo = function (raw, today) {
    var out = { buybacks: [], results: [], notes: [] };
    if (!raw) return out;
    var guid = [];
    (raw.press || []).forEach(function (p) {
      var d = ES.parseDate(p.date); if (!d || d > today) return;
      var c = ES.classifyPressTitle(p.title); if (!c) return;
      var base = { sourceUrl: p.url || null, note: 'Détecté automatiquement d\'après le titre du communiqué : « ' + String(p.title).slice(0, 160) + ' »' + (p.provider ? ' (' + p.provider + ')' : ''), auto: true };
      if (c.kind === 'buyback') out.buybacks.push(Object.assign({ id: 'bb' + ES.hash(raw.ticker + d + p.title), stage: c.value, date: d, amount: null, pctCapital: ES.pctFromTitle(p.title), confirmed: true }, base));
      else guid.push(Object.assign({ date: d, value: c.value }, base));
    });
    (raw.earnings || []).forEach(function (e) {
      var d = ES.parseDate(e.date); if (!d || d > today) return;
      var act = typeof e.epsActual === 'number' ? e.epsActual : null, est = typeof e.epsEstimate === 'number' ? e.epsEstimate : null;
      if (act == null) return; // trimestre pas encore publié
      var g = guid.filter(function (x) { return Math.abs(ES.daysBetween(x.date, d)) <= 3; })[0];
      if (g) g.used = true;
      out.results.push({ id: 'res' + ES.hash(raw.ticker + d), pubDate: d, period: null, epsActual: act, epsConsensus: est, revActual: null, revConsensus: null,
        consensusDate: est != null ? ES.addDays(d, -1) : null, comparable: est != null ? true : null, consensusSource: 'Yahoo Finance (estimation figée à la publication, même base que le BPA publié)',
        guidance: g ? g.value : null, sourceUrl: g ? g.sourceUrl : null, currency: null, auto: true });
    });
    guid.filter(function (g) { return !g.used; }).forEach(function (g) {
      out.results.push({ id: 'gd' + ES.hash(raw.ticker + g.date + g.value), pubDate: g.date, period: null, epsActual: null, epsConsensus: null, revActual: null, revConsensus: null, consensusDate: null, comparable: null, guidance: g.value, sourceUrl: g.sourceUrl, note: g.note, auto: true });
    });
    out.buybacks.sort(function (a, b) { return a.date < b.date ? -1 : 1; });
    out.results.sort(function (a, b) { return a.pubDate < b.pubDate ? -1 : 1; });
    if (raw.epsTrend && typeof raw.epsTrend.current === 'number' && typeof raw.epsTrend.d30 === 'number' && raw.epsTrend.d30 !== 0)
      out.revision30d = (raw.epsTrend.current / raw.epsTrend.d30 - 1) * 100 * (raw.epsTrend.d30 < 0 ? -1 : 1);
    return out;
  };

  /* ======================== Normalisation des autres imports ======================== */
  ES.normalizePriceRows = function (rows, map, locale) {
    var out = [], errors = [];
    rows.forEach(function (r, i) {
      var d = ES.parseDate(r[map.date]), c = ES.parseNumber(r[map.close], locale);
      if (!d) { errors.push('ligne ' + (i + 2) + ' : date illisible'); return; }
      if (c == null || c <= 0) { errors.push('ligne ' + (i + 2) + ' : clôture invalide'); return; }
      var o = map.open ? ES.parseNumber(r[map.open], locale) : null, h = map.high ? ES.parseNumber(r[map.high], locale) : null,
        l = map.low ? ES.parseNumber(r[map.low], locale) : null, v = map.volume ? ES.parseNumber(r[map.volume], locale) : null;
      if (h != null && l != null && h < l) { errors.push('ligne ' + (i + 2) + ' : plus haut < plus bas'); h = l = null; }
      out.push({ key: map.isin ? String(r[map.isin] || '').toUpperCase() : map.ticker ? String(r[map.ticker] || '').toUpperCase() : null, row: [d, o, h, l, c, v != null && v >= 0 ? v : null] });
    });
    return { rows: out, errors: errors };
  };

  root.ES = ES;
  if (typeof module !== 'undefined' && module.exports) module.exports = ES;
})(typeof window !== 'undefined' ? window : globalThis);
