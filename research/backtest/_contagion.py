"""Contagion dans un même métier (Foster 1981, Ramnath 2002) : quand une société bondit (📣 : semaine ≥ +8 % sur 3 fois le volume, ou
2 fois au plus haut de l'année), ses concurrentes du même métier (classement Yahoo « industry ») qui n'ont pas encore bondi font-elles
mieux ensuite ? Signal « avant » pour elles. Mesure par événement (une société au plus une fois par semestre, écart avec la moyenne).
Métier d'aujourd'hui appliqué à tout l'historique (approximation)."""
import numpy as np, json
exec(open('_longue_base2.py').read().split("if __name__ == '__main__':")[0])
cols = [str(c) for c in z['cols']]
IND = json.load(open('industries.json'))
codes = {}
ind = np.array([codes.setdefault(IND.get(c) or ('?' + c), len(codes)) for c in cols])
hi52p = shift(hi52, 1); gap52 = P / hi52p - 1
R0 = (r1 >= .08) & (vy >= 3); R1 = (r1 >= .08) & (vy >= 2) & (gap52 >= 0)
B = (R0 | R1) & fin(P)
B4 = ago_any(B, 4)
B8 = ago_any(B, 8)
cnt = np.zeros((len(codes), T))
for k in range(len(codes)):
    cnt[k] = B4[ind == k].sum(0)
size = np.bincount(ind, minlength=len(codes))
peer4 = cnt[ind] - B4                                     # concurrentes ayant bondi dans les 4 dernières semaines
npeer = (size[ind] - 1)[:, None] * np.ones((1, T))
base = valid & ~(mp < 1/3) & ~(v52 >= .8)
calm = ~B8                                                # la société elle-même n'a pas bondi depuis 8 semaines
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
first1 = (peer4 >= 1) & ~(shift(peer4, 1) >= 1)          # première semaine où une concurrente a bondi
S = {
    'une concurrente vient de bondir (≤ 4 sem.), elle pas encore': base & calm & (peer4 >= 1) & (npeer >= 2),
    '  … en tendance': base & calm & (peer4 >= 1) & (npeer >= 2) & trend,
    '  … en tendance, hors 🎯': base & calm & (peer4 >= 1) & (npeer >= 2) & trend & ~Q,
    '  … semaine même du bond de la concurrente': base & calm & first1 & (npeer >= 2) & trend & ~Q,
    'au moins 2 concurrentes ont bondi (≤ 4 sem.), en tendance, hors 🎯': base & calm & (peer4 >= 2) & (npeer >= 2) & trend & ~Q,
    'au moins 3 concurrentes': base & calm & (peer4 >= 3) & (npeer >= 3) & trend & ~Q,
    'au moins 25 % du métier a bondi (≥ 2 sociétés)': base & calm & (peer4 >= 2) & (peer4 >= .25 * npeer) & trend & ~Q,
    'contrôle : en tendance, hors 🎯, sans bond ni chez elle ni chez les concurrentes': base & calm & (peer4 == 0) & (npeer >= 2) & trend & ~Q,
}
if __name__ == '__main__':
    print(f"Données : {N} sociétés, {len(codes)} métiers, {dates[t0]} → {dates[-1]}")
    for h in (26, 52):
        print(f"\n=== à {h // 4.33:.0f} mois")
        ev('📣 la société qui bondit (référence)', base & B & trend & ~Q, h)
        for k, M in S.items():
            ev(k, M, h)
    print("\n=== suite : part qui bondit à son tour ou entre au 🎯 dans les 6 mois")
    ledB = np.zeros_like(B); ledQ = np.zeros_like(B)
    for k2 in range(1, 27):
        ledB |= blead(B, k2); ledQ |= blead(Qentry, k2)
    for k, M in S.items():
        F = dedup(M, 26); n = F.sum()
        print(f"  {k:62s} {n:6d} cas · bondit ensuite {(F & ledB).sum() / max(n, 1) * 100:3.0f} % · 🎯 ensuite {(F & ledQ).sum() / max(n, 1) * 100:3.0f} %")
