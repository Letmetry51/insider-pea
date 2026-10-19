import json,glob,statistics as st,math,collections,bisect
ser={};dates=None
for f in glob.glob('../../data/societes/*.json'):
    s=json.load(open(f)); dates=s['wDates']
    for k,x in s['items'].items():
        w=x.get('w') or []
        if len(w)==len(dates) and sum(1 for v in w if v)>=120: ser[k]=w
n=len(dates); H={'3 mois':13,'6 mois':26}
def ma(p,t,L):
    v=[p[j] for j in range(t-L+1,t+1) if p[j]]
    return sum(v)/len(v) if len(v)>=L*0.8 else None
obs=collections.defaultdict(list)
for k,p in ser.items():
    for t in range(60,n-1):
        c=p[t]
        if not c or not p[t-4] or not p[t-52] or not p[t-13]: continue
        win=[v for v in p[t-51:t+1] if v]
        if len(win)<45: continue
        m10,m40=ma(p,t,10),ma(p,t,40); m10b,m40b=ma(p,t-8,10),ma(p,t-8,40)
        if None in (m10,m40,m10b,m40b): continue
        hi=max(win); prevhi=max([v for v in p[t-51:t] if v]); 
        # premier nouveau plus haut 52 s après au moins 26 semaines sans nouveau plus haut
        last_hi_k=None
        for j in range(t-1,t-52,-1):
            pj=p[j]
            if not pj: continue
            w2=[v for v in p[max(0,j-51):j+1] if v]
            if w2 and pj>=max(w2): last_hi_k=j; break
        fresh_high = c>=prevhi and (last_hi_k is None or t-last_hi_k>=26)
        x=dict(mom=p[t-4]/p[t-52]-1, r3=c/p[t-13]-1, ratio=c/hi, trend=m10>m40 and c>m40,
               cross=(m10>m40 and m10b<=m40b), fresh=fresh_high,
               fw={h:max(-.6,min(1.5,p[t+L]/c-1)) for h,L in H.items() if t+L<n and p[t+L]})
        obs[t].append(x)
# ampleur du marché par semaine
breadth={}
for t,v in obs.items():
    ms=sorted(x['mom'] for x in v); rs=sorted(x['r3'] for x in v)
    for x in v:
        x['mp']=bisect.bisect_left(ms,x['mom'])/len(ms); x['rp']=bisect.bisect_left(rs,x['r3'])/len(rs)
        x['px']=30*x['mp']+20*max(0,min(1,(x['ratio']-.6)/.4))+(15 if x['trend'] else 0)
    cut=sorted(x['px'] for x in v)[int(len(v)*.8)]
    for x in v: x['top']=x['px']>=cut
    breadth[t]=sum(1 for x in v if x['trend'])/len(v)
G={'Notre partie cours : 20 % mieux notés':lambda x:x['top'],
 'Croisement MM50/MM200 depuis moins de 2 mois':lambda x:x['cross'],
 'Premier plus haut annuel après 6 mois de base':lambda x:x['fresh'],
 'Accélération : tiers fort sur 3 mois, pas encore sur 12':lambda x:x['rp']>=2/3 and x['mp']<2/3,
 'Accélération ET tendance de fond haussière':lambda x:x['rp']>=2/3 and x['mp']<2/3 and x['trend'],
 'Croisement récent ET tiers fort sur 3 mois':lambda x:x['cross'] and x['rp']>=2/3}
def run(pred_week=lambda t:True,label=''):
    for h,L in H.items():
        print('==',h,label)
        for g,f in G.items():
            diffs=[];cnt=0;beat=0
            for t,v in obs.items():
                if not pred_week(t): continue
                a=[x for x in v if h in x['fw']]
                if len(a)<100: continue
                m=sum(x['fw'][h] for x in a)/len(a); s=[x['fw'][h]-m for x in a if f(x)]
                if not s: continue
                diffs.append(sum(s)/len(s)); cnt+=len(s); beat+=sum(1 for y in s if y>0)
            if len(diffs)<8: print(f"{g:55} trop peu"); continue
            md=sum(diffs)/len(diffs); sd=st.pstdev(diffs); tt=md/(sd/math.sqrt(len(diffs)))/math.sqrt(L)
            print(f"{g:55} {100*md:+5.1f} pts  bat {100*beat/cnt:3.0f}%  t≈{tt:+.1f}  ({cnt}, {len(diffs)} sem.)")
run()
bs=sorted(breadth.values()); lo,hi=bs[len(bs)//3],bs[2*len(bs)//3]
print('ampleur : tiers', round(lo,2), round(hi,2))
G={'Notre partie cours : 20 % mieux notés':G['Notre partie cours : 20 % mieux notés'],'Accélération ET tendance de fond haussière':G['Accélération ET tendance de fond haussière']}
run(lambda t:breadth[t]<lo,'marché faible (peu de sociétés au-dessus de MM200)')
run(lambda t:breadth[t]>hi,'marché large (beaucoup au-dessus de MM200)')
# rendement du titre moyen selon l'ampleur (psychologie du marché, niveau global)
for nm,pred in [('faible',lambda t:breadth[t]<lo),('moyen',lambda t:lo<=breadth[t]<=hi),('large',lambda t:breadth[t]>hi)]:
    r=[sum(x['fw']['6 mois'] for x in v if '6 mois' in x['fw'])/max(1,sum(1 for x in v if '6 mois' in x['fw'])) for t,v in obs.items() if pred(t) and any('6 mois' in x['fw'] for x in v)]
    print('titre moyen à 6 mois, marché',nm, round(100*sum(r)/len(r),1),'%', len(r),'semaines')
