"""Real receipt-validation tests; no model, browser or production execution."""
import copy, importlib.util, unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'scripts/probe_v5_citation.py'
s=importlib.util.spec_from_file_location('citation_proposal',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ActualReceiptGuards(unittest.TestCase):
 def setUp(self):
  self.doc={'case':{'nonce':'V5review-1234abcd-actions-1234abcd','permission_session':'a'*32,'project_id':'b'*32,'created_session_ids':['a'*32]},'checks':{'real_Wikipedia_search':{'state':'completed','result':{'provider':'Wikipedia','attachment':{'id':'c'*32},'sources':[{'id':'12','title':'Example','url':'https://en.wikipedia.org/wiki/Example'}]}}}}
 def test_accepts_only_exact_created_case_and_completed_real_attachment(self):
  case,aid,sources=m.actions_case(self.doc);self.assertEqual(aid,'c'*32);self.assertEqual(case['permission_session'],'a'*32);self.assertEqual(len(sources),1)
 def test_rejects_unowned_session_and_absent_attachment(self):
  for where in ('session','attachment'):
   x=copy.deepcopy(self.doc)
   if where=='session':x['case']['created_session_ids']=[]
   else:x['checks']['real_Wikipedia_search']['result']['attachment']=None
   with self.subTest(where=where),self.assertRaises(RuntimeError):m.actions_case(x)
 def test_rejects_noncompleted_or_fabricated_provider(self):
  for field,value in [('state','approved'),('provider','Fixture')]:
   x=copy.deepcopy(self.doc)
   if field=='state':x['checks']['real_Wikipedia_search'][field]=value
   else:x['checks']['real_Wikipedia_search']['result'][field]=value
   with self.subTest(field=field),self.assertRaises(RuntimeError):m.actions_case(x)
 def test_rejects_arbitrary_or_credentialed_source_urls(self):
  for url in ['http://en.wikipedia.org/wiki/X','https://example.com/wiki/X','https://u:p@en.wikipedia.org/wiki/X','https://en.wikipedia.org:443/wiki/X','https://en.wikipedia.org/api/X']:
   x=copy.deepcopy(self.doc);x['checks']['real_Wikipedia_search']['result']['sources'][0]['url']=url
   with self.subTest(url=url),self.assertRaises(RuntimeError):m.actions_case(x)
 def test_rejects_oversized_or_duplicate_source_groups_without_reindexing(self):
  for count in [0,2,5]:
   x=copy.deepcopy(self.doc);x['checks']['real_Wikipedia_search']['result']['sources']*=count
   with self.subTest(count=count),self.assertRaises(RuntimeError):m.actions_case(x)
if __name__=='__main__':unittest.main()
