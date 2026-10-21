"""Behavioral regressions for round 3. Synthetic examples never enter public data."""
import hashlib,sys,unittest,copy
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bibliography as bib,collect,build
from test_pipeline import sample

class BibliographyTests(unittest.TestCase):
    def test_shared_toc_is_not_article_identity(self):
        a=sample(id='a',title='测试甲论文',url='https://example.org/toc',verified_urls=['https://example.org/toc'],source_kind='publisher_toc')
        b=sample(id='b',title='测试乙论文',url='https://example.org/toc',verified_urls=['https://example.org/toc'],source_kind='publisher_toc')
        self.assertEqual(len(collect.merge_items([],[a,b,a,b])),2)
    def test_same_title_in_different_journals_stays_separate(self):
        b=sample(journal='另一期刊',url='https://example.org/2',verified_urls=['https://example.org/2'])
        self.assertEqual(len(collect.merge_items([sample()],[b])),2)
    def test_different_issues_are_not_collapsed(self):
        a=sample(issue_year=2026,issue_number=1);b=sample(issue_year=2026,issue_number=2,url='https://example.org/2',verified_urls=['https://example.org/2'])
        self.assertEqual(len(collect.merge_items([a],[b])),2)
    def test_longest_job_title_removed_first(self):
        self.assertEqual(bib.authors(['殷一博副教授','测试讲师']),['殷一博','测试'])
    def test_original_and_reprint_dates_stay_distinct(self):
        h='<meta name="pageTitle" content="《转载刊》转载：测试原论文题名"><div class="v_news_content">发布时间：2026-08-06 我院测试人教授发表的论文：测试原论文题名，被《转载刊》2026年第15期转载，该文原载于《原发刊》2026年第2期。</div>'
        x=collect.parse_vsb(h,'https://example.org/info/1/2.htm',{'id':'snnu'})
        self.assertEqual(x['journal'],'原发刊');self.assertEqual(x['issue_number'],2);self.assertEqual(x['authors'],['测试人'])
        self.assertEqual(x['reprints'][0]['journal'],'转载刊');self.assertEqual(x['reprints'][0]['issue_number'],15)
        self.assertIsNone(x['reprints'][0]['reprint_date']);self.assertIsNone(x['publication_date'])
    def test_keywords_do_not_swallow_abstract(self):
        h='<h1>测试论文题名</h1><p>关键词：思想政治教育;人工智能; Abstract：This is an abstract. KeyWords：test</p>'
        x=collect.parse_cnki(h,'https://example.org/paper/1',{'name':'测试期刊'})
        self.assertEqual(x['keywords'],['思想政治教育','人工智能']);self.assertIsNone(x['abstract_excerpt'])
    def test_socialism_keywords_stop_at_paragraph_boundary(self):
        h='<h1>【2026.01】测试正式论文题名</h1><div class="top_about">作者：测试甲、测试乙 【单位】</div><div id="read_tpc"><p>【关键词】思想政治教育；学科建设</p><p>这是正文，不是关键词。后面还有许多正文。</p></div>'
        x=collect.parse_socialism(h,'https://example.org/paper/1',{'name':'测试期刊'})
        self.assertEqual(x['keywords'],['思想政治教育','学科建设']);self.assertEqual(x['authors'],['测试甲','测试乙'])
    def test_reject_long_keyword_and_sentences(self):
        self.assertEqual(bib.keywords(['真正关键词','正文。下一句话','字'*25,'摘要：后面是内容']),['真正关键词'])
    def test_pagination_follows_second_page_and_deduplicates(self):
        source={'id':'fixture','name':'测试期刊','home':'https://example.org/','lists':['https://example.org/list'],'adapter':'cnki','rights':'fixture','max_items':20}
        p1='<h3><a href="/paper/1">第一篇测试论文</a></h3><a href="/paperPage_list?pageNum=2">下一页</a>'
        p2='<h3><a href="/paper/2">第二篇测试论文</a></h3><a href="/paper/1">第一篇测试论文</a>'
        class Fetch:
            verified_at={}
            def policy(self,u):return {'allowed':True,'status':'fixture'}
            def get(self,u,**kw):
                if u.endswith('/list'):return p1
                if 'pageNum=2'in u:return p2
                return '<h1>'+('第二篇测试论文'if'/2'in u else'第一篇测试论文')+'</h1>'
        out,status=collect.collect_source(source,Fetch(),'2026-10-20T00:00:00+00:00')
        self.assertEqual(len(out),2);self.assertEqual(status['list_pages'],2);self.assertFalse(status['pagination_truncated'])
    def test_changed_reviewed_image_is_not_imported(self):
        spec={'journal':'马克思主义与现实','year':2026,'issue':1,'tier':1,'toc_url':'https://example.org/toc','mode':'reviewed_images','checks':[{'url':'https://example.org/image','sha256':hashlib.sha256(b'old').hexdigest()}],'entries':[{'title':'测试论文','authors':['测试人'],'url':'https://example.org/toc','included':True}]}
        class Fetch:
            def get(self,*args,**kw):return b'changed'
        out,states=bib.collect_issues([spec],Fetch(),'2026-10-20T00:00:00+00:00',force=True)
        self.assertEqual(out,[]);self.assertEqual(states[0]['status'],'needs_review')
    def test_formal_windows_30_90_boundaries(self):
        today=date(2026,10,20)
        for days in [7,30,90]:
            from datetime import timedelta
            self.assertTrue(build.in_window(sample(publication_date=(today-timedelta(days=days-1)).isoformat()),days,today))
            self.assertFalse(build.in_window(sample(publication_date=(today-timedelta(days=days)).isoformat()),days,today))
    def test_reprint_and_news_not_counted_and_work_id_deduped(self):
        xs=[sample(id='1',work_id='same'),sample(id='2',work_id='same'),sample(id='3',kind='event'),sample(id='4',is_reprint=True)]
        r=build.rankings(xs,[{'id':'capital','name':'测试主题'}],date(2026,10,20))
        self.assertEqual(r['90'][0]['work_count'],1)
    def test_sparse_context_never_claims_ranking(self):
        c=build.ranking_context([sample()],[],date(2026,10,20))
        self.assertTrue(all(v['mode']=='collected_topics'for v in c.values()))
    def test_paper_sort_never_uses_web_report_date(self):
        a=sample(id='a',publication_date=None,issue_year=2025,web_date='2026-10-20')
        b=sample(id='b',publication_date=None,issue_year=2026,web_date='2026-01-01')
        self.assertEqual(sorted([a,b],key=collect.sort_key,reverse=True)[0]['id'],'b')
if __name__=='__main__':unittest.main()
