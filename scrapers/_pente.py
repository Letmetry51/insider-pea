"""Pente des canaux et signaux de départ de hausse : test historique (5 ans catalogue ≥ 1 M€/j, 8 ans > 500 M€)."""
import json, glob, numpy as np
def load_cat():
    ser=[];names=[];dates=None
    for f in glob.glob('data/societes/*.json'):
        s=json.load(open(f)); dates=s['wDates']
        for k,x in s['items'].items():
            w=x.get('w') or []
            if len(w)==len(dates) and (x.get('turnoverEur') or 0)>=1e6:
                ser.append([v if v else np.nan for v in w]); names.append(k)
    return dates,names,np.array(ser,float)
def load_8y():
    import pandas as pd
    W=pd.read_csv('data/sectors/weekly.csv.gz',index_col=0,parse_dates=True,compression='gzip').sort_index()
    uni=json.load(open('data/sectors/universe.json'))['items']
    cols=[c for c in W.columns if c in uni and W[c].notna().sum()>=120]
    return [str(d.date()) for d in W.index],cols,W[cols].values.T.astype(float)
def run(dates,names,P,label):
    P=np.where(P>0,P,np.nan)
    jr=P[:,1:]/P[:,:-1]
    bad=(np.nanmax(jr,1)>2.5)|(np.nanmin(jr,1)<0.35)
    P=P[~bad]; N,T=P.shape
    print(f"\n=== {label} : {N} sociétés ({bad.sum()} écartées pour sauts suspects), {T} semaines {dates[0]} → {dates[-1]}")
    L=np.log(P)
    def sma(k):
        out=np.full_like(P,np.nan)
        for t in range(k-1,T): out[:,t]=np.nanmean(P[:,t-k+1:t+1],1)
        return out
    m10,m40=sma(10),sma(40)
    trend=(m10>m40)&(P>m40)
    mom=np.full_like(P,np.nan); mom[:,52:]=P[:,48:-4]/P[:,:-52]-1
    hi=np.full_like(P,np.nan); lo=np.full_like(P,np.nan)
    for t in range(51,T): hi[:,t]=np.nanmax(P[:,t-51:t+1],1); lo[:,t]=np.nanmin(P[:,t-51:t+1],1)
    ratio=P/hi
    W=26; x=np.arange(W)-(W-1)/2; sl=np.full_like(P,np.nan); r2=np.full_like(P,np.nan)
    for t in range(W-1,T):
        y=L[:,t-W+1:t+1]; ym=np.nanmean(y,1,keepdims=True); b=np.nansum((y-ym)*x,1)/(x*x).sum()
        res=y-ym-b[:,None]*x; r2[:,t]=1-np.nansum(res**2,1)/np.nansum((y-ym)**2,1); sl[:,t]=np.exp(b*52)-1
    def fwd(h):
        f=np.full_like(P,np.nan); f[:,:-h]=P[:,h:]/P[:,:-h]-1
        for t in range(T):
            v=f[:,t]; ok=np.isfinite(v)
            if ok.sum()>30: a,b_=np.percentile(v[ok],[2,98]); f[ok,t]=np.clip(v[ok],a,b_)
        return f
    F={h:fwd(h) for h in (13,26)}
    def pct(a):
        r=np.full_like(a,np.nan)
        for t in range(T):
            v=a[:,t]; ok=np.isfinite(v)
            if ok.sum()>30: r[ok,t]=v[ok].argsort().argsort()/(ok.sum()-1)
        return r
    valid=np.isfinite(mom)&np.isfinite(sl)
    mp=pct(np.where(valid,mom,np.nan)); slp=pct(np.where(valid&trend,sl,np.nan)); qp=pct(np.where(valid&trend,sl*np.clip(r2,0,1),np.nan))
    rl=np.full_like(P,np.nan); rl[:,26:]=ratio[:,:-26]
    brk=valid&(ratio>=0.999)&(rl<0.75)
    rec=np.zeros_like(brk)
    for t in range(T): rec[:,t]=np.any(brk[:,max(0,t-8):t+1],1)
    t4=np.zeros_like(trend); t4[:,4:]=trend[:,4:]&~trend[:,:-4]
    top=valid&(mp>=2/3)&trend
    # pente absolue (classes fixes) parmi tendance
    G={
     'classement (momentum tiers haut + tendance)': top,
     'tendance : pente forte (tiers haut des tendances)': valid&trend&(slp>=2/3),
     'tendance : pente moyenne': valid&trend&(slp>=1/3)&(slp<2/3),
     'tendance : pente légère (tiers bas)': valid&trend&(slp<1/3),
     'tendance : régularité forte (pente×R²)': valid&trend&(qp>=2/3),
     'tendance : régularité faible': valid&trend&(qp<1/3),
     'classement + pente forte': top&(slp>=2/3),
     'classement + pente moyenne/légère': top&(slp<2/3),
     'canal ≥ +100 %/an': valid&trend&(sl>=1.0),
     'canal +30 à +100 %/an': valid&trend&(sl>=0.3)&(sl<1.0),
     'canal +0 à +30 %/an': valid&trend&(sl>=0)&(sl<0.3),
     'réveil : tendance haussière depuis < 4 sem': valid&t4,
     'cassure du plus-haut 52 s après base (<75 % il y a 6 mois)': brk,
     'cassure après base < 8 sem, toujours en tendance': rec&trend,
     'classement + cassure récente': top&rec,
     'classement sans cassure récente': top&~rec,
     'creux : 12 m négatif, sous MM40': valid&(mom<0)&(P<m40),
    }
    mid=(52+T)//2
    print(f"{'groupe':60s} {'13 s':>14s} {'26 s':>14s} {'26 s 1re/2e moitié':>20s} {'%sem+':>6s} {'taille':>6s}")
    for g,M in G.items():
        cols=[]
        for h,rng in ((13,(52,T)),(26,(52,T)),(26,(52,mid)),(26,(mid,T))):
            ex=[]
            for t in range(rng[0],min(rng[1],T-h)):
                ok=valid[:,t]&np.isfinite(F[h][:,t]); m=M[:,t]&ok
                if m.sum()>=3: ex.append(F[h][m,t].mean()-F[h][ok,t].mean())
            ex=np.array(ex)
            cols.append((ex.mean(),ex.mean()/ex.std()*np.sqrt(len(ex))/np.sqrt(h) if len(ex)>5 else np.nan,(ex>0).mean() if len(ex) else np.nan))
        sz=np.nanmean([M[:,t].sum() for t in range(52,T)])
        print(f"{g:60s} {cols[0][0]*100:+6.1f}% t{cols[0][1]:4.1f} {cols[1][0]*100:+6.1f}% t{cols[1][1]:4.1f} {cols[2][0]*100:+8.1f}% /{cols[3][0]*100:+6.1f}% {cols[1][2]*100:5.0f}% {sz:6.0f}")
if __name__=='__main__':
    run(*load_cat(),'5 ans, catalogue liquide')
    try: run(*load_8y(),'8 ans, sociétés > 500 M€')
    except Exception as e: print('8 ans indisponible',e)
