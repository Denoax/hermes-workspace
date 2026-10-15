"""Rollback behavior on disposable source fixtures only; never production state."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from workspace.rollback_parity import restore
class Rollback(unittest.TestCase):
 def fixture(self,base):
  project=base/'project';checkpoint=base/'checkpoint';(project/'workspace/ui').mkdir(parents=True);(checkpoint/'before/workspace/ui').mkdir(parents=True)
  entries={}
  for name,before,after in [('app.js',b'old source',b'new source'),('flight-kernel.mjs',None,b'new module')]:
   relative='workspace/ui/'+name;(project/relative).write_bytes(after)
   if before is not None:(checkpoint/'before'/relative).write_bytes(before)
   entries[relative]={'before':hashlib.sha256(before).hexdigest()if before else None,'after':hashlib.sha256(after).hexdigest(),'mode':0o644}
  (checkpoint/'manifest.json').write_text(json.dumps({'files':entries}));return project,checkpoint
 def test_restores_only_reviewed_source_preserving_data(self):
  with tempfile.TemporaryDirectory()as d:
   p,c=self.fixture(Path(d));(p/'private-data').write_text('preserve');restore(p,c);self.assertEqual((p/'workspace/ui/app.js').read_bytes(),b'old source');self.assertFalse((p/'workspace/ui/flight-kernel.mjs').exists());self.assertEqual((p/'private-data').read_text(),'preserve')
 def test_refuses_any_drift_before_mutating_other_files(self):
  with tempfile.TemporaryDirectory()as d:
   p,c=self.fixture(Path(d));(p/'workspace/ui/flight-kernel.mjs').write_text('user edit')
   with self.assertRaisesRegex(ValueError,'unrelated_drift'):restore(p,c)
   self.assertEqual((p/'workspace/ui/app.js').read_bytes(),b'new source')
 def test_refuses_symlink(self):
  with tempfile.TemporaryDirectory()as d:
   p,c=self.fixture(Path(d));(p/'workspace/ui/app.js').unlink();(p/'workspace/ui/app.js').symlink_to(p/'private-data')
   with self.assertRaisesRegex(ValueError,'symlink'):restore(p,c)
if __name__=='__main__':unittest.main()
