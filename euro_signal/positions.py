"""
Euro Signal — suivi de VOS positions et alertes de revente personnelles.

Confidentialité : le dépôt et le tableau de bord sont publics. Vos positions n'y sont donc jamais écrites.
Elles vivent uniquement dans votre Gmail :
  - « Je l'ai acheté » (fiche du tableau de bord) prépare un email à vous-même, objet « [Euro Signal] Position <ISIN> »,
    avec le prix payé, la date, l'objectif de hausse et le seuil de protection ;
  - « Je l'ai vendu » prépare un email « [Euro Signal] Vente <ISIN> » qui clôt le suivi ;
  - « Surveiller » (plan d'entrée d'une fiche) prépare « [Euro Signal] Surveiller <ISIN> » ; « Ne plus surveiller » l'arrête.
    Alerte quand le cours entre dans la zone d'achat, casse sa résistance ou la droite haute d'un biseau descendant,
    ou passe sous le stop du plan (une seule fois par niveau).
Chaque soir, ce script relit ces emails dans le dossier « Envoyés » (seuls les messages envoyés depuis votre compte
comptent), compare au dernier cours et vous écrit, une seule fois par événement :
  - objectif de hausse atteint ;
  - seuil de protection franchi ;
  - vente d'un dirigeant depuis votre achat ;
  - rappel à 6 mois : sur 8 ans de cours (2018-2026), garder 6 mois les premières du classement a donné 64 % de gagnants ;
    les sorties sur MM50 sous MM200, sur recul de 20 % depuis le plus haut ou sur stop serré (−15 %) en ont donné 45 à 52 %.
    Ces deux signaux ne sont donc plus envoyés (test du 17/10/2026).
L'unicité des envois est vérifiée dans votre dossier « Envoyés » (référence dans l'objet) : rien n'est stocké ailleurs.
Le journal GitHub étant public, le script n'y écrit rien de personnel : ni ISIN, ni prix, ni adresse, ni même le nombre de positions.
"""
import email
import imaplib
import json
import os
import math
import re
import smtplib
import ssl
import sys
from datetime import date, datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
# sociétés du catalogue sans dossier Euro Signal (classement tendance + comptes) : symbole Yahoo, ex. « VOLV-B.ST »
SYM_RE = re.compile(r"\]\s*(?:Position|Vente|Surveiller|Ne plus surveiller)\s+([A-Z0-9][A-Z0-9&-]{0,20}\.[A-Z]{1,3})\b")
DRAWDOWN_PCT = 20  # plus utilisé pour les alertes (voir l'en-tête)
HOLD_DAYS = 182
STOP_DEFAULT = 30


def pc(v):
    return ("%+.1f %%" % v).replace(".", ",")


