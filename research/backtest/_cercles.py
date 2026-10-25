"""Les 4 sociétés montrées le 25/10/2026 (Wallenius Wilhelmsen, Repsol, Bravida, JCDecaux) : semaine par semaine sur un an,
cours, hausse sur 12 mois et son rang, pente, tendance, moyenne 10 semaines, volumes, et passage des règles 🎯."""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
cols = list(z['cols'])
hi13p = shift(roll(P, 13, np.nanmax), 1)
for sym, name in [('WAWI.OL', 'Wallenius Wilhelmsen'), ('REP.MC', 'Repsol'), ('BRAV.ST', 'Bravida'), ('DEC.PA', 'JCDecaux')]:
    i = cols.index(sym)
    print(f"\n=== {name} ({sym})")
    print("  semaine     cours  12m(%) rang  pente  tend  /MM10  vol×  /haut52  🎯  raisons")
    first = None
    for t in range(T - 56, T):
        def f(a, k=0):
            v = a[i, t]
            return v if np.isfinite(v) else np.nan
        why = []
        if not valid[i, t]: why.append('données')
        if not (mp[i, t] >= 2/3): why.append('rang<2/3')
        if not trend[i, t]: why.append('tendance')
        if not (s26[i, t] >= .41): why.append('pente<41%')
        if not (mom[i, t] >= .6): why.append('12m<60%')
        if mom[i, t] > 2: why.append('12m>200%')
        if v52[i, t] >= .8: why.append('⚡')
        if not (P[i, t] >= m10[i, t]): why.append('⏸️ sous MM10')
        q = bool(Q[i, t])
        if q and first is None: first = dates[t]
        brk = P[i, t] > hi13p[i, t]
        print(f"  {dates[t]}  {P[i,t]:7.2f}  {mom[i,t]*100:6.0f}  {mp[i,t]:4.2f}  {s26[i,t]*100:5.0f}  {'oui' if trend[i,t] else 'non':4s} {(P[i,t]/m10[i,t]-1)*100:+5.1f}  {vx[i,t]:4.1f}  {dd52[i,t]*100:+6.1f}  {'🎯' if q else '  '}  {'' if q else ', '.join(why)}{'  ↑ plus haut 13 sem.' if brk else ''}")
    print(f"  première semaine 🎯 sur la période : {first}")
