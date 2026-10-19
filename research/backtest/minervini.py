import json,glob,statistics as st,math,collections
ser={};dates=None
for f in glob.glob('../../data/societes/*.json'):
    s=json.load(open(f)); dates=s['wDates']
    for k,x in s['items'].items():
        w=x.get('w') or []
        if len(w)==len(dates) and sum(1 for v in w if v)>=120: ser[k]=w
n=len(dates); H={'3 mois':13,'6 mois':26}
obs=collections.defaultdict(list)
def ma(p,t,L):
    v=[p[j] for j in range(t-L+1,t+1) if p[j]]
    return sum(v)/len(v) if len(v)>=L*0.8 else None
for k,p in ser.items():
    for t in range(56,n-1):
        if not p[t] or not p[t-4] or not p[t-52]: continue
        win=[v for v in p[t-51:t+1] if v]
        if len(win)<45: continue
        m10,m30,m40,m40b=ma(p,t,10),ma(p,t,30),ma(p,t,40),ma(p,t-4,40)
        if None in (m10,m30,m40,m40b): continue
        hi,lo=max(win),min(win); c=p[t]
        mom=p[t-4]/p[t-52]-1
        tmpl= c>m30 and c>m40 and m30>m40 and m40>m40b and m10>m30 and c>m10 and c>=1.3*lo and c>=0.75*hi
        fw={h:max(-.6,min(1.5,p[t+L]/c-1)) for h,L in H.items() if t+L<n and p[t+L]}
        obs[t].append(dict(mom=mom,ratio=c/hi,trend=m10>m40 and c>m40,tmpl=tmpl,nearlow=c<=1.15*lo,fw=fw))
for t,v in obs.items():
    ms=sorted(x['mom'] for x in v)
    for x in v:
        import bisect; x['mp']=bisect.bisect_left(ms,x['mom'])/len(ms)
        x['px']=30*x['mp']+20*max(0,min(1,(x['ratio']-.6)/.4))+(15 if x['trend'] else 0)
    cut=sorted(x['px'] for x in v)[int(len(v)*.8)]
    for x in v: x['top']=x['px']>=cut
G={'Notre partie « cours » : 20 % mieux notés':lambda x:x['top'],'Trend Template de Minervini (7 règles)':lambda x:x['tmpl'],
   'Les deux à la fois':lambda x:x['top'] and x['tmpl'],'Template SANS être dans nos 20 %':lambda x:x['tmpl'] and not x['top'],
   'À moins de 15 % du plus bas sur un an':lambda x:x['nearlow']}
for h,L in H.items():
    print('==',h)
    for g,f in G.items():
        diffs=[];cnt=0;beat=0
        for t,v in obs.items():
            a=[x for x in v if h in x['fw']]
            if len(a)<100: continue
            m=sum(x['fw'][h] for x in a)/len(a); s=[x['fw'][h]-m for x in a if f(x)]
            if not s: continue
            diffs.append(sum(s)/len(s)); cnt+=len(s); beat+=sum(1 for y in s if y>0)
        md=sum(diffs)/len(diffs); sd=st.pstdev(diffs); tt=md/(sd/math.sqrt(len(diffs)))/math.sqrt(L)
        print(f"{g:45} {100*md:+5.1f} pts  bat {100*beat/cnt:3.0f}%  t≈{tt:+.1f}  ({cnt} relevés)")
