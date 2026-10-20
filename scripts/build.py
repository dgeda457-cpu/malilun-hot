"""Reproducible static export, transparent rankings, source-based briefs and RSS."""
import html, json, shutil, sys
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from collections import Counter
from xml.etree import ElementTree as ET
from email.utils import format_datetime

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from collect import read_json,write_json,sort_key

RULE='成果数降序 → 独立出版机构/期刊数降序 → 最近出版日降序；仅计精确出版日可核实、去重后的论文/著作。会议与转载次数不计分。'
def in_window(item,days,today):
    value=item.get('publication_date')
    if not value or item.get('kind') not in ('paper','book') or item.get('verification')=='存在冲突':return False
    try:delta=(today-date.fromisoformat(value)).days
    except ValueError:return False
    return 0<=delta<days
def rankings(items,topics,today):
    out={}
    for days in (7,30,90):
        rows=[]
        for topic in topics:
            relevant=[x for x in items if topic['id'] in x.get('topics',[]) and in_window(x,days,today)]
            if not relevant:continue
            sources=sorted({x.get('journal') or x['source_name'] for x in relevant})
            rows.append({'topic_id':topic['id'],'name':topic['name'],'work_count':len(relevant),'source_count':len(sources),'sources':sources,'latest':max(x['publication_date'] for x in relevant),'item_ids':[x['id'] for x in relevant],'sparse':len(relevant)<3 or len(sources)<2})
        rows.sort(key=lambda x:(x['work_count'],x['source_count'],x['latest']),reverse=True)
        out[str(days)]=rows
    return out

def discover(items,topics):
    # Only literal author-supplied keywords; a new term needs two independent works.
    count=Counter(k for x in items for k in set(x.get('keywords',[])) if 3<=len(k)<=16)
    existing={k for t in topics for k in t['keywords']}
    return [{'keyword':k,'works':n,'item_ids':[x['id'] for x in items if k in x.get('keywords',[])]} for k,n in count.most_common(8) if n>=2 and k not in existing]

def rss(items,title,base):
    root=ET.Element('rss',version='2.0');channel=ET.SubElement(root,'channel')
    for tag,value in [('title',title),('link',base),('description','真实学术元数据索引；仅反映本站监测范围，不代表学术影响力。'),('language','zh-CN')]:ET.SubElement(channel,tag).text=value
    for x in items[:60]:
        entry=ET.SubElement(channel,'item');ET.SubElement(entry,'title').text=x['title'];ET.SubElement(entry,'link').text=x['url'];ET.SubElement(entry,'guid',isPermaLink='false').text=x['id'];ET.SubElement(entry,'source',url=x['url']).text=x['source_name']
        description=f"来源：{x['source_name']}；出版日期：{x.get('publication_date') or '未核实'}；网页日期：{x.get('web_date') or '未核实'}；{x['verification']}。"
        if x.get('abstract_excerpt'):description+=' 摘要摘录：'+x['abstract_excerpt']
        ET.SubElement(entry,'description').text=description
        if x.get('publication_date'):ET.SubElement(entry,'pubDate').text=format_datetime(datetime.fromisoformat(x['publication_date']).replace(tzinfo=timezone.utc))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def build():
    catalog=read_json(ROOT/'public/data/catalog.json',{'items':[],'sources':[],'runs':[],'last_success':None,'last_attempt':None})
    items=catalog['items'];topics=read_json(ROOT/'config/topics.json',[])
    # Windows may lack an IANA tz database; UTC is explicit, never silently use host time.
    latest=catalog.get('last_attempt') or datetime.now(timezone.utc).isoformat()
    today=datetime.fromisoformat(latest).date()
    for t in topics:
        t['count']=sum(t['id'] in x.get('topics',[]) for x in items)
        t['research_questions']=[{'title':x['title'],'item_id':x['id']} for x in items if t['id'] in x.get('topics',[]) and any(k in x['title'] for k in ['问题','何以','如何','何谓','何为'])][:5]
    payload={**catalog,'topics':topics,'rankings':rankings(items,topics,today),'ranking_rule':RULE,'ranking_as_of':today.isoformat(),'ranking_timezone':'UTC','discovered_keywords':discover(items,topics)}
    dist=ROOT/'dist';dist.mkdir(exist_ok=True)
    # Copy only known public files; evidence, configuration and credentials are never published.
    for name in ('index.html','styles.css','app.js','favicon.svg','robots.txt','_headers'):
        shutil.copyfile(ROOT/'public'/name,dist/name)
    write_json(dist/'data/catalog.json',payload)
    write_json(ROOT/'public/data/site.json',payload)
    briefs_dir=ROOT/'public/data/briefs';briefs_dir.mkdir(exist_ok=True)
    run=catalog.get('runs',[])[-1] if catalog.get('runs') else None
    if run and run.get('verified_items',0)>0:
        day=latest[:10]
        existing=read_json(briefs_dir/(day+'.json'),{'item_ids':[]})
        # First discovery is distinct from publication date. Initial import is marked.
        discovered=[x for x in items if x['first_seen'][:10]==day]
        report={'date':day,'timezone':'UTC','generated_at':latest,'title':'马理论日报','initial_import':len({r['at'][:10] for r in catalog['runs'] if r['verified_items']})==1,'item_ids':list(dict.fromkeys(existing['item_ids']+[x['id'] for x in discovered])),'note':'按本站首次发现时间编排，含历史文献首次收录；不将其称为当日发表成果。无新资料时明确显示空刊；全部来源失败时不生成新一期。','new_publications':[x['id'] for x in discovered if x.get('publication_date')==day],'ranking_90':payload['rankings']['90'][:5]}
        write_json(briefs_dir/(day+'.json'),report)
    briefs=[read_json(p,{}) for p in sorted(briefs_dir.glob('*.json'),reverse=True)][:90]
    write_json(dist/'data/briefs.json',briefs)
    write_json(ROOT/'public/data/briefs.json',briefs)
    feed=dist/'feeds';feed.mkdir(exist_ok=True)
    settings=read_json(ROOT/'config/site.json',{});base=settings.get('url','https://malilun-hot.fast-plum-3707.chatgpt.site')
    (feed/'all.xml').write_bytes(rss(items,'马理论 HOT · 全站',base))
    for category in ('academic','admission','opportunity'):
        kinds={'academic':['paper','book'],'admission':['admission'],'opportunity':['event','call']}[category]
        (feed/(category+'.xml')).write_bytes(rss([x for x in items if x['kind'] in kinds],'马理论 HOT · '+{'academic':'学术前沿','admission':'博士招生','opportunity':'学术机会'}[category],base))
    for topic in topics:(feed/(topic['id']+'.xml')).write_bytes(rss([x for x in items if topic['id'] in x.get('topics',[])],'马理论 HOT · '+topic['name'],base))
    shutil.copytree(feed,ROOT/'public/feeds',dirs_exist_ok=True)
    write_json(dist/'data/health.json',{'last_success':catalog.get('last_success'),'last_attempt':catalog.get('last_attempt'),'source_status':[{k:v for k,v in s.items() if k in ('id','name','status','items','checked_at','last_success','errors')} for s in catalog['sources']],'runs':catalog.get('runs',[])})
    print(f"Built {len(items)} real records, {len(topics)} topics, {len(briefs)} briefs; no AI/API/build dependency.")
    return payload
if __name__=='__main__':build()
