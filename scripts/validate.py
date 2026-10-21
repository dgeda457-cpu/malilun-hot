"""Validate the actual production export, without inventing fixture articles."""
import json,re,sys
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
def validate():
    p=json.loads((ROOT/'dist/data/catalog.json').read_text(encoding='utf8'))
    items=p['items'];ids=[x['id'] for x in items]
    assert len(ids)==len(set(ids)),'duplicate item IDs'
    for x in items:
        assert re.fullmatch('[a-f0-9]{16}',x['id'])
        assert x['title'] and x['url'].startswith('https://')
        assert x['first_seen']<=x['last_verified']
        assert x['evidence_level'] in ('abstract','metadata')
        if x['kind']=='paper':
            assert x.get('work_id'),'missing work identity'
            assert all(2<=len(k)<=24 and not re.search('[。!?！？]',k)for k in x.get('keywords',[])),'keyword contains prose'
        assert 'main_points' not in x and 'research_methods' not in x
        assert not x.get('abstract_excerpt') or len(x['abstract_excerpt'])<=121
        for k in ['publication_date','web_date','event_date','deadline']:
            if x.get(k):date.fromisoformat(x[k])
    valid={x['id'] for x in items};by_id={x['id']:x for x in items}
    works=[x['work_id']for x in items if x['kind']=='paper']
    assert len(works)==len(set(works)),'duplicate scholarly work identities'
    coverage=p.get('issue_coverage',[])
    assert sum(c['expected']for c in coverage)==141,'priority denominator changed without audit'
    assert len(coverage)==8 and len({c['journal']for c in coverage})==5
    for c in coverage:
        assert c['expected']==c['collected']+c['missing']
        for e in c['entries']:
            if e['item_id']:
                assert e['item_id']in valid
                x=by_id[e['item_id']]
                assert (x['journal'],x['issue_year'],x['issue_number'])==(c['journal'],c['year'],c['issue'])
    assert not any('云南'in c['journal']for c in coverage),'third-tier issue entered priority denominator'
    assert all(x.get('journal')!='新华文摘'for x in items if x['kind']=='paper'),'reprint must link original work'
    assert not any('副'in a[-1:]for x in items for a in x.get('authors',[])),'job title residue'
    for days,rows in p['rankings'].items():
        for row in rows:
            assert set(row['item_ids'])<=valid
            assert row['work_count']==len(set(row['item_ids']))
            assert all(by_id[i].get('publication_date') and by_id[i]['kind'] in ('paper','book') for i in row['item_ids'])
    for b in json.loads((ROOT/'dist/data/briefs.json').read_text(encoding='utf8')):assert set(b['item_ids'])<=valid
    for source in ROOT.joinpath('public').glob('*.js'):
        assert not re.search(r'(?:sk-proj-|ghp_|github_pat_|art_v2_)',source.read_text(encoding='utf8')),'possible credential'
    print(f'Production data PASS: {len(items)} real records; dates, references, deduplication, evidence limits and credential patterns validated.')
if __name__=='__main__':validate()
