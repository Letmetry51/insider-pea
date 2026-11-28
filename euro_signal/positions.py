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
  - nouveaux comptes publiés, lus par l'IA (scrapers/comptes_ia.py) : résumé, points forts et faibles, avis et conseil, une seule
    fois par période (sauf pour une société du 🎯 / 💎 du soir, qui a déjà son email : euro_signal/build.mjs) ;
  - 🧾 ordres de la semaine (version mixte choisie par François le 28/11/2026, « Version 2 ») : le soir où part la sélection du
    lundi, un email à vous seul avec les ordres prêts à copier dans votre courtier : achats à cours limité (quantité selon votre
    montant par ligne, secret GitHub MONTANT_PAR_LIGNE, en euros), ordre stop de protection à poser ensuite, lignes déjà
    détenues, ventes dues (6 mois, protection franchie), protections à vérifier ou à reposer après un dividende. Rien n'est
    passé automatiquement : Euro Signal ne se connecte à aucun courtier ;
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
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail_status import record  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
# sociétés du catalogue sans dossier Euro Signal (classement tendance + comptes) : symbole Yahoo, ex. « VOLV-B.ST »
SYM_RE = re.compile(r"\]\s*(?:Position|Vente|Surveiller|Ne plus surveiller)\s+([A-Z0-9][A-Z0-9&-]{0,20}\.[A-Z]{1,3})\b")
# objet d'un email à lire en entier (positions, ventes, plans surveillés) ; les autres (alertes, contrôles) : objet seulement
POS_SUBJ = re.compile(r"\]\s*(?:Position|Vente|Surveiller|Ne plus surveiller)\b", re.I)
REF_RE = re.compile(r"réf\. ([A-Za-z0-9:._&-]+)")  # « & » comme dans SYM_RE (jusqu'au 04/11/2026 : réf. jamais reconnue, email chaque soir)
DRAWDOWN_PCT = 20  # plus utilisé pour les alertes (voir l'en-tête)
HOLD_DAYS = 182
STOP_DEFAULT = 30
ORDER_MARGIN = 0.02  # ordres prêts à copier : prix limite d'achat au dernier cours + 2 %
EXCHANGES = {"PA": "Euronext Paris", "AS": "Euronext Amsterdam", "BR": "Euronext Bruxelles", "LS": "Euronext Lisbonne",
             "IR": "Euronext Dublin", "MI": "Euronext Milan", "OL": "Euronext Oslo", "MC": "Bourse de Madrid", "DE": "Xetra (Francfort)",
             "F": "Bourse de Francfort", "VI": "Bourse de Vienne", "HE": "Nasdaq Helsinki", "ST": "Nasdaq Stockholm",
             "CO": "Nasdaq Copenhague", "WA": "Bourse de Varsovie", "PR": "Bourse de Prague"}


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


def sig3(v, up):
    """Prix arrondi à 3 chiffres significatifs, vers le haut (limite d'achat) ou vers le bas (seuil de protection) : un multiple des
    pas de cotation courants (28,3 ; 337 ; 14 000), que les courtiers acceptent."""
    if not v or v <= 0:
        return None
    e = math.floor(math.log10(v)) - 2
    k = v / 10 ** e
    k = math.ceil(k - 1e-9) if up else math.floor(k + 1e-9)
    return round(k * 10 ** e, max(0, -e))


def px_txt(v):
    """Prix à la française, avec les décimales d'un arrondi à 3 chiffres (« 28,3 », « 14 000 », « 0,523 »)."""
    d = max(0, 2 - math.floor(math.log10(v))) if v and v > 0 else 2
    return ("{:,.%df}" % d).format(v).replace(",", " ").replace(".", ",")


def amt_txt(v):
    """Cours ou montant exact à la française : 2 décimales sous 1 000 (« 27,68 »), aucune au-delà (« 13 720 »)."""
    if v is None:
        return "?"
    return ("{:,.%df}" % (0 if v >= 1000 else 2 if v >= 1 else 4)).format(v).replace(",", " ").replace(".", ",")


def cur_txt(c):
    return "€" if (c or "EUR") == "EUR" else c


def fr_day(d):
    return "%s/%s/%s" % (d[8:10], d[5:7], d[:4]) if isinstance(d, str) and len(d) >= 10 else "?"


STOP_TEST = ("testé sur 25 ans sans biais du survivant (28/11/2026, research/survivant_stop.py) : un ordre stop à −30 % posé chez le "
             "courtier a rapporté +19,3 % par an, contre +20,4 % pour la règle testée (vente à la clôture de la semaine) ; il vend 1 ligne "
             "sur 5 au lieu de 1 sur 7, souvent sur un creux passager de la séance")


