"""Fixtures are synthetic and remain only in isolated test temp folders."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import collect,build
def sample(**kw):
    x={'id':'test-1','title':'测试夹具：平台资本主义研究','kind':'paper','authors':['测试作者'],'journal':'测试期刊','url':'https://example.org/paper/1','verified_urls':['https://example.org/paper/1'],'first_seen':'2026-10-01T00:00:00+00:00','last_verified':'2026-10-01T00:00:00+00:00','publication_date':'2026-10-01','web_date':'2026-10-02','evidence_level':'metadata','verification':'部分核实','topics':['capital'],'source_name':'测试源'};x.update(kw);return x
class PipelineTests(unittest.TestCase):
    def test_same_url_idempotent(self):
        a=sample();b=sample(last_verified='2026-10-03T00:00:00+00:00');out=collect.merge_items([a],[b,b]);self.assertEqual(len(out),1);self.assertEqual(out[0]['first_seen'],a['first_seen']);self.assertEqual(out[0]['last_verified'],b['last_verified'])
    def test_same_paper_other_source_merges(self):
        a=sample();b=sample(url='https://example.net/report/1',verified_urls=['https://example.net/report/1'],publication_date=None,source_name='测试高校');out=collect.merge_items([a],[b]);self.assertEqual(len(out),1);self.assertEqual(len(out[0]['verified_urls']),2);self.assertEqual(out[0]['publication_date'],a['publication_date'])
    def test_conflicting_authors_stay_separate(self):
        b=sample(url='https://example.net/2',verified_urls=['https://example.net/2'],authors=['另一测试作者']);self.assertEqual(len(collect.merge_items([sample()],[b])),2)
    def test_conflicting_publication_dates_not_ranked(self):
        rows=collect.merge_items([sample()],[sample(publication_date='2026-10-03')]);self.assertEqual(rows[0]['verification'],'存在冲突');self.assertFalse(build.in_window(rows[0],30,date(2026,10,20)))
    def test_web_date_never_substitutes_publication(self):
        self.assertFalse(build.in_window(sample(publication_date=None,web_date='2026-10-20'),7,date(2026,10,20)))
    def test_window_boundaries_and_future(self):
        today=date(2026,10,20)
        self.assertTrue(build.in_window(sample(publication_date='2026-10-14'),7,today));self.assertFalse(build.in_window(sample(publication_date='2026-10-13'),7,today));self.assertFalse(build.in_window(sample(publication_date='2026-10-21'),7,today))
    def test_meetings_not_ranked(self):self.assertFalse(build.in_window(sample(kind='event'),90,date(2026,10,20)))
    def test_same_title_different_notice_dates_are_separate(self):
        a=sample(kind='event',id='old-activity',url='https://example.org/1',verified_urls=['https://example.org/1','https://example.org/2'],web_date='2026-01-01')
        b=sample(kind='event',id='new-activity',url='https://example.org/2',verified_urls=['https://example.org/2'],web_date='2026-02-01')
        out=collect.merge_items([a],[b]);self.assertEqual(len(out),2);self.assertEqual(sum(len(x['verified_urls'])for x in out),2)
    def test_independent_sources_count_journals(self):
        rows=build.rankings([sample(),sample(id='test-2',source_name='另一测试高校')],[{'id':'capital','name':'资本'}],date(2026,10,20));self.assertEqual(rows['90'][0]['source_count'],1)
    def test_sort_real_dates(self):
        a,b=sample(publication_date='2026-10-10'),sample(id='2',publication_date='2026-10-01');self.assertEqual(sorted([b,a],key=collect.sort_key,reverse=True)[0],a)
    def test_no_generated_abstract_or观点(self):
        html='<html><head><meta name="pageTitle" content="测试学术讲座"></head><div class="v_news_content">报告时间未定。</div></html>'
        out=collect.parse_vsb(html,'https://example.org/info/1/1.htm',{'id':'test'});self.assertIsNone(out['abstract_excerpt']);self.assertIsNone(out['deadline']);self.assertNotIn('main_points',out)
    def test_invalid_dates(self):self.assertIsNone(collect.exact_date('2026-02-30'));self.assertEqual(collect.exact_date('2026年10月02日'),'2026-10-02')
    def test_url_and_title_normalization(self):
        self.assertEqual(collect.title_key('《测试期刊》：平台资本主义研究'),collect.title_key('平台资本主义研究'));self.assertNotIn('utm_',collect.canonical('https://example.org/a?utm_source=x&id=2#test'))
    def test_single_source_failure_retains_old_data_and_others(self):
        temp_root=ROOT/'tests/.tmp';temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as td:
            r=Path(td);collect.write_json(r/'config/sources.json',[{'id':'broken'},{'id':'working'}]);collect.write_json(r/'public/data/catalog.json',{'items':[sample(id='old')],'runs':[],'sources':[]})
            def runner(s,*args):
                if s['id']=='broken':raise TimeoutError('isolated fixture timeout')
                return [sample(id='new',url='https://example.org/2',verified_urls=['https://example.org/2'],title='另一测试夹具')],{'id':'working','status':'ok','last_success':collect.now()}
            with patch.object(collect,'ROOT',r),patch.object(sys,'argv',['collect.py']):out=collect.run(runner)
            self.assertEqual(len(out['items']),2);self.assertEqual(out['sources'][0]['status'],'failed')
    def test_all_failed_does_not_reset_last_success(self):
        temp_root=ROOT/'tests/.tmp';temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as td:
            r=Path(td);collect.write_json(r/'config/sources.json',[{'id':'broken'}]);collect.write_json(r/'public/data/catalog.json',{'items':[sample()],'last_success':'2026-10-01T00:00:00+00:00','sources':[],'runs':[]})
            with patch.object(collect,'ROOT',r),patch.object(sys,'argv',['collect.py']):out=collect.run(lambda *args:(_ for _ in ()).throw(TimeoutError('fixture')))
            self.assertEqual(out['last_success'],'2026-10-01T00:00:00+00:00');self.assertEqual(out['runs'][-1]['verified_items'],0)
    def test_empty_state_rankings(self):self.assertEqual(build.rankings([],[],date(2026,10,20)),{'7':[],'30':[],'90':[]})
if __name__=='__main__':unittest.main()
