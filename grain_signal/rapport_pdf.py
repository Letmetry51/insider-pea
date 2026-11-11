"""
Grain Signal — synthèse PDF (A4) jointe au rapport du matin et à la lecture hebdomadaire : le marché, sans conseil.

Entrées : data/grain/grain-signal.json (calcul du matin). Sortie : data/grain/prive/synthese.pdf (jamais publiée).
Mise en page HTML/CSS imprimée par Chromium (Playwright) : jauges et graphiques en SVG, sans emoji (pas de police couleur
sur les serveurs), coupures de page maîtrisées (un bloc n'est jamais coupé en deux).

  python grain_signal/rapport_pdf.py            fabrique le PDF
  python grain_signal/rapport_pdf.py --besoin   code 0 si un email en a besoin (rapport du matin, lecture hebdo, test), 1 sinon
  python grain_signal/rapport_pdf.py --html F   écrit seulement la page HTML (contrôle de la mise en page)
"""
import html
import re
import os
import sys
from datetime import date
from pathlib import Path

from commun import load  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grain"
PDF = OUT / "prive" / "synthese.pdf"

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
COUL = {"good": "#1f7a3e", "bad": "#b0281f", "warn": "#9a5b00", "info": "#2a62b8", "neutral": "#6b6d60"}

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF]")


def e(t):
    """Texte échappé, sans emoji (les serveurs n'ont pas de police couleur : ils s'imprimeraient en carrés vides)."""
    return html.escape(EMOJI.sub("", str(t if t is not None else "")).strip(), quote=True)


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
# couleurs de position (bas → haut), sans jugement : bas = bleu, moyenne = gris, haut = ambre
SEG_P = [(20, "info"), (40, "info"), (60, "neutral"), (80, "warn"), (100, "warn")]
SEG_G = [(30, "neutral"), (70, "neutral"), (90, "warn"), (100, "bad")]  # risque géopolitique
LAB = {
    "prix": lambda v: ("Bas sur 5 ans", "info") if v <= 20 else ("Plutôt bas", "info") if v <= 40 else ("Dans la moyenne", "neutral")
    if v < 60 else ("Plutôt haut", "warn") if v < 80 else ("Haut sur 5 ans", "warn"),
    "stocks": lambda v: ("Stocks très serrés", "warn") if v <= 20 else ("Stocks plutôt serrés", "warn") if v <= 40 else
    ("Stocks dans la moyenne", "neutral") if v < 60 else ("Stocks plutôt confortables", "info") if v < 80 else ("Stocks très confortables", "info"),
    "psy": lambda v: ("Peur extrême", "info") if v <= 20 else ("Peur", "info") if v <= 40 else ("Humeur neutre", "neutral") if v < 60
    else ("Optimisme", "warn") if v < 80 else ("Euphorie", "warn"),
    "geo": lambda v: ("Monde calme", "neutral") if v <= 30 else ("Tensions habituelles", "neutral") if v < 70 else
    ("Tensions élevées", "warn") if v < 90 else ("Tensions très élevées", "bad"),
}
SEGS = {"prix": SEG_P, "stocks": [(20, "warn"), (40, "warn"), (60, "neutral"), (80, "info"), (100, "info")], "psy": SEG_P, "geo": SEG_G}
SENS = {"haussière": ("hausse", "good"), "baissière": ("baisse", "bad"), "neutre": ("neutre", "neutral"), "équilibrée": ("neutre", "neutral")}
ACTU_NOMS = {"ble": "Blé", "orge": "Orges", "colza": "Colza", "mais": "Maïs", "engrais": "Azote"}


def actu_html(d):
    """Actualité : synthèse et nouvelles qui comptent, avec leur effet sur les prix."""
    ac = load(OUT / "actualites.json", {}) or {}
    arts = [a for a in ac.get("articles") or [] if a.get("pertinent") and not a.get("doublon_de") and a.get("theme") != "marche"
            and (a.get("importance") or 0) >= 2]
    arts.sort(key=lambda a: ((a.get("importance") or 0), str(a.get("date"))), reverse=True)
    lis = []
    for a in arts[:4]:
        fx = " · ".join(f"<span style='color:{COUL['good'] if v > 0 else COUL['bad']}'>{ACTU_NOMS.get(c, c)} {'↑' * abs(v) if v > 0 else '↓' * abs(v)}</span>"
                        for c, v in (a.get("impacts") or {}).items() if v)
        lis.append(f"<li><b>{e(a.get('titre_fr') or a.get('titre'))}</b> <span class='muted'>({e(a.get('source') or '')}, {dfr(a['date'][:10])})</span>"
                   f"<br>{e(a.get('impact'))}{f'<br>{fx}' if fx else ''}</li>")
    if not lis and not ac.get("synthese"):
        return ""
    syn = f"<div class='resume'><b>Synthèse de l'actualité</b> — {e(ac['synthese'])}</div>" if ac.get("synthese") else ""
    return (syn + (f"<ul class='news'>{''.join(lis)}</ul>" if lis else "")
            + "<p class='muted small'>Titres de Google Actualités et de la presse agricole, classés par l'IA d'après leur seul titre "
              "(↑ pousse le prix à la hausse, ↓ à la baisse ; azote ↑ = plus cher).</p>")