def orders_email(week, sel_date, buys, waits, held_sel, sells, prots, montant, fx, today, dash_url, stop_order=False, margin=ORDER_MARGIN):
    """🧾 Ordres de la semaine, prêts à copier : (objet, corps) ou None s'il n'y a rien à faire. Fonction pure (testée hors ligne).
    buys / waits : [{icon, name, key, isin, sym, cur, last, lastDay}] ; held_sel : noms des lignes de la sélection déjà détenues ;
    sells : [{name, why}] ; prots : [{name, cur, stop, stopPct, buy, date, div}] ; montant : euros par ligne ou None ;
    fx : devises pour 1 € ; today : date ; stop_order : protection posée chez le courtier (ordre stop, « ordres.stopCourtier » de
    euro_signal/config.json ; déconseillée par le test du 28/11/2026) ou vente à la main sur l'email du seuil (par défaut)."""
    if not (buys or waits or sells or (stop_order and any(x.get("div") for x in prots))):
        return None
    fri = today + timedelta(days=(4 - today.weekday()) % 7 or 7)  # vendredi de la semaine (le suivant si c'est déjà vendredi)
    lines = []

    def order(x):
        last = x.get("last")
        lim = sig3(last * (1 + margin), True) if last else None
        if not lim:
            return None
        cur = x.get("cur") or "EUR"
        rate = 1.0 if cur == "EUR" else (fx or {}).get(cur)
        q = int(montant * rate // lim) if montant and rate else None
        return {"lim": lim, "stop": sig3(0.70 * lim, False), "q": q, "rate": rate, "cur": cur}

    def place(x):
        suf = (x.get("sym") or "").rsplit(".", 1)[-1] if "." in (x.get("sym") or "") else ""
        return EXCHANGES.get(suf, suf or "place ?")

    def fiche(x):
        k = x.get("key") or x.get("isin") or x.get("sym") or ""
        return (dash_url + "#" + (k if ISIN_RE.fullmatch(k) else "co=" + k)) if dash_url and k else ""
    nb = 0
    if buys:
        lines.append("ACHATS (✅ conditions réunies)")
        for x in buys:
            o = order(x)
            ident = " — ".join(v for v in (place(x), x.get("isin") or "", x.get("sym") or "") if v)
            lines.append("• %s %s — %s" % (x.get("icon") or "🎯", x.get("name") or x.get("key"), ident))
            if not o:
                lines.append("  Dernier cours inconnu ce soir : voir la fiche avant d'acheter. " + fiche(x))
                continue
            nb += 1
            c = cur_txt(o["cur"])
            fxs = "" if o["cur"] == "EUR" or not o["rate"] else " ; 1 € = %s %s" % (("%.4g" % o["rate"]).replace(".", ","), o["cur"])
            ref = "dernier cours %s %s le %s + %s %%%s" % (amt_txt(x["last"]), c, fr_day(x.get("lastDay")), ("%g" % (margin * 100)).replace(".", ","), fxs)
            if o["q"] is None:
                qty, qn = "à %s %s au plus" % (px_txt(o["lim"]), c), "toutes les actions achetées"
                lines.append("  Achat à cours limité %s (%s), valable jusqu'au vendredi %s ; quantité : montant par ligne ÷ prix limite%s."
                             % (qty, ref, fri.strftime("%d/%m/%Y"), "" if o["cur"] == "EUR" else " (en %s)" % o["cur"]))
            elif o["q"] == 0:
                qn = "l'action achetée"
                lines.append("  Une action coûte jusqu'à %s %s (%s), plus que votre montant par ligne (%s €) : une action ou rien, à vous de voir."
                             % (px_txt(o["lim"]), c, ref, amt_txt(montant)))
            else:
                qn = "ces %d actions" % o["q"]
                lines.append("  Achat à cours limité : %d actions à %s %s au plus (%s), valable jusqu'au vendredi %s."
                             % (o["q"], px_txt(o["lim"]), c, ref, fri.strftime("%d/%m/%Y")))
            if stop_order:
                lines.append("  Dès l'achat exécuté : ordre stop de vente (à seuil de déclenchement) sur %s, seuil %s %s (70 %% du prix limite ; "
                             "si vous avez payé moins, 70 %% de votre prix), avec la validité la plus longue proposée." % (qn, px_txt(o["stop"]), c))
            else:
                lines.append("  Protection : seuil à %s %s (70 %% du prix limite ; 70 %% de votre prix si vous avez payé moins). Pas d'ordre stop "
                             "chez le courtier : l'email « seuil de protection franchi » vous dira quand vendre." % (px_txt(o["stop"]), c))
            lines.append("  Puis « Je l'ai acheté » sur sa fiche (suivi, rappel à 6 mois)%s" % ((" : " + fiche(x)) if fiche(x) else "."))
    if waits:
        lines.append("")
        lines.append("EN ATTENTE (⏸️ sous leur moyenne 10 semaines : pas d'achat pour l'instant ; un email « Feu vert » vous préviendra)")
        for x in waits:
            o = order(x)
            if not o:
                lines.append("• %s %s : dernier cours inconnu ce soir." % (x.get("icon") or "🎯", x.get("name") or x.get("key")))
                continue
            c = cur_txt(o["cur"])
            q = ("%d actions" % o["q"]) if o["q"] else "quantité : montant ÷ prix limite"
            lines.append("• %s %s — %s : ordres prêts pour le feu vert : %s à %s %s au plus, puis protection à %s %s (à recalculer si le "
                         "cours a bougé)." % (x.get("icon") or "🎯", x.get("name") or x.get("key"), place(x), q, px_txt(o["lim"]), c,
                                              px_txt(o["stop"]), c))
    if held_sel:
        lines.append("")
        lines.append("DÉJÀ EN PORTEFEUILLE (d'après vos emails « Je l'ai acheté ») : %s : rien à acheter." % ", ".join(held_sel))
    if sells:
        lines.append("")
        lines.append("À VENDRE")
        for x in sells:
            lines.append("• %s : %s : vendre toute la ligne, puis « Je l'ai vendu » sur sa fiche." % (x["name"], x["why"]))
    if prots:
        lines.append("")
        lines.append("PROTECTIONS EN PLACE (ordres stop à vérifier chez votre courtier)" if stop_order else
                     "SEUILS DE PROTECTION DE VOS LIGNES (l'email du soir vous préviendra s'il est franchi)")
        for x in prots:
            lines.append("• %s : %s %s %s (%d %% sous votre prix d'achat de %s %s le %s)%s" % (
                x["name"], "ordre stop à" if stop_order else "seuil", px_txt(x["stop"]), cur_txt(x.get("cur")), x["stopPct"], amt_txt(x["buy"]),
                cur_txt(x.get("cur")), fr_day(x["date"]),
                (" ⚠️ dividende détaché le %s : l'ordre a pu être annulé, à reposer." % fr_day(x["div"])) if stop_order and x.get("div") else "."))
    head = ("Sélection de la semaine %s (envoyée le %s) : ordres prêts à copier dans votre courtier. Euro Signal ne passe aucun ordre : "
            "vérifiez chaque ligne avant de la saisir." % (week, fr_day(sel_date)))
    mt = ("Montant par ligne : %s € (secret GitHub MONTANT_PAR_LIGNE)." % amt_txt(montant) if montant else
          "Montant par ligne non réglé : créez le secret GitHub MONTANT_PAR_LIGNE (en euros, par exemple 2000) pour avoir les quantités.")
    foot = ["", "À SAVOIR"]
    if stop_order:
        foot += ["• Ordre stop : il se déclenche en séance dès qu'un cours touche le seuil, et s'exécute plus bas si le cours ouvre en dessous ; "
                 + STOP_TEST + ".",
                 "• Au détachement d'un dividende, Euronext annule les ordres non exécutés : reposez votre ordre stop après chaque dividende "
                 "(cet email signale ceux de la semaine écoulée pour vos lignes)."]
    else:
        foot += ["• Pourquoi pas d'ordre stop chez le courtier : " + STOP_TEST + "."]
    foot += ["• Prix limite et seuils arrondis à 3 chiffres, pour respecter les pas de cotation ; un ordre non exécuté vendredi est à revoir "
             "avec la sélection suivante.",
             "• Règles testées : lignes égales (4 🎯 + 1 📣 + 2 💎 ≈ 70 / 30), garder 6 mois, protection à −30 %. Ce n'est pas un conseil en "
             "investissement."]
    nw, ns = len(waits), len(sells)
    subject = "[Euro Signal] 🧾 Ordres de la semaine (%s) : %d achat%s%s%s (réf. ordres:%s)" % (
        week, nb, "s" if nb > 1 else "", (", %d en attente" % nw) if nw else "", (", %d vente%s" % (ns, "s" if ns > 1 else "")) if ns else "", week)
    return subject, "\n".join([head, mt, ""] + lines + foot)


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


def one_line(s):
    """Objet d'email sur une ligne : un retour à la ligne (nom de société lu dans une déclaration) fait refuser l'objet par Python
    (EmailMessage), et l'envoi de toutes les alertes suivantes de la liste s'arrêtait chaque soir."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+", " ", str(s or "")).strip()


def read_positions(imap):
    """Dernier message par ISIN dans les Envoyés : une Position ouvre ou met à jour, une Vente clôt.
    Objet et date d'abord, par lots de 200 ; le message entier seulement pour les positions, ventes et plans surveillés. Jusqu'au
    04/11/2026, chaque email « [Euro Signal] » des Envoyés (toutes les alertes envoyées par le calcul du soir, des centaines par an)
    était téléchargé en entier, un par un : de plus en plus long chaque soir, jusqu'à dépasser le délai de l'étape."""
    folder = sent_folder(imap)
    imap.select(folder, readonly=True)
    typ, data = imap.search(None, '(SUBJECT "[Euro Signal]")')
    ids = data[0].split() if data and data[0] else []
    latest, watch, refs = {}, {}, set()
    heads = []
    for k in range(0, len(ids), 200):
        typ, part = imap.fetch(b",".join(ids[k:k + 200]), "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
        for it in part or []:
            if isinstance(it, tuple) and len(it) >= 2 and it[0]:
                heads.append((it[0].split()[0], email.message_from_bytes(it[1])))
    for mid, head in heads:
        subject = str(make_header(decode_header(head.get("Subject", ""))))
        for r in REF_RE.findall(subject):
            refs.add(r)  # alertes de revente déjà envoyées
        if not POS_SUBJ.search(subject):
            continue
        typ, msgdata = imap.fetch(mid, "(RFC822)")
        if not msgdata or not msgdata[0] or not isinstance(msgdata[0], tuple):
            continue
        msg = email.message_from_bytes(msgdata[0][1])
        try:
            sent_at = email.utils.parsedate_to_datetime(head.get("Date") or msg.get("Date")).astimezone(timezone.utc).isoformat()
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


COMPTES_AVIS = {"fav": "favorable", "mit": "mitigé", "def": "défavorable"}
COMPTES_IMPACT = {"up": "hausse possible", "down": "baisse possible", "flat": "effet neutre"}


def fr_date(d):
    s = str(d or "")[:10]
    return "%s/%s/%s" % (s[8:10], s[5:7], s[:4]) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else s


def comptes_conseil(c):
    """Même texte que ES.comptesConseil (euro_signal/core.js) et conseil() de scrapers/comptes_ia.py : la règle testée reste la référence."""
    if c.get("a") == "def" or c.get("al"):
        return "Point d'alerte : à vérifier avant d'acheter ou de garder (la règle testée reste la référence)."
    return "Rien dans ces comptes qui contredise la règle testée."


def comptes_event(c, today):
    """Lecture des comptes par l'IA à signaler pour une position : nouveaux comptes vus il y a 10 jours au plus (champ pub, jamais
    posé au premier relevé d'une société ni pour une lecture refaite). → texte de l'email, ou None."""
    if not isinstance(c, dict) or not c.get("res") or c.get("a") not in COMPTES_AVIS or not c.get("per"):
        return None
    try:
        age = (today - date.fromisoformat(str(c.get("pub"))[:10])).days
    except ValueError:
        return None
    if not 0 <= age <= 10:
        return None
    nat = c.get("nat") if c.get("nat") in ("exercice", "trimestre", "semestre") else "période"
    lines = ["Nouveaux comptes (%s %s le %s), lus par l'IA le %s." % (nat, "close" if nat == "période" else "clos", fr_date(c["per"]), fr_date(c.get("at"))),
             "", "Effet possible sur le cours : %s · avis sur les comptes : %s." % (COMPTES_IMPACT.get(c.get("i"), "effet neutre"), COMPTES_AVIS[c["a"]]),
             str(c["res"])]
    if c.get("f"):
        lines.append("Points forts : " + " · ".join(map(str, c["f"])))
    if c.get("w"):
        lines.append("Points faibles : " + " · ".join(map(str, c["w"])))
    if c.get("al"):
        lines.append("⚠️ " + str(c["al"]))
    lines.append("Conseil : " + comptes_conseil(c))
    return "\n".join(lines)


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


def catalogue_item(sym):
    """Fiche d'une société du catalogue et dates de ses cours journaliers ({} et [] si absente)."""
    try:
        sh = json.loads((DATA / "societes" / ("%d.json" % shard_of(sym))).read_text(encoding="utf-8"))
    except Exception:
        return {}, []
    return ((sh.get("items") or {}).get(sym) or {}), (sh.get("dDates") or [])


def catalogue_rows(sym):
    """Clôtures journalières (un an) d'une société du catalogue, au format [date, o, h, l, close, v]."""
    x, dd = catalogue_item(sym)
    return [[d, c, c, c, c, None] for d, c in zip(dd, x.get("d") or []) if d and c]


def catalogue_dividends(sym):
    """Dividendes détachés sur un an d'une société du catalogue : [{date, amount}] (champ « dvd » des fiches, [[date, montant]])."""
    x, _ = catalogue_item(sym)
    out = []
    for v in x.get("dvd") or []:
        if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], (int, float)) and v[1] > 0:
            out.append({"date": v[0], "amount": float(v[1])})
    return out


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


