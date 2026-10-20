"""Anonymous HTTP production verification, explicitly not browser visual QA."""
import json,sys,urllib.request,hashlib
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
base='https://malilun-hot.fast-plum-3707.chatgpt.site'
targets=[base+'/',base+'/app.js',base+'/styles.css',base+'/data/catalog.json',base+'/data/briefs.json',base+'/feeds/all.xml','https://raw.githubusercontent.com/dgeda457-cpu/malilun-hot/main/public/data/site.json','https://raw.githubusercontent.com/dgeda457-cpu/malilun-hot/main/public/feeds/all.xml']
rows=[]
for url in targets:
    row={'url':url,'checked_at':datetime.now(timezone.utc).isoformat(),'authentication':'none'}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'MalilunHOT-production-verifier/1.0','Cache-Control':'no-cache'})
        with urllib.request.urlopen(req,timeout=25)as r:
            raw=r.read();row.update(status=r.status,final_url=r.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),content_type=r.headers.get('Content-Type'),cors=r.headers.get('Access-Control-Allow-Origin'),csp=r.headers.get('Content-Security-Policy'))
            assert r.status==200 and raw
            if url.endswith('.json'):
                d=json.loads(raw)
                if isinstance(d,dict):row.update(records=len(d.get('items',[])),cloud_run_verified=any(x.get('cloud_verified') and x.get('verified_items',0)>0 for x in d.get('runs',[])))
            if url==base+'/':assert '马理论'.encode() in raw
            if 'raw.githubusercontent' in url:assert row['cors']=='*'
    except Exception as e:row['error']=str(e)
    rows.append(row)
report={'verification':'anonymous HTTP only; no browser rendering or screenshot','at':datetime.now(timezone.utc).isoformat(),'checks':rows,'passed':sum(x.get('status')==200 and not x.get('error') for x in rows),'total':len(rows)}
(ROOT/'evidence/online-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
if report['passed']!=len(rows):sys.exit(1)
