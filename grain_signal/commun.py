"""Bulletin des grains — lecture et écriture des fichiers JSON, communes à tous les modules.

Lecture tolérante (fichier absent ou illisible : valeur par défaut), écriture atomique (fichier temporaire puis remplacement :
une étape coupée en pleine écriture ne laisse jamais un fichier à moitié écrit).
"""
import json
from pathlib import Path


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)
