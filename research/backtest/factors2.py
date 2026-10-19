import json,bisect,statistics as st,math,collections,sys
SP=sys.argv[1]
L=json.load(open('../../data/euro-signal-long.json'))['items']
E=json.load(open(SP+'/histevents.json'))
ser={i:v['w'] for i,v in L.items() if v.get('w') and len(v['w'])>60}
# insider buys in past 13 weeks (publication), by isin
A=json.load(open(SP+'/acc.json'))
buys=collections.defaultdict(list)
for e in E: buys[e['isin']].append(e['d'])
for i in buys: buys[i].sort()
H={'1 mois':4,'3 mois':13,'6 mois':26}
obs=collections.defaultdict(list)  # date -> list of (feat dict, fwd dict)
for i,w in ser.items():
    d=[x[0] for x in w]; p=[x[1] for x in w]
    for k in range(52,len(w)-4):
        if p[k]<=0 or p[k-52]<=0: continue
        ma40=sum(p[k-39:k+1])/40; ma10=sum(p[k-9:k+1])/10; hi52=max(p[k-51:k+1])
        rets=[p[j]/p[j-1]-1 for j in range(k-25,k+1) if p[j-1]>0]
        f={'trend':ma10>ma40 and p[k]>ma40,'mom':p[k-4]/p[k-52]-1,'nearHigh':p[k]/hi52>=0.9,'deep':p[k]/hi52<=0.6,
           'vol':st.pstdev(rets) if len(rets)>10 else None,'rev1m':p[k]/p[k-4]-1}
        b=buys.get(i,[]); lo=bisect.bisect_left(b,d[k-13] if k>=13 else '0'); hi_=bisect.bisect_right(b,d[k])
        f['ins']=hi_>lo
        lo4=bisect.bisect_left(b,d[k-1]); f['insNew']=hi_>lo4
        acc=None
        for a in A.get(i,[]):
            if a['from']<=d[k]: acc=a
        f['acc']=acc
        fw={}
        for h,n in H.items():
            if k+n<len(w): fw[h]=max(-.6,min(1.5,p[k+n]/p[k]-1))
        obs[d[k]].append((f,fw))
dates=sorted(dt for dt,v in obs.items() if len(v)>=100)
print('semaines',len(dates),dates[0],dates[-1],'titres',len(ser))
# ranks for mom and vol within date
for dt in dates:
    v=obs[dt]
    for key in ('mom','vol'):
        xs=sorted(x[0][key] for x in v if x[0][key] is not None)
        for f,_ in v:
            if f[key] is None: f[key+'T']=None; continue
            r=bisect.bisect_left(xs,f[key])/len(xs); f[key+'T']=0 if r<1/3 else 2 if r>=2/3 else 1
tests={'Achat de dirigeant publié dans la semaine':lambda f:f['insNew'],
 'Comptes solides (F-score ≥ 7, bénéficiaire)':lambda f:f['acc'] and f['acc']['key']=='good',
 'Comptes en dégradation (F-score ≤ 3)':lambda f:f['acc'] and f['acc']['key']=='bad',
 'Bilan en détresse (Altman confirmé)':lambda f:f['acc'] and f['acc']['alt']=='distress',
 'Dernier exercice en perte':lambda f:f['acc'] and f['acc']['loss'],
 'Dilution ≥ 10 % sur 3 ans':lambda f:f['acc'] and (f['acc']['dil'] or 0)>=10,
 'Tendance + comptes solides':lambda f:f['trend'] and f['acc'] and f['acc']['key']=='good',
 'Dirigeant + tendance + comptes solides':lambda f:f['ins'] and f['trend'] and f['acc'] and f['acc']['key']=='good',
 'Dirigeant + comptes solides':lambda f:f['ins'] and f['acc'] and f['acc']['key']=='good',
'Achat de dirigeant (publié < 3 mois)':lambda f:f['ins'],
 'Tendance haussière (MM50>MM200, cours>MM200)':lambda f:f['trend'],
 'Force relative 12-1 mois : tiers supérieur':lambda f:f['momT']==2,
 'Force relative 12-1 mois : tiers inférieur':lambda f:f['momT']==0,
 'Cours à moins de 10 % du plus haut 52 s':lambda f:f['nearHigh'],
 'Cours ≥ 40 % sous le plus haut 52 s':lambda f:f['deep'],
 'Volatilité : tiers le plus calme':lambda f:f['volT']==0,
 'Volatilité : tiers le plus agité':lambda f:f['volT']==2,
 'Dirigeant + tendance haussière':lambda f:f['ins'] and f['trend'],
 'Dirigeant + force relative tiers sup.':lambda f:f['ins'] and f['momT']==2,
 'Dirigeant sans tendance (cours en repli)':lambda f:f['ins'] and not f['trend'],
 'Dirigeant + ≥ 40 % sous le plus haut':lambda f:f['ins'] and f['deep'],
 'Tendance haussière SANS dirigeant':lambda f:(not f['ins']) and f['trend'],
}
for h,n in H.items():
    print('\n== à',h,': écart avec le titre moyen de l\'univers la même semaine')
    for name,fn in tests.items():
        diffs=[];allx=0;cnt=0;beat=0
        for dt in dates:
            v=[(f,fw[h]) for f,fw in obs[dt] if h in fw]
            if len(v)<100: continue
            m=sum(x for _,x in v)/len(v); g=[x-m for f,x in v if fn(f)]
            if not g: continue
            diffs.append(sum(g)/len(g)); cnt+=len(g); beat+=sum(1 for x in g if x>0)
        md=sum(diffs)/len(diffs); sd=st.pstdev(diffs)
        t=md/(sd/math.sqrt(len(diffs)))/math.sqrt(n) if sd else 0
        print(f"{name:46} {100*md:+5.1f} pts  bat {100*beat/cnt:3.0f}%  t≈{t:+.1f}  ({cnt} relevés, {len(diffs)} semaines)")