def num(s):
    if s is None:
        return None
    s = str(s).strip().replace(" ", "").replace(" ", "").replace("%", "").replace("€", "").replace("+", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        v = float(s)
        return v if v == v else None
    except ValueError:
        return None


def text_of(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")


def parse_position(subject, body, sent_at):
    """Objet « [Euro Signal] Position ISIN » ou « [Euro Signal] Vente ISIN » ; corps en lignes « clé : valeur »."""
    m = ISIN_RE.search(subject or "") or SYM_RE.search(subject or "")
    if not m:
        return None
    kind = ("arret" if re.search(r"\]\s*Ne plus surveiller\b", subject, re.I) else "surveiller" if re.search(r"\]\s*Surveiller\b", subject, re.I)
            else "vente" if re.search(r"\]\s*Vente\b", subject, re.I) else "position" if re.search(r"\]\s*Position\b", subject, re.I) else None)
    if not kind:
        return None
    kv = {}
    for line in (body or "").splitlines():
        mm = re.match(r"\s*([^:\n]{2,40}?)\s*:\s*(.+?)\s*$", line)
        if mm:
            kv[mm.group(1).strip().lower().replace("’", "'")] = mm.group(2).strip()
    d = kv.get("date d'achat") or kv.get("date") or ""
    dm = re.search(r"(\d{4}-\d{2}-\d{2})", d) or re.search(r"(\d{2})/(\d{2})/(\d{4})", d)
    buy_date = None
    if dm:
        buy_date = dm.group(1) if len(dm.groups()) == 1 else f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"
    # plan d'entrée ajusté à la main dans la fiche (« ✏️ Ajuster le plan ») : il remplace le plan calculé pour les alertes
    custom = {k: num(kv.get(lbl)) for k, lbl in (("entry", "entrée ajustée"), ("stop", "stop ajusté"), ("target", "objectif ajusté"), ("ref", "cours à la demande"))}
    custom = {k: v for k, v in custom.items() if v and v > 0}
    return {
        "kind": kind, "isin": m.group(1), "sentAt": sent_at, "name": kv.get("société"),
        "price": num(kv.get("prix d'achat") or kv.get("prix")), "date": buy_date or sent_at[:10],
        "target": num(kv.get("objectif de hausse") or kv.get("objectif")), "stop": num(kv.get("seuil de protection") or kv.get("protection")),
        "custom": custom if any(k in custom for k in ("entry", "stop", "target")) else None,
    }


def sent_folder(imap):
    typ, data = imap.list()
    for raw in data or []:
        line = raw.decode("utf-8", "replace")
        if "\\Sent" in line:
            return line.split(' "/" ')[-1].strip()
    return '"[Gmail]/Sent Mail"'


def read_positions(imap):
    """Dernier message par ISIN dans les Envoyés : une Position ouvre ou met à jour, une Vente clôt."""
    folder = sent_folder(imap)
    imap.select(folder, readonly=True)
    typ, data = imap.search(None, '(SUBJECT "[Euro Signal]")')
    latest, watch, refs = {}, {}, set()
    for mid in (data[0].split() if data and data[0] else []):
        typ, msgdata = imap.fetch(mid, "(RFC822)")
        if not msgdata or not msgdata[0]:
            continue
        msg = email.message_from_bytes(msgdata[0][1])
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        for r in re.findall(r"réf\. ([A-Za-z0-9:._-]+)", subject):
            refs.add(r)  # alertes de revente déjà envoyées
        try:
            sent_at = email.utils.parsedate_to_datetime(msg.get("Date")).astimezone(timezone.utc).isoformat()
        except Exception:
            sent_at = datetime.now(timezone.utc).isoformat()
        p = parse_position(subject, text_of(msg), sent_at)
        if not p:
            continue
        box = watch if p["kind"] in ("surveiller", "arret") else latest  # surveillance et positions sont indépendantes
        if p["isin"] not in box or p["sentAt"] > box[p["isin"]]["sentAt"]:
            box[p["isin"]] = p
    positions = [p for p in latest.values() if p["kind"] == "position" and p["price"]]
    return positions, refs, [p for p in watch.values() if p["kind"] == "surveiller"]


def level_key(v):
    """Niveau arrondi par tranches d'environ 1 % : stable d'un soir à l'autre malgré les petites variations de l'ATR."""
    return int(round(math.log(v) * 100)) if v and v > 0 else 0


def watch_events(plan, last, today=None):
    """Déclenchements du plan d'entrée au dernier cours. La clé ne dépend que du niveau technique (support, résistance,
    stop) ou de la semaine (biseau, dont les droites bougent chaque jour) : une seule alerte par événement, jamais
    un email chaque soir tant que la situation dure."""
    if not plan or not last:
        return []
    pr, ev = plan.get("primary") or {}, []
    k = pr.get("key")
    f = lambda v: ("%.2f" % v).replace(".", ",")
    lvl = pr.get("level") or pr.get("zoneLo") or pr.get("trigger") or pr.get("entry")
    if k in ("support", "retest") and pr.get("zoneLo") and pr.get("zoneHi") and pr["zoneLo"] <= last <= pr["zoneHi"]:
        ev.append(("zone%d" % level_key(lvl), "entre dans sa zone d'achat (%s à %s), à confirmer par une clôture de rebond" % (f(pr["zoneLo"]), f(pr["zoneHi"]))))
    if k == "breakout" and pr.get("trigger") and last > pr["trigger"]:
        ev.append(("cassure%d" % level_key(lvl), "clôture au-dessus du déclencheur %s : cassure de la résistance" % f(pr["trigger"])))
    w = plan.get("wedge") or {}
    if w.get("type") == "falling" and w.get("upperNow") and last > w["upperNow"]:
        y, wk, _ = (today or date.today()).isocalendar()
        ev.append(("biseau%d%02d" % (y, wk), "sortie par le haut du biseau descendant (droite haute vers %s)" % f(w["upperNow"])))
    if plan.get("verdict") == "buyNow":
        ev.append(("achat%d" % level_key(lvl), "plan d'entrée : %s" % (plan.get("label") or "zone d'entrée").lower()))
    if pr.get("stop") and last < pr["stop"]:
        ev.append(("stop%d" % level_key(lvl), "sous le stop du plan (%s) : le scénario est invalidé" % f(pr["stop"])))
    return ev


def custom_events(c, last):
    """Plan ajusté à la main : prix d'entrée (franchi dans le sens où il a été fixé), stop et objectif. Une alerte par niveau."""
    if not c or not last:
        return []
    f = lambda v: ("%.2f" % v).replace(".", ",")
    ev, e, ref = [], c.get("entry"), c.get("ref")
    if e:
        if ref and ref > e * 1.005:
            hit, txt = last <= e * 1.005, "descend à votre prix d'entrée (%s)" % f(e)
        elif ref and ref < e * 0.995:
            hit, txt = last >= e, "franchit votre prix d'entrée (%s)" % f(e)
        else:
            hit, txt = abs(last / e - 1) <= 0.01, "est à votre prix d'entrée (%s)" % f(e)
        if hit:
            ev.append(("perso-entree%d" % level_key(e), txt))
    if c.get("stop") and last <= c["stop"]:
        ev.append(("perso-stop%d" % level_key(c["stop"]), "passe sous votre stop (%s)" % f(c["stop"])))
    if c.get("target") and last >= c["target"]:
        ev.append(("perso-objectif%d" % level_key(c["target"]), "atteint votre objectif (%s)" % f(c["target"])))
    return ev


def plan_txt(c):
    """Résumé d'un plan ajusté à la main, pour le corps de l'email."""
    if not c:
        return None
    f = lambda v: ("%.2f" % v).replace(".", ",")
    return "ajusté à la main (" + ", ".join(lbl + " " + f(c[k]) for k, lbl in (("entry", "entrée"), ("stop", "stop"), ("target", "objectif")) if c.get(k)) + ")"


def shard_of(sym, n=32):
    """Même répartition que ES.shardOf (fiches du catalogue)."""
    h = 0
    for ch in str(sym):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % n


def catalogue_rows(sym):
    """Clôtures journalières (un an) d'une société du catalogue, au format [date, o, h, l, close, v]."""
    try:
        sh = json.loads((DATA / "societes" / ("%d.json" % shard_of(sym))).read_text(encoding="utf-8"))
    except Exception:
        return []
    x = (sh.get("items") or {}).get(sym) or {}
    return [[d, c, c, c, c, None] for d, c in zip(sh.get("dDates") or [], x.get("d") or []) if d and c]


def death_cross(rows, since):
    """Date à laquelle la MM50 est repassée sous la MM200 après « since » (clôtures journalières), sinon None."""
    c = [(r[0], r[4]) for r in rows if r and r[4]]
    if len(c) < 201:
        return None
    vals = [v for _, v in c]
    prev = None
    for k in range(200, len(c)):
        below = sum(vals[k - 49:k + 1]) / 50 < sum(vals[k - 199:k + 1]) / 200
        if prev is False and below and c[k][0] > since:
            return c[k][0]
        prev = below
    return None


def evaluate(pos, rows, stats, txs, today, in_pick=None):
    """Événements de revente pour une position. rows : [[date, o, h, l, close, v], …] (cours bruts suffisent ici)."""
    closes = [(r[0], r[4]) for r in rows if r and r[4]]
    after = [c for d, c in closes if d >= pos["date"]]
    if not after:
        return [], None
    last, peak, buy = after[-1], max(after), pos["price"]
    perf = (last / buy - 1) * 100
    ev = []
    if pos.get("target") and perf >= pos["target"]:
        ev.append(("obj" + str(int(pos["target"])), "objectif de +%d %% atteint (%s depuis votre achat)" % (pos["target"], pc(perf))))
    stop = abs(pos.get("stop") or STOP_DEFAULT)  # règle testée : protection à −30 % si rien n'a été indiqué
    if perf <= -stop:
        ev.append(("stop" + str(int(stop)), "seuil de protection de -%d %% franchi (%s depuis votre achat) : la règle testée est de vendre" % (stop, pc(perf))))
    # paliers de baisse de 10 % : un seul email par palier, le plus profond franchi ce soir
    lvl = int(-perf // 10) * 10 if perf <= -10 else 0
    if lvl and lvl != int(stop):
        ev.append(("baisse%d" % lvl, ("baisse de %d %% depuis votre achat (%s) : %s" % (lvl, pc(perf),
                   "la règle testée est de garder jusqu'à la protection à -%d %% ; sur 29 ans, 2 lignes 🎯 sur 3 finissaient en hausse à 6 mois malgré des replis" % stop
                   if lvl < stop else "sous la protection de -%d %%, la règle testée était de vendre" % stop))))
    sells = [t for t in (txs or []) if t.get("type") == "vente" and t.get("status") != "annulee" and (t.get("pubDate") or t.get("txDate") or "") > pos["date"]]
    if sells:
        ev.append(("vente" + max((t.get("pubDate") or t.get("txDate")) for t in sells).replace("-", ""),
                   "un dirigeant a vendu depuis votre achat (" + ", ".join(((t.get("person") or "?") + " le " + (t.get("txDate") or "?")) for t in sells[:3]) + ")"))
    try:
        held = (today - date.fromisoformat(pos["date"][:10])).days
    except (TypeError, ValueError):
        held = 0
    if held >= HOLD_DAYS:
        if in_pick is True:
            nxt = "elle est encore dans le 🎯 ou le 💎 cette semaine : vous pouvez la garder comme une nouvelle ligne de 6 mois (dans un PEA, garder revient à vendre puis racheter, sans frais)"
        elif in_pick is False:
            nxt = "elle n'est plus dans le 🎯 ni le 💎 : la règle est de vendre et de réinvestir dans une société proposée"
        else:
            nxt = "vendre, puis racheter seulement si elle figure encore dans le 🎯"
        ev.append(("6mois", "6 mois depuis votre achat (%s) : c'est l'horizon testé (62 %% de gagnants sur 29 ans) ; %s" % (pc(perf), nxt)))
    return ev, {"last": last, "perf": perf, "peak": peak}


SECTORS_FR = {"Basic Materials": "Matériaux de base", "Communication Services": "Médias et télécoms", "Consumer Cyclical": "Consommation cyclique",
              "Consumer Defensive": "Consommation courante", "Energy": "Énergie", "Financial Services": "Finance", "Healthcare": "Santé", "Industrials": "Industrie",
              "Real Estate": "Immobilier", "Technology": "Technologie", "Utilities": "Services aux collectivités"}


def correlation(a, b, n=120):
    """Corrélation des rendements quotidiens sur les n dernières séances communes (None si trop peu de données)."""
    ca = {r[0]: r[4] for r in a if r and r[4]}
    cb = {r[0]: r[4] for r in b if r and r[4]}
    days = sorted(set(ca) & set(cb))[-(n + 1):]
    if len(days) < 40:
        return None
    ra = [ca[days[k]] / ca[days[k - 1]] - 1 for k in range(1, len(days))]
    rb = [cb[days[k]] / cb[days[k - 1]] - 1 for k in range(1, len(days))]
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / (va * vb) ** 0.5 if va > 0 and vb > 0 else None


def diversification(positions, dash, prices):
    """Concentration du portefeuille suivi : secteurs trop représentés, titres qui évoluent ensemble. Texte ou None."""
    n = len(positions)
    if n < 2:
        return None
    inst = dash.get("inst") or {}
    by = {}
    for p in positions:
        sec = SECTORS_FR.get((inst.get(p["isin"]) or {}).get("sector") or "", "Secteur inconnu")
        by.setdefault(sec, []).append((inst.get(p["isin"]) or {}).get("name") or p["isin"])
    heavy = [(s, l) for s, l in by.items() if s != "Secteur inconnu" and len(l) >= 2 and (n >= 3 and len(l) / n >= 0.5 or len(l) >= 3)]
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = prices.get(positions[i]["isin"]), prices.get(positions[j]["isin"])
            c = correlation(a.get("rows") or [], b.get("rows") or []) if a and b else None
            if c is not None and c >= 0.75:
                pairs.append(((inst.get(positions[i]["isin"]) or {}).get("name") or positions[i]["isin"], (inst.get(positions[j]["isin"]) or {}).get("name") or positions[j]["isin"], c))
    if not heavy and not pairs:
        return None
    lines = ["Vos %d positions suivies se répartissent ainsi :" % n] + ["  - %s : %d (%s)" % (s, len(l), ", ".join(l)) for s, l in sorted(by.items(), key=lambda x: -len(x[1]))]
    if heavy:
        lines.append("")
        lines += ["Concentration : %d positions sur %d en %s. Un même choc (taux, matières premières, réglementation) toucherait toutes ces lignes à la fois." % (len(l), n, s) for s, l in heavy]
    if pairs:
        lines.append("")
        lines += ["%s et %s évoluent presque ensemble (corrélation %s sur 6 mois) : elles comptent presque comme une seule position." % (a, b, ("%.2f" % c).replace(".", ",")) for a, b, c in pairs[:5]]
    lines += ["", "Repères : pas plus de 25 à 30 % du portefeuille dans un même secteur, et 8 à 15 lignes peu corrélées pour diluer le risque propre à chaque société.",
              "Ce message n'est envoyé qu'en cas de concentration, au plus une fois par semaine. Ce n'est pas un ordre : à vous de juger."]
    return "\n".join(lines)


def main():
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not (user and pwd):
        print("Positions : Gmail non configuré, rien à suivre")
        return 0
    try:
        prices = json.loads((DATA / "prices.json").read_text(encoding="utf-8")).get("items", {})
    except Exception:
        prices = {}
    try:
        dash = json.loads((DATA / "euro-signal.json").read_text(encoding="utf-8"))
    except Exception:
        dash = {}
    try:
        state = json.loads((DATA / "euro-signal-state.json").read_text(encoding="utf-8"))
    except Exception:
        state = {}
    dash_url = ((dash.get("cfg") or {}).get("dashboardUrl")) or ""
    pk = (dash.get("rank") or {}).get("pick10")
    vk = (dash.get("rank") or {}).get("value10")
    picks = (set(pk) | set(vk if isinstance(vk, list) else [])) if isinstance(pk, list) else None  # 🎯 et 💎 de ce soir (ISIN ou symbole)
    today = date.today().isoformat()
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context())
        imap.login(user, pwd)
        positions, refs, watches = read_positions(imap)
        imap.logout()
    except Exception as e:
        print("Positions : lecture Gmail impossible (" + type(e).__name__ + ")")
        return 0
    to_send = []
    for pos in positions:
        isin = pos["isin"]
        p = prices.get(isin)
        inst = (dash.get("inst") or {}).get((dash.get("aliases") or {}).get(isin, isin)) or {}  # ancien ISIN réuni à un autre dossier
        name = inst.get("name") or pos.get("name") or isin
        if not p and not ISIN_RE.fullmatch(isin):  # société du catalogue : cours du catalogue, MM50 / MM200 recalculées ici
            rows = catalogue_rows(isin)
            p = {"rows": rows} if rows else None
            stats = {"deathCrossDate": death_cross(rows, pos["date"])} if rows else {}
        else:
            stats = inst.get("stats") or {}
        if not p:
            continue
        evs, info = evaluate(pos, p.get("rows") or [], stats, (state.get("txArchive") or {}).get(isin) or [], today,
                             (isin in picks) if picks is not None else None)
        for key, label in evs:
            ref = "%s:%s:%s" % (isin, pos["date"].replace("-", ""), key)
            if ref in refs:
                continue
            body = ("%s — %s.\n\nVotre achat : %s le %s. Dernier cours : %s (%s).\n"
                    "Règles testées : garder 6 mois, vendre sous -30 %%. Ce n'est pas un ordre : à décider selon votre stratégie.\n"
                    "Pour arrêter le suivi : bouton « Je l'ai vendu » dans la fiche%s.") % (
                name, label, ("%.2f" % pos["price"]).replace(".", ","), pos["date"], ("%.2f" % info["last"]).replace(".", ","), pc(info["perf"]),
                (" : " + dash_url + "#" + (isin if ISIN_RE.fullmatch(isin) else "co=" + isin)) if dash_url else "")
            to_send.append(("[Euro Signal] Revente — %s : %s (réf. %s)" % (name, label.split(" (")[0], ref), body))
    # Plans d'entrée surveillés
    rank_by_sym = {r.get("sym"): r for r in ((dash.get("rank") or {}).get("rows") or []) if isinstance(r, dict) and r.get("sym")}
    for w in watches:
        isin = w["isin"]
        p = prices.get(isin)
        inst = (dash.get("inst") or {}).get((dash.get("aliases") or {}).get(isin, isin)) or {}  # ancien ISIN réuni à un autre dossier
        rows = [r for r in (p or {}).get("rows") or [] if r and r[4]]
        if not ISIN_RE.fullmatch(isin):  # société du catalogue : cours du catalogue, plan calculé le soir dans le classement
            rk = rank_by_sym.get(isin) or {}
            pw = rk.get("pw")
            rows = catalogue_rows(isin)
            inst = {"name": rk.get("name"), "plan": {"verdict": pw.get("v"), "label": pw.get("label"), "primary": pw.get("p") or {}, "wedge": pw.get("w") or {}}} if pw else {}
        if not rows or not (inst.get("plan") or w.get("custom")):
            continue
        last = rows[-1][4]  # dernier cours brut = dernier cours ajusté (aucun ajustement après la dernière séance)
        name = inst.get("name") or w.get("name") or isin
        evs = custom_events(w["custom"], last) if w.get("custom") else watch_events(inst["plan"], last)
        for key, label in evs:
            ref = "plan:%s:%s" % (isin, key)
            if ref in refs:
                continue
            body = ("%s %s.\n\nDernier cours : %s. Plan du soir : %s.\n%s\n"
                    "Ce n'est pas un ordre : vérifiez la fiche avant d'agir.\nPour arrêter : bouton « Ne plus surveiller » dans la fiche%s.") % (
                name, label, ("%.2f" % last).replace(".", ","), plan_txt(w.get("custom")) or (inst.get("plan") or {}).get("label") or "", ("Convergence : %s signaux sur 5." % inst["convergence"].get("n", "?")) if inst.get("convergence") else "",
                (" : " + dash_url + "#" + (isin if ISIN_RE.fullmatch(isin) else "co=" + isin)) if dash_url else "")
            to_send.append(("[Euro Signal] Plan — %s : %s (réf. %s)" % (name, label.split(" (")[0], ref), body))
    # Diversification : une fois par semaine au plus, seulement si une concentration apparaît
    try:
        div = diversification(positions, dash, prices)
    except Exception:
        div = None
    if div:
        wk = date.today().isocalendar()
        ref = "diversif:%d-W%02d" % (wk[0], wk[1])
        if ref not in refs:
            to_send.append(("[Euro Signal] Diversification de vos positions (réf. %s)" % ref, div))
    sent = 0
    if to_send:
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=40) as s:
                s.login(user, pwd)
                for subject, body in to_send:
                    msg = EmailMessage()
                    msg["Subject"], msg["From"], msg["To"] = subject, user, user  # vos positions ne vont qu'à vous
                    msg.set_content(body)
                    s.send_message(msg)
                    sent += 1
        except Exception as e:
            print("Positions : envoi interrompu (" + type(e).__name__ + ")")
    print("Positions : contrôle effectué")  # journal public : ni nombre de positions, ni nombre d'alertes
    return 0


if __name__ == "__main__":
    sys.exit(main())
