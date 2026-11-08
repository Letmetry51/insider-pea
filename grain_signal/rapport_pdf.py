"""
Grain Signal — synthèse PDF (A4) jointe aux emails du comité.

Entrées : data/grain/grain-signal.json (calcul du matin). Sortie : data/grain/prive/synthese.pdf (jamais publiée).
Mise en page HTML/CSS imprimée par Chromium (Playwright) : jauges et graphiques en SVG, sans emoji (pas de police couleur
sur les serveurs), coupures de page maîtrisées (un bloc n'est jamais coupé en deux).

  python grain_signal/rapport_pdf.py            fabrique le PDF
  python grain_signal/rapport_pdf.py --besoin   code 0 si un email de la file en a besoin (comité ou email de test), 1 sinon
  python grain_signal/rapport_pdf.py --html F   écrit seulement la page HTML (contrôle de la mise en page)
"""
import html
import json
import re
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grain"
PDF = OUT / "prive" / "synthese.pdf"

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
COUL = {"good": "#1f7a3e", "bad": "#b0281f", "warn": "#9a5b00", "info": "#2a62b8", "neutral": "#6b6d60"}
DECISION = {"ordre": ("ORDRE", "warn"), "executer": ("VENDRE", "good"), "vendre": ("AVANCER", "good"), "attendre": ("ATTENDRE", "bad"),
            "couvrir": ("COUVRIR", "info"), "rien": ("RIEN", "neutral"), "patienter": ("PATIENTER", "warn")}
SIGNAL = {"VENDRE": ("Vendre une tranche", "good"), "TENIR": ("Tenir le plan", "warn"), "ATTENDRE": ("Attendre / stocker", "bad"),
          "COUVRIR": ("Couvrir", "info")}
ENGRAIS = {"ACHETER_LARGE": ("ACHETER LARGE", "good"), "SUIVRE": ("SUIVRE LE PLAN", "info"), "FRACTIONNER": ("FRACTIONNER", "warn"),
           "ATTENDRE": ("ATTENDRE", "bad")}


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF]")


def e(t):
    """Texte échappé, sans emoji (les serveurs n'ont pas de police couleur : ils s'imprimeraient en carrés vides)."""
    return html.escape(EMOJI.sub("", str(t if t is not None else "")).strip(), quote=True)


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def n(v, d=2):
    """Nombre à la française (espace fine pour les milliers, virgule décimale)."""
    if v is None:
        return "—"
    s = f"{v:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def sg(v, d=2):
    return "—" if v is None else ("+" if v > 0 else "") + n(v, d)


def dfr(iso):
    try:
        x = date.fromisoformat(str(iso)[:10])
        return f"{x.day} {MOIS[x.month - 1]} {x.year}"
    except ValueError:
        return str(iso or "")


def mfr(m):
    return f"{MOIS[int(m[5:7]) - 1]} {m[:4]}" if m and len(m) >= 7 else str(m or "")


def badge(txt, cl):
    return f"<span class='badge' style='background:{COUL.get(cl, COUL['neutral'])}'>{e(txt)}</span>"


