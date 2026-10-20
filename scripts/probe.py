"""Direct HTTP feasibility evidence; no browser/search results count as success."""
import concurrent.futures, hashlib, json, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    'mlky': 'https://mlky.cbpt.cnki.net/portal',
    'socialism': 'https://socialismstudies.ccnu.edu.cn/',
    'snnu': 'https://marxism.snnu.edu.cn/',
    'ccnu': 'https://marx.ccnu.edu.cn/',
}
def fetch(pair):
    key, url = pair
    out = {'id': key, 'url': url, 'checked_at': datetime.now(timezone.utc).isoformat(), 'transport': 'Python urllib HTTPS; certificate validation enabled'}
    for kind, target in [('robots', url.split('/')[0]+'//'+url.split('/')[2]+'/robots.txt'), ('home', url)]:
        try:
            req = urllib.request.Request(target, headers={'User-Agent': 'MalilunHOT/1.0 (+academic metadata index; 2 requests per second maximum)', 'Accept': 'text/html,text/plain'})
            with urllib.request.urlopen(req, timeout=22) as r:
                raw = r.read(3_000_000)
                charset = r.headers.get_content_charset() or ('gb18030' if b'gb2312' in raw[:2000].lower() or b'gbk' in raw[:2000].lower() else 'utf-8')
                html = raw.decode(charset, errors='replace')
                (ROOT/'evidence'/f'{key}-{kind}.html').write_text(html, encoding='utf-8')
                out[kind] = {'status': r.status, 'final_url':r.url, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest(), 'file': f'evidence/{key}-{kind}.html', 'content_type':r.headers.get('Content-Type')}
        except Exception as e:
            out[kind] = {'error': str(e), 'status':getattr(e,'code',None)}
    return out
if __name__ == '__main__':
    rows = list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(fetch, TARGETS.items()))
    (ROOT/'evidence'/'initial-http-probe.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False, indent=2))
