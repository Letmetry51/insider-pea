"""
Euro Signal — suivi de VOS positions et alertes de revente personnelles.

Confidentialité : le dépôt et le tableau de bord sont publics. Vos positions n'y sont donc jamais écrites.
Elles vivent uniquement dans votre Gmail :
  - « Je l'ai acheté » (fiche du tableau de bord) prépare un email à vous-même, objet « [Euro Signal] Position <ISIN> »,
    avec le prix payé, la date, l'objectif de hausse et le seuil de protection ;
  - « Je l'ai vendu » prépare un email « [Euro Signal] Vente <ISIN> » qui clôt le suivi.
Chaque soir, ce script relit ces emails dans le dossier « Envoyés » (seuls les messages envoyés depuis votre compte
comptent), compare au dernier cours et vous écrit, une seule fois par événement :
  - objectif de hausse atteint ;
  - seuil de protection franchi ;
  - signal de sortie : vente d'un dirigeant, MM50 repassée sous la MM200, recul de 20 % depuis le plus haut atteint
    depuis votre achat.
L'unicité des envois est vérifiée dans votre dossier « Envoyés » (référence dans l'objet) : rien n'est stocké ailleurs.
Le journal GitHub étant public, le script n'y écrit rien de personnel : ni ISIN, ni prix, ni adresse, ni même le nombre de positions.
"""
import email
import imaplib
import json
import os
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
DRAWDOWN_PCT = 20


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
    m = ISIN_RE.search(subject or "")
    if not m:
        return None
    kind = "vente" if re.search(r"\]\s*Vente\b", subject, re.I) else "position" if re.search(r"\]\s*Position\b", subject, re.I) else None
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
    return {
        "kind": kind, "isin": m.group(1), "sentAt": sent_at, "name": kv.get("société"),
        "price": num(kv.get("prix d'achat") or kv.get("prix")), "date": buy_date or sent_at[:10],
        "target": num(kv.get("objectif de hausse") or kv.get("objectif")), "stop": num(kv.get("seuil de protection") or kv.get("protection")),
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
    latest, refs = {}, set()
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
        if p and (p["isin"] not in latest or p["sentAt"] > latest[p["isin"]]["sentAt"]):
            latest[p["isin"]] = p
    return [p for p in latest.values() if p["kind"] == "position" and p["price"]], refs


def evaluate(pos, rows, stats, txs, today):
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
    if pos.get("stop") and perf <= -abs(pos["stop"]):
        ev.append(("stop" + str(int(abs(pos["stop"]))), "seuil de protection de -%d %% franchi (%s depuis votre achat)" % (abs(pos["stop"]), pc(perf))))
    if (stats or {}).get("deathCrossDate") and stats["deathCrossDate"] > pos["date"]:
        ev.append(("mm" + stats["deathCrossDate"].replace("-", ""), "la MM50 est repassée sous la MM200 le " + stats["deathCrossDate"]))
    sells = [t for t in (txs or []) if t.get("type") == "vente" and t.get("status") != "annulee" and (t.get("pubDate") or t.get("txDate") or "") > pos["date"]]
    if sells:
        ev.append(("vente" + max((t.get("pubDate") or t.get("txDate")) for t in sells).replace("-", ""),
                   "un dirigeant a vendu depuis votre achat (" + ", ".join(((t.get("person") or "?") + " le " + (t.get("txDate") or "?")) for t in sells[:3]) + ")"))
    if peak > buy and last / peak - 1 <= -DRAWDOWN_PCT / 100:
        ev.append(("repli%d" % DRAWDOWN_PCT, "recul de %d %% depuis le plus haut atteint depuis votre achat" % round((1 - last / peak) * 100)))
    return ev, {"last": last, "perf": perf, "peak": peak}


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
    today = date.today().isoformat()
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context())
        imap.login(user, pwd)
        positions, refs = read_positions(imap)
        imap.logout()
    except Exception as e:
        print("Positions : lecture Gmail impossible (" + type(e).__name__ + ")")
        return 0
    to_send = []
    for pos in positions:
        isin = pos["isin"]
        p = prices.get(isin)
        inst = (dash.get("inst") or {}).get(isin) or {}
        name = inst.get("name") or pos.get("name") or isin
        if not p:
            continue
        evs, info = evaluate(pos, p.get("rows") or [], inst.get("stats") or {}, (state.get("txArchive") or {}).get(isin) or [], today)
        for key, label in evs:
            ref = "%s:%s:%s" % (isin, pos["date"].replace("-", ""), key)
            if ref in refs:
                continue
            body = ("%s — %s.\n\nVotre achat : %s le %s. Dernier cours : %s (%s).\n"
                    "Ce n'est pas un ordre de vente : à décider selon votre stratégie (vendre tout, une partie, ou relever l'objectif).\n"
                    "Pour arrêter le suivi : bouton « Je l'ai vendu » dans la fiche%s.") % (
                name, label, ("%.2f" % pos["price"]).replace(".", ","), pos["date"], ("%.2f" % info["last"]).replace(".", ","), pc(info["perf"]),
                (" : " + dash_url + "#" + isin) if dash_url else "")
            to_send.append(("[Euro Signal] Revente — %s : %s (réf. %s)" % (name, label.split(" (")[0], ref), body))
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