# --------------------------------------------------------------------------------------------- jauges et graphiques SVG
SEG_V = [(20, "bad"), (40, "warn"), (60, "neutral"), (80, "info"), (100, "good")]  # vendeur : vert = bon moment pour vendre
SEG_A = [(20, "good"), (40, "info"), (60, "neutral"), (80, "warn"), (100, "bad")]  # acheteur : vert = bon moment pour acheter
SEG_R = [(20, "good"), (60, "neutral"), (80, "warn"), (100, "bad")]  # ratio azote/blé
SEG_C = [(15, "bad"), (85, "neutral"), (100, "good")]  # positions des fonds (à contre-courant)
LAB = {
    "vendeur": lambda v: ("Prix bas : ne pas brader", "bad") if v <= 20 else ("Plutôt bas", "warn") if v <= 40 else
    ("Dans la moyenne", "neutral") if v < 60 else ("Plutôt haut", "info") if v < 80 else ("Prix haut : bon pour vendre", "good"),
    "acheteur": lambda v: ("Bas : bon prix d'achat", "good") if v <= 20 else ("Plutôt bas", "info") if v <= 40 else
    ("Dans la moyenne", "neutral") if v < 60 else ("Plutôt cher", "warn") if v < 80 else ("Cher : le minimum", "bad"),
    "ratio": lambda v: ("Azote bon marché : acheter large", "good") if v <= 20 else ("Normal : suivre le plan", "neutral") if v <= 60
    else ("Cher : fractionner", "warn") if v <= 80 else ("Très cher : attendre", "bad"),
    "prime": lambda v: ("Prime faible : vendre via Euronext", "bad") if v <= 20 else ("Prime plutôt faible", "warn") if v <= 40 else
    ("Prime normale", "neutral") if v < 60 else ("Prime plutôt forte", "info") if v < 80 else ("Prime forte : vendre au physique", "good"),
    "cot": lambda v: ("Fonds très vendeurs : rebond possible", "bad") if v <= 15 else ("Fonds très acheteurs : vendre", "good")
    if v >= 85 else ("Neutre", "neutral"),
}
SEGS = {"vendeur": SEG_V, "prime": SEG_V, "acheteur": SEG_A, "ratio": SEG_R, "cot": SEG_C}


def gauge_svg(v, segs, w=150):
    h, y = 16, 5
    out, x0 = [], 0
    for i, (to, cl) in enumerate(segs):
        x1 = to / 100 * w
        rx = " rx='3'" if i in (0, len(segs) - 1) else ""
        out.append(f"<rect x='{x0:.1f}' y='{y}' width='{x1 - x0 + (0 if i == len(segs) - 1 else 0.5):.1f}' height='6'{rx} fill='{COUL[cl]}'/>")
        x0 = x1
    cx = max(5, min(w - 5, v / 100 * w))
    out.append(f"<circle cx='{cx:.1f}' cy='8' r='5' fill='#fff' stroke='#1c1a12' stroke-width='2'/>")
    return f"<svg class='gauge' viewBox='0 0 {w} {h}' width='{w}' height='{h}'>{''.join(out)}</svg>"


def jauge(v, kind, titre=None, note=None, compact=False):
    if v is None:
        return ""
    lab, cl = LAB[kind](v)
    t = f"<div class='jt'>{e(titre)}</div>" if titre else ""
    nt = f"<div class='jn'>{e(note)}</div>" if note else ""
    return (f"<div class='jauge{' compact' if compact else ''}'>{t}<div class='jl'>{badge(f'{round(v)}e', cl)}"
            f"<span class='jlab'>{e(lab)}</span></div>{gauge_svg(v, SEGS[kind], 130 if compact else 170)}{nt}</div>")


