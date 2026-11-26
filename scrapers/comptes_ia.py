"""
Euro Signal — lecture des comptes publiés par une IA (Claude Haiku) à chaque publication : bloc « 📑 Lecture des comptes » des
fiches, ligne 📑 de l'email de la sélection, email quand une société 🎯 / 💎 ou une position suivie publie de nouveaux comptes.

Demande de François (25/11/2026) : « Est-ce possible d'ajouter la lecture des comptes publiés pour chaque entreprise à chaque
publication et donner un conseil », avec le modèle Haiku.

Chaque société de data/financials.json (4 exercices et, quand Yahoo les donne, les 6 derniers trimestres ou semestres) est lue quand
une période plus récente que celle de sa dernière lecture apparaît, quand elle n'a pas encore de lecture, ou quand la consigne change
(VERSION). Claude reçoit les chiffres publiés et des ratios calculés ici (croissance, marges, dette nette / EBITDA, couverture des
intérêts, dilution, comparaison au même trimestre un an plus tôt) : rien d'autre que des chiffres publics, jamais de position. Il
écrit en français ce que montre la dernière publication, 3 points forts et 3 points faibles au plus, l'effet possible sur le cours
(↑ / ↓ / →) et un avis sur les comptes (favorable, mitigé, défavorable). Les points d'alerte ne viennent pas de l'IA : sept cas
chiffrés calculés ici (alertes() : dette nette au-delà de 4 fois l'EBITDA, intérêts couverts moins de 2 fois, capitaux propres
négatifs, dilution, chiffre d'affaires en chute, pertes qui se creusent, trésorerie qui ne couvre pas un an de déficit). Le conseil
affiché en découle, sans IA non plus (conseil() ici, ES.comptesConseil dans la page) : la règle testée (🎯 / 💎) reste la seule
référence pour acheter, garder ou vendre, et la lecture n'entre dans aucune règle du classement.

Lectures dans data/comptes_ia.json (clé : ISIN ou symbole, celle du classement), gardées d'un soir à l'autre. « pub » : date où le
collecteur a vu ces nouveaux comptes (financials.py, champs newAt / newPer) quand elle a moins de PUB_DAYS jours : seules ces
lectures déclenchent un email (euro_signal/build.mjs pour le 🎯 et le 💎, euro_signal/positions.py pour les positions). Sans le
secret ANTHROPIC_API_KEY, ou si l'API ne répond pas, le fichier reste tel quel. Modèle, taille des lots et budget de temps :
euro_signal/config.json (« lectureComptes ») ; la publication du code donne un budget plus long (variable COMPTES_BUDGET) pour
rattraper les sociétés pas encore lues. Lancé par le calcul du soir (étape 4c ter) et à chaque publication du code (publish.yml).
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from news_ia import appel, cout, lire  # noqa: E402  (même API et même lecture robuste de la réponse que les titres de presse)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "comptes_ia.json"
VERSION = 1  # version de la consigne : une lecture plus ancienne est refaite
PUB_DAYS = 10  # nouveaux comptes vus il y a moins de 10 jours : la lecture part aussi par email
DEFAUT = {"modele": "claude-haiku-5-5", "maxTokens": 4000, "lot": 5, "budget": 140, "paralleles": 4, "reflexion": "non"}
FINANCE = re.compile(r"financ|banq|bank|assur|insur", re.I)
FONCIERE = re.compile(r"immobil|real estate|reit", re.I)
AVIS = {"favorable": "fav", "mitigé": "mit", "mitige": "mit", "défavorable": "def", "defavorable": "def"}
IMPACT = {"hausse": "up", "baisse": "down", "neutre": "flat"}

SYSTEME = """Tu aides un investisseur particulier qui achète des actions européennes repérées par une règle testée (tendance du cours
et qualité des comptes) et les garde environ six mois. Pour chaque société, tu reçois ses comptes publiés (source Yahoo Finance) :
exercices annuels, et souvent la dernière période infra-annuelle (trimestre ou semestre) avec la même période un an plus tôt, plus
des ratios déjà calculés. Tu les lis comme un analyste financier prudent et tu dis ce que montre la DERNIÈRE période publiée.

Pour CHAQUE société :
- resume : en français, 35 mots au plus : ce que montre la dernière période face à la MÊME période un an plus tôt quand elle est
  donnée, sinon face à l'exercice précédent : chiffre d'affaires, rentabilité, trésorerie, dette.
- forts : de 0 à 3 points forts nets, chacun un fait chiffré tiré des données (12 mots au plus). N'en ajoute pas pour remplir :
  aucun point vaut mieux qu'un point sans intérêt.
