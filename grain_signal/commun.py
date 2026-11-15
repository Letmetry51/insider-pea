"""Bulletin des grains — lecture et écriture des fichiers JSON, communes à tous les modules.

Lecture tolérante (fichier absent ou illisible : valeur par défaut), écriture atomique (fichier temporaire puis remplacement :
une étape coupée en pleine écriture ne laisse jamais un fichier à moitié écrit).
"""
import json
from pathlib import Path


def load(p, default):
    """Contenu JSON du fichier, ou `default` s'il est absent, illisible ou d'un autre type que `default` (une liste là où on
    attend un objet, « null »…) : un fichier abîmé ne fait jamais planter un calcul."""
    try:
        v = json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default
    return v if default is None or isinstance(v, type(default)) else default


def boite(p):
    """Boîte d'envoi (a-envoyer.json) : seulement les messages bien formés (objet avec un identifiant texte)."""
    return [x for x in load(p, []) if isinstance(x, dict) and isinstance(x.get("id"), str)]


def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


# lecture d'un article de la revue de presse (champ « acces », déterminé à la collecte) : mention ajoutée après la source
ACCES = {"entier": " · disponible en entier", "abonnes": " · réservé aux abonnés"}


def nombre(v, d=2):
    """Nombre à la française (espace pour les milliers, virgule décimale) ; « — » si absent ou non numérique."""
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v != v:
        return "—"
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def signe(v, d=2):
    """Nombre signé à la française (+1,25 / −0,50) ; « — » si absent."""
    return nombre(v, d) if nombre(v, d) == "—" else ("+" if v > 0 else "") + nombre(v, d)