def chart_svg(rows, ordres=(), revision=None, w=440, h=165):
    """Cours des 6 derniers mois (trait plein), MM20 (pointillés), ordres (vert) et seuil de révision (rouge)."""
    pts = [(r[0], r[1], r[2] if len(r) > 2 else None) for r in rows if r[1] is not None][-126:]
    if len(pts) < 5:
        return ""
    vals = [p[1] for p in pts] + [p[2] for p in pts if p[2] is not None] + list(ordres) + ([revision] if revision else [])
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 30, 122, 8, 16
    X = lambda i: L + i / (len(pts) - 1) * (w - L - R)  # noqa: E731
    Y = lambda v: T + (1 - (v - lo) / (hi - lo)) * (h - T - B)  # noqa: E731
    out = []
    raw = (hi - lo) / 4
    mag = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 0.1
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    v = (int(lo / step) + 1) * step
    while v < hi:
        out.append(f"<line x1='{L}' x2='{w - R}' y1='{Y(v):.1f}' y2='{Y(v):.1f}' stroke='#e2ddd0' stroke-width='0.6'/>"
                   f"<text x='{L - 3}' y='{Y(v) + 3:.1f}' text-anchor='end' class='ax'>{n(v, 0)}</text>")
        v += step
    for i in (0, len(pts) // 2, len(pts) - 1):
        anchor = "start" if i == 0 else "end" if i == len(pts) - 1 else "middle"
        out.append(f"<text x='{X(i):.1f}' y='{h - 3}' text-anchor='{anchor}' class='ax'>{e(dfr(pts[i][0]))}</text>")
    used = []

    def level(val, col, txt):
        yy = Y(val)
        ty = yy + 3
        while any(abs(ty - u) < 10 for u in used):
            ty += 10
        used.append(ty)
        out.append(f"<line x1='{L}' x2='{w - R}' y1='{yy:.1f}' y2='{yy:.1f}' stroke='{col}' stroke-width='1' stroke-dasharray='3 2'/>"
                   f"<text x='{w - R + 3}' y='{ty:.1f}' class='lv' fill='{col}'>{e(txt)}</text>")
    niv = [(o, COUL["good"], f"{'1er' if i == 0 else f'{i + 1}e'} ordre : {n(o)} €/t") for i, o in enumerate(ordres)]
    if revision:
        niv.append((revision, COUL["bad"], f"Révision : {n(revision)} €/t"))
    for args in sorted(niv, key=lambda x: -x[0]):  # du plus haut au plus bas : les étiquettes gardent l'ordre des prix
        level(*args)
    mm = " ".join(f"{'M' if k == 0 else 'L'}{X(i):.1f} {Y(p[2]):.1f}" for k, (i, p) in enumerate((i, p) for i, p in enumerate(pts) if p[2] is not None))
    if mm:
        out.append(f"<path d='{mm}' fill='none' stroke='#2a78d6' stroke-width='1' stroke-dasharray='3 2'/>")
    line = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f} {Y(p[1]):.1f}" for i, p in enumerate(pts))
    out.append(f"<path d='{line}' fill='none' stroke='#866400' stroke-width='1.6' stroke-linejoin='round'/>")
    out.append(f"<circle cx='{X(len(pts) - 1):.1f}' cy='{Y(pts[-1][1]):.1f}' r='2.6' fill='#866400'/>")
    return f"<svg class='chart' viewBox='0 0 {w} {h}' width='100%'>{''.join(out)}</svg>"


# --------------------------------------------------------------------------------------------- contenu
def court(p, sur_ble, ecart=None):
    """Même résumé de la tranche que la page (tuiles « Décisions du jour ») ; orges : prix de l'orge (blé + écart du jour)."""
    if not p:
        return "—"
    if p.get("code") == "rien":
        return f"Prochaine tranche : {p.get('periode', '')}"
    if sur_ble and p.get("ordre") and ecart is not None:
        prix = f"à ≈ {n(p['ordre'] + ecart)} €/t"
    else:
        prix = f"{'blé ≥ ' if sur_ble else 'à '}{n(p['ordre'])} €/t" if p.get("ordre") else ""
    return {"ordre": f"{p['pct']} % {prix}", "executer": f"{p['pct']} % {prix or 'cette période'}".strip(),
            "attendre": f"Décaler les {p['pct']} %", "patienter": f"{p['pct']} % au prochain rebond",
            "couvrir": f"Couvrir {p['pct']} %"}.get(p.get("code"), f"{p.get('pct', '')} %")


def stock_txt(st):
    if not st or not st.get("code") or st["code"] == "nouvelle":
        return ""
    b = st.get("meilleure") or {}
    if st["code"] == "stocker":
        return f"Stocker jusqu'à {mfr(b.get('echeance'))} : {sg(b.get('gain'))} €/t net"
    if st["code"] == "vendre":
        return "Stockage non payé : vendre plutôt que stocker"
    return f"Stockage à peine payé ({sg(b.get('gain'))} €/t net)"


