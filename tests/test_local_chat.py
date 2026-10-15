"""Disposable catalog/transport fixtures; these are not live model acceptance."""
import hashlib,io,json,os,socket,sqlite3,tempfile,threading,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from workspace.catalog import Catalog
from workspace.conversations import Conversations
from workspace.attachments import Attachments
from workspace.models import Inventory,identity
from workspace.reset import delete_captured
from lab.native_client import request_schema


def new_id():return uuid.uuid4().hex


class LocalChatContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.c=Catalog(self.root);self.store=Conversations(self.c)
        self.session=self.c.session(None,'normal')['id']
    def tearDown(self):self.c.db.close();self.tmp.cleanup()
    def admit(self,run=None,prompt='A labelled test message',**overrides):
        fields=dict(run_id=run or new_id(),session=self.session,model='normal',prompt=prompt,reasoning='off',attachments=[]);fields.update(overrides);return self.store.admit(**fields)
    def test_chat_requires_no_project_and_persists_after_reopen(self):
        r,_=self.admit();self.store.append(r['id'],'Test reply');self.store.state(r['id'],'completed')
        reopened=Catalog(self.root)
        try:self.assertEqual([r['text'] for r in reopened.history(self.session)],['A labelled test message','Test reply']);self.assertIsNone(reopened.session_record(self.session)['project'])
        finally:reopened.db.close()
    def test_duplicate_retry_is_same_run_and_message(self):
        r,_=self.admit();second,created=self.admit(r['id']);self.assertFalse(created);self.assertEqual(r,second);self.assertEqual(len(self.c.history(self.session)),1)
    def test_reused_id_cannot_change_prompt_or_model(self):
        r,_=self.admit()
        with self.assertRaisesRegex(ValueError,'idempotency'):self.admit(r['id'],prompt='different')
    def test_repeated_send_cannot_overlap_conversation(self):
        self.admit()
        with self.assertRaisesRegex(RuntimeError,'already_running'):self.admit()
    def test_ordered_replay_keeps_partial_text_and_durable_cancel(self):
        r,_=self.admit();i=r['id'];self.store.state(i,'generating');self.store.append(i,'part');self.store.append(i,' two');self.store.state(i,'cancelled')
        all_events=self.store.events(i,0);self.assertEqual([e['seq'] for e in all_events],list(range(1,len(all_events)+1)))
        self.assertEqual(self.store.events(i,all_events[2]['seq']),all_events[3:]);self.assertEqual(self.c.history(self.session)[1]['text'],'part two')
        self.store.state(i,'completed');self.assertEqual(self.store.run(i)['state'],'cancelled')
    def test_folder_moves_reject_cycles_and_preserve_colors(self):
        a=self.c.create('A')['id'];b=self.c.create('B')['id'];self.store.folder(b,'B',a,'orange')
        with self.assertRaisesRegex(ValueError,'cycle'):self.store.folder(a,'A',b,'green')
        self.assertEqual(next(p for p in self.c.projects() if p['id']==b)['color'],'orange')
    def test_capture_reset_preserves_later_conversation(self):
        project=self.c.create('Original host untouched')['id'];old=self.c.session(project,'normal')['id'];fresh=self.c.session(project,'normal')['id']
        original=self.root/'independent-original';original.mkdir();(original/'keep').write_text('original')
        receipt=delete_captured(self.c,[project],[old]);self.assertEqual(receipt['deleted_conversations'],1)
        self.assertIsNone(self.c.session_record(fresh)['project']);self.assertEqual((original/'keep').read_text(),'original')
        backup=next((self.root/'trash').glob('*/catalog.sqlite3'));db=sqlite3.connect(backup)
        try:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions WHERE id=?',(old,)).fetchone()[0],1)
        finally:db.close()
    def test_active_delete_preserves_files_and_record(self):
        r,_=self.admit()
        with self.assertRaisesRegex(RuntimeError,'cancel_active'):delete_captured(self.c,[],[self.session])
        self.assertEqual(self.store.run(r['id'])['state'],'queued')
    def test_project_deletion_includes_conversations_beyond_navigation_page(self):
        from types import SimpleNamespace
        from workspace.reset import delete_content
        project=self.c.create('Complete deletion scope')['id']
        with self.c.lock,self.c.db:self.c.db.executemany('INSERT INTO sessions VALUES (?,?,?)',[(new_id(),project,'normal') for _ in range(1002)])
        app=SimpleNamespace(catalog=self.c,chat=SimpleNamespace(lock=threading.RLock(),store=self.store))
        result=delete_content(app,'project',project)
        self.assertEqual(result['deleted_conversations'],1002)
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM sessions WHERE project=?',(project,)).fetchone()[0],0)
    def test_deleted_conversation_retires_only_its_unshared_attachments(self):
        files=Attachments(self.c);a=files.upload(io.BytesIO(b'private test fixture'),20,'fixture.txt','text/plain')
        r,_=self.admit(attachments=[a['id']]);self.store.state(r['id'],'completed')
        delete_captured(self.c,[],[self.session])
        with self.assertRaisesRegex(ValueError,'unknown_attachment'):files.get(a['id'])
        self.assertFalse((self.root/'attachments'/(a['id']+'.bin')).exists())
        self.assertTrue(list((self.root/'trash').glob('*/'+a['id']+'.bin')))
    def test_restart_reconciles_files_moved_before_database_commit(self):
        project=self.c.create('Recover moved copy')['id'];batch=self.root/'trash'/'fixture';batch.mkdir(parents=True)
        (self.root/'projects'/project).rename(batch/project)
        (batch/'scope.json').write_text(json.dumps({'projects':[project],'sessions':[],'attachments':[],'phase':'prepared'}))
        recovered=Catalog(self.root)
        try:self.assertTrue((self.root/'projects'/project).is_dir());self.assertEqual(json.loads((batch/'scope.json').read_text())['phase'],'rolled_back')
        finally:recovered.db.close()
    def test_real_attachment_content_is_scoped_and_inert(self):
        a=Attachments(self.c).upload(io.BytesIO(b'nonce: test-42'),14,'fixture.txt','text/plain')
        self.assertEqual(Attachments(self.c).context(a['id'])[1],'nonce: test-42');self.admit(attachments=[a['id']])
    def test_upload_rejects_traversal_type_size_and_disconnection(self):
        store=Attachments(self.c)
        for name,mime,data,size in [('../outside','text/plain',b'x',1),('bad.png','image/png',b'fake',4),('large.txt','text/plain',b'',9000000),('short.txt','text/plain',b'a',3)]:
            with self.subTest(name=name),self.assertRaises(ValueError):store.upload(io.BytesIO(data),size,name,mime)
        self.assertEqual(list(store.root.iterdir()),[])
    def test_attachment_symlink_is_refused(self):
        a=Attachments(self.c).upload(io.BytesIO(b'x'),1,'fixture.txt','text/plain');p=self.root/'attachments'/(a['id']+'.bin');p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaises(OSError):Attachments(self.c).read(a['id'])
    def test_verified_inventory_invalidates_on_file_or_link_drift(self):
        weights=self.root/'fixture.gguf';weights.write_bytes(b'labelled disposable weights');info=weights.stat();sha=hashlib.sha256(weights.read_bytes()).hexdigest()
        lock=self.root/'links.json';cache=self.root/'cache.json';lock.write_text(json.dumps({'models':{'normal':{'source':str(weights),'bytes':info.st_size,'sha256':sha}}}));cache.write_text(json.dumps({'normal':{'path':str(weights),'identity':identity(info),'sha256':sha}}))
        inv=Inventory(lock,cache);self.assertEqual([m['id'] for m in inv.entries()],['normal']);weights.write_bytes(b'drift');self.assertEqual(inv.entries(),[])
        with self.assertRaisesRegex(ValueError,'not_verified'):inv.require('cloud-model')
    def test_native_text_contract_has_no_prompt_url_or_tool_surface(self):
        self.assertEqual(request_schema('chat_admit',job_id='a'*32,arm='normal')['arm'],'normal')
        for kwargs in [{'job_id':'../x','arm':'normal'},{'job_id':'a'*32,'arm':'cloud'},{'job_id':'a'*32,'arm':'normal','payload':{'command':'id'}}]:
            with self.assertRaises(ValueError):request_schema('chat_admit',**kwargs)
    def test_search_refuses_private_DNS_before_connection(self):
        from workspace.search import public_addresses
        with patch('workspace.search.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaisesRegex(ValueError,'public_DNS'):public_addresses('example.test')
    def test_text_watchdog_tick_never_blocks_on_loading_lock(self):
        from native.text_chat import TextChat
        owner=TextChat(None);ready=threading.Event();release=threading.Event()
        def hold():
            with owner.lock:ready.set();release.wait(2)
        t=threading.Thread(target=hold);t.start();ready.wait(2)
        try:owner.check()
        finally:release.set();t.join()
    def test_native_acknowledgement_is_sent_before_recovery_stops_daemon(self):
        from native.supervisor import send_native_result
        actions=[]
        class Connection:
            def sendall(self,data):actions.append(('reply',json.loads(data)))
        send_native_result(Connection(),{'status':'ok','_restore_window':True},restore=lambda:actions.append(('restore',None)))
        self.assertEqual(actions,[('reply',{'status':'ok'}),('restore',None)])
    def test_disconnected_release_still_schedules_recovery(self):
        from native.supervisor import send_native_result
        done=[]
        class Connection:
            def sendall(self,data):raise BrokenPipeError()
        with self.assertRaises(BrokenPipeError):send_native_result(Connection(),{'status':'ok','_restore_window':True},restore=lambda:done.append(True))
        self.assertEqual(done,[True])
    def test_guard_can_write_its_recovery_receipt_without_writable_home(self):
        from native.window import unit_text
        text=unit_text();self.assertIn('/var/lib/mani-vmlab-review',text);self.assertIn('ProtectHome=read-only',text);self.assertIn('ProtectSystem=strict',text)
        self.assertNotIn('After=mani-vmlab-supervisor.service',text)

if __name__=='__main__':unittest.main()
