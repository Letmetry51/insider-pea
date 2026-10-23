"""Solidité, par période, de « ne pas vendre dans la panique » : positions 🎯 touchées (−15 % en 4 semaines) pendant une panique
générale ou un marché calme ; et sociétés seules à leur plus bas (marché calme)."""
import numpy as np
exec(open('_panique4.py').read().split('print("=== 🎯 selon')[0])
held = valid & ago_any(Q, 26)
hit = held & (P / shift(P, 4) - 1 <= -.15)
PAN = W(lambda t: lo_sh[t] >= .20)
YR = np.broadcast_to(yr, P.shape)
for lab, M in [('positions −15 % en 4 sem., panique générale', hit & PAN), ('positions −15 % en 4 sem., marché calme', hit & CALM)]:
    out = []
    for l, a, b in E3:
        mm = M.copy(); mm[:, :a] = False; mm[:, b:] = False
        out.append(f"{l} : 3 mois {np.nanmean(f13[mm])*100:+5.1f} %, écart 6 mois {st(mm, a, b)[0]:+5.1f} pts ({int(mm.sum())})")
    eps = sorted(set(dates[t][:7] for t in range(T) if M[:, t].any())) if 'panique' in lab else []
    print(f"  {lab:44s} " + ' · '.join(out))
    if eps:
        print('     mois concernés : ' + ', '.join(eps))
