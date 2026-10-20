"""Low-volume academic metadata collection. No login, proxy, full text or AI API.

Network evidence is private under evidence/http.jsonl; only bounded metadata goes public.
Python 3.11+, BeautifulSoup. All dates retain their semantic meaning.
"""
import argparse, hashlib, json, re, sys, time, unicodedata
import urllib.request, urllib.error, urllib.robotparser
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
UA='MalilunHOT/1.0 (public academic metadata index; daily; no full text)'
DATE_RE=r'(20\d{2})[年./-]\s*(\d{1,2})[月./-]\s*(\d{1,2})日?'
def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def read_json(path,default):
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else default
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8'); tmp.replace(path)
def clean(text): return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text or '')).strip()
def exact_date(text):
    m=re.search(DATE_RE,text or '')
    if m:
        try:return date(*map(int,m.groups())).isoformat()
        except ValueError: pass
    return None
def canonical(url):
    p=urlsplit(url); query=[(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_') and k not in ['from','spm']]
    return urlunsplit((p.scheme,p.netloc.lower(),p.path,urlencode(sorted(query)),''))
def title_key(title):
    title=re.sub(r'^[【\[]20\d{2}[.年]\d{1,2}[】\]]','',title)
    title=re.sub(r'^《[^》]+》[转载]*\s*[:：]\s*','',title)
    return re.sub(r'[^\w\u4e00-\u9fff]','',unicodedata.normalize('NFKC',title)).lower()
def sort_key(item):
    return (item.get('publication_date') or item.get('web_date') or '',item.get('issue_year') or 0,item.get('issue_number') or 0,item['id'])

class Fetcher:
    def __init__(self,evidence=True):
        self.last={};self.robots={};self.verified_at={};self.events=[];self.cache=ROOT/'.cache';self.cache.mkdir(exist_ok=True);self.evidence=evidence
    def get(self,url,cache_hours=0,robots=False):
        p=urlsplit(url)
        if p.scheme!='https': raise ValueError('仅采集HTTPS公开网页')
        host=p.netloc
        if not robots:
            policy=self.policy(url)
            if not policy['allowed']:raise PermissionError('robots禁止或无法确认可访问性: '+policy['status'])
            rp=policy.get('_parser')
            if rp and not rp.can_fetch(UA,url): raise PermissionError('robots禁止此路径')
        key=hashlib.sha256(url.encode()).hexdigest(); f=self.cache/(key+'.json')
        if cache_hours and f.exists() and time.time()-f.stat().st_mtime<cache_hours*3600:
            cached=read_json(f,{});self.verified_at[url]=cached['fetched_at']
            return cached['html']
        # Each host is strictly sequential, with at least 1.2 seconds between requests.
        delay=max(1.2,self.robots.get(host,{}).get('delay',0))
        time.sleep(max(0,delay-(time.monotonic()-self.last.get(host,0))))
        self.last[host]=time.monotonic()
        event={'url':url,'checked_at':now()}
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html,text/plain'})
            with urllib.request.urlopen(req,timeout=18) as r:
                if urlsplit(r.url).netloc!=host: raise ValueError('跨域跳转需人工核查后配置')
                raw=r.read(2_000_001)
                if len(raw)>2_000_000:raise ValueError('页面超出2MB限制')
                enc=r.headers.get_content_charset()
                if not enc:
                    m=re.search(br'charset=["\s]*([\w-]+)',raw[:5000],re.I);enc=m.group(1).decode() if m else 'utf-8'
                if enc.lower() in ('gb2312','gbk'):enc='gb18030'
                html=raw.decode(enc,errors='replace')
                event.update(status=r.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),final_url=r.url)
            if not robots:
                self.verified_at[url]=now();write_json(f,{'html':html,'url':url,'fetched_at':self.verified_at[url]})
            return html
        except Exception as e:
            event.update(status=getattr(e,'code',None),error=str(e)); raise
        finally:self.events.append(event)
    def policy(self,url):
        p=urlsplit(url);host=p.netloc
        if host in self.robots:return self.robots[host]
        result={'checked_at':now(),'url':f'{p.scheme}://{host}/robots.txt','allowed':True,'status':'not_checked'}
        try:
            txt=self.get(result['url'],robots=True)
            if re.search(r'(?im)^\s*(User-agent|Disallow|Allow)\s*:',txt):
                rp=urllib.robotparser.RobotFileParser();rp.parse(txt.splitlines());result.update(_parser=rp,allowed=rp.can_fetch(UA,url),status='parsed',delay=rp.crawl_delay(UA) or rp.crawl_delay('*') or 0)
            else:result.update(status='200_non_robots_response',note='响应不是有效robots指令；不是转载许可。仅低频公开元数据索引。')
        except urllib.error.HTTPError as e:
            result.update(status=str(e.code),allowed=e.code in (404,410))
        except Exception as e:result.update(status='unavailable',allowed=False,error=str(e))
        self.robots[host]=result
        return result

def article_links(soup,url,adapter):
    rows=[];seen=set()
    for a in soup.select('a[href]'):
        href=urljoin(url,a['href']);title=clean(a.get('title') or a.get_text(' ',strip=True))
        is_detail=('/paper/' in href if adapter=='cnki' else 'bencandy.php' in href if adapter=='socialism' else bool(re.search(r'/info/\d+/\d+\.htm',href)))
        if not is_detail or len(title)<6 or href in seen or urlsplit(href).netloc!=urlsplit(url).netloc:continue
        seen.add(href);rows.append((canonical(href),title))
    return rows

def parse_cnki(html,url,source):
    soup=BeautifulSoup(html,'html.parser');text=clean(soup.get_text(' ',strip=True))
    # Structural title/author selectors are checked against public CNKI publisher pages.
    title_node=soup.select_one('.paper-title, .paperTitle, .title h1, h1, .paper_tit')
    title=clean(title_node.get_text(' ',strip=True)) if title_node else ''
    # Fallback from publication information preceding the author affiliation.
    if not title or title=='马克思主义理论学科研究':
        marker=re.search(r'20\d{2},\s*\d{1,2},\s*v\.\d+\s+[\d-]+\s+(.+?)\s+\d+\.',text)
        if marker:
            candidate=marker.group(1); title=candidate.rsplit(' ',1)[0]
    # Bibliographic quote contains independently delineated title and author.
    quote=re.search(r'引用信息:\s*\[1\](.+?)\.\s*(.+?)\[J\]\.\s*([^,]+),(20\d{2}),.*?\((\d{1,2})\)',text)
    authors=[];journal=source['name'];year=issue=None
    if quote:
        authors=[clean(x) for x in re.split('[,;]',quote.group(1)) if clean(x)];title=quote.group(2).strip();journal=quote.group(3);year=int(quote.group(4));issue=int(quote.group(5))
    pub=re.search(r'出版时间[:：]\s*('+DATE_RE+r')',text)
    web=re.search(r'发布时间[:：]\s*('+DATE_RE+r')',text)
    abs_m=re.search(r'摘要[:：]\s*(.+?)\s*关键词[:：]',text)
    kw_m=re.search(r'关键词[:：]\s*(.+?)\s*Abstract',text)
    return {'title':title,'authors':authors,'journal':journal,'kind':'paper','publication_date':exact_date(pub.group(1)) if pub else None,'web_date':exact_date(web.group(1)) if web else None,'issue_year':year,'issue_number':issue,'abstract_excerpt':abs_m.group(1)[:120]+'…' if abs_m else None,'keywords':[clean(x) for x in re.split('[;；]',kw_m.group(1)) if clean(x)] if kw_m else [],'evidence_level':'abstract' if abs_m else 'metadata'}

def parse_vsb(html,url,source):
    soup=BeautifulSoup(html,'html.parser');meta=soup.select_one('meta[name="pageTitle"]')
    title=clean(meta['content']) if meta else clean(soup.title.get_text()).removesuffix('-马克思主义学院').lstrip('\ufeff ')
    content=soup.select_one('.v_news_content')
    body=clean(content.get_text(' ',strip=True)) if content else ''
    alltext=clean(soup.get_text(' ',strip=True));m=re.search(r'(?:发布时间|发布日期|时间|日期)[:：]\s*('+DATE_RE+r')',alltext)
    paper=bool(re.match(r'^《.+?》(?:转载)?[:：]',title))
    kind='paper' if paper else 'admission' if '博士' in title and any(w in title for w in ['招生','申请','考核','报名']) else 'call' if any(w in title for w in ['征文','征稿']) else 'event' if any(w in title for w in ['讲座','论坛','研讨','讲坛','沙龙','学术报告','大讲堂']) else None
    # Exclude lists of names, scores and results; these are not actionable admissions notices.
    if kind=='admission' and any(w in title for w in ['名单','成绩','补录','录取','材料的考生']):return None
    if not kind:return None
    journal=None;authors=[];year=issue=None;abstract=None
    if paper:
        mt=re.match(r'^《(.+?)》(?:转载)?[:：]\s*(.+)',title)
        journal,title=mt.groups()
        ym=re.search(r'《'+re.escape(journal)+r'》\s*(20\d{2})年\s*第?(\d{1,2})期',body)
        if ym:year,issue=map(int,ym.groups())
        am=re.search(r'我院(.{2,50}?)在《',body)
        if am:
            raw=am.group(1)
            for suffix in ['教授','副教授','讲师','博士研究生','博士','老师','硕士研究生','研究员']:raw=raw.replace(suffix,'')
            if not any(w in raw for w in ['论文','发表','教师','团队','近日']):authors=[x.strip() for x in re.split('[和、,]',raw) if 1<len(x.strip())<8]
        ab=re.search(r'摘要[:：]\s*(.+)',body)
        if ab:abstract=ab.group(1)[:120]+'…'
    event_date=None
    # No inference from report date or relative dates for events/deadlines.
    em=re.search(r'(?:活动时间|举办时间|报告时间|讲座时间)\s*[:：]\s*('+DATE_RE+r')',body)
    if em:event_date=exact_date(em.group(1))
    deadline=None;deadline_evidence=None
    dm=re.search(r'(?:报名截止(?:时间)?|截稿(?:日期|时间)?|投稿截止(?:时间)?)\s*[:：为]?\s*('+DATE_RE+r')',body)
    if dm:deadline=exact_date(dm.group(1));deadline_evidence=dm.group(0)
    return {'title':title,'authors':authors,'journal':journal,'kind':kind,'publication_date':None,'web_date':exact_date(m.group(1)) if m else None,'issue_year':year,'issue_number':issue,'abstract_excerpt':abstract,'evidence_level':'abstract' if abstract else 'metadata','keywords':[],'event_date':event_date,'deadline':deadline,'deadline_evidence':deadline_evidence,'enrollment_year':int(re.search(r'20\d{2}',title).group()) if kind=='admission' and re.search(r'20\d{2}',title) else None,'scope_0305':'学院公告；具体招生学科须以原文为准' if kind=='admission' else None}

def parse_socialism(html,url,source):
    soup=BeautifulSoup(html,'html.parser');text=clean(soup.get_text(' ',strip=True))
    h=soup.find(['h1','h2'])
    # Only accept an unambiguous article title with issue designation.
    candidates=[clean(n.get_text(' ',strip=True)) for n in soup.select('h1,h2,.main_title,.content_title,.title')]
    title=next((t for t in candidates if re.match(r'【20\d{2}\.\d+】',t)),None)
    if not title:return None
    issue=re.match(r'【(20\d{2})\.(\d+)】(.+)',title)
    about=soup.select_one('.top_about');about=clean(about.get_text(' ',strip=True)) if about else ''
    author=re.search(r'作者[:：]\s*(.+?)\s*【',about)
    body=soup.select_one('#read_tpc');body=clean(body.get_text(' ',strip=True)) if body else ''
    ab=re.search(r'【摘要】\s*(.+?)\s*【关键词】',body)
    kw=re.search(r'【关键词】\s*(.+?)(?:\s+20\d{2}年|\s+一[、,])',body)
    return {'title':issue.group(3).strip(),'authors':[clean(x) for x in re.split('[、,;；]|\\s+',author.group(1)) if clean(x)] if author else [],'journal':source['name'],'kind':'paper','publication_date':None,'web_date':exact_date(about),'issue_year':int(issue.group(1)),'issue_number':int(issue.group(2)),'abstract_excerpt':ab.group(1)[:120]+'…' if ab else None,'evidence_level':'abstract' if ab else 'metadata','keywords':[clean(x) for x in re.split('[;；]',kw.group(1)) if clean(x)] if kw else []}

def enrich(item,url,source,stamp):
    item.update(url=canonical(url),source_id=source['id'],source_name=source['name'],first_seen=stamp,last_verified=stamp,verified_urls=[canonical(url)])
    identity=item['kind']+':'+title_key(item['title'])
    if item['kind'] not in ('paper','book'):identity+=':'+str(item.get('event_date') or item.get('web_date') or url)
    item['id']=hashlib.sha256(identity.encode()).hexdigest()[:16]
    item['verification']='已核实' if item.get('publication_date') and item.get('authors') else '部分核实'
    item['verification_note']='原始网页及书目字段已读取。未核验论文全文；期刊/学院网页本身的声明不等于第三方事实核查。'
    item['date_note']='出版日期已由期刊详情页核实' if item.get('publication_date') else '原始网页未给出精确出版日；网页日期不作为论文出版日' if item['kind']=='paper' else '网页发布日期与活动日期分别记录；未明确字段留空'
    # Invalid future publication dates must not enter rankings.
    if item.get('publication_date') and item['publication_date']>datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        item['verification']='存在冲突';item['publication_date']=None;item['date_note']='原文日期晚于核验日，已排除近期关注统计'
    topics=read_json(ROOT/'config/topics.json',[])
    corpus=clean(' '.join([item['title'],item.get('abstract_excerpt') or '',' '.join(item.get('keywords',[]))]))
    item['topics']=[t['id'] for t in topics if any(k in corpus for k in t['keywords'])]
    item['topic_basis']='题名、公开摘要摘录和原文关键词的字面匹配，仅供检索'
    return item

def merge_items(previous,incoming):
    by_id={x['id']:dict(x) for x in previous};url_map={u:x['id'] for x in previous for u in x.get('verified_urls',[x['url']])}
    for item in incoming:
        key=url_map.get(item['url'],item['id']);old=by_id.get(key)
        if old:
            # A title match is conservative when both records provide conflicting author names.
            if old.get('authors') and item.get('authors') and not set(old['authors'])&set(item['authors']) and item['url'] not in old.get('verified_urls',[]):
                item['id']=hashlib.sha256((item['id']+'|'+','.join(item['authors'])).encode()).hexdigest()[:16];by_id[item['id']]=item;continue
            urls=list(dict.fromkeys(old.get('verified_urls',[old['url']])+item.get('verified_urls',[item['url']])))
            choose=item if (bool(item.get('publication_date')),bool(item.get('authors')),item['evidence_level']=='abstract')>=(bool(old.get('publication_date')),bool(old.get('authors')),old['evidence_level']=='abstract') else old
            merged={**choose,'id':key,'verified_urls':urls,'first_seen':min(old['first_seen'],item['first_seen']),'last_verified':max(old['last_verified'],item['last_verified'])}
            merged['topics']=list(dict.fromkeys(old.get('topics',[])+item.get('topics',[])))
            # Keep different claimed publication dates visible as a conflict and out of ranking.
            if old.get('publication_date') and item.get('publication_date') and old['publication_date']!=item['publication_date']:
                merged.update(verification='存在冲突',date_note='不同来源出版日期冲突，已排除排名',date_conflict=[old['publication_date'],item['publication_date']],publication_date=None)
            by_id[key]=merged
        else:by_id[key]=item
        url_map[item['url']]=key
    return sorted(by_id.values(),key=sort_key,reverse=True)

def collect_source(source,fetcher,stamp,force=False):
    status={'id':source['id'],'name':source['name'],'home':source['home'],'rights':source['rights'],'checked_at':stamp,'errors':[],'http_successes':0,'items':0,'fields':[]}
    items=[];links=[]
    if not source.get('enabled',True):status['status']='disabled';return [],status
    policy=fetcher.policy(source['home']);status['robots']={k:v for k,v in policy.items() if not k.startswith('_')}
    if not policy['allowed']:status['status']='blocked';return [],status
    for page in source['lists']:
        try:
            html=fetcher.get(page);status['http_successes']+=1
            links+=article_links(BeautifulSoup(html,'html.parser'),page,source['adapter'])
        except Exception as e:status['errors'].append({'url':page,'error':str(e)})
    links=list(dict.fromkeys(links))
    # Exclude administrative posts before requesting detail pages.
    if source['adapter']=='vsb':links=[(u,t) for u,t in links if re.match(r'^《.+?》(?:转载)?[:：]',t) or any(w in t for w in ['博士','论坛','讲座','讲坛','大讲堂','征文','征稿','研讨','沙龙'])]
    parser={'cnki':parse_cnki,'socialism':parse_socialism,'vsb':parse_vsb}[source['adapter']]
    for url,title in links[:source.get('max_items',15)]:
        try:
            html=fetcher.get(url,cache_hours=0 if force else 18);status['http_successes']+=1
            item=parser(html,url,source)
            if item and len(item['title'])>=6:
                item=enrich(item,url,source,stamp);item['last_verified']=fetcher.verified_at.get(url,stamp);item['first_seen']=min(stamp,item['last_verified'])
                items.append(item)
            else:status['errors'].append({'url':url,'error':'未提取到符合学术/招生范围的完整字段；未入库'})
        except Exception as e:
            status['errors'].append({'url':url,'error':str(e)})
            if getattr(e,'code',None) in (401,403,429):
                status['errors'].append({'url':source['home'],'error':'访问限制：停止本轮该来源详情请求，不重试或绕过'});break
    status['items']=len(items);status['status']='ok' if items and not status['errors'] else 'partial' if items or status['http_successes'] else 'failed'
    status['fields']=sorted({k for item in items for k,v in item.items() if v is not None and v!=[]})
    if items:status['last_success']=stamp
    return items,status

def run(source_runner=collect_source):
    parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true');parser.add_argument('--only',default='');args=parser.parse_args()
    stamp=now();fetcher=Fetcher();store=ROOT/'public/data/catalog.json';old=read_json(store,{'items':[],'sources':[],'runs':[]})
    items=[];statuses=[];old_status={s['id']:s for s in old.get('sources',[])}
    for source in read_json(ROOT/'config/sources.json',[]):
        if args.only and source['id'] not in args.only.split(','):
            if source['id'] in old_status:statuses.append(old_status[source['id']])
            continue
        try:batch,status=source_runner(source,fetcher,stamp,args.force)
        except Exception as e:batch=[];status={'id':source['id'],'name':source.get('name',source['id']),'home':source.get('home',''),'status':'failed','checked_at':stamp,'items':0,'errors':[{'error':str(e)}]}
        if not status.get('last_success'):status['last_success']=old_status.get(source['id'],{}).get('last_success')
        items+=batch;statuses.append(status)
        print(f"{source['id']}: {status['status']}, {len(batch)} 条")
    merged=merge_items(old.get('items',[]),items);fix=read_json(ROOT/'config/corrections.json',{})
    merged=[x for x in merged if not set(x.get('verified_urls',[x['url']]))&set(fix.get('exclude_urls',[]))]
    for item in merged:
        correction=fix.get('overrides',{}).get(item['url'])
        if correction and correction.get('correction_evidence'):item.update(correction)
    success=bool(items);new_ids={i['id'] for i in merged}-{i['id'] for i in old.get('items',[])}
    run_id=stamp.replace(':','-');run={'id':run_id,'at':stamp,'new_items':len(new_ids),'verified_items':len(items),'source_ok':sum(s['status']=='ok' for s in statuses),'source_partial':sum(s['status']=='partial' for s in statuses),'source_failed':sum(s['status'] in ['failed','blocked'] for s in statuses),'outcome':'success' if success else 'no_verified_content','environment':'GitHub Actions' if __import__('os').environ.get('GITHUB_ACTIONS') else 'local Windows/Python','cloud_verified':bool(__import__('os').environ.get('GITHUB_ACTIONS'))}
    catalog={'schema_version':1,'last_attempt':stamp,'last_success':stamp if success else old.get('last_success'),'items':merged,'sources':statuses,'runs':(old.get('runs',[])+[run])[-90:],'coverage_note':'仅反映本站监测范围；资讯数量不代表学术价值。'}
    write_json(store,catalog);write_json(ROOT/'evidence'/f'run-{run_id}.json',{'run':run,'sources':statuses,'http':fetcher.events,'sample':items[:4]})
    print(json.dumps({'total':len(merged),'new':len(new_ids),'last_success':catalog['last_success']},ensure_ascii=False))
    return catalog
if __name__=='__main__':run()