def split_base(price, adj):
    """Prix d'achat corrigé d'une division ou d'un regroupement d'actions survenu depuis l'achat (même règle que ES.splitBase) :
    adj = cours du jour de l'achat dans la série ajustée du soir. Un écart de plus de 20 % ne peut venir que d'une opération sur
    le capital (un dividende n'ajuste que de quelques %) : la série ajustée sert alors de base. Sans cela, une division par 2
    déclenchait à tort l'alerte de protection à −30 % (et un regroupement par 10, un faux « objectif atteint »)."""
    if not price or price <= 0 or not adj or adj <= 0:
        return price
    f = adj / price
    return adj if f < 0.8 or f > 1.25 else price


def evaluate(pos, rows, stats, txs, today, in_pick=None, splits=None, adjusted=False, dividends=None):
    """Événements de revente pour une position. rows : [[date, o, h, l, close, v], …] : cours bruts publiés (cours d'Euro Signal,
    divisions et regroupements dans « splits » : [{date, ratio}]) ou cours ajustés (catalogue, adjusted=True). Dans les deux cas,
    prix d'achat et cours sont ramenés à la même base : une division par 2 ne compte plus pour une baisse de 50 %.
    dividends : [{date, amount}] détachés (montant par action au jour du détachement pour les cours bruts, à la base du jour pour
    le catalogue) : ceux détachés depuis l'achat comptent dans la performance, comme dans les tests (cours ajustés des dividendes).
    Sans cela, un dividende de 8 % déclenchait l'email de baisse trop tôt, et un dividende exceptionnel la protection à −30 %
    (relecture du 07/11/2026 ; Wallenius Wilhelmsen, Frontline : 3 à 9 % par détachement)."""
    closes = [(r[0], r[4]) for r in rows if r and r[4]]
    sp = [(x["date"], float(x["ratio"])) for x in (splits or []) if isinstance(x, dict) and x.get("date") and (x.get("ratio") or 0) > 0]

    def now_basis(c, d):  # cours brut du jour d exprimé au nombre d'actions d'aujourd'hui
        for sd, r in sp:
            if sd > d:
                c = c / r
        return c
    after = [now_basis(c, d) for d, c in closes if d >= pos["date"]]
    if not after:
        return [], None
    buy = now_basis(pos["price"], pos["date"])
    if adjusted:
        at_buy = [c for d, c in closes if d <= pos["date"]][-1:] or [None]
        paid, buy = buy, split_base(buy, at_buy[0])
        if buy != paid:  # prix d'achat remplacé par le cours ajusté (division depuis l'achat) : dividendes déjà compris dedans
            dividends = None
    div = 0.0
    last_day = closes[-1][0] if closes else None
    for x in dividends or []:
        try:
            d, amt = str(x.get("date") or ""), float(x.get("amount") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if amt > 0 and pos["date"] < d and (last_day is None or d <= last_day):  # détaché après l'achat, connu au dernier cours
            div += amt if adjusted else now_basis(amt, d)
    last, peak = after[-1], max(after)
    perf = ((last + div) / buy - 1) * 100
    # séance à −20 % ou pire depuis l'achat : souvent une augmentation de capital (détachement de droits), une scission ou une
    # distribution que Yahoo n'ajuste pas, alors que les tests (cours EODHD) les ajustaient (contrôle du 22/11/2026 : Eramet −30 %
    # le 16/11/2026, Electrolux, Kongsberg, Worldline). L'alerte part quand même (une vraie chute aussi), avec cet avertissement.
    dated = [(d, now_basis(c, d)) for d, c in closes if d >= pos["date"]]
    gap = None
    for (d0, c0), (d1, c1) in zip(dated, dated[1:]):
        try:
            near = (date.fromisoformat(d1[:10]) - date.fromisoformat(d0[:10])).days <= 5
        except (TypeError, ValueError):
            near = False
        if near and c0 > 0 and c1 / c0 - 1 <= -0.20 and (gap is None or c1 / c0 - 1 < gap[1]):
            gap = (d1, c1 / c0 - 1)
    note = ("" if not gap else " ; dont %s le %s/%s/%s en une seule séance : vérifier d'abord une augmentation de capital (détachement de "
            "droits), une scission ou une distribution, que Yahoo n'ajuste pas" % (pc(gap[1] * 100), gap[0][8:10], gap[0][5:7], gap[0][:4]))
    ev = []
    if pos.get("target") and perf >= pos["target"]:
        ev.append(("obj" + str(int(pos["target"])), "objectif de +%d %% atteint (%s depuis votre achat)" % (pos["target"], pc(perf))))
    stop = abs(pos.get("stop") or STOP_DEFAULT)  # règle testée : protection à −30 % si rien n'a été indiqué
    if perf <= -stop:
        ev.append(("stop" + str(int(stop)), "seuil de protection de -%d %% franchi (%s depuis votre achat) : la règle testée est de vendre%s" % (stop, pc(perf), note)))
    # paliers de baisse de 10 % : un seul email par palier, le plus profond franchi ce soir
    lvl = int(-perf // 10) * 10 if perf <= -10 else 0
    if lvl and lvl != int(stop):
        ev.append(("baisse%d" % lvl, ("baisse de %d %% depuis votre achat (%s) : %s%s" % (lvl, pc(perf),
                   "la règle testée est de garder jusqu'à la protection à -%d %% ; sur 29 ans, 2 lignes 🎯 sur 3 finissaient en hausse à 6 mois malgré des replis" % stop
                   if lvl < stop else "sous la protection de -%d %%, la règle testée était de vendre" % stop, note))))
    sells = [t for t in (txs or []) if t.get("type") == "vente" and t.get("status") != "annulee" and (t.get("pubDate") or t.get("txDate") or "") > pos["date"]]
    if sells:
        ev.append(("vente" + max((t.get("pubDate") or t.get("txDate")) for t in sells).replace("-", ""),
                   "un dirigeant a vendu depuis votre achat (" + ", ".join(((t.get("person") or "?") + " le " + (t.get("txDate") or "?")) for t in sells[:3]) + ")"))
    try:
        if isinstance(today, str):  # date du jour en texte (« 2026-11-04 ») : jusqu'au 04/11/2026, le rappel des 6 mois ne partait jamais
            today = date.fromisoformat(today[:10])
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
    return ev, {"last": last, "perf": perf, "peak": peak, "div": div, "buy": buy}


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


def weekly_orders(dash, state, prices, positions, held_info, refs, today, montant):
    """Données des ordres de la semaine (sélection envoyée, cours du soir, lignes détenues) → orders_email, ou None (pas de sélection
    cette semaine, email déjà envoyé, rien à faire)."""
    rank = dash.get("rank") or {}
    sel = rank.get("selection") or {}
    week = sel.get("week")
    rs = (state.get("rankSelections") or {}).get(week) if week else None
    if not rs or ("ordres:%s" % week) in refs:
        return None
    try:
        if (today - date.fromisoformat(str(rs.get("date"))[:10])).days > 6:
            return None
    except ValueError:
        return None
    aliases = dash.get("aliases") or {}
    rows = {r.get("key"): r for r in rank.get("rows") or [] if isinstance(r, dict)}
    rows.update({r.get("key"): r for r in sel.get("items") or [] if isinstance(r, dict)})  # lignes du soir de la sélection
    held = set()
    for pos in positions:
        held |= {pos["isin"], aliases.get(pos["isin"], pos["isin"])}
    lines = [(x.get("key"), "📣" if x.get("bd") else "🎯", x.get("name")) for x in rs.get("items") or [] if x.get("key")]
    lines += [(k, "💎", None) for k in (rank.get("value10") or [])[:2] if isinstance(k, str)]
    buys, waits, held_sel, seen = [], [], [], set()
    for key, icon, nm in lines:
        if key in seen:
            continue
        seen.add(key)
        r = rows.get(key) or {}
        name = r.get("name") or nm or key
        if {key, r.get("isin"), r.get("sym")} & held:
            held_sel.append(name)
            continue
        day, last = last_close(key, r.get("sym"), prices)
        x = {"icon": icon, "name": name, "key": key, "isin": r.get("isin") if r.get("isin") and r.get("isin") != r.get("sym") else None,
             "sym": r.get("sym"), "cur": r.get("cur") or "EUR", "last": last, "lastDay": day}
        (waits if icon != "💎" and r.get("m10") is not None and r["m10"] < 0 else buys).append(x)
    sells, prots = [], []
    for h in held_info:
        pos, info, name = h["pos"], h["info"], h["name"]
        keys = {k for k, _ in h["evs"]}
        r = rows.get(aliases.get(pos["isin"], pos["isin"])) or {}
        stop = abs(pos.get("stop") or STOP_DEFAULT)
        if any(k.startswith("stop") for k in keys):
            sells.append({"name": name, "why": "protection de -%d %% franchie (%s depuis l'achat) ; si votre ordre stop ne s'est pas "
                          "déclenché" % (stop, pc(info["perf"]))})
        elif "6mois" in keys and h.get("inPick") is False:
            sells.append({"name": name, "why": "6 mois depuis l'achat du %s (%s) et plus dans le 🎯 ni le 💎" % (fr_day(pos["date"]), pc(info["perf"]))})
        recent = [str(d.get("date") or "")[:10] for d in h.get("dividends") or [] if isinstance(d, dict)]
        recent = [d for d in recent if d and 0 <= (today - date.fromisoformat(d)).days <= 7] if recent else []
        prots.append({"name": name, "cur": r.get("cur") or "EUR", "stop": sig3(info["buy"] * (1 - stop / 100), False), "stopPct": stop,
                      "buy": info["buy"], "date": pos["date"], "div": max(recent) if recent else None})
    dash_url = ((dash.get("cfg") or {}).get("dashboardUrl")) or ""
    oc = orders_config()
    return orders_email(week, rs.get("date"), buys, waits, held_sel, sells, prots, montant, dash.get("fx") or {}, today, dash_url,
                        stop_order=oc["stopCourtier"], margin=oc["margeLimite"])


def orders_config():
    """Réglages des ordres de la semaine (« ordres » de euro_signal/config.json) : protection chez le courtier ou à la main, marge du
    prix limite."""
    try:
        o = json.loads((ROOT / "euro_signal" / "config.json").read_text(encoding="utf-8")).get("ordres") or {}
    except Exception:
        o = {}
    m = o.get("margeLimite")
    return {"stopCourtier": o.get("stopCourtier") is True,
            "margeLimite": m if isinstance(m, (int, float)) and 0 <= m <= 0.1 else ORDER_MARGIN}


def last_close(key, sym, prices):
    """(date, dernier cours brut) : dossier Euro Signal (prices.json) ou fiche du catalogue ; (None, None) si inconnu."""
    rows = ((prices.get(key) or {}).get("rows") if ISIN_RE.fullmatch(key or "") else None) or (catalogue_rows(sym) if sym else []) or []
    for r in reversed(rows):
        if r and len(r) > 4 and r[4]:
            return str(r[0])[:10], float(r[4])
    return None, None


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
    today = date.today()
    try:
        # délai de 30 s par échange : un Gmail qui ne répond plus ne bloque plus l'étape jusqu'à sa limite
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context(), timeout=30)
        imap.login(user, pwd)
        positions, refs, watches = read_positions(imap)
        imap.logout()
    except Exception as e:
        print("Positions : lecture Gmail impossible (" + type(e).__name__ + ")")
        record("positions", False, "lecture Gmail impossible (" + type(e).__name__ + ")")  # vu par la garde du matin
        return 1
    record("positions", True)  # fichier public : rien sur les positions elles-mêmes
    to_send = []
    held_info = []  # pour les ordres de la semaine
    for pos in positions:
        isin = pos["isin"]
        p = prices.get(isin)
        inst = (dash.get("inst") or {}).get((dash.get("aliases") or {}).get(isin, isin)) or {}  # ancien ISIN réuni à un autre dossier
        name = inst.get("name") or pos.get("name") or isin
        if not p and not ISIN_RE.fullmatch(isin):  # société du catalogue : cours du catalogue, MM50 / MM200 recalculées ici
            rows = catalogue_rows(isin)
            p = {"rows": rows, "dividends": catalogue_dividends(isin)} if rows else None
            stats = {"deathCrossDate": death_cross(rows, pos["date"])} if rows else {}
        else:
            stats = inst.get("stats") or {}
        if not p:
            continue
        evs, info = evaluate(pos, p.get("rows") or [], stats, (state.get("txArchive") or {}).get(isin) or [], today,
                             (isin in picks) if picks is not None else None, splits=p.get("splits"), adjusted="splits" not in p,
                             dividends=p.get("dividends"))
        if info:
            held_info.append({"pos": pos, "name": name, "evs": evs, "info": info, "dividends": p.get("dividends") or [],
                              "inPick": (isin in picks) if picks is not None else None})
        for key, label in evs:
            ref = "%s:%s:%s" % (isin, pos["date"].replace("-", ""), key)
            if ref in refs:
                continue
            body = ("%s — %s.\n\nVotre achat : %s le %s. Dernier cours : %s (%s" + (", dividendes détachés depuis l'achat compris : "
                    + ("%.2f" % info["div"]).replace(".", ",") + " par action" if info.get("div") else "") + ").\n"
                    "Règles testées : garder 6 mois, vendre sous -30 %%. Ce n'est pas un ordre : à décider selon votre stratégie.\n"
                    "Pour arrêter le suivi : bouton « Je l'ai vendu » dans la fiche%s.") % (
                name, label, ("%.2f" % pos["price"]).replace(".", ","), pos["date"], ("%.2f" % info["last"]).replace(".", ","), pc(info["perf"]),
                (" : " + dash_url + "#" + (isin if ISIN_RE.fullmatch(isin) else "co=" + isin)) if dash_url else "")
            to_send.append(("[Euro Signal] Revente — %s : %s (réf. %s)" % (name, label.split(" (")[0], ref), body))
    # 📑 Nouveaux comptes d'une position, lus par l'IA (scrapers/comptes_ia.py) : une fois par société et par période ; une société
    # du 🎯 / 💎 de ce soir a déjà son email (build.mjs, 6h bis)
    try:
        cpt = json.loads((DATA / "comptes_ia.json").read_text(encoding="utf-8")).get("items") or {}
    except Exception:
        cpt = {}
    done_c = set()
    for pos in positions:
        isin = pos["isin"]
        key = (dash.get("aliases") or {}).get(isin, isin)
        if picks is not None and (key in picks or isin in picks):
            continue
        c = cpt.get(key) or cpt.get(isin)
        txt = comptes_event(c, today)
        if not txt:
            continue
        ref = "comptes:%s:%s" % (key, c["per"])
        if ref in refs or ref in done_c:
            continue
        done_c.add(ref)
        inst = (dash.get("inst") or {}).get(key) or {}
        name = inst.get("name") or pos.get("name") or isin
        body = ("%s — %s\n\nVotre achat : %s le %s. Règles testées : garder 6 mois, vendre sous -30 %%. Ce n'est pas un ordre : à décider "
                "selon votre stratégie.\nLecture automatique des chiffres publiés (Yahoo Finance) par une IA (Claude), non testée : seules les "
                "règles 🎯 et 💎 sont testées.%s") % (
            name, txt, ("%.2f" % pos["price"]).replace(".", ","), pos["date"],
            ("\nFiche : " + dash_url + "#" + (isin if ISIN_RE.fullmatch(isin) else "co=" + isin)) if dash_url else "")
        to_send.append(("[Euro Signal] Comptes — %s : avis %s (réf. %s)" % (name, COMPTES_AVIS[c["a"]], ref), body))
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
    # 🧾 Ordres de la semaine : le soir où la sélection du lundi est décidée (une fois par semaine)
    try:
        om = weekly_orders(dash, state, prices, positions, held_info, refs, today, num(os.environ.get("MONTANT_PAR_LIGNE")))
    except Exception as e:  # jamais de quoi bloquer les alertes de revente
        om = None
        print("Positions : ordres de la semaine non préparés (" + type(e).__name__ + ")")
    if om:
        to_send.append(om)
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
                    msg["Subject"], msg["From"], msg["To"] = one_line(subject), user, user  # vos positions ne vont qu'à vous
                    msg.set_content(body)
                    s.send_message(msg)
                    sent += 1
        except Exception as e:
            print("Positions : envoi interrompu (" + type(e).__name__ + ")")
            record("positions", False, "envoi interrompu (" + type(e).__name__ + ")")
            return 1
    print("Positions : contrôle effectué")  # journal public : ni nombre de positions, ni nombre d'alertes
    return 0


if __name__ == "__main__":
    sys.exit(main())