def sens_badge(s_):
    t, cl = SENS.get(s_ or "", ("—", "neutral"))
    return badge(t, cl)


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
    txt = str(round(v)) if kind == "psy" else f"{round(v)}e"  # humeur : indice de 0 à 100, pas un percentile
    return (f"<div class='jauge{' compact' if compact else ''}'>{t}<div class='jl'>{badge(txt, cl)}"
            f"<span class='jlab'>{e(lab)}</span></div>{gauge_svg(v, SEGS[kind], 130 if compact else 170)}{nt}</div>")


def chart_svg(rows, resistances=(), supports=(), w=440, h=165):
    """Cours des 6 derniers mois (trait plein), MM20 (pointillés), résistances et supports (repères techniques)."""
    pts = [(r[0], r[1], r[2] if len(r) > 2 else None) for r in rows if r[1] is not None][-126:]
    if len(pts) < 5:
        return ""
    vals = [p[1] for p in pts] + [p[2] for p in pts if p[2] is not None] + list(resistances) + list(supports)
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
    niv = [(o, COUL["warn"], f"Résistance {n(o)}") for o in resistances] + [(o, COUL["info"], f"Support {n(o)}") for o in supports]
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
def page_html(d):
    cultures = d.get("cultures") or {}
    contrats = d.get("contrats") or {}
    com = d.get("comite") or {}
    eng = d.get("engrais") or {}
    seance = (contrats.get("EBM") or {}).get("seance") or d.get("date")
    # 1. le marché ce matin : cours, technique, actualité (calculés par build.py : mêmes chiffres que la page et l'email)
    rows = []
    for c in cultures.values():
        tq, ac = c.get("technique") or {}, c.get("actualite") or {}
        var = c.get("var1j")
        cours = (f"<b>{n(c['cours'])}</b>" + (f" <span class='muted'>{sg(var)}</span>" if var else "")
                 + ("<div class=muted>physique Creil</div>" if c.get("physique") else "")) if c.get("cours") else "—"
        niv = " · ".join(([f"résistance {n(tq['resistances'][0])}"] if tq.get("resistances") else [])
                         + ([f"support {n(tq['supports'][0])}"] if tq.get("supports") else []))
        rows.append(f"<tr><td class='cn'><b>{e(c['nom'].replace(' brassicole', '').replace(' tendre', ''))}</b></td><td class='r'>{cours}</td>"
                    f"<td>{sens_badge(tq.get('sens'))}{' <span class=muted>(blé)</span>' if tq.get('sur_ble') else ''}"
                    f"<div class='muted'>{e(niv)}</div></td>"
                    f"<td>{sens_badge(ac.get('sens'))}</td></tr>")
    u = (eng.get("france") or {}).get("uree") or {}
    if u.get("prix"):
        rows.append(f"<tr><td class='cn'><b>Azote</b></td><td class='r'><b>{n(u['prix'])}</b><div class=muted>urée"
                    + (f", {sg(u['var1m'], 1)} % en 1 mois" if u.get("var1m") is not None else "") + "</div></td>"
                    f"<td class='muted'>{e('Ratio azote/blé au ' + str(eng['percentile_retenu']) + 'e percentile (10 ans)') if eng.get('percentile_retenu') is not None else '—'}</td>"
                    f"<td>{sens_badge((eng.get('actualite') or {}).get('sens'))}{' <span class=muted>(+ = plus cher)</span>' if eng.get('actualite') else ''}</td></tr>")
    marche = ("<table class='dec'><thead><tr><th>Culture</th><th class='r'>Cours €/t</th><th>Technique</th><th>Actualité</th>"
              "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")

    # 2. détail par contrat Euronext
    blocs = []
    for prod, main in (("EBM", "ble"), ("ECO", "colza"), ("EMA", "mais")):
        con, c = contrats.get(prod) or {}, cultures.get(main) or {}
        if not con or not c:
            continue
        tq = c.get("technique") or {}
        rp = c.get("reperes") or {}
        th = con.get("thermo") or {}
        cc = c.get("comite") or {}
        kv = [("Technique", tq.get("texte") or "—"),
              ("Résistances", " · ".join(n(x) for x in tq.get("resistances") or []) + " €/t" if tq.get("resistances") else "—"),
              ("Supports", " · ".join(n(x) for x in tq.get("supports") or []) + " €/t" if tq.get("supports") else "—")]
        if rp.get("plus_haut") is not None:
            kv.append(("Campagne", f"plus haut {n(rp['plus_haut'])} €/t le {dfr(rp['plus_haut_le'])} ({sg(rp['ecart_plus_haut'])} €/t depuis)"))
        if (con.get("stockage") or {}).get("texte"):
            kv.append(("Report", con["stockage"]["texte"]))
        if cc.get("lecture"):
            kv.append(("Lecture de la semaine", cc["lecture"]))
        jauges = jauge(th.get("percentile"), "prix", "Prix sur 5 ans" + (" (indicatif : huile de soja)" if "soja" in str(th.get("source", "")).lower() else ""),
                       (f"Médiane {n(th.get('mediane'), 0)} €/t · habituel {n(th.get('p20'), 0)}–{n(th.get('p80'), 0)} €/t (Euronext, 5 ans)"
                        if th.get("euronext") else f"{th.get('source', 'marché mondial')} en €/t, 5 ans")) if th else ""
        stm = (d.get("stocks_mondiaux") or {}).get(main)
        if stm:
            jauges += jauge(stm["percentile"], "stocks", f"Stocks mondiaux / conso{' hors Chine' if stm.get('hors_chine') else ''}",
                            f"{n(stm['ratio'], 1)} % en {stm['campagne']} (moy. {n(stm['moyenne'], 1)} %) · USDA")
        src = (con.get("proxy") or {}).get("graphique") or con.get("graphique") or []
        graph = chart_svg(src, tq.get("resistances") or [], tq.get("supports") or [])
        if graph:
            graph += ("<div class='cleg'><i style='background:#866400'></i>cours (6 mois"
                      + (f", {e((con.get('proxy') or {}).get('nom', ''))} recalé" if con.get("proxy") else "") + ") "
                      "<i class='d' style='border-color:#2a78d6'></i>MM20 <i class='d' style='border-color:#9a5b00'></i>résistances "
                      "<i class='d' style='border-color:#2a62b8'></i>supports</div>")
        blocs.append(
            f"<section class='bloc'><h3>{e(con.get('nom'))} <span class='muted'>Euronext {prod} · {n(con.get('dernier_reel'))} €/t "
            f"({mfr(con.get('echeance'))})</span></h3>"
            f"<div class='duo'><div>{graph}</div><div class='jcol'>{jauges}</div></div>"
            "<table class='kv'>" + "".join(f"<tr><th>{e(a)}</th><td>{e(b)}</td></tr>" for a, b in kv) + "</table></section>")

    cal = [x for x in com.get("calendrier") or [] if str(x.get("date", "")) >= str(d.get("date", ""))][:3]
    trig = d.get("declencheurs") or []
    actu = actu_html(d)
    resume = (f"<div class='resume'><b>Lecture du marché de la semaine ({dfr(com.get('date'))})</b> — {e(com.get('resume'))}</div>"
              if com.get("resume") and com.get("valide") else "")
    agenda = ("<p class='small'><b>À venir :</b> " + " · ".join(f"{dfr(x['date'])} : {e(x.get('evenement'))}" for x in cal) + "</p>") if cal else ""
    alerte_h = ("<div class='resume'>" + "<br>".join(e(t["titre"]) for t in trig[:5]) + "</div>") if trig else ""
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Grain Signal — synthèse du {dfr(d.get('date'))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>{CSS}</style></head><body>
<header class="top"><div><div class="brand">Grain Signal</div><div class="muted">Synthèse du {dfr(d.get('date'))} · séance du {dfr(seance)}</div></div>
</header>
{alerte_h}<h2>Le marché ce matin</h2>{marche}
<p class="muted small">Technique : tendance des moyennes mobiles, élan (MACD) et excès (RSI) · Actualité : effet des nouvelles des
7 derniers jours sur le prix · Escourgeon et orge de printemps : prix physique, technique du blé.</p>
{agenda}{resume}
{f'<h2>Actualité</h2>{actu}' if actu else ''}
<h2>Par contrat</h2>{''.join(blocs)}
<p class="foot">Outil d'aide à la décision : il décrit le marché, il ne conseille ni de vendre ni d'acheter. La décision vous appartient.
Page complète : {e(d.get('url') or 'letmetry51.github.io/insider-pea/grain-signal.html')}</p>
</body></html>"""


CSS = """
ul.news { margin: 4px 0 8px; padding-left: 16px; } ul.news li { margin: 3px 0; break-inside: avoid; }
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
table.dec td.cn { width: 22%; }
table.dec td:nth-child(2) { width: 18%; white-space: nowrap; }
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import send_alerts

    return comite or bool(send_alerts.rapport_attendu(OUT)) or os.environ.get("GS_TEST_EMAIL", "").lower() == "true"


def main():
    if "--besoin" in sys.argv:
        ok = besoin()
        print("Synthèse PDF :", "à joindre" if ok else "aucun email ne la joint aujourd'hui")
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
