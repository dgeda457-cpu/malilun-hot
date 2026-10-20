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
        assert 'main_points' not in x and 'research_methods' not in x
        assert not x.get('abstract_excerpt') or len(x['abstract_excerpt'])<=121
        for k in ['publication_date','web_date','event_date','deadline']:
            if x.get(k):date.fromisoformat(x[k])
    valid={x['id'] for x in items};by_id={x['id']:x for x in items}
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
