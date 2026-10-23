"""
Lien avec Yahoo Finance, rendu robuste (18/10/2026).

- Cache des fuseaux horaires de yfinance dans un dossier propre au processus : évite l'erreur « database is locked »
  quand plusieurs lots sont téléchargés en parallèle.
- Téléchargement par lots avec nouvelles tentatives : jeton (crumb) renouvelé sur 401, attente croissante sur 429 / « Too Many ».
- Titres manquants dans un lot : relance en petits lots, puis un par un (dans une limite), au lieu de les perdre pour la nuit.
- Compteurs (demandés, reçus, récupérés, manquants, erreurs) écrits dans data/diagnostics/yahoo.json, lus par le contrôle du soir.
"""
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

DIAG = Path(__file__).resolve().parent.parent / "data" / "diagnostics" / "yahoo.json"
STATS = {}
_CONFIGURED = False


def log(*a):
    print(*a, flush=True)


def configure():
    """Cache sqlite de yfinance isolé par processus (les écritures concurrentes provoquaient « database is locked »)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    import yfinance as yf
    try:
        d = Path(tempfile.gettempdir()) / f"yf-cache-{os.getpid()}"
        d.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(d))
    except Exception:
        pass
    _CONFIGURED = True


def reset_session():
    """Jeton Yahoo refusé : yfinance en redemande un."""
    try:
        from yfinance.data import YfData
        d = YfData()
        for k in ("_crumb", "_cookie"):
            if hasattr(d, k):
                setattr(d, k, None)
    except Exception:
        pass


def _stat(section, **inc):
    s = STATS.setdefault(section, {"requested": 0, "received": 0, "recovered": 0, "missing": 0, "errors": 0, "carried": 0})
    for k, v in inc.items():
        s[k] = s.get(k, 0) + v
    return s


def call(fn, tries=4, section=None):
    """Appel Yahoo avec nouvelles tentatives ; l'exception finale est relancée."""
    for k in range(tries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if section:
                _stat(section, errors=1)
            if k == tries - 1:
                raise
            if "Crumb" in msg or "401" in msg or "Unauthorized" in msg:
                reset_session()
            rate = "429" in msg or "Too Many" in msg or "Rate" in msg
            time.sleep((10 if rate else 2) * (k + 1))


def _frames(df, batch, fields):
    """Colonnes « Close » / « Volume » d'un résultat yf.download, quel que soit son format."""
    import pandas as pd
    out = {}
    if df is None or df.empty:
        return {f: pd.DataFrame() for f in fields}
    for f in fields:
        if isinstance(df.columns, pd.MultiIndex):
            out[f] = df[f] if f in df.columns.get_level_values(0) else pd.DataFrame()
        else:
            out[f] = df[[f]].rename(columns={f: batch[0]}) if f in df.columns else pd.DataFrame()
    return out


def download(tickers, section, batch=80, fields=("Close", "Volume"), max_single=60, **kw):
    """yf.download robuste : renvoie {champ: DataFrame dates × titres}. kw : period, interval, start, auto_adjust…"""
    import pandas as pd
    import yfinance as yf
    configure()
    kw = dict(dict(progress=False, threads=True, group_by="column", auto_adjust=True), **kw)
    tick = sorted(set(t for t in tickers if t))
    _stat(section, requested=len(tick))
    parts = {f: [] for f in fields}

    def fetch(b, threads=True):
        df = call(lambda: yf.download(b, **dict(kw, threads=threads)), section=section)
        return _frames(df, b, fields)

    def have(fr):
        c = fr.get("Close")
        return set() if c is None or c.empty else {k for k in c.columns if c[k].notna().sum() > 0}

    got = set()
    for i in range(0, len(tick), batch):
        b = tick[i:i + batch]
        try:
            fr = fetch(b)
        except Exception as e:
            log(f"  Yahoo ({section}) lot {i} : échec après plusieurs essais ({str(e)[:80]})")
            fr = {}
        for f in fields:
            if fr.get(f) is not None and not fr[f].empty:
                parts[f].append(fr[f])
        got |= have(fr)
        time.sleep(1)
    miss = [t for t in tick if t not in got]
    # deuxième passe : petits lots sans fils parallèles, puis un par un
    if miss:
        time.sleep(5)
        rec = set()
        for i in range(0, len(miss), 10):
            b = miss[i:i + 10]
            try:
                fr = fetch(b, threads=False)
            except Exception:
                continue
            h = have(fr)
            for f in fields:
                if fr.get(f) is not None and not fr[f].empty:
                    parts[f].append(fr[f][[c for c in fr[f].columns if c in h]] if h else fr[f].iloc[:, :0])
            rec |= h
            time.sleep(1)
        still = [t for t in miss if t not in rec][:max_single]
        for t in still:
            try:
                fr = fetch([t], threads=False)
            except Exception:
                continue
            h = have(fr)
            if h:
                for f in fields:
                    if fr.get(f) is not None and not fr[f].empty:
                        parts[f].append(fr[f])
                rec |= h
            time.sleep(0.5)
        got |= rec
        _stat(section, recovered=len(rec))
    _stat(section, received=len(got), missing=len(tick) - len(got))

    def tidy(frames):
        if not frames:
            return pd.DataFrame()
        X = pd.concat([f for f in frames if not f.empty], axis=1, sort=True) if any(not f.empty for f in frames) else pd.DataFrame()
        if X.empty:
            return X
        X = X.loc[:, ~X.columns.duplicated(keep="last")]
        X.index = pd.to_datetime(X.index).tz_localize(None).normalize()
        return X[~X.index.duplicated(keep="last")].sort_index()
    s = STATS[section]
    log(f"  Yahoo ({section}) : {s['received']}/{s['requested']} titres reçus, {s['recovered']} récupérés en 2e passe, {s['missing']} manquants")
    return {f: tidy(parts[f]) for f in fields}


def carried(section, n):
    _stat(section, carried=n)


def write_diag(now=None):
    """Compteurs de ce script, fusionnés avec ceux des autres scripts des 20 dernières heures (calcul du soir et historique du
    matin) : chaque partie garde son heure ; un passage de minuit pendant le calcul ne perd plus les compteurs du début."""
    try:
        import yfinance as yf
        ver = getattr(yf, "__version__", "?")
    except Exception:
        ver = "?"
    try:
        old = json.loads(DIAG.read_text()) if DIAG.exists() else {}
    except Exception:
        old = {}
    now = now or datetime.now(timezone.utc)
    sections = {}
    for k, v in (old.get("sections") or {}).items():
        try:
            at = datetime.fromisoformat(str((v or {}).get("at") or old.get("at")))
            fresh = (now - at).total_seconds() < 20 * 3600
        except Exception:
            fresh = False
        if fresh and isinstance(v, dict):
            sections[k] = v
    for k, v in STATS.items():
        sections[k] = dict(v, at=now.isoformat())
    DIAG.parent.mkdir(parents=True, exist_ok=True)
    DIAG.write_text(json.dumps({"date": now.date().isoformat(), "at": now.isoformat(), "yfinance": ver, "sections": sections},
                               ensure_ascii=False, indent=1))
