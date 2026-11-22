"""Suite de audit_yahoo_eodhd.py (22/11/2026) : cause de chaque écart notable entre Yahoo et EODHD. Pour chaque société signalée, les
dates où le rapport des cours (Yahoo / EODHD, ajustés) change d'un coup, avec ce qu'EODHD enregistre autour (division ou
opération sur le capital, dividende et son rendement) : dividende pas encore ajusté par Yahoo, augmentation de capital ou division
ignorée par Yahoo, ou erreur de données. Environ 120 appels ; n'imprime que des dates, des rapports et des rendements, jamais de
cours EODHD ; rien n'est écrit dans out/.
"""
import numpy as np
import pandas as pd

import audit_yahoo_eodhd as A
import survivant_eodhd as SE

log = SE.log
CAS = ('AVTX.AS ERA.PA BRIGHT.ST OET.OL ENH.OL BETS-B.ST DOFG.OL KESKOB.HE KCC.OL SOFF.OL PLGC.OL CYNCA.ST DVD.OL HUNT.OL FLOB.BR '
       'MPCES.OL LUOTEA.HE ELUX-B.ST GEOS.OL MHM.PA NAPA.OL KOG.OL WYLD.ST WLN.PA INTRUM.ST DUST.ST PROGEN.ST LXB.ST ALCPB.PA '
       'FLMNG.ST WTG.ST MOFAST.ST EMH.DE ALHYF.PA').split()


def events(q, thr):
    lq = np.log(q.dropna())
    d = lq.diff()
    big = d[d.abs() > thr]
    return [(t, float(np.exp(v))) for t, v in big.items()]


def near(lst, t, days=7):
    return [x for x in lst if abs((x[0] - t).days) <= days]


def main():
    if not SE.KEY:
        log("Secret EODHD_API_KEY absent.")
        return
    F, dD, wD = A.fiches()
    Dz = A.dossiers()
    for s in CAS:
        code, suf = s.rsplit('.', 1)
        ex = A.SUF.get(suf)
        _, E, err = A.fetch(f"{code}.{ex}")
        if E is None:
            log(f"\n{s} : {err}")
            continue
        sp, _ = SE.get(f"splits/{code}.{ex}", **{'from': '2021-10-01'})
        dv, _ = SE.get(f"div/{code}.{ex}", **{'from': '2021-10-01'})
        raw = E['close'].where(E['close'] > 0)
        SP = [(pd.Timestamp(z['date']), z.get('split')) for z in (sp or []) if isinstance(z, dict) and z.get('date')]
        DV = []
        for z in (dv or []):
            if isinstance(z, dict) and z.get('date'):
                t = pd.Timestamp(z['date'])
                prev = raw[raw.index < t]
                try:
                    v = float(z.get('value') or z.get('unadjustedValue') or 'nan')
                except (TypeError, ValueError):
                    v = np.nan
                DV.append((t, v / prev.iloc[-1] * 100 if len(prev) and np.isfinite(v) else np.nan))
        r = F.get(s)
        lines = []
        if r and r.get('d'):
            di = pd.DatetimeIndex(pd.to_datetime(dD))
            d = pd.Series([np.nan if v is None else float(v) for v in r['d']], index=di[:len(r['d'])])
            q = d / E['adjusted_close'].reindex(d.index)
            for t, f in events(q, .02)[-5:]:
                lines.append(f"séance {t.date()} : rapport ×{f:.3f}" + ''.join(f" ; division EODHD {x[0].date()} {x[1]}" for x in near(SP, t)) +
                             ''.join(f" ; dividende EODHD {x[0].date()} ({x[1]:.1f} %)" for x in near(DV, t)))
        if r and r.get('w'):
            wi = pd.DatetimeIndex(pd.to_datetime(wD[-len(r['w']):]))
            w = pd.Series([np.nan if v is None else float(v) for v in r['w']], index=wi)
            ew = E['adjusted_close'].resample('W-FRI').last().reindex(wi)
            for t, f in events(w / ew, .05)[-5:]:
                lines.append(f"semaine {t.date()} : rapport ×{f:.3f}" + ''.join(f" ; division EODHD {x[0].date()} {x[1]}" for x in near(SP, t, 10)) +
                             ''.join(f" ; dividende EODHD {x[0].date()} ({x[1]:.1f} %)" for x in near(DV, t, 10)))
            if len(w) >= 53:
                my = (w.iloc[-5] / w.iloc[-53] - 1) * 100
                me = (ew.iloc[-5] / ew.iloc[-53] - 1) * 100
                lines.append(f"hausse sur 52 semaines (décalée de 4) : Yahoo {my:+.0f} %, EODHD {me:+.0f} %")
        z = Dz.get(s)
        if z:
            ys = [x.get('date') for x in (z.get('splits') or []) if isinstance(x, dict)]
            last = (z.get('rows') or [[None]])[-1][0]
            lines.append(f"dossier d'initiés : divisions Yahoo {ys or 'aucune'} ; dernier cours Yahoo {last} ; dernier cours EODHD "
                         f"{raw.dropna().index[-1].date() if raw.notna().any() else '·'}")
        lines.append("divisions EODHD : " + (', '.join(f"{t.date()} {x}" for t, x in SP) or 'aucune'))
        log(f"\n{s} ({(r or z or {}).get('name')})\n  " + '\n  '.join(lines))
    log(f"\n{SE.calls[0]} appels")


if __name__ == '__main__':
    main()
