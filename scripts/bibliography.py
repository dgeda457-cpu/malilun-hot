"""Factual bibliography, issue accounting and conservative record normalization.

Publisher TOCs only. No database scraping, abstracts, full text, OCR inference,
login or paid APIs. Reviewed image TOCs require exact image hashes to refresh.
"""
import copy,hashlib,re,unicodedata
from collections import Counter
from urllib.parse import urlsplit,urljoin
from bs4 import BeautifulSoup

TIERS={'马克思主义研究':1,'马克思主义与现实':1,'马克思主义理论学科研究':1,
       '思想理论教育':2,'思想理论教育导刊':2,'社会主义研究':2,'中共党史研究':2,
       '思想教育研究':2,'思想政治教育研究':2,'科学社会主义':2}
SOURCE_IDS={'马克思主义研究':'mkszy','马克思主义与现实':'reality','马克思主义理论学科研究':'mlky','思想理论教育导刊':'gxsj','中共党史研究':'history'}
def norm(s):return ''.join(c.lower()for c in unicodedata.normalize('NFKC',s or '')if unicodedata.category(c)[0]not in 'PZC')
def authors(value):
    raw=value if isinstance(value,list)else re.split(r'[、,，;；和\s]+',value or '')
    out=[]
    for a in raw:
        for suffix in sorted(['副教授','教授','讲师','博士研究生','硕士研究生','研究员','博士','老师'],key=len,reverse=True):a=a.replace(suffix,'')
        a=a.strip()
        if a and a not in out:out.append(a)
    return out
def keywords(values):
    """Reject prose rather than guessing keywords from an abstract/body."""
    if isinstance(values,str):values=re.split('[;；]',values)
    out=[]
    for k in values or []:
        k=k.strip().strip(';,；， ')
        if not 2<=len(k)<=24 or re.search(r'[。!?！？\n]|^(?:摘要|Abstract|KeyWords|关键词)\s*[:：]|基金项目|一[、.]|二[、.]|20\d{2}年',k,re.I):continue
        if k not in out:out.append(k)
    return out[:12]
def work_key(x):
    doi=(x.get('doi')or'').lower().removeprefix('https://doi.org/').strip()
    if doi:return 'doi:'+doi
    return '|'.join([norm(x.get('title')),norm(x.get('journal')),str(x.get('issue_year')or''),str(x.get('issue_number')or'')])
def normalize(x):
    x=copy.deepcopy(x);x['authors']=authors(x.get('authors',[]))
    old=x.get('keywords',[]);x['keywords']=keywords(old)
    if x['keywords']!=old:x['keyword_note']='疑似正文或过长词项已排除；未从摘要补造关键词。'
    if x.get('kind')in ('paper','book'):
        x['journal_tier']=TIERS.get(x.get('journal'),3)
        x['source_kind']=x.get('source_kind')or('academy_report'if x.get('source_id')in ['snnu','ccnu']else'publisher')
        x['work_id']=hashlib.sha256(work_key(x).encode()).hexdigest()[:16]
        x.setdefault('network_first_date',None);x.setdefault('reprints',[])
        # Publication, web, reprint and discovery timestamps never substitute.
        x['date_precision']='day'if x.get('publication_date')else'issue'if x.get('issue_year')and x.get('issue_number')else'unknown'
    x['collected_at']=x.get('collected_at')or x.get('first_seen')
    return x
def match_work(a,b):
    if a.get('kind')!=b.get('kind')or norm(a.get('title'))!=norm(b.get('title')):return False
    if a.get('kind')not in ('paper','book'):return (a.get('event_date')or a.get('web_date'))==(b.get('event_date')or b.get('web_date'))
    if a.get('doi')and b.get('doi')and a['doi'].lower()!=b['doi'].lower():return False
    for k in ['journal','issue_year','issue_number']:
        if a.get(k)and b.get(k)and norm(str(a[k]))!=norm(str(b[k])):return False
    return not(a.get('authors')and b.get('authors')and not set(a['authors'])&set(b['authors']))

def toc_rows(html,url):
    soup=BeautifulSoup(html,'html.parser');rows=[]
    if '.cbpt.'in url:
        for h in soup.select('h3'):
            a=h.find('a',href=True)
            if not a or '/paper/'not in a['href']:continue
            au=h.parent.find('span',recursive=False)
            rows.append({'title':a.get_text(' ',strip=True),'authors':authors(au.get_text(' ',strip=True)if au else''),'url':urljoin(url,a['href'])})
    elif 'ajcass.com'in url:
        for a in soup.select('a[href*="/Magazine/Show/"]'):
            sp=a.parent.find('span');txt=sp.get_text(' ',strip=True)if sp else''
            m=re.search(r'作者：(.*?)\s*（(\d+)）',txt)
            if m:rows.append({'title':a.get_text(' ',strip=True),'authors':authors(m.group(1)),'page_start':int(m.group(2)),'url':urljoin(url,a['href'])})
    return rows

