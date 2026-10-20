"""Achats de dirigeants croisés avec le 🎯 au feu vert : un achat récent (personne physique) ajoute-t-il quelque chose ?
France (AMF, depuis 2021) et Suède (FI, depuis 2016), cours hebdomadaires, écart à 6 mois avec la société moyenne."""
import json, numpy as np
src = open('_indic.py').read(); exec(src.split("# MACD hebdomadaire")[0])
D = np.array([str(d)[:10] for d in dates])
z0 = np.load('long.npz', allow_pickle=True); cols = [str(c) for c in z0['cols']]
assert len(cols) == P.shape[0] and len(D) == P.shape[1], (len(cols), P.shape, len(D))
tk = json.load(open('/home/claude/ip-audit/data/history/tickers.json'))
isin_of = {}
for isin, v in tk.items():
    t = (v or {}).get('ticker')
    if t and t not in isin_of: isin_of[t] = isin
col_isin = [isin_of.get(str(c)) for c in cols]
start = {'FR': '2021-01-27', 'SE': '2016-07-04'}
COV = np.zeros_like(valid)
for i, isin in enumerate(col_isin):
    if isin and isin[:2] in start: COV[i, int(np.searchsorted(D, start[isin[:2]])):] = True
print('sociétés couvertes (FR, SE) dans le panel :', int(COV.any(1).sum()))
ins = json.load(open('/home/claude/ip-audit/data/euro-signal-insiders.json'))
idx = {isin: i for i, isin in enumerate(col_isin) if isin}
def mask(minEur, weeks):
    M = np.zeros_like(valid); n = 0
    for p, v in ins['persons'].items():
        for r in v.get('rows') or []:
            if r[3] != 'A' or r[11] or r[12] or (r[7] or 0) < minEur: continue  # achats de personnes physiques, non exclus
            i = idx.get(r[2])
            if i is None: continue
            t = int(np.searchsorted(D, r[0]))  # première semaine dont la clôture suit la publication
            if t < T: M[i, t:min(T, t + weeks)] = True; n += 1
    return M, n
def rowC(lab, M, base):
    r = st(M)
    if r is None or M.sum() < 100: print(f"  {lab:52s} trop peu ({int(M.sum())})"); return
    print(f"  {lab:52s} {r[0]:+6.1f} pts  chutes {r[1]:4.1f} %  n {int(M.sum()):6d}  part {M.sum()/max(base.sum(),1)*100:4.0f} %")
FC = F & COV
print('\n🎯 au feu vert, sociétés françaises et suédoises couvertes')
rowC('tous', FC, FC)
for minEur, lab in [(0, 'tout achat'), (1e5, 'achats ≥ 100 k€')]:
    for w in (4, 13):
        M, n = mask(minEur, w)
        print(f'\n- {lab}, publié dans les {w} dernières semaines ({n} achats placés)')
        rowC('avec achat récent', FC & M, FC); rowC('sans', FC & ~M, FC)
        rowC('(toutes sociétés couvertes) avec achat récent', valid & COV & M, valid & COV); rowC('(toutes sociétés couvertes) sans', valid & COV & ~M, valid & COV)
