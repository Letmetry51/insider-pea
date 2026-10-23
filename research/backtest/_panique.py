"""Les creux de 2025-2026 (avril 2025, mars-avril 2026) sont des paniques de tout le marché : part des sociétés à leur plus bas de l'année
(cours ≤ plus bas 52 semaines + 2 %, comme la « Psychologie du marché » de la page). Que s'est-il passé ensuite, 1997-2026 ?
Marché = moyenne des sociétés (équipondéré, variations écrêtées à −60 % / +150 % comme la page)."""
import numpy as np
exec(open('_depart.py').read().split('print(f"Données')[0])
okc = fin(P) & fin(lo52) & fin(m40)
lo_sh = np.array([((P[:, t] <= lo52[:, t] * 1.02) & okc[:, t]).sum() / max(okc[:, t].sum(), 1) for t in range(T)])
up_sh = np.array([(trend[:, t] & okc[:, t]).sum() / max(okc[:, t].sum(), 1) for t in range(T)])
ncs = okc.sum(0)


def mkt(t, h):
    if t + h >= T:
        return np.nan
    a, b = P[:, t], P[:, t + h]; ok = okc[:, t] & fin(b)
    return np.mean(np.clip(b[ok] / a[ok] - 1, -.6, 1.5)) if ok.sum() > 30 else np.nan


idx = np.cumprod(1 + np.nan_to_num(mk))   # indice équipondéré (moyenne des variations hebdomadaires)
ok_t = ncs >= 100
t1 = int(np.argmax(ok_t))
print(f"Semaines exploitables : {dates[t1]} → {dates[-1]} ({ok_t.sum()}) ; part au plus bas : médiane {np.median(lo_sh[ok_t])*100:.1f} %, "
      f"9e décile {np.percentile(lo_sh[ok_t], 90)*100:.1f} %")
for d in ['2025-04-04', '2025-04-11', '2025-04-18', '2025-05-02', '2026-03-20', '2026-03-27', '2026-04-03', '2026-04-17']:
    t = int(np.searchsorted(dates, d))
    if t < T:
        print(f"  {dates[t]} : {lo_sh[t]*100:4.1f} % au plus bas, {up_sh[t]*100:4.1f} % en tendance")


def episodes(sig, gap=13):
    ts = [t for t in range(T) if sig[t] and ok_t[t]]
    out, last = [], -999
    for t in ts:
        if t - last > gap:
            out.append(t)
        last = t
    return out


def report(lab, sig):
    ws = [t for t in range(T) if sig[t] and ok_t[t]]
    eps = episodes(sig)
    f = {h: np.array([mkt(t, h) for t in ws]) for h in (13, 26, 52)}
    base = {h: np.nanmean([mkt(t, h) for t in range(t1, T) if ok_t[t]]) for h in (13, 26, 52)}
    fe = {h: np.array([mkt(t, h) for t in eps]) for h in (26, 52)}
    # pire baisse supplémentaire de l'indice dans les 26 semaines suivant le 1er signal de chaque épisode
    dd = np.array([idx[t:t + 27].min() / idx[t] - 1 for t in eps if t + 26 < T])
    print(f"\n{lab} : {len(ws)} semaines, {len(eps)} épisodes")
    print("  marché ensuite (toutes les semaines du signal) : " + ' · '.join(
        f"{h} sem. {np.nanmean(f[h])*100:+5.1f} % (normal {base[h]*100:+5.1f} %, en hausse {np.nanmean(f[h] > 0)*100:3.0f} %)" for h in (13, 26, 52)))
    print(f"  par épisode (1re semaine) : 6 mois {np.nanmean(fe[26])*100:+5.1f} % (en hausse {np.nanmean(fe[26][fin(fe[26])] > 0)*100:3.0f} %), "
          f"12 mois {np.nanmean(fe[52])*100:+5.1f} % ; baisse supplémentaire médiane {np.median(dd)*100:+5.1f} %, pire {dd.min()*100:+5.1f} %")
    print("  épisodes : " + ', '.join(f"{dates[t][:7]} ({mkt(t, 26)*100:+.0f} %)" if fin(mkt(t, 26)) else f"{dates[t][:7]}" for t in eps))
    return ws


lo4 = np.array([lo_sh[max(0, t-3):t+1].max() for t in range(T)])     # pic de plus bas sur les 4 dernières semaines
lo8 = np.array([lo_sh[max(0, t-7):t+1].max() for t in range(T)])
S1 = report('Panique : ≥ 20 % des sociétés au plus bas de l\'année', lo_sh >= .20)
S2 = report('Panique forte : ≥ 25 %', lo_sh >= .25)
S3 = report('Panique puis reprise : ≥ 20 % au plus bas dans les 8 sem., ≤ 5 % aujourd\'hui', (lo8 >= .20) & (lo_sh <= .05))
S4 = report('Panique puis reprise, avec ≥ 15 %', (lo8 >= .15) & (lo_sh <= .05))
S5 = report('Repère de la page : 😟 pessimiste (tiers bas de la part en tendance, tout l\'historique)', up_sh < np.percentile(up_sh[ok_t], 100/3))

print("\n=== Quelles sociétés acheter à ces moments ? (écart avec la société moyenne, 6 mois)")
def only(ws):
    m = np.zeros(T, bool); m[ws] = True
    return np.broadcast_to(m, P.shape)
lead = valid & (mp >= 2/3)                       # tiers fort sur 12 mois
lag = valid & (mp <= 1/3)                         # tiers faible
for lab, ws in [('panique ≥ 20 %', S1), ('panique puis reprise', S3)]:
    W = only(ws)
    for k, M in [('🎯', Q), ('tiers fort sur 12 mois (meneuses)', lead), ('tiers faible sur 12 mois (les plus touchées)', lag),
                 ('creux −30 % puis rebond ≥ +25 % et 🔊 (creux en « V »)', valid & deep26 & (P >= roll(P, 13, np.nanmin) * 1.25) & (vx >= 1.5))]:
        e, cr, bg, n = st(M & W)
        e2 = st(M & W, F=fut52)
        print(f"  {lab:24s} {k:52s} {e:+5.1f} pts · chutes {cr:4.1f} % · ≥ +50 % {bg:4.1f} % · {n:5d} cas | 12 mois {e2[0]:+5.1f}")
