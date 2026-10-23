"""Solidité de la « force du signal » (nombre de repères favorables) : en plus de 🔊 ? par période ? hors échantillon ? t de l'écart ;
et la hausse étirée (+60 % au-dessus de la moyenne 40 semaines) à volatilité égale."""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
hot = vx >= 1.5
d26 = P / roll(P, 26, np.nanmax) - 1
p52 = np.full_like(P, np.nan)
for t in range(T):
    ok = valid[:, t]
    if ok.sum() > 30:
        p52[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
m_sl, m_top, m_hi, m_rs = (s26 >= .8), (p52 >= .9), (d26 > -.02), (mans > shift(mans, 8))
marks = hot.astype(int) + m_sl.astype(int) + m_top.astype(int) + m_hi.astype(int) + m_rs.astype(int)
k4 = m_sl.astype(int) + m_top.astype(int) + m_hi.astype(int) + m_rs.astype(int)
print("=== Force : 4 ou 5 repères contre 0 à 2 (parmi les 🎯)")
compare('4-5 repères / 0-2', Q & (marks >= 4), Q & (marks <= 2))
print("\n=== Chaque repère seul (avec / sans, parmi les 🎯)")
for lab, M in [('🔊 volumes ×1,5', hot), ('pente ≥ +80 %/an', m_sl), ('12 mois dans les 10 % meilleurs', m_top), ('au plus haut de 6 mois', m_hi), ('force relative en hausse sur 8 sem.', m_rs)]:
    compare(lab + ' / sans', Q & M, Q & ~M)
print("\n=== Sans compter 🔊 : les 4 autres repères, avec 🔊 puis sans")
for h, lab in [(hot, 'avec 🔊'), (~hot, 'sans 🔊')]:
    for k in range(5):
        line(f'{lab}, {k} repère(s) sur 4', Q & h & (k4 == k))
    compare(f'{lab} : 3-4 repères / 0-1', Q & h & (k4 >= 3), Q & h & (k4 <= 1))
print("\n=== Part des fortes hausses (≥ +50 % en 6 mois) par période, selon le nombre de repères (sur 5)")
for k in range(6):
    s = []
    for l, a, b in E3:
        e, cr, bg, n = st(Q & (marks == k), a, b)
        s.append(f"{l} {bg:4.1f} % / chutes {cr:4.1f} % ({n})")
    print(f"  {k} repère(s) : " + ' · '.join(s))
print("\n=== À 12 mois")
for k in range(6):
    e, cr, bg, n = st(Q & (marks == k), F=fut52)
    print(f"  {k} repère(s) : {e:+5.1f} pts · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n}")
print("\n=== Hausse étirée (+60 % au-dessus de la moyenne 40 sem. / moins de +30 %), à volatilité comparable")
for lab, a, b in [('volatilité < 35 %/an', 0, .35), ('35 à 50 %', .35, .5), ('50 à 80 %', .5, .8)]:
    vb = (v52 >= a) & (v52 < b)
    compare(lab, Q & vb & (ext40 > .6), Q & vb & (ext40 < .3))
