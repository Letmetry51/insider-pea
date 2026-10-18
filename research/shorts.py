"""
Recherche ponctuelle (18/10/2026) : les ventes à découvert publiées (AMF depuis 2012, FCA britannique) aident-elles à mieux choisir
parmi les sociétés en tendance ? Données publiques gratuites ; cours Yahoo hebdomadaires. Ne modifie pas le tableau de bord.

Positions courtes nettes ≥ 0,5 % du capital : publiques, nominatives. Pour chaque société et chaque vendredi, somme des positions
publiées et encore en cours ce jour-là (dates de publication : rien n'est connu avant d'être publié).
Résultat : écart de performance à 6 mois avec la société moyenne de la même semaine, comme les autres tests de l'outil.
"""
import io, json, glob, sys, time, re
from pathlib import Path
import numpy as np, pandas as pd, requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scrapers'))
OUT = ROOT / 'research' / 'out'; OUT.mkdir(parents=True, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (euro-signal research)'}
AMF_URL = 'https://www.data.gouv.fr/api/1/datasets/r/c2539d1c-8531-4937-9cba-3bd8e9786cc5'
FCA_URL = 'https://www.fca.org.uk/publication/data/short-positions-daily-update.xlsx'
def log(*a): print(*a, flush=True)
def col(df, *keys, avoid=()):
    for c in df.columns:
        n = str(c).lower()
        if all(k in n for k in keys) and not any(a in n for a in avoid): return c
    raise KeyError(f'colonne {keys} introuvable dans {list(df.columns)}')

def amf():
    r = requests.get(AMF_URL, headers=UA, timeout=120); r.raise_for_status()
    raw = r.content.decode('utf-8-sig', errors='replace')
    df = pd.read_csv(io.StringIO(raw), sep=None, engine='python')
    log('AMF colonnes :', list(df.columns)); log(df.head(3).to_string())
    ci, cr = col(df, 'isin'), next(c for c in df.columns if re.search(r'ratio|position courte nette|net short', str(c), re.I) and 'date' not in str(c).lower() and 'détenteur' not in str(c).lower() and 'holder' not in str(c).lower())
    cs = next(c for c in df.columns if re.search(r'd[ée]but.*publi|publi.*start|start.*publi', str(c), re.I))
    ce = next(c for c in df.columns if re.search(r'fin.*publi|publi.*end|end.*publi', str(c), re.I))
    v = pd.to_numeric(df[cr].astype(str).str.replace(',', '.').str.replace('%', ''), errors='coerce')
    if v.median() < 0.1: v = v * 100
    out = pd.DataFrame({'isin': df[ci].astype(str).str.strip().str.upper(), 'pct': v,
                        'start': pd.to_datetime(df[cs], dayfirst=True, errors='coerce'), 'end': pd.to_datetime(df[ce], dayfirst=True, errors='coerce'), 'src': 'AMF'})
    log('AMF :', len(out), 'lignes,', out.isin.nunique(), 'sociétés, de', out.start.min(), 'à', out.start.max(), '| % médian', out.pct.median())
    return out.dropna(subset=['pct', 'start'])

def fca():
    r = requests.get(FCA_URL, headers=UA, timeout=120); r.raise_for_status()
    xl = pd.read_excel(io.BytesIO(r.content), sheet_name=None)
    rows = []
    for name, df in xl.items():
        log('FCA feuille', name, list(df.columns)[:8], len(df))
        try: ch, ci, cp, cd = col(df, 'holder'), col(df, 'isin'), col(df, 'net short'), col(df, 'date')
        except KeyError: continue
        rows.append(pd.DataFrame({'holder': df[ch].astype(str), 'isin': df[ci].astype(str).str.strip().str.upper(), 'pct': pd.to_numeric(df[cp], errors='coerce'), 'date': pd.to_datetime(df[cd], errors='coerce')}))
    d = pd.concat(rows).dropna(subset=['pct', 'date']).drop_duplicates().sort_values(['holder', 'isin', 'date'])
    # chaque déclaration vaut jusqu'à la suivante du même détenteur ; sous 0,5 % la position cesse d'être publique
    d['start'] = d['date'] + pd.Timedelta(days=1)
    d['end'] = d.groupby(['holder', 'isin'])['start'].shift(-1)
    d = d[d.pct >= 0.5]
    log('FCA :', len(d), 'positions publiques,', d.isin.nunique(), 'sociétés, de', d.start.min(), 'à', d.start.max())
    return d[['isin', 'pct', 'start', 'end']].assign(src='FCA')

def resolve(isins, cache_path):
    """ISIN → symbole Yahoo (Paris pour FR, Londres sinon), recherche Yahoo, en cache."""
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    import yfinance as yf
    todo = [i for i in isins if i not in cache]
    log('ISIN à résoudre :', len(todo), '(en cache :', len(isins) - len(todo), ')')
    for k, i in enumerate(todo):
        sym = None
        for a in range(3):
            try:
                q = yf.Search(i, max_results=8, news_count=0).quotes; break
            except Exception as e:
                q = []; time.sleep(3 * (a + 1))
        pref = ('.PA',) if i.startswith('FR') else ('.L',)
        eq = [x.get('symbol') for x in q if x.get('quoteType') == 'EQUITY' and x.get('symbol')]
        sym = next((s for s in eq if s.endswith(pref)), None) or next((s for s in eq if s.endswith(('.PA', '.L', '.AS', '.BR', '.MI', '.DE', '.MC'))), None)
        cache[i] = sym
        if k % 100 == 0: log(f'  {k}/{len(todo)}'); cache_path.write_text(json.dumps(cache))
        time.sleep(0.25)
    cache_path.write_text(json.dumps(cache)); return cache

def main():
    S = pd.concat([amf(), fca()], ignore_index=True)
    S = S[S.isin.str.match(r'^[A-Z]{2}[A-Z0-9]{9}\d$')]
    m = resolve(sorted(S.isin.unique()), OUT / 'isin_yahoo.json')
    S['sym'] = S.isin.map(m); log('ISIN résolus :', S.drop_duplicates('isin').sym.notna().sum(), '/', S.isin.nunique())
    # univers témoin : sociétés liquides de Paris et Londres du catalogue (non vendues à découvert = 0)
    uni = set()
    for f in glob.glob(str(ROOT / 'data' / 'societes' / '*.json')):
        for k, x in json.load(open(f))['items'].items():
            if k.endswith(('.PA', '.L')) and (x.get('turnoverEur') or 0) >= 1e6: uni.add(k)
    uni |= set(S.sym.dropna()); uni = sorted(uni); log('titres à télécharger :', len(uni))
    import yahoo
    fr = yahoo.download(uni, 'research', start='2011-06-01', interval='1wk', fields=('Close',))
    W = fr['Close'].resample('W-FRI').last().loc['2011-06-01':]
    W = W.loc[:, W.notna().sum() >= 104]
    dates = W.index; cols = list(W.columns); T, N = len(dates), len(cols); log('cours :', W.shape)
    P = W.values.T.astype(float); P = np.where(P > 0, P, np.nan)
    # coupe après un saut anormal (comme les autres tests)
    for i in range(N):
        p = P[i]; ok = np.where(np.isfinite(p))[0]
        if len(ok) < 2: continue
        q = p[ok[1:]] / p[ok[:-1]]; bad = np.where((q > 2.5) | (q < 0.35))[0]
        if len(bad): P[i, :ok[bad[-1] + 1]] = np.nan
    # positions courtes : somme des positions publiées en cours chaque vendredi
    SI = np.zeros((N, T)); idx = {c: k for k, c in enumerate(cols)}
    for r in S.dropna(subset=['sym']).itertuples():
        k = idx.get(r.sym)
        if k is None: continue
        a = np.searchsorted(dates.values, np.datetime64(r.start))
        b = T if pd.isna(r.end) else np.searchsorted(dates.values, np.datetime64(r.end))
        if b > a: SI[k, a:b] += r.pct
    lon = np.array([c.endswith('.L') for c in cols])
    def sma(A, k):
        o = np.full_like(A, np.nan); c = np.nancumsum(np.nan_to_num(A), 1); n = np.cumsum(np.isfinite(A), 1)
        o[:, k-1:] = (c[:, k-1:] - np.concatenate([np.zeros((N, 1)), c[:, :-k]], 1)) / k
        cnt = n[:, k-1:] - np.concatenate([np.zeros((N, 1)), n[:, :-k]], 1); o[:, k-1:][cnt < k] = np.nan; return o
    m10, m40 = sma(P, 10), sma(P, 40); trend = (m10 > m40) & (P > m40)
    mom = np.full_like(P, np.nan); mom[:, 52:] = P[:, 48:-4] / P[:, :-52] - 1
    L = np.log(P); x = np.arange(26) - 12.5; s26 = np.full_like(P, np.nan)
    for t in range(25, T):
        y = L[:, t-25:t+1]; ym = y.mean(1, keepdims=True); s26[:, t] = np.exp(((y - ym) * x).sum(1) / (x * x).sum() * 26) - 1
    H = 26; fut = np.full_like(P, np.nan); fut[:, :-H] = P[:, H:] / P[:, :-H] - 1
    valid = np.isfinite(mom) & np.isfinite(fut) & np.isfinite(s26)
    mp = np.full_like(P, np.nan)
    for t in range(T):
        ok = valid[:, t]
        if ok.sum() > 30: mp[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
    d13 = np.zeros_like(SI); d13[:, 13:] = SI[:, 13:] - SI[:, :-13]
    t0 = int(np.searchsorted(dates.values, np.datetime64('2013-01-01')))
    yr = dates.year.values
    def st(M, a=t0, b=T):
        ex = []; n = 0; cr = 0; win = 0
        for t in range(max(a, t0), min(b, T - H)):
            ok = valid[:, t]; mm = M[:, t] & ok
            if ok.sum() < 30 or not mm.any(): continue
            f = np.clip(fut[:, t], *np.nanpercentile(fut[ok, t], [2, 98]))
            ex.append(np.nanmean(f[mm]) - np.nanmean(f[ok])); n += mm.sum(); cr += (fut[mm, t] <= -.25).sum(); win += (fut[mm, t] > 0).sum()
        if not ex: return None
        ex = np.array(ex); tt = ex.mean() / ex.std() * np.sqrt(len(ex)) / np.sqrt(H) if ex.std() > 0 else 0
        return ex.mean() * 100, tt, cr / n * 100, win / n * 100, n
    P1 = [('2013-2019', t0, int(np.searchsorted(yr, 2020))), ('2020-2026', int(np.searchsorted(yr, 2020)), T)]
    B = valid & (mp >= 2/3) & trend & (s26 >= .41); Q = B & (mom >= .6) & (mom <= 2)
    lines = []
    def show(lab, M):
        r = st(M)
        if not r: lines.append(f'{lab:56s} —'); return
        per = '  '.join(f"{p}: {'—' if st(M, a, b) is None else '%+.1f' % st(M, a, b)[0]}" for p, a, b in P1)
        lines.append(f"{lab:56s} {r[0]:+6.1f} pts  t={r[1]:4.1f}  chutes {r[2]:4.1f} %  gagnants {r[3]:3.0f} %  n={r[4]:6d} | {per}")
    lines.append(f"Sociétés : {N} (Londres {lon.sum()}, Paris {(~lon).sum()}), semaines {dates[t0].date()} → {dates[-1].date()} ; part des cas avec une position publiée : {(SI[valid] > 0).mean()*100:.1f} %")
    for zone, Z in [('Paris + Londres', np.ones(N, bool)), ('Paris', ~lon), ('Londres', lon)]:
        Zb = Z[:, None]
        lines.append(f"\n=== {zone} ===")
        for lab, M in [('toutes, sans position publiée', valid & (SI == 0)), ('toutes, 0,5 à 2 % vendus à découvert', valid & (SI > 0) & (SI < 2)),
                       ('toutes, 2 à 5 %', valid & (SI >= 2) & (SI < 5)), ('toutes, 5 % ou plus', valid & (SI >= 5)), ('toutes, hausse de la vente à découvert ≥ +1 pt sur 3 mois', valid & (d13 >= 1)),
                       ('classement + pente forte', B), ('  … sans position publiée', B & (SI == 0)), ('  … avec 0,5 % ou plus', B & (SI > 0)), ('  … avec 2 % ou plus', B & (SI >= 2)),
                       ('filtres 🎯 (sans les comptes)', Q), ('  … sans position publiée', Q & (SI == 0)), ('  … avec 0,5 % ou plus', Q & (SI > 0)), ('  … avec 2 % ou plus', Q & (SI >= 2)), ('  … vente à découvert en hausse ≥ +1 pt', Q & (d13 >= 1))]:
            show(lab, M & Zb)
    rep = '\n'.join(lines); log('\n' + rep)
    (OUT / 'rapport.txt').write_text('Ventes à découvert publiées et tendance — écart à 6 mois avec la société moyenne\n' + rep + '\n')

if __name__ == '__main__':
    main()