def page_html(d):
    cultures = d.get("cultures") or {}
    contrats = d.get("contrats") or {}
    com = d.get("comite") or {}
    eng = d.get("engrais") or {}
    seance = (contrats.get("EBM") or {}).get("seance") or d.get("date")
    # 1. décisions du jour
    rows = []
    for k, c in cultures.items():
        plan = c.get("plan") or []
        due = next((p for p in plan if p.get("statut") == "due" and not p.get("avant_moisson")), None) or \
            next((p for p in plan if p.get("statut") == "due"), None) or (plan[0] if plan else None)
        lab, cl = DECISION.get((due or {}).get("code"), ("—", "neutral"))
        con = contrats.get(c.get("contrat")) or {}
        phys = c.get("physique") or {}
        cours = phys.get("prix") if phys.get("prix") else con.get("dernier_reel")
        v1 = (con.get("technique") or {}).get("var1s")
        th = con.get("thermo") or {}
        sur = (c.get("niveaux_retenus") or {}).get("sur_ble")
        gap = ((d.get("orges") or {}).get(k) or {}).get("ecart_ble") if sur else None
        sous = f"Récolte {due['recolte']} · {due['periode']}" if due and due.get("periode") else ""
        if sur and due and due.get("ordre"):
            sous += f"<br>quand le blé Euronext atteint {n(due['ordre'])}&nbsp;€/t"
        autre = next((p for p in plan if p is not due and p.get("statut") == "due"), None)
        if autre:
            sous += f"<br>Récolte {autre['recolte']} : {e(court(autre, sur, gap))}"
        st = "" if c.get("proxy") else stock_txt(con.get("stockage"))
        rows.append(
            f"<tr><td class='cn'><b>{e(c['nom'].replace(' brassicole', ''))}</b>"
            f"<div class='muted'>{e(SIGNAL.get(c.get('signal'), ('—',))[0])}{' · suit le blé' if c.get('proxy') else ''}</div></td>"
            f"<td>{badge(lab, cl)}<div class='quoi'>{e(court(due, sur, gap))}</div><div class='muted'>{sous}</div></td>"
            f"<td class='r'><b>{n(cours)} €/t</b>{'<div class=muted>physique</div>' if phys.get('prix') else ''}"
            f"{f'<div class=muted>{sg(v1, 1)} % en 1 sem.</div>' if v1 is not None and not c.get('proxy') else ''}</td>"
            f"<td>{jauge(th.get('percentile'), 'vendeur', compact=True) if th else '—'}"
            f"{'<div class=muted>selon le blé</div>' if c.get('proxy') and th else ''}{f'<div class=muted>{e(st)}</div>' if st else ''}</td></tr>")
    ec = eng.get("comite") or {}
    elab, ecl = ENGRAIS.get(ec.get("signal") or eng.get("signal"), ("—", "neutral"))
    ur = (eng.get("france") or {}).get("uree") or {}
    plaf = f"<div class='muted'>Plafond d'achat : {n(ec.get('prix_plafond'), 0)} €/t</div>" if ec.get("prix_plafond") else ""
    uree = f"<b>{n(ur.get('prix'))} €/t</b><div class='muted'>urée</div>" if ur.get("prix") else "—"
    rows.append(
        f"<tr><td class='cn'><b>Azote (achat)</b><div class='muted'>{'avis du comité' if ec.get('signal') else 'règles chiffrées'}</div></td>"
        f"<td>{badge(elab, ecl)}<div class='quoi'>{e((ec.get('pct') or eng.get('a_acheter') or '').split('(')[0].strip())}</div>"
        f"{plaf}</td><td class='r'>{uree}</td>"
        f"<td>{jauge(eng.get('percentile_retenu'), 'ratio', compact=True)}<div class='muted'>ratio azote/blé sur 10 ans</div></td></tr>")
    decisions = ("<table class='dec'><thead><tr><th>Culture</th><th>Que faire</th><th class='r'>Cours</th>"
                 "<th>Prix sur 5 ans</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

    # 2. détail par culture (contrats Euronext)
    blocs = []
    for prod, main in (("EBM", "ble"), ("ECO", "colza"), ("EMA", "mais")):
        con, c = contrats.get(prod) or {}, cultures.get(main) or {}
        if not con or not c:
            continue
        nr = c.get("niveaux_retenus") or {}
        cc = c.get("comite") or {}
        th = con.get("thermo") or {}
        pl = con.get("prime_locale") or {}
        ta = con.get("technique") or {}
        met = ((d.get("meteo") or {}).get("cultures") or {}).get(main)
        sa = (d.get("saison") or {}).get(main)
        kv = [("Ordres", " · ".join(n(o) for o in nr.get("ordres") or []) + (f" €/t ({mfr(nr.get('echeance'))})" if nr.get("ordres") else "") or "—"),
              ("Révision", f"sous {n(nr['revision'])} €/t" if nr.get("revision") else "—"),
              ("Timing", (c.get("feu") or {}).get("texte", "—")),
              ("Stocker ?", (con.get("stockage") or {}).get("texte", "—"))]
        if pl.get("places"):
            kv.append(("Prime locale", " · ".join(f"{x['place']} {sg(x['prime'])} €/t" for x in pl["places"])))
        if met:
            alertes = [f"{z['zone']} {z['etat']}" for z in met.get("zones", []) if z.get("etat") != "normal" and z.get("saison")]
            kv.append(("Météo", f"note {sg(met.get('score'))}" + (" : " + ", ".join(alertes) if alertes else " : rien à signaler en saison")))
        if sa:
            kv.append(("Mois chers", ", ".join(MOIS[m - 1] for m in sa.get("plus_chers", []))))
        if ta.get("rsi") is not None:
            kv.append(("Technique", f"RSI {n(ta.get('rsi'), 0)} · MACD {'haussier' if (ta.get('histo') or 0) > 0 else 'baissier'} · "
                       f"{sg(ta.get('ecart_mm20'), 1)} % vs MM20"))
        ceu = ((d.get("cot") or {}).get("EURONEXT_" + prod) or {}).get("indice")
        jauges = jauge(th.get("percentile"), "vendeur", "Prix sur 5 ans" + (" (indicatif : huile de soja)" if "soja" in str(th.get("source", "")).lower() else ""),
                       f"{th.get('source', 'marché mondial')} en €/t, 5 ans") if th else ""
        if ceu is not None:
            jauges += jauge(ceu, "cot", "Fonds sur Euronext (3 ans)")
        if pl.get("percentile") is not None:
            jauges += jauge(pl["percentile"], "prime", "Prime locale (1 an)")
        sig, scl = SIGNAL.get(c.get("signal"), ("—", "neutral"))
        # historique Euronext encore court : lecture de secours (marché américain recalé), comme sur la page
        src = (con.get("proxy") or {}).get("graphique") or con.get("graphique") or []
        graph = chart_svg(src, nr.get("ordres") or [], nr.get("revision"))
        if graph:
            graph += ("<div class='cleg'><i style='background:#866400'></i>cours (6 mois"
                      + (f", {e((con.get('proxy') or {}).get('nom', ''))} recalé" if con.get("proxy") else "") + ") "
                      "<i class='d' style='border-color:#2a78d6'></i>MM20 <i class='d' style='border-color:#1f7a3e'></i>ordres "
                      "<i class='d' style='border-color:#b0281f'></i>révision</div>")
        blocs.append(
            f"<section class='bloc'><h3>{e(con.get('nom'))} <span class='muted'>Euronext {prod} · {n(con.get('dernier_reel'))} €/t "
            f"({mfr(con.get('echeance'))})</span></h3><div class='sigl'>{badge(sig, scl)}"
            f"<span>{e(cc.get('texte') or c.get('note') or '')}</span></div>"
            f"<div class='duo'><div>{graph}</div><div class='jcol'>{jauges}</div></div>"
            "<table class='kv'>" + "".join(f"<tr><th>{e(a)}</th><td>{e(b)}</td></tr>" for a, b in kv) + "</table></section>")

    # 3. orges brassicoles
    org = []
    for k, o in (d.get("orges") or {}).items():
        c = cultures.get(k) or {}
        due = next((p for p in c.get("plan") or [] if p.get("statut") == "due"), None)
        org.append(f"<tr><td><b>{e(o.get('nom'))}</b></td><td class='r nw'>{n(o.get('prix'))} €/t</td>"
                   f"<td class='r nw'>{sg(o.get('prime'))} €/t</td><td class='r nw'>{sg(o.get('ecart_ble'))} €/t</td>"
                   f"<td>{e((due or {}).get('action', '—'))}</td></tr>")
    orges = ("<table class='tab'><thead><tr><th>Orge (Creil FOB)</th><th class='r nw'>Prix</th><th class='r nw'>Prime</th>"
             "<th class='r nw'>Écart / blé</th><th>Plan</th></tr></thead><tbody>" + "".join(org) + "</tbody></table>") if org else ""

    # 4. engrais
    mond, est, ttf = eng.get("mondial") or {}, eng.get("estimation") or {}, eng.get("ttf") or {}
    ej = "".join([jauge(est.get("percentile"), "ratio", f"Ratio azote/blé estimé ce matin : {n(est.get('ratio'), 3)}") if est else "",
                  jauge(mond.get("percentile"), "ratio", f"Ratio mondial ({mfr(mond.get('mois'))}) : {n(mond.get('ratio'), 3)}") if mond else "",
                  jauge(mond.get("uree_percentile"), "acheteur", f"Urée mondiale sur 10 ans : {n(mond.get('uree'), 0)} $/t") if mond else "",
                  jauge(ttf.get("percentile_5ans"), "acheteur", f"Gaz TTF sur 5 ans : {n(ttf.get('dernier'))} €/MWh") if ttf else ""])
    fr = "".join(f"<tr><td>{e(v.get('nom'))}</td><td class='r'>{n(v.get('prix'))} €/t</td><td class='r'>{sg(v.get('var1m'), 1) + ' %' if v.get('var1m') is not None else '—'}</td>"
                 f"<td class='r'>{n(v.get('euro_un'), 3) if v.get('euro_un') else '—'}</td></tr>" for v in (eng.get("france") or {}).values())
    engrais = (f"<div class='sigl'>{badge(elab, ecl)}<span>{e(ec.get('texte') or '')}</span></div><div class='jrow'>{ej}</div>"
               "<ul class='notes'>" + "".join(f"<li>{e(x)}</li>" for x in eng.get("notes") or []) + "</ul>"
               + (("<table class='tab'><thead><tr><th>Engrais France</th><th class='r'>Prix</th><th class='r'>1 mois</th>"
                   "<th class='r'>€ par kg d'azote</th></tr></thead><tbody>" + fr + "</tbody></table>") if fr else ""))

    # 5. déclencheurs, carnet, calendrier
    trig = d.get("declencheurs") or []
    trig_h = ("<ul class='notes'>" + "".join(f"<li><b>{e(t['titre'])}</b> — {e(t.get('detail'))}</li>" for t in trig) + "</ul>") if trig \
        else "<p class='muted'>Aucun déclencheur ce matin.</p>"
    cb = (d.get("carnet") or {})
    juges = [x for x in cb.get("entrees") or [] if isinstance(x.get("s4"), dict) and x["s4"].get("variation") is not None]
    b = cb.get("bilan") or {}
    if juges:
        def ver(r):
            if not r or r.get("variation") is None:
                return f"en attente ({dfr((r or {}).get('le'))})"
            ic = {"bon": "bon", "mauvais": "mauvais"}.get(r.get("verdict"), "neutre")
            return f"{ic} ({sg(r.get('gain'))} €/t)" if r.get("gain") is not None else f"{ic} (cours {sg(r.get('pct'), 1)} %)"
        gm = f" · gain moyen {sg(b.get('gain_moyen'))} €/t" if b.get("gain_moyen") is not None else ""
        carnet = (f"<p>Avis jugés à 8 semaines : {b.get('bons', 0)} bon(s), {b.get('mauvais', 0)} mauvais{gm}.</p>"
                  "<table class='tab'><thead><tr><th>Date</th><th>Culture</th><th>Avis</th><th class='r'>Prix</th><th>4 semaines</th><th>8 semaines</th></tr></thead><tbody>"
                  + "".join(f"<tr><td>{dfr(x['date'])}</td><td>{e(x['cle'])}</td><td>{e(x['signal'].lower().replace('_', ' '))}</td>"
                            f"<td class='r'>{n(x.get('prix'))}</td><td>{e(ver(x.get('s4')))}</td><td>{e(ver(x.get('s8')))}</td></tr>"
                            for x in reversed(juges[-12:])) + "</tbody></table>")
    else:
        attente = sorted(x["s4"]["le"] for x in cb.get("entrees") or [] if isinstance(x.get("s4"), dict) and x["s4"].get("le"))
        carnet = f"<p class='muted'>Premiers résultats le {dfr(attente[0])} : chaque avis du comité est jugé 4 et 8 semaines après.</p>" if attente else ""
    cal = [x for x in com.get("calendrier") or [] if str(x.get("date", "")) >= str(d.get("date", ""))][:8]
    cal_h = ("<table class='tab'><tbody>" + "".join(f"<tr><td class='nw'><b>{dfr(x['date'])}</b></td><td>{e(x.get('evenement'))}</td></tr>" for x in cal)
             + "</tbody></table>") if cal else ""

    resume = f"<div class='resume'><b>Comité du {dfr(com.get('date'))}</b> — {e(com.get('resume'))}</div>" if com.get("resume") else ""
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Grain Signal — synthèse du {dfr(d.get('date'))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>{CSS}</style></head><body>
<header class="top"><div><div class="brand">Grain Signal</div><div class="muted">Synthèse du {dfr(d.get('date'))} · séance du {dfr(seance)}
{f" · comité du {dfr(com.get('date'))}" if com.get('date') else ''}</div></div>
<div class="legend">{badge('vert', 'good')} bon moment pour vendre (céréales) ou acheter (azote) · {badge('rouge', 'bad')} mauvais moment</div></header>
<h2>Décisions du jour</h2>{decisions}
<p class="muted small">ORDRE : placer un ordre de vente au prix indiqué, pas de vente au prix du jour · PATIENTER : attendre un rebond ·
VENDRE : la tranche peut partir · ATTENDRE : décaler · RIEN : pas de tranche prévue. Percentile : 10e = plus bas que 90 % des 5 dernières années.</p>
{resume}
<h2>Détail par culture</h2>{''.join(blocs)}
{f'<h2>Orges brassicoles</h2>{orges}' if orges else ''}
<h2>Engrais azotés</h2>{engrais}
<div class="two"><section><h2>Déclencheurs du jour</h2>{trig_h}</section><section><h2>Calendrier</h2>{cal_h or '<p class=muted>—</p>'}</section></div>
{f'<h2>Carnet de bord des avis</h2>{carnet}' if carnet else ''}
<p class="foot">Aide à la décision automatique, pas un conseil en investissement : la décision finale revient à l'exploitant.
Page complète : {e(d.get('url') or 'letmetry51.github.io/insider-pea/grain-signal.html')}</p>
</body></html>"""


CSS = """
@page { size: A4; margin: 13mm 12mm 15mm; }
* { box-sizing: border-box; }
body { font-family: 'IBM Plex Sans', 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif; font-size: 9.6pt; color: #1c1a12;
  line-height: 1.35; margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.top { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2.5px solid #866400; padding-bottom: 6px; }
.brand { font-size: 19pt; font-weight: 700; color: #866400; letter-spacing: -0.3px; }
.legend { font-size: 8pt; color: #625d4c; text-align: right; }
.legend .badge { font-size: 7pt; padding: 1px 5px; }
h2 { font-size: 12.5pt; margin: 14px 0 6px; color: #1c1a12; break-after: avoid; }
h2.newpage { break-before: page; margin-top: 0; }
h3 { font-size: 10.5pt; margin: 0 0 4px; }
.muted { color: #625d4c; font-weight: 400; }
.small { font-size: 8pt; }
.badge { display: inline-block; color: #fff; font: 600 8.6pt/1.25 'IBM Plex Mono', 'DejaVu Sans Mono', monospace; padding: 2px 6px;
  border-radius: 4px; white-space: nowrap; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; font-size: 7.6pt; text-transform: uppercase; letter-spacing: 0.3px; color: #625d4c; font-weight: 600; }
.r { text-align: right; }
.nw { white-space: nowrap; }
table.dec td, table.dec th { padding: 6px 6px; border-bottom: 1px solid #ddd6c3; vertical-align: top; }
table.dec tr { break-inside: avoid; }
table.dec td.cn { width: 19%; }
table.dec td:nth-child(2) { width: 37%; }
table.dec td:nth-child(3) { width: 14%; white-space: nowrap; }
.quoi { font-weight: 700; font-size: 10.5pt; margin: 3px 0 1px; }
.jauge { break-inside: avoid; }
.jauge .jt { font-size: 8pt; color: #625d4c; }
.jauge .jl { display: flex; align-items: center; gap: 5px; margin: 2px 0 1px; }
.jauge .jlab { font-weight: 600; font-size: 8.6pt; }
.jauge .jn { font-size: 7.6pt; color: #625d4c; }
.jauge.compact .badge { font-size: 7.8pt; padding: 1px 4px; }
.jauge.compact .jlab { font-size: 8pt; }
svg.gauge { display: block; margin: 1px 0 2px; }
.resume { background: #f4f0e2; border-left: 3px solid #866400; padding: 8px 10px; margin: 10px 0; break-inside: avoid; }
.bloc { border: 1px solid #ddd6c3; border-radius: 6px; padding: 9px 11px; margin: 0 0 10px; break-inside: avoid; }
.sigl { display: flex; gap: 8px; align-items: baseline; margin: 2px 0 6px; }
svg.chart { display: block; margin: 2px 0 6px; }
svg.chart .ax { font-size: 8.5px; fill: #625d4c; }
svg.chart .lv { font-size: 8.5px; font-weight: 700; }
.duo { display: grid; grid-template-columns: 1fr 190px; gap: 12px; align-items: start; }
.jcol .jauge { margin-bottom: 8px; }
.cleg { font-size: 7.4pt; color: #625d4c; margin: -2px 0 4px; }
.cleg i { display: inline-block; width: 12px; height: 3px; vertical-align: 2px; margin: 0 3px 0 8px; }
.cleg i:first-child { margin-left: 0; }
.cleg i.d { height: 0; border-top: 2px dashed; }
.jrow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 2px 0 6px; }
table.kv th { width: 22%; padding: 2px 6px 2px 0; text-transform: none; font-size: 8.4pt; letter-spacing: 0; vertical-align: top; }
table.kv td { padding: 1.5px 0; font-size: 8.6pt; }
table.tab td, table.tab th { padding: 4px 5px; border-bottom: 1px solid #e6e0cf; vertical-align: top; }
table.tab tr { break-inside: avoid; }
ul.notes { margin: 4px 0 8px; padding-left: 16px; }
ul.notes li { margin: 2px 0; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; break-inside: avoid; }
.foot { margin-top: 16px; font-size: 7.6pt; color: #625d4c; border-top: 1px solid #ddd6c3; padding-top: 5px; }
"""


def besoin():
    outbox = load(OUT / "prive" / "a-envoyer.json", [])
    sent = (load(OUT / "etat.json", {}) or {}).get("envoyes") or {}
    comite = any(x.get("type") == "comite" and x.get("id") not in sent for x in outbox if isinstance(x, dict))
    return comite or os.environ.get("GS_TEST_EMAIL", "").lower() == "true"


def main():
    if "--besoin" in sys.argv:
        ok = besoin()
        print("Synthèse PDF :", "à joindre" if ok else "pas d'email du comité aujourd'hui")
        return 0 if ok else 1
    d = load(OUT / "grain-signal.json", None)
    if not d:
        print("Synthèse PDF : pas de calcul du matin")
        return 1
    page = page_html(d)
    if "--html" in sys.argv:
        Path(sys.argv[sys.argv.index("--html") + 1]).write_text(page, encoding="utf-8")
        return 0
    from playwright.sync_api import sync_playwright

    PDF.parent.mkdir(parents=True, exist_ok=True)
    foot = ("<div style='font:7pt Arial,sans-serif;color:#777;width:100%;padding:0 12mm;display:flex;justify-content:space-between'>"
            f"<span>Grain Signal — synthèse du {e(dfr(d.get('date')))}</span>"
            "<span>page <span class='pageNumber'></span> / <span class='totalPages'></span></span></div>")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(page, wait_until="networkidle", timeout=60000)
        pg.pdf(path=str(PDF), format="A4", print_background=True, display_header_footer=True, header_template="<span></span>",
               footer_template=foot, prefer_css_page_size=True)
        b.close()
    print(f"Synthèse PDF : {PDF.stat().st_size // 1024} ko")
    return 0


if __name__ == "__main__":
    sys.exit(main())