def collect_issues(specs,fetcher,stamp,previous=None,force=False):
    """Recheck factual reviewed targets. Manual image transcription is explicit.

    No scheduled image recognition. Unchanged manually reviewed image hashes
    can confirm the old transcription, never discover an unseen new issue.
    """
    incoming=[];states=[];previous=previous or[]
    for spec in sorted(specs,key=lambda s:(s['tier'],s['journal'],s['year'],s['issue'])):
        old=next((s for s in previous if(s['journal'],s['year'],s['issue'])==(spec['journal'],spec['year'],spec['issue'])),{})
        state={k:spec[k]for k in ['journal','year','issue','tier','toc_url','mode']}
        state['spec_digest']=hashlib.sha256(__import__('json').dumps(spec,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        state.update(expected_count=sum(e['included']for e in spec['entries']),toc_count=len(spec['entries']),excluded=[{'title':e['title'],'reason':e.get('excluded_reason')}for e in spec['entries']if not e['included']],attempted_at=stamp,checked_at=old.get('checked_at'),errors=[],evidence=[])
        try:
            observed=[]
            # Reuse a recently checked, unchanged reviewed issue; don't re-download images twice daily.
            from datetime import datetime,timedelta
            recent=not force and old.get('spec_digest')==state['spec_digest']and old.get('checked_at')and datetime.fromisoformat(stamp)-datetime.fromisoformat(old['checked_at'])<timedelta(days=7)
            if recent:state['evidence']=old.get('evidence',[])
            else:
                for check in spec['checks']:
                    u=check['url']
                    if spec['mode']=='reviewed_images':
                        raw=fetcher.get(u,binary=True);digest=hashlib.sha256(raw).hexdigest()
                        if digest!=check['sha256']:raise ValueError('目录图片已变化，需重新逐篇核验，不自动识别或猜测')
                    else:
                        html=fetcher.get(u,cache_hours=0);observed+=toc_rows(html,u);digest=next(e.get('sha256')for e in reversed(fetcher.events)if e['url']==u)
                    state['evidence'].append({'url':u,'sha256':digest,'checked_at':stamp})
                if spec['mode']=='html':
                    bytitle={norm(r['title']):r for r in observed}
                    if set(bytitle)!={norm(e['title'])for e in spec['entries']}:raise ValueError('完整目录与已核验期次不一致；保留已有记录，待查漏')
                    for e in spec['entries']:
                        if {norm(a)for a in bytitle[norm(e['title'])]['authors']}!={norm(a)for a in e['authors']}:raise ValueError('目录作者变化，需核对：'+e['title'])
                state['checked_at']=stamp
            state['status']='verified'
            for e in spec['entries']:
                if not e['included']:continue
                item={'title':e['title'],'authors':e['authors'],'journal':spec['journal'],'issue_year':spec['year'],'issue_number':spec['issue'],'kind':'paper','url':e['url'],'publication_date':e.get('publication_date'),'web_date':None,'network_first_date':None,'doi':None,'keywords':[],'abstract_excerpt':None,'evidence_level':'metadata','source_kind':'publisher_toc','source_id':SOURCE_IDS[spec['journal']],'source_name':spec['journal'],'pages':e.get('pages'),'page_start':e.get('page_start'),'first_seen':stamp,'last_verified':state['checked_at'],'collected_at':stamp,'verified_urls':list(dict.fromkeys([e['url'],spec['toc_url']])),'observations':[{'url':spec['toc_url'],'role':'publisher_toc','checked_at':state['checked_at'],'method':'目录图目读转录及原图SHA复核'if spec['mode']=='reviewed_images'else'完整HTML目录逐篇题名作者核对','evidence':state['evidence']}],'verification':'题录已核实','verification_note':'已核对正式期次目录的题名、作者、年期；未读取论文全文。字段缺失留空。','date_note':'目录明确标出的出版日；不使用网页日或采集日补填'if e.get('publication_date')else'已核实年期，精确出版日未知；不计入按日时间窗。','reprints':[]}
                item=normalize(item);item['id']=hashlib.sha256(('paper:'+norm(item['title'])).encode()).hexdigest()[:16]
                incoming.append(item)
        except Exception as exc:
            state['status']='needs_review';state['errors'].append(str(exc))
        states.append(state)
    return incoming,states

def issue_coverage(specs,items,states):
    out=[]
    for s in specs:
        rows=[]
        for e in s['entries']:
            if not e['included']:continue
            matches=[x for x in items if x['kind']=='paper'and norm(x['title'])==norm(e['title'])and norm(x.get('journal'))==norm(s['journal'])and x.get('issue_year')==s['year']and x.get('issue_number')==s['issue']]
            x=matches[0]if matches else None
            rows.append({'title':e['title'],'url':e['url'],'item_id':x['id']if x else None,'missing_reason':None if x else'本轮未取得通过目录核验的题录，或目录/访问发生变化','fields':{k:bool(x and x.get(k))for k in ['authors','pages','page_start','publication_date','web_date','doi','keywords','abstract_excerpt']}})
        state=next((t for t in states if(t['journal'],t['year'],t['issue'])==(s['journal'],s['year'],s['issue'])),{})
        out.append({'journal':s['journal'],'tier':s['tier'],'year':s['year'],'issue':s['issue'],'toc_url':s['toc_url'],'expected':len(rows),'collected':sum(bool(r['item_id'])for r in rows),'missing':sum(not r['item_id']for r in rows),'checked_at':state.get('checked_at'),'attempted_at':state.get('attempted_at'),'status':state.get('status','not_checked'),'errors':state.get('errors',[]),'excluded':state.get('excluded',[]),'entries':rows,'scope_note':s['scope_note']})
    return out