- faibles : de 0 à 3 points faibles nets, même forme, même règle.
- impact : effet possible de ces comptes sur le cours. "hausse" s'ils montrent une nette amélioration (croissance, marges, trésorerie,
  désendettement, bénéfice au-dessus des attentes quand l'écart est donné) ; "baisse" s'ils montrent une nette dégradation (chiffre
  d'affaires ou marges en recul, pertes qui se creusent, trésorerie qui fond, dette qui monte, dilution, bénéfice sous les attentes) ;
  "neutre" si l'ensemble est stable, partagé, ou trop incomplet pour juger.
- avis : sur la santé et la tendance des comptes, sans regarder le cours. "favorable" : rentable, en progrès ou stable, bilan
  solide. "mitigé" : des points faibles réels. "défavorable" : pertes, dégradation nette ou bilan fragile.
Les « points d'alerte calculés par l'outil », quand il y en a, sont déjà vérifiés : tiens-en compte dans l'avis, sans les inventer
ni les contredire ; un bon résultat jugé « exceptionnel » ou « volatil » n'est pas un point faible en soi.

Règles :
- N'utilise que les chiffres donnés : n'invente aucun chiffre, aucune nouvelle, aucune prévision, ne refais pas les calculs déjà
  donnés.
- Ne compare JAMAIS une période au trimestre ou au semestre qui la précède, ni ses marges à celles de l'exercice entier : l'activité
  est souvent saisonnière. Comparaisons valables : la même période un an plus tôt, et les 12 mois glissants (somme des derniers
  trimestres) face au dernier exercice. Sans elles, ne commente pas l'évolution du chiffre d'affaires ni des résultats sur la
  période : juge le bilan récent face au dernier bilan annuel et les derniers exercices.
- Une donnée absente n'est ni un point fort ni un point faible : n'en parle pas dans les points.
- Si la dernière période n'a que le bilan (fréquent : Yahoo ne donne pas toujours le compte de résultat du semestre), juge sur le
  dernier exercice et ce bilan récent, sans pénaliser l'avis pour cette absence.
- Banques et assurances : dette, trésorerie et flux ne sont pas donnés (ils n'ont pas le sens habituel) ; juge le résultat net, sa
  tendance et la rentabilité des capitaux propres. Foncières (immobilier) : une dette élevée est habituelle ; juge la couverture des
  intérêts et la trésorerie.
- Montants en millions de la devise des comptes ; « actions » : nombre d'actions en millions.
- Pas de conseil d'achat ni de vente : tu juges les comptes, pas l'action.

Réponds uniquement par un objet JSON : {"lectures": [{"id": "…", "resume": "…", "forts": ["…"], "faibles": ["…"],
"impact": "neutre", "avis": "mitigé"}, …]}, une entrée par société, avec l'identifiant donné."""

LIB = (("revenue", "CA"), ("grossProfit", "marge brute"), ("operatingIncome", "résultat d'exploitation"), ("ebitda", "EBITDA"),
       ("netIncome", "résultat net"), ("interestExpense", "charges d'intérêts"), ("cfo", "flux d'exploitation"),
       ("capex", "investissements"), ("fcf", "FCF"), ("cash", "trésorerie"), ("totalDebt", "dette financière"),
       ("equity", "capitaux propres"), ("totalAssets", "total du bilan"), ("shares", "actions"))


def load(path, default):
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def config():
    try:
        c = json.loads((ROOT / "euro_signal" / "config.json").read_text(encoding="utf-8")).get("lectureComptes") or {}
    except Exception:
        c = {}
    cfg = {**DEFAUT, **{k: v for k, v in c.items() if k in DEFAUT}}
    try:
        if os.environ.get("COMPTES_BUDGET"):
            cfg["budget"] = max(10, min(1200, int(os.environ["COMPTES_BUDGET"])))
    except ValueError:
        pass
    return cfg


def num(v):
    return v if isinstance(v, (int, float)) and v == v and abs(v) != float("inf") else None


def mil(v):
    """Montant en millions, à la française : « 1 234 », « 12,5 », « −0,35 »."""
    v = num(v)
    if v is None:
        return None
    x = v / 1e6
    a = abs(x)
    s = ("{:,.0f}" if a >= 100 else "{:,.1f}" if a >= 1 else "{:,.2f}").format(a).replace(",", " ").replace(".", ",")
    return ("−" if x < 0 else "") + s


def pc(x, signe=False):
    """Part ou variation en % à la française (0.032 → « 3,2 % », signe : « +3,2 % »)."""
    s = "{:.1f}".format(abs(x) * 100).replace(".", ",") + " %"
    return ("−" if x < 0 else "+" if signe else "") + s


def div(a, b):
    a, b = num(a), num(b)
    return a / b if a is not None and b not in (None, 0) else None


def growth(a, b):
    """Variation de a face à b, seulement sur une base positive (une variation en % d'une perte n'a pas de sens)."""
    a, b = num(a), num(b)
    return a / b - 1 if a is not None and b is not None and b > 0 else None


def day(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def nature(quarters):
    """Trimestres ou semestres : écart médian entre deux périodes."""
    ds = sorted(d for d in (day(q.get("date")) for q in quarters or []) if d)
    gaps = sorted((b - a).days for a, b in zip(ds, ds[1:]))
    if not gaps:
        return "période"
    g = gaps[len(gaps) // 2]
    return "trimestre" if g < 120 else "semestre" if g < 220 else "période"


def derniere(fin):
    """(date, nature) de la dernière période publiée : exercice si la date est celle d'un exercice, sinon trimestre ou semestre."""
    ys = {str(y.get("date")) for y in fin.get("years") or [] if isinstance(y, dict) and y.get("date")}
    qs = {str(q.get("date")) for q in fin.get("quarters") or [] if isinstance(q, dict) and q.get("date")}
    if not ys:
        return None
    top = max(ys | qs)
    return (top, "exercice") if top in ys else (top, nature(fin.get("quarters")))


def same_year_before(lst, d):
    """Période close environ un an avant d (à 25 jours près)."""
    d0 = day(d)
    best = None
    for p in lst:
        dp = day(p.get("date"))
        if d0 and dp and abs((d0 - dp).days - 365) <= 25:
            best = p
    return best


FIN_ONLY = {"revenue", "netIncome", "equity", "totalAssets", "shares"}  # banques et assurances : dette, trésorerie, flux sans le sens habituel


def glissant(Q, Y, fi=False):
    """Somme des 4 derniers trimestres (ou des 2 derniers semestres) face au dernier exercice : la tendance sans effet de saison,
    quand Yahoo n'a pas le même trimestre un an plus tôt (fréquent : 5 trimestres seulement, avec des trous). Seulement pour des
    périodes qui se suivent, plus récentes que l'exercice, et un total vraisemblable (60 % à 180 % du chiffre d'affaires annuel)."""
    nq = nature(Q)
    n = 4 if nq == "trimestre" else 2 if nq == "semestre" else 0
    if fi or not n or len(Q) < n or not Y:
        # banques et assurances : chiffre d'affaires trimestriel de Yahoo défini autrement que l'annuel (BNP Paribas +19 % sur 12 mois
        # glissants à l'essai du 25/11/2026) : pas de comparaison qui mêle les deux
        return None
    last, y0 = Q[-n:], Y[-1]
    ds = [day(q.get("date")) for q in last]
    if not all(ds) or str(last[-1].get("date")) <= str(y0.get("date")):
        return None
    lo, hi = (75, 105) if n == 4 else (165, 200)
    if not all(lo <= (b - a).days <= hi for a, b in zip(ds, ds[1:])):
        return None
    p, tot = [], {}
    for k, lab in (("revenue", "CA"), ("operatingIncome", "résultat d'exploitation"), ("netIncome", "résultat net"), ("cfo", "flux d'exploitation")):
        vals = [num(q.get(k)) for q in last]
        if (fi and k not in FIN_ONLY) or any(v is None for v in vals) or num(y0.get(k)) is None:
            continue
        t = tot[k] = sum(vals)
        if k == "revenue" and not (y0[k] > 0 and 0.6 <= t / y0[k] <= 1.8):
            return None  # total invraisemblable (exercice rangé dans le 4e trimestre, données mêlées) : rien plutôt qu'un faux chiffre
        g = growth(t, y0[k])
        p.append("%s %s (%s face à l'exercice)" % (lab, mil(t), pc(g, True)) if g is not None and (k == "revenue" or t > 0)
                 else "%s %s (%s sur l'exercice)" % (lab, mil(t), mil(y0[k])))
    if "revenue" not in tot:
        return None
    m0, m1 = div(tot.get("operatingIncome"), tot["revenue"]), div(y0.get("operatingIncome"), y0.get("revenue"))
    if m0 is not None and m1 is not None and not fi:
        p.append("marge d'exploitation %s contre %s" % (pc(m0), pc(m1)))
    return "Sur 12 mois glissants au %s (%d derniers %ss) face au dernier exercice (%s) : %s." % (
        last[-1]["date"], n, nq, str(y0["date"])[:10], " ; ".join(p))


def ligne(p, fi=False):
    return str(p.get("date")) + " : " + " ; ".join("%s %s" % (lab, mil(p[k])) for k, lab in LIB
                                                   if num(p.get(k)) is not None and (not fi or k in FIN_ONLY))


def ratios(fin, secteur):
    """Ratios calculés ici (Haiku n'a pas à faire les calculs) : dernier exercice face au précédent, dernière période infra-annuelle
    face à la même période un an plus tôt, bilan récent face au dernier bilan annuel."""
    Y = sorted((y for y in fin.get("years") or [] if isinstance(y, dict) and y.get("date")), key=lambda y: str(y["date"]))
    Q = sorted((q for q in fin.get("quarters") or [] if isinstance(q, dict) and q.get("date")), key=lambda q: str(q["date"]))
    fi = bool(FINANCE.search(secteur or ""))
    fo = bool(FONCIERE.search(secteur or ""))
    out = []
    if Y:
        y0, y1 = Y[-1], (Y[-2] if len(Y) > 1 else {})
        p = []
        g = growth(y0.get("revenue"), y1.get("revenue"))
        if g is not None:
            p.append("croissance du CA " + pc(g, True))
        if not fi:
            mo0, mo1 = div(y0.get("operatingIncome"), y0.get("revenue")), div(y1.get("operatingIncome"), y1.get("revenue"))
            if mo0 is not None:
                p.append("marge d'exploitation " + pc(mo0) + (" (%s l'exercice précédent)" % pc(mo1) if mo1 is not None else ""))
        mn = div(y0.get("netIncome"), y0.get("revenue"))
        if mn is not None and not fi:
            p.append("marge nette " + pc(mn))
        fcf = num(y0.get("fcf"))
        if fcf is None and num(y0.get("cfo")) is not None and num(y0.get("capex")) is not None:
            fcf = y0["cfo"] + y0["capex"]
        if fcf is not None and num(y0.get("revenue")) and y0["revenue"] > 0 and not fi:
            p.append("FCF / CA " + pc(fcf / y0["revenue"]))
        if not fi and num(y0.get("totalDebt")) is not None and num(y0.get("cash")) is not None:
            nd, eb = y0["totalDebt"] - y0["cash"], num(y0.get("ebitda"))
            if nd <= 0:
                p.append("trésorerie nette (plus de trésorerie que de dette) " + mil(-nd))
            elif eb is not None and eb > 0 and not fo:  # foncière : dette élevée habituelle, jugée sur la couverture des intérêts
                p.append("dette nette %s = %s fois l'EBITDA" % (mil(nd), ("%.1f" % (nd / eb)).replace(".", ",")))
            else:
                p.append("dette nette " + mil(nd) + (" avec un EBITDA négatif" if eb is not None and eb <= 0 else ""))
        ie = num(y0.get("interestExpense"))
        ebit = num(y0.get("ebit")) if num(y0.get("ebit")) is not None else num(y0.get("operatingIncome"))
        if not fi and ie and abs(ie) > 0 and ebit is not None:
            p.append("intérêts couverts %s fois par le résultat d'exploitation" % ("%.1f" % (ebit / abs(ie))).replace(".", ","))
        eq, ta = num(y0.get("equity")), num(y0.get("totalAssets"))
        if eq is not None and eq < 0:
            p.append("capitaux propres négatifs")
        elif eq is not None and ta and ta > 0 and not fi:  # banque : bilan 20 fois les fonds propres, sans alerte à en tirer
            p.append("capitaux propres / bilan " + pc(eq / ta))
        sh = growth(y0.get("shares"), y1.get("shares"))
        if sh is not None:
            p.append("nombre d'actions " + pc(sh, True) + " sur un an")
        if eq and eq > 0 and num(y0.get("netIncome")) is not None:
            p.append("rentabilité des capitaux propres " + pc(y0["netIncome"] / eq))
        if p:
            out.append("Dernier exercice (%s) : %s." % (str(y0["date"])[:10], " ; ".join(p)))
    if Q:
        q0 = Q[-1]
        q1 = same_year_before(Q[:-1], q0.get("date"))
        if q1:
            p = []
            for k, lab in (("revenue", "CA"), ("operatingIncome", "résultat d'exploitation"), ("netIncome", "résultat net"), ("cfo", "flux d'exploitation")):
                a, b = num(q0.get(k)), num(q1.get(k))
                if a is None or b is None:
                    continue
                g = growth(a, b)
                p.append("%s %s" % (lab, pc(g, True)) if g is not None and (k == "revenue" or a > 0) else "%s %s contre %s" % (lab, mil(a), mil(b)))
            m0, m1 = div(q0.get("operatingIncome"), q0.get("revenue")), div(q1.get("operatingIncome"), q1.get("revenue"))
            if m0 is not None and m1 is not None and not fi:
                p.append("marge d'exploitation %s contre %s" % (pc(m0), pc(m1)))
            if p:
                nq = nature(Q)
                out.append(("Dernière période infra-annuelle (%s) face à la même période un an plus tôt (%s) : %s." if nq == "période" else
                            "Dernier " + nq + " (%s) face au même " + nq + " un an plus tôt (%s) : %s.") % (q0["date"], q1["date"], " ; ".join(p)))
        g12 = glissant(Q, Y, fi)
        if g12:
            out.append(g12)
        if Y and str(q0.get("date")) > str(Y[-1].get("date")):
            y0, p = Y[-1], []
            for k, lab in ((("equity", "capitaux propres"), ("shares", "actions")) if fi else
                           (("cash", "trésorerie"), ("totalDebt", "dette financière"), ("equity", "capitaux propres"), ("shares", "actions"))):
                if num(q0.get(k)) is not None and num(y0.get(k)) is not None:
                    p.append("%s %s (%s à la clôture de l'exercice)" % (lab, mil(q0[k]), mil(y0[k])))
            if p:
                out.append("Bilan au %s face au dernier exercice (%s) : %s." % (q0["date"], str(y0["date"])[:10], " ; ".join(p)))
    return out


def jusqua(fin, per):
    """Comptes connus à la fin de la période lue : une lecture plus ancienne que les derniers comptes garde ses propres alertes."""
    return dict(fin, years=[y for y in fin.get("years") or [] if isinstance(y, dict) and str(y.get("date")) <= str(per)],
                quarters=[q for q in fin.get("quarters") or [] if isinstance(q, dict) and str(q.get("date")) <= str(per)])


def alertes(fin, secteur):
    """Points d'alerte calculés ici, sans IA : sept cas chiffrés. À la mise en service (25/11/2026), Haiku en ajoutait hors des cas
    prévus (Louis Hachette Group : « dette nette … 3,3 fois l'EBITDA : sous le seuil de 4 fois, mais élevée »), et chacun faisait
    passer le conseil à « point d'alerte ». Dernier exercice face au précédent, dernier trimestre ou semestre face au même un an plus
    tôt, bilan le plus récent. Banques et assurances : capitaux propres et pertes seulement ; foncières : sans dette / EBITDA."""
    Y = sorted((y for y in fin.get("years") or [] if isinstance(y, dict) and y.get("date")), key=lambda y: str(y["date"]))
    Q = sorted((q for q in fin.get("quarters") or [] if isinstance(q, dict) and q.get("date")), key=lambda q: str(q["date"]))
    if not Y:
        return []
    fi, fo = bool(FINANCE.search(secteur or "")), bool(FONCIERE.search(secteur or ""))
    cur = fin.get("currency") or ""
    m = lambda v: mil(v) + " M" + (" " + cur if cur else "")  # noqa: E731
    f1 = lambda x: ("%.1f" % x).replace(".", ",")  # noqa: E731
    y0, y1 = Y[-1], (Y[-2] if len(Y) > 1 else {})
    ex = "exercice " + str(y0["date"])[:4]
    q0 = Q[-1] if Q and str(Q[-1]["date"]) > str(y0["date"]) else None
    q1 = same_year_before(Q[:-1], q0["date"]) if q0 else None
    nq = nature(Q) if q0 else ""
    lq = "dernière période" if nq == "période" else "dernier " + nq  # « dernier trimestre », « dernière période »
    last = lambda k: num(q0.get(k)) if q0 and num(q0.get(k)) is not None else num(y0.get(k))  # noqa: E731
    out = []
    if not fi and not fo and num(y0.get("totalDebt")) is not None and num(y0.get("cash")) is not None:
        nd, eb = y0["totalDebt"] - y0["cash"], num(y0.get("ebitda"))
        if nd > 0 and eb is not None and eb > 0 and nd / eb > 4:
            out.append("dette nette à %s fois l'EBITDA (%s)" % (f1(nd / eb), ex))
        elif nd > 0 and eb is not None and eb <= 0:
            out.append("dette nette de %s avec un EBITDA négatif (%s)" % (m(nd), ex))
    ie = abs(num(y0.get("interestExpense")) or 0)
    ebit = num(y0.get("ebit")) if num(y0.get("ebit")) is not None else num(y0.get("operatingIncome"))
    if not fi and ie > 0 and ebit is not None and 0 < ebit < 2 * ie:  # société en perte : vue par les cas suivants
        out.append("intérêts couverts %s fois seulement par le résultat d'exploitation (%s)" % (f1(ebit / ie), ex))
    eq = last("equity")
    if eq is not None and eq < 0:
        out.append("capitaux propres négatifs (%s)" % m(eq))
    for a, b, lab in ((y0, y1, ex), (q0, q1, lq)):
        g = growth((a or {}).get("shares"), (b or {}).get("shares"))
        if g is not None and 0.10 <= g <= 0.80:  # au-delà : division du nominal plutôt qu'une émission d'actions
            out.append("nombre d'actions %s en un an (%s) : dilution" % (pc(g, True), lab))
            break
    if not fi:
        for a, b, lab in ((q0, q1, lq + " face à un an plus tôt"), (y0, y1, ex + " face au précédent")):
            g = growth((a or {}).get("revenue"), (b or {}).get("revenue"))
            if g is not None and g < -0.20:
                out.append("chiffre d'affaires %s (%s)" % (pc(g, True), lab))
                break
    for a, b, lab in ((q0, q1, lq), (y0, y1, ex)):
        n0, n1 = num((a or {}).get("netIncome")), num((b or {}).get("netIncome"))
        if n0 is not None and n1 is not None and n0 < 0 and n0 < n1:
            out.append("perte de %s (%s), contre %s un an plus tôt" % (m(-n0), lab, ("un bénéfice de " if n1 >= 0 else "une perte de ") + m(abs(n1))))
            break
    cfo, cash = num(y0.get("cfo")), last("cash")
    if not fi and cfo is not None and cfo < 0 and cash is not None and cash < -cfo:
        out.append("flux d'exploitation négatif (%s sur l'%s) et trésorerie de %s : moins d'un an" % (m(cfo), ex, m(cash)))
    return out


def alerte_txt(fin, secteur, per):
    """Texte des deux premiers points d'alerte de la période lue, ou chaîne vide."""
    a = alertes(jusqua(fin, per), secteur)[:2]
    t = " ; ".join(a)
    return t[:1].upper() + t[1:] if t else ""


def surprise(key, sym, per, events, est):
    """Première publication de résultats dans les 120 jours après la fin de la période lue (celle qui la présente : les résultats du
    trimestre suivant tombent aussi dans la fenêtre d'un exercice), et écart du bénéfice par action à l'attente des analystes quand
    Yahoo le donne (relevé du soir des sociétés suivies, relevé hebdomadaire du catalogue). → (date, écart en %) ou None."""
    d0 = day(per)
    if not d0:
        return None
    lo, hi = d0.isoformat(), (d0 + timedelta(days=120)).isoformat()
    found = []
    e = events.get(key) if isinstance(events, dict) else None
    for x in (e or {}).get("earnings") or []:
        if not isinstance(x, dict) or not (lo < str(x.get("date") or "") <= hi):
            continue
        a, b = num(x.get("epsActual")), num(x.get("epsEstimate"))
        found.append((str(x["date"]), (a - b) / abs(b) * 100 if a is not None and b not in (None, 0) else None))
    s = est.get(sym) if isinstance(est, dict) and sym else None
    for x in (s or {}).get("surprises") or []:
        if isinstance(x, (list, tuple)) and len(x) >= 2 and isinstance(x[0], str) and lo < x[0] <= hi:
            found.append((x[0], num(x[1])))
    today_s = date.today().isoformat()
    found = sorted((f for f in found if f[0] <= today_s), key=lambda f: (f[0], f[1] is None))
    return found[0] if found else None


def contexte():
    """Nom, symbole, pays, secteur, F-score et note des sociétés (classement du soir, puis dossiers Euro Signal), et sociétés 🎯 / 💎."""
    dash = load(DATA / "euro-signal.json", {})
    out = {}
    for isin, i in (dash.get("inst") or {}).items():
        if isinstance(i, dict):
            out[isin] = {"nom": i.get("name") or isin, "symbole": i.get("ticker") or "", "pays": i.get("country") or "",
                         "secteur": i.get("sector") or (i.get("fund") or {}).get("sector") or ""}
    rank = dash.get("rank") or {}
    for r in rank.get("rows") or []:
        if isinstance(r, dict) and r.get("key"):
            out[r["key"]] = {"nom": r.get("name") or r["key"], "symbole": r.get("sym") or "", "pays": r.get("country") or "",
                             "secteur": r.get("sector") or r.get("secEn") or "", "f9": r.get("f9"), "note": r.get("note")}
    picks = set()
    for k in ("pick10", "value10"):
        if isinstance(rank.get(k), list):
            picks |= {str(x) for x in rank[k]}
    return out, picks


def a_lire(cur, fin):
    """Lecture à faire : aucune lecture, consigne changée, ou période plus récente que celle déjà lue (une période plus ancienne,
    trimestre retiré un soir par Yahoo, ne refait pas la lecture)."""
    last = derniere(fin)
    if not last:
        return None
    if not isinstance(cur, dict) or cur.get("v") != VERSION or str(last[0]) > str(cur.get("per") or ""):
        return last
    return None


def pub_of(fin, per, today):
    """Date des nouveaux comptes vus par le collecteur, si la lecture porte sur eux et qu'ils ont moins de PUB_DAYS jours."""
    na, d = day(fin.get("newAt")), str(fin.get("newPer") or "")
    return fin["newAt"] if na and d == per and 0 <= (today - na).days < PUB_DAYS else None


def bloc(key, fin, ctx, per, nat, events, est):
    c = ctx.get(key) or {}
    sym = c.get("symbole") or fin.get("ticker") or ""
    head = 'Société id "%s" : %s (symbole %s, pays %s, secteur %s) ; comptes en %s, montants en millions' % (
        key, c.get("nom") or fin.get("ticker") or key, sym or "?", c.get("pays") or "?", c.get("secteur") or "?", fin.get("currency") or "?")
    if isinstance(c.get("f9"), (int, float)):
        head += " ; F-score de Piotroski calculé par l'outil : %d/9" % c["f9"]
    lines = [head + ".", "Dernière période : %s (%s)." % (per, nat)]
    fi = bool(FINANCE.search(c.get("secteur") or ""))
    Y = sorted((y for y in fin.get("years") or [] if isinstance(y, dict) and y.get("date")), key=lambda y: str(y["date"]))[-4:]
    if Y:
        lines.append("Exercices annuels :")
        lines += ["  " + ligne(y, fi) for y in reversed(Y)]
    Q = sorted((q for q in fin.get("quarters") or [] if isinstance(q, dict) and q.get("date")), key=lambda q: str(q["date"]))
    if Q:
        # dernière période et même période un an plus tôt seulement : à l'essai du 25/11/2026, Haiku comparait au trimestre précédent
        nq = nature(Q)
        q0, q1 = Q[-1], same_year_before(Q[:-1], Q[-1].get("date"))
        lab0 = "Dernière période infra-annuelle" if nq == "période" else "Dernier " + nq
        lines.append("%s : %s" % (lab0, ligne(q0, fi)))
        lines.append(("Même période un an plus tôt : " if nq == "période" else "Même " + nq + " un an plus tôt : ")
                     + (ligne(q1, fi) if q1 else "non fourni par Yahoo (ne pas comparer à une autre période)"))
    R = ratios(fin, c.get("secteur") or "")
    if R:
        lines.append("Ratios calculés :")
        lines += ["  " + r for r in R]
    al = alertes(jusqua(fin, per), c.get("secteur") or "")
    if al:
        lines.append("Points d'alerte calculés par l'outil : " + " ; ".join(al) + ".")
    s = surprise(key, sym, per, events, est)
    if s:
        lines.append("Résultats publiés le %s%s." % (s[0], "" if s[1] is None else " : bénéfice par action %s %s l'attente des analystes" % (
            pc(abs(s[1]) / 100), "au-dessus de" if s[1] >= 0 else "en dessous de")))
    return "\n".join(lines)


def court(t, n):
    t = re.sub(r"\s+", " ", t if isinstance(t, str) else "").strip()
    if len(t) <= n:
        return t
    cut = t[:n - 1]
    return (cut[:cut.rfind(" ")] if " " in cut else cut).rstrip(" ,;:") + "…"


def conseil(rec):
    """Conseil affiché sans IA, d'après l'avis et l'alerte : la règle testée reste la référence (même texte que ES.comptesConseil)."""
    if rec.get("a") == "def" or rec.get("al"):
        return "Point d'alerte : à vérifier avant d'acheter ou de garder (la règle testée reste la référence)."
    return "Rien dans ces comptes qui contredise la règle testée."


def applique(store, lectures, todo, today_s, modele):
    """Reporte les lectures valides ; renvoie le nombre de sociétés lues. Une entrée sans avis reconnu ou sans résumé est ignorée."""
    n = 0
    for x in lectures:
        k = str(x.get("id") or "")
        if k not in todo:
            continue
        avis = AVIS.get(str(x.get("avis") or "").strip().lower())
        res = court(x.get("resume"), 240)
        if not avis or not res:
            continue
        per, nat, pub = todo[k]
        rec = {"per": per, "nat": nat, "at": today_s, "v": VERSION, "m": modele, "res": res,
               "f": [court(t, 100) for t in (x.get("forts") or []) if isinstance(t, str) and t.strip()][:3] if isinstance(x.get("forts"), list) else [],
               "w": [court(t, 100) for t in (x.get("faibles") or []) if isinstance(t, str) and t.strip()][:3] if isinstance(x.get("faibles"), list) else [],
               "i": IMPACT.get(str(x.get("impact") or "").strip().lower(), "flat"), "a": avis}
        if pub:
            rec["pub"] = pub
        store[k] = rec
        n += 1
    return n


def ecrit(store, meta):
    tmp = OUT.with_name(OUT.name + ".tmp")  # écriture atomique : une étape coupée par son délai garde le fichier précédent entier
    tmp.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "lecture": meta, "items": store},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    fin = load(DATA / "financials.json", {}).get("items")
    if not isinstance(fin, dict) or not fin:
        print("Lecture des comptes : data/financials.json absent ou vide, rien à faire")
        return 0
    old = load(OUT, {})
    store = old.get("items") if isinstance(old.get("items"), dict) else {}
    cfg = config()
    ctx, picks = contexte()
    events = load(DATA / "events.json", {}).get("items") or {}
    est = load(DATA / "sectors" / "estimates.json", {})
    today = datetime.now(timezone.utc).date()
    today_s = today.isoformat()
    # clé des comptes : ISIN, ou « @symbole » pour le catalogue ; clé des lectures : celle du classement (ISIN ou symbole)
    todo = {}
    for fk, f in fin.items():
        if not isinstance(f, dict) or not f.get("years"):
            continue
        k = fk[1:] if fk.startswith("@") else fk
        last = a_lire(store.get(k), f)
        if last:
            todo[k] = (last[0], last[1], pub_of(f, last[0], today), f)
    keys = sorted(todo, key=lambda k: (todo[k][2] is None, k not in picks, -(num((ctx.get(k) or {}).get("note")) or 0), k))
    n_pub = sum(1 for k in keys if todo[k][2])
    if not key:
        print("Lecture des comptes : pas de secret ANTHROPIC_API_KEY, %d sociétés à lire (%d nouvelles publications)" % (len(keys), n_pub))
        return 0
    size = max(1, int(cfg["lot"]))
    L = [keys[i:i + size] for i in range(0, len(keys), size)]
    t0, lus, err, usage, done_lots = time.time(), 0, {}, {}, 0
    meta = dict(old.get("lecture") or {})

    def one(lot):
        if time.time() - t0 > cfg["budget"]:
            return lot, None, "budget"
        try:
            texte = "\n\n".join(bloc(k, todo[k][3], ctx, todo[k][0], todo[k][1], events, est) for k in lot)
            return lot, appel(key, cfg, texte, SYSTEME), None
        except Exception as e:  # noqa: BLE001
            return lot, None, str(e)[:40]
    with cf.ThreadPoolExecutor(max(1, int(cfg["paralleles"]))) as pool:  # rien à lire : points d'alerte recalculés quand même
        futs = [pool.submit(one, lot) for lot in L]
        for fu in cf.as_completed(futs):
            lot, res, e = fu.result()
            if e:
                err[e] = err.get(e, 0) + 1
                continue
            for k_, v_ in (res.get("usage") or {}).items():
                if isinstance(v_, (int, float)):
                    usage[k_] = usage.get(k_, 0) + v_
            text = "".join(b.get("text", "") for b in res.get("content") or [] if isinstance(b, dict) and b.get("type") == "text")
            lus += applique(store, lire(text), {k: todo[k][:3] for k in lot}, today_s, cfg["modele"])
            done_lots += 1
            if lus and done_lots % 10 == 0:  # étape coupée par son délai : les lectures déjà faites sont gardées
                ecrit(store, dict(meta, modele=cfg["modele"], version=VERSION, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    gone = [k for k in store if ("@" + k) not in fin and k not in fin]  # sociétés sorties des comptes suivis
    for k in gone:
        store.pop(k, None)
    changed = 0  # points d'alerte calculés ici : recalculés pour chaque lecture, sans appel à l'API
    for fk, f in fin.items():
        k = fk[1:] if fk.startswith("@") else fk
        r = store.get(k)
        if not isinstance(f, dict) or not isinstance(r, dict) or not r.get("per"):
            continue
        al = alerte_txt(f, (ctx.get(k) or {}).get("secteur") or "", r["per"])
        if al != (r.get("al") or ""):
            if al:
                r["al"] = al
            else:
                r.pop("al", None)
            changed += 1
    if lus or gone or changed:  # rien de lu (API en panne), rien à retirer ni à recalculer : fichier laissé tel quel
        ecrit(store, {"modele": cfg["modele"], "version": VERSION, "lus": lus,
                      "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) if lus else meta.get("at")})
    rd = [v for v in store.values() if isinstance(v, dict) and v.get("v") == VERSION]
    print("Lecture des comptes (%s) : %d sociétés lues sur %d à lire (dont %d nouvelles publications), en %.0f s, environ %.3f $ ; "
          "lectures à jour : %d (%d favorables, %d mitigées, %d défavorables, %d avec un point d'alerte)%s" % (
              cfg["modele"], lus, len(keys), n_pub, time.time() - t0, cout(usage, cfg["modele"]), len(rd),
              sum(1 for v in rd if v.get("a") == "fav"), sum(1 for v in rd if v.get("a") == "mit"),
              sum(1 for v in rd if v.get("a") == "def"), sum(1 for v in rd if v.get("al")),
              (" ; points d'alerte recalculés : %d" % changed if changed else "")
              + ((" ; lots non lus : " + ", ".join("%s (%d)" % kv for kv in err.items())) if err else "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
