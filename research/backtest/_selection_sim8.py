"""« Et si l'on ne sélectionnait que les sociétés avec le drapeau ? » (03/11/2026). Portefeuille simulé 1998-2026 en 26 tranches
(une par semaine, gardée 6 mois, frais 0,3 % par sens) ; une tranche sans société reste en liquidités (0 %). Comparé à la sélection
actuelle (4 🎯 + 1 📣). Mesures : rendement annuel, écart avec le marché (moyenne des sociétés), pire baisse, part investie, nombre
de lignes tenues, années sans aucun 🚩."""
import numpy as np
exec(open('_selection_sim7.py').read().split("\nif __name__ == '__main__':")[0])
okp = okn & trend & ~(v52 >= .8) & (mpn >= 1/3) & (mom <= 2)          # filtres de la place 📣 connus dans l'historique
FB20 = (R0 | R1) & trend & flag(pole=.20)


def flag_only(M, k=4, n=5):
    W = ago_any(M, k)

    def f(t):
        idx = np.where(W[:, t] & okp[:, t])[0]
        idx = idx[np.lexsort((-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t])))]
        return idx[:n].tolist()
    return f


def flag_first(t, n=5):
    idx = np.where(FB3[:, t] & okp[:, t])[0]
    idx = idx[np.lexsort((-np.nan_to_num(s26[idx, t]), -np.nan_to_num(note[idx, t])))][:n].tolist()
    rest = [i for i in pick(t, n=n, reserve=1, bondCap=2) if i not in idx]
    return (idx + rest)[:n]


def sim_cash(f, a, b, hold=26, cost=.003):
    tr, R, M, inv, lines, picks = [], [], [], [], [], []
    for t in range(a, min(b, T - 1)):
        s = np.array(f(t), dtype=int)
        tr.append([t, s, np.ones(len(s)) / len(s) if len(s) else np.zeros(0)])
        if len(s):
            picks.append((t, s))
        tr = [x for x in tr if t - x[0] < hold]
        r, ni, held = 0.0, 0, set()
        for x in tr:
            if not len(x[1]):
                continue
            rr = retw[x[1], t + 1]
            r += (x[2] * rr).sum() - cost * 2 / hold
            x[2] = x[2] * (1 + rr)
            ni += 1
            held.update(x[1].tolist())
        R.append(r / hold); M.append(mkw[t + 1]); inv.append(ni / hold); lines.append(len(held))
    R, M = np.array(R), np.array(M)
    eq = np.cumprod(1 + R); em = np.cumprod(1 + M)
    c = eq[-1] ** (52 / len(R)) - 1; cm = em[-1] ** (52 / len(M)) - 1
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    y12 = (eq[52:] / eq[:-52] - 1).min() if len(eq) > 52 else np.nan
    ex = []
    for t, s in picks:
        if t + 26 >= T:
            continue
        F = P[:, t + 26] / P[:, t] - 1
        okk = okn[:, t] & fin(F)
        if okk.sum() < 30:
            continue
        lo_, hi_ = np.nanpercentile(F[okk], [2, 98]); Fc = np.clip(F, lo_, hi_)
        v = Fc[s][fin(Fc[s])]
        if len(v):
            ex.append(v.mean() - Fc[okk].mean())
    return dict(c=c, cm=cm, dd=dd, y12=y12, inv=np.mean(inv), lines=np.mean(lines), empty=np.mean(np.array(inv) == 0),
                ex=np.mean(ex) * 100 if ex else np.nan, R=R)


if __name__ == '__main__':
    print(f"{N} sociétés, {dates[t1997]} → {dates[-1]} ; tranches hebdomadaires gardées 6 mois, liquidités à 0 %")
    strat = [('sélection actuelle (4 🎯 + 1 📣)', lambda t: pick(t, n=5, reserve=1, bondCap=2)),
             ('🚩 seulement (drapeau dans les 4 semaines)', flag_only(FB, 4)),
             ('🚩 seulement, la semaine du bond', flag_only(FB, 1)),
             ('🚩 seulement, mât de +20 % (plus de cas)', flag_only(FB20, 4)),
             ('🚩 d\'abord, complété par la sélection actuelle', flag_first)]
    base = {}
    for lab, f in strat:
        print(f"\n  {lab}")
        for el, a, b in ERAS:
            r = sim_cash(f, a, b)
            if lab.startswith('sélection'):
                base[el] = r['R']
            d = r['R'] - base[el] if el in base and len(base[el]) == len(r['R']) else None
            dt = ''
            if d is not None and not lab.startswith('sélection'):
                blk = np.array([d[k:k + 26].sum() for k in range(0, len(d) - 25, 26)])
                dt = f" · écart avec l'actuelle {d.mean() * 52 * 100:+5.1f} pts/an (t {blk.mean() / (blk.std(ddof=1) / np.sqrt(len(blk))):4.1f})"
            print(f"    {el} {r['c'] * 100:+5.1f} %/an (marché {r['cm'] * 100:+4.1f}) · pire baisse {r['dd'] * 100:4.0f} % · pire année "
                  f"{r['y12'] * 100:4.0f} % · investi {r['inv'] * 100:3.0f} % · lignes {r['lines']:4.1f} · semaines sans rien {r['empty'] * 100:3.0f} %"
                  f" · 6 mois par choix {r['ex']:+5.1f}{dt}")
    F = FB & okp
    print("\n🚩 nouveaux par an (une fois par semestre et par société) :",
          {int(y): int(dedup(F, 26)[:, yr == y].sum()) for y in range(1998, 2027)})
