import json,glob,numpy as np
ser=[];dates=None;names=[]
for f in glob.glob('../../data/societes/*.json'):
    s=json.load(open(f)); dates=s['wDates']
    for k,x in s['items'].items():
        w=x.get('w') or []
        if len(w)==len(dates) and (x.get('turnoverEur') or 0)>=1e6:
            ser.append([v if v else np.nan for v in w]); names.append(k)
P=np.array(ser,float)
jr=P[:,1:]/P[:,:-1]
bad=np.nanmax(jr,1)>2.5; bad|=np.nanmin(jr,1)<0.35
print('séries écartées (sauts suspects, splits non ajustés)',bad.sum())
P=P[~bad]; names=[n for n,b in zip(names,bad) if not b]; N,T=P.shape
print('sociétés',N,'semaines',T)
L=np.log(P)
def sma(k):
    out=np.full_like(P,np.nan)
    c=np.nancumsum(np.nan_to_num(P),axis=1)
    out[:,k-1:]=(c[:,k-1:]-np.concatenate([np.zeros((N,1)),c[:,:-k]],1))/k
    return out
m10,m40=sma(10),sma(40)
trend=(m10>m40)&(P>m40)
mom=np.full_like(P,np.nan); mom[:,52:]=P[:,48:-4]/P[:,:-52]-1
hi=np.full_like(P,np.nan); lo=np.full_like(P,np.nan)
for t in range(51,T): hi[:,t]=np.nanmax(P[:,t-51:t+1],1); lo[:,t]=np.nanmin(P[:,t-51:t+1],1)
ratio=P/hi; up_lo=P/lo
# pente régression 26 sem (log), R²
W=26; x=np.arange(W)-(W-1)/2; sl=np.full_like(P,np.nan); r2=np.full_like(P,np.nan)
for t in range(W-1,T):
    y=L[:,t-W+1:t+1]; ym=y.mean(1,keepdims=True); b=((y-ym)*x).sum(1)/(x*x).sum()
    res=y-ym-b[:,None]*x; r2[:,t]=1-(res**2).sum(1)/((y-ym)**2).sum(1); sl[:,t]=np.exp(b*52)-1
def fwd(h):
    f=np.full_like(P,np.nan); f[:,:-h]=P[:,h:]/P[:,:-h]-1
    for t in range(T):
        v=f[:,t]; ok=np.isfinite(v)
        if ok.sum()>30: lo_,hi_=np.percentile(v[ok],[2,98]); f[ok,t]=np.clip(v[ok],lo_,hi_)
    return f
F={h:fwd(h) for h in (13,26)}
def pct(a):  # rang par semaine
    r=np.full_like(a,np.nan)
    for t in range(T):
        v=a[:,t]; ok=np.isfinite(v)
        if ok.sum()>30: r[ok,t]=v[ok].argsort().argsort()/(ok.sum()-1)
    return r
mp=pct(mom); q=sl*np.clip(r2,0,1); qp=pct(q); slp=pct(sl)
trend4=np.zeros_like(trend); trend4[:,4:]=trend[:,4:]&~trend[:,:-4]
ratio26=np.full_like(P,np.nan); ratio26[:,26:]=ratio[:,:-26]
valid=np.isfinite(mom)
eligible=valid&(mp>=1/3)
G={
 'classement (mom tiers haut + tendance)': valid&(mp>=2/3)&trend,
 'tendance + pente FORTE (tiers haut)': valid&trend&(slp>=2/3),
 'tendance + pente MOYENNE': valid&trend&(slp>=1/3)&(slp<2/3),
 'tendance + pente FAIBLE (tiers bas)': valid&trend&(slp<1/3),
 'tendance + régularité forte (pente×R²)': valid&trend&(qp>=2/3),
 'tendance + régularité faible': valid&trend&(qp<1/3),
 'mom haut + pente forte': valid&(mp>=2/3)&trend&(slp>=2/3),
 'mom haut + pente faible/moy.': valid&(mp>=2/3)&trend&(slp<2/3),
 'réveil : tendance devenue haussière <4 sem': valid&trend4,
 'cassure plus-haut 52s après base (<75% il y a 6 mois)': valid&(ratio>=0.999)&(ratio26<0.75),
 'sortie de creux : +30% du plus-bas, 12m encore négatif': valid&(up_lo>=1.3)&(mom<0)&trend,
 'creux pur : 12m négatif, sous MM40': valid&(mom<0)&(P<m40),
}
print(f"{'groupe':58s} {'13s':>7s} {'t':>5s} {'26s':>7s} {'t':>5s} {'%sem+':>6s} {'taille':>6s}")
for g,M in G.items():
    row=[]
    for h in (13,26):
        ex=[]
        for t in range(52,T-h):
            ok=valid[:,t]&np.isfinite(F[h][:,t]); m=M[:,t]&ok
            if m.sum()>=5: ex.append(F[h][m,t].mean()-F[h][ok,t].mean())
        ex=np.array(ex); row.append((ex.mean(), ex.mean()/ex.std()*np.sqrt(len(ex))/np.sqrt(h), (ex>0).mean()))
    sz=np.nanmean([M[:,t].sum() for t in range(52,T)])
    print(f"{g:58s} {row[0][0]*100:+6.1f}% {row[0][1]:5.1f} {row[1][0]*100:+6.1f}% {row[1][1]:5.1f} {row[1][2]*100:5.0f}% {sz:6.0f}")
np.save('names.npy',np.array(names))
