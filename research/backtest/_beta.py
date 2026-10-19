"""Bêta dans le 🎯 : simple information, critère de tri après les volumes, ou bêta fort placé en fin de liste ? Portefeuille simulé 1997-2026."""
import numpy as np, sys
src = open('stress2.py').read(); exec(src.split("rng = np.random")[0])
v52 = np.load('v52.npy').astype(float)
r1 = np.full_like(P, np.nan); r1[:, 1:] = P[:, 1:] / P[:, :-1] - 1
BETA = np.full_like(P, np.nan)
for t in range(52, T):
    R1 = r1[:, t-51:t+1]; M = mk[t-51:t+1]; Mc = M - np.nanmean(M); Rc = R1 - np.nanmean(R1, 1, keepdims=True)
    BETA[:, t] = np.nansum(np.nan_to_num(Rc) * Mc, 1) / np.sum(Mc ** 2)
below = P < m10
def pick_with(t, key):
    ok = valid[:, t] & np.isfinite(P[:, t]) & ~(v52[:, t] >= .8)
    tiers = [ok & (mp[:, t] >= 2/3) & trend[:, t] & (s26[:, t] >= .41) & (mom[:, t] >= .6) & (mom[:, t] <= 2),
             ok & (mp[:, t] >= 1/3) & trend[:, t] & (s26[:, t] >= .14) & (mom[:, t] >= .3) & (mom[:, t] <= 2)]
    out, seen = [], {}
    for M in tiers:
        idx = np.where(M & ~np.isin(np.arange(N), out))[0]
        hot = vx[idx, t] >= 1.5; wt = below[idx, t]; b = np.nan_to_num(BETA[idx, t], nan=1.0)
        if key == 'actuel': order = idx[np.lexsort((-score[idx, t], wt, ~hot))]
        elif key == 'beta_tri': order = idx[np.lexsort((-score[idx, t], b > 1.3, wt, ~hot))]   # bêta fort après, à volumes et moyenne égaux
        elif key == 'beta_avant': order = idx[np.lexsort((-score[idx, t], wt, ~hot, b > 1.3))]  # bêta fort en dernier, avant tout
        elif key == 'beta_rang': order = idx[np.lexsort((b, wt, ~hot))]                       # bêta le plus faible d'abord, au lieu de la note
        for i in order:
            if len(out) >= 10: break
            if seen.get(sec[i], 0) >= 2: continue
            seen[sec[i]] = seen.get(sec[i], 0) + 1; out.append(i)
    return out
for lab, a, b in ERAS + [('1997-2026', t0, T)]:
    print('---', lab)
    for k, nm in [('actuel', 'actuel (volumes, moyenne 10 sem., note)'), ('beta_tri', 'bêta > 1,3 après, à volumes et moyenne égaux'), ('beta_avant', 'bêta > 1,3 toujours en dernier'), ('beta_rang', 'bêta le plus faible au lieu de la note')]:
        s_, m_, ir, bw = simulate(lambda t, k=k: pick_with(t, k), a, b)
        print(f"  {nm:46s} {s_[0]*100:+6.1f} %/an  volatilité {s_[1]*100:3.0f} %  perte max {s_[2]*100:+5.0f} %  ratio {ir:5.2f}")
