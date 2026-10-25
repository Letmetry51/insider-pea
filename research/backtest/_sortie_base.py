"""Les « moments » entourés le 25/10/2026 (Wallenius, Repsol, Bravida, JCDecaux) : une consolidation de quelques semaines près des
plus hauts, puis une sortie par le haut. Signal « sortie de base » testé sur 1997-2026 (toutes les sociétés, et dans le 🎯), et
calendrier des 4 sociétés : quand le 🎯 et ce signal se seraient allumés."""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
cols = list(z['cols'])
# rang sur 12 mois sans regarder la suite (pour le calendrier récent : valid exige le rendement à 6 mois, inconnu en fin de série)
okn = fin(mom) & fin(s26)
mpn = np.full_like(P, np.nan)
for t in range(T):
    ok = okn[:, t]
    if ok.sum() > 30:
        mpn[ok, t] = mom[ok, t].argsort().argsort() / (ok.sum() - 1)
Qn = okn & (mpn >= 2/3) & trend & (s26 >= .41) & (mom >= .6) & (mom <= 2) & ~(v52 >= .8)
volw = VO / shift(sma(VO, 10), 1)            # volume de la semaine / moyenne des 10 semaines précédentes
def base_break(L=10, depth=.20, near=.95):
    Hb = shift(roll(P, L, np.nanmax), 1); Lb = shift(roll(P, L, np.nanmin), 1)
    hi52p = shift(hi52, 1)
    base = (Lb >= Hb * (1 - depth)) & (Hb >= hi52p * near)          # consolidation près des plus hauts
    return base & (P > Hb)                                            # clôture au-dessus de la base
SB = {}
for L in (8, 13):
    for dp in (.15, .25):
        SB[(L, dp)] = base_break(L, dp)
up = (shift(P, 13) > shift(P, 39)) & trend                          # hausse avant la base, tendance de fond
print("=== 1. Sortie de base (consolidation près des plus hauts, puis clôture au-dessus) : écart avec la société moyenne à 6 mois")
line('🎯 (référence)', Q)
for (L, dp), M in SB.items():
    line(f'base {L} sem., profondeur ≤ {dp*100:.0f} %, tendance', valid & M & up)
B = SB[(13, .25)] & up
line('  base 13 sem. ≤ 25 % + volume de la semaine ×1,5', valid & B & (volw >= 1.5))
line('  … + 12 mois dans la moitié haute', valid & B & (mp >= .5))
line('  … + 12 mois dans le tiers haut', valid & B & (mp >= 2/3))
line('  … dans le 🎯 (filtres réunis)', B & Q)
line('  … hors 🎯 (pas encore qualifiée)', valid & B & ~Q & (mp >= .5))
compare('🎯 : sortie de base cette semaine / autres semaines 🎯', Q & B, Q & ~B)
print("\n  À 12 mois :")
for k, M in [('🎯 (référence)', Q), ('base 13 sem. ≤ 25 %, tendance', valid & B), ('  … + 12 mois moitié haute', valid & B & (mp >= .5)),
             ('  … hors 🎯', valid & B & ~Q & (mp >= .5))]:
    e, cr, bg, n = st(M, F=fut52)
    print(f"  {k:58s} {e:+5.1f} pts à 12 mois · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n} cas")
# 2. avance sur le 🎯 : signaux suivis d'une entrée 🎯 dans les 6 mois, semaines et hausse d'avance
Qentry = Q & ~bshift(ago_any(Q, 26), 1)
Bfirst = valid & B & (mp >= .5) & ~Q & ~bshift(ago_any(valid & B & (mp >= .5) & ~Q, 13), 1)
lead_w, lead_r, n_led = [], [], 0
for i in range(N):
    ts = np.where(Bfirst[i])[0]
    qs = np.where(Qentry[i])[0]
    for t in ts:
        nxt = qs[(qs > t) & (qs <= t + 26)]
        if len(nxt):
            n_led += 1; lead_w.append(nxt[0] - t); lead_r.append(P[i, nxt[0]] / P[i, t] - 1)
print(f"\n=== 2. Avance : {n_led} sorties de base hors 🎯 sur {int(Bfirst.sum())} suivies d'une entrée 🎯 dans les 6 mois "
      f"({n_led / max(Bfirst.sum(), 1) * 100:.0f} %) ; avance médiane {np.median(lead_w):.0f} semaines, hausse déjà faite à l'entrée 🎯 : "
      f"médiane {np.median(lead_r)*100:+.0f} %")
print("\n=== 3. Les 4 sociétés : 🎯 (rang calculé sans regarder la suite), feu vert ⏸️, sortie de base")
for sym, name in [('WAWI.OL', 'Wallenius Wilhelmsen'), ('REP.MC', 'Repsol'), ('BRAV.ST', 'Bravida'), ('DEC.PA', 'JCDecaux')]:
    i = cols.index(sym)
    ev = []
    for t in range(T - 56, T):
        q = Qn[i, t] and P[i, t] >= m10[i, t]
        wait = Qn[i, t] and not P[i, t] >= m10[i, t]
        b = bool(SB[(13, .25)][i, t] and up[i, t])
        tag = ('🎯' if q else '⏸️' if wait else '  ') + (' 📦 sortie de base' if b else '')
        if q or wait or b:
            ev.append(f"{dates[t]} {P[i,t]:7.2f} {tag} (12 m {mom[i,t]*100:+.0f} %, rang {mpn[i,t]:.2f}, pente {s26[i,t]*100:.0f} %)")
    print(f"\n  {name} :"); print('   ' + '\n   '.join(ev))
