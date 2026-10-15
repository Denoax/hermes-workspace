import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from lab.native_client import request_schema
from lab.relay import validate_request
from lab.workspace_contract import TOOLS,READ_TOOLS,submit
from native.evidence import PinnedImage,bunker_policy
from workspace.catalog import Catalog
from workspace.files import Files
from workspace.server import Application,BoundedServer,handler,ORIGIN,PORT


class FileBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.files=Files(self.root);self.addCleanup(self.files.close)

    def test_UTF8_hash_bound_update_and_drift_refusal(self):
        before=self.files.write('src/program.py','print("✓")\n')
        after=self.files.write('src/program.py','print("new")\n',before['sha256'])
        self.assertNotEqual(before['sha256'],after['sha256'])
        with self.assertRaises(ValueError):self.files.write('src/program.py','drift',before['sha256'])
        self.assertEqual(self.files.read('src/program.py')['text'],'print("new")\n')

    def test_absolute_parent_hidden_and_authority_paths_denied(self):
        for path in ['/etc/passwd','../file','a/../../file','a/.env','answer_keys.json','starter/scoring.py','a//b','a/.aws/credentials','secrets.yaml','private.pem']:
            with self.subTest(path=path),self.assertRaises(ValueError):self.files.write(path,'data')

    def test_leaf_directory_and_ancestor_symlinks_rejected(self):
        (self.root/'real').mkdir();(self.root/'real/file').write_text('private')
        (self.root/'link').symlink_to(self.root/'real',target_is_directory=True)
        (self.root/'leaf').symlink_to(self.root/'real/file')
        with self.assertRaises(OSError):self.files.read('link/file')
        with self.assertRaises(OSError):self.files.read('leaf')
        with self.assertRaises(OSError):Files(self.root/'link')

    def test_hardlink_FIFO_binary_and_oversize_fail_without_blocking(self):
        (self.root/'regular').write_text('value');os.link(self.root/'regular',self.root/'hard')
        os.mkfifo(self.root/'fifo');(self.root/'binary').write_bytes(b'x\0y');(self.root/'large').write_bytes(b'x'*(1024*1024+1))
        for name in ['regular','hard','fifo','binary','large']:
            with self.subTest(name=name),self.assertRaises(ValueError):self.files.read(name)

    def test_mount_identity_drift_rejected(self):
        self.files.write('file','data')
        with patch('workspace.files.mount_id',return_value='different mount'):
            with self.assertRaises(ValueError):self.files.read('file')


class CatalogBehavior(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.catalog=Catalog(self.root/'catalog');self.addCleanup(self.catalog.db.close)

    def test_reconnect_preserves_opaque_project_session_and_messages(self):
        p=self.catalog.create('Selected project');s=self.catalog.session(p['id'],'normal')
        self.catalog.message(s['id'],'user','hello')
        other=Catalog(self.root/'catalog')
        try:self.assertEqual(other.history(s['id']),[{'role':'user','text':'hello','job':None}])
        finally:other.db.close()

    def test_import_is_explicit_byte_copy_and_drift_bound(self):
        source=self.root/'selected';source.mkdir();(source/'program.py').write_text('print(1)\n')
        (source/'.env').write_text('omitted')
        project=self.catalog.create('Source copy')['id'];preview=self.catalog.import_preview(project,source)
        self.assertEqual(preview['files'],['program.py'])
        (source/'program.py').write_text('changed')
        with self.assertRaises(ValueError):self.catalog.import_commit(project,preview['ticket'])
        new=self.catalog.import_preview(project,source);self.catalog.import_commit(project,new['ticket'])
        files=self.catalog.files(project)
        try:
            before=files.read('program.py');files.write('program.py','inert edit',before['sha256'])
        finally:files.close()
        self.assertEqual((source/'program.py').read_text(),'changed')

    def test_unknown_scope_model_and_staging_budget_rejected(self):
        with self.assertRaises(ValueError):self.catalog.files('f'*32)
        p=self.catalog.create('Budget')['id']
        with self.assertRaises(ValueError):self.catalog.session(p,'remote')
        files=self.catalog.files(p)
        try:files.write('large.py','x'*32769)
        finally:files.close()
        with self.assertRaises(ValueError):self.catalog.snapshot(p)


class NativeWorkspaceContracts(unittest.TestCase):
    def payload(self):
        snapshot=[]
        return {'version':1,'project_id':'a'*32,'session_id':'b'*32,'job_id':'c'*32,
          'arm':'normal','prompt':'review selected files','task_kind':'chat','authority':'read','snapshot':snapshot,
          'snapshot_sha256':hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()}

    def test_fixed_submit_and_read_contract(self):
        p=self.payload();self.assertEqual(submit(p),p)
        self.assertEqual(request_schema('workspace_read',version=1,job_id='c'*32)['job_id'],'c'*32)

    def test_root_paths_commands_models_version_and_authority_expansions_denied(self):
        for field,value in [('version',True),('arm','remote'),('authority','root'),('project_id','../../etc'),('executable','/bin/sh')]:
            p={**self.payload(),field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):submit(p)
        with self.assertRaises(ValueError):request_schema('workspace_submit',version=1,payload=self.payload(),run_id='a'*32)

    def test_bad_snapshot_size_hash_duplicate_and_oracle_rejected(self):
        item={'path':'program.py','text':'x','bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}
        from lab.workspace_contract import snapshot_files
        for files in [[{**item,'path':'bench/answer_keys.json'}],[{**item,'bytes':True}],[item,item],[{**item,'sha256':'0'*64}]]:
            with self.assertRaises(ValueError):snapshot_files(files)

    def test_tool_profile_preserves_default_denial_and_read_authority(self):
        data={'model':'lab','messages':[{'role':'user','content':'read'}],'tools':READ_TOOLS,'parallel_tool_calls':False}
        with self.assertRaises(ValueError):validate_request(json.dumps(data).encode(),'lab')
        self.assertEqual(validate_request(json.dumps(data).encode(),'lab','read')['tools'],READ_TOOLS)
        with self.assertRaises(ValueError):validate_request(json.dumps({**data,'tools':TOOLS}).encode(),'lab','read')
        with_name={**data,'messages':[{'role':'tool','name':'lab_read_file','tool_call_id':'owned-call','content':'scoped text'}]}
        self.assertEqual(validate_request(json.dumps(with_name).encode(),'lab','read')['messages'],with_name['messages'])
        with self.assertRaises(ValueError):validate_request(json.dumps({**with_name,'messages':[{**with_name['messages'][0],'name':'terminal'}]}).encode(),'lab','read')
        final={key:value for key,value in data.items() if key!='tools'}
        self.assertNotIn('tools',validate_request(json.dumps(final).encode(),'lab','read'))
        with self.assertRaises(ValueError):validate_request(json.dumps(data).encode(),'lab','root')

    def test_unrelated_drop_chains_do_not_qualify_PC_Bunker(self):
        rules=[{'chain':{'family':'inet','table':'unrelated','name':name,'hook':hook,'policy':'drop','type':'filter','prio':0}} for name,hook in [('input','input'),('forward_guard','forward')]]
        self.assertFalse(bunker_policy(rules))
        for item in rules:item['chain']['table']='mani_pc_bunker'
        self.assertTrue(bunker_policy(rules))
        rules[0]['chain']['hook']='output';self.assertFalse(bunker_policy(rules))

    def test_status_pin_polling_does_not_repeat_full_hash_and_drift_invalidates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'image';p.write_bytes(b'verified image')
            pin=PinnedImage(p,hashlib.sha256(p.read_bytes()).hexdigest())
            metadata=[1,2,len(p.read_bytes()),3,4]
            with patch('native.evidence.identity',side_effect=lambda _:tuple(metadata)):
                pin.verify()
                for _ in range(100):self.assertTrue(pin.current())
                self.assertEqual(pin.full_hashes,1)
                metadata[-1]+=1;self.assertFalse(pin.current())


class OriginAuthentication(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=Application(Path(self.temp.name)/'catalog')
        self.addCleanup(self.app.catalog.db.close)
        self.server=BoundedServer(('127.0.0.1',0),handler(self.app,'fixture-cookie'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)

    def request(self,method,path,headers,body=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            c.request(method,path,body,headers);r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()

    def test_foreign_origin_host_missing_cookie_and_CSRF_denied(self):
        body=json.dumps({'version':1,'method':'workspace.create','fields':{'label':'test'}})
        valid={'Host':f'127.0.0.1:{PORT}','Origin':ORIGIN,'Cookie':'hermes_session=fixture-cookie','X-Hermes-CSRF':self.app.csrf,'Content-Type':'application/json'}
        for changes in [{'Origin':'https://foreign.example'},{'Host':'evil.example'},{'Cookie':''},{'X-Hermes-CSRF':''}]:
            code,_=self.request('POST','/hermes-workspace/api/rpc',{**valid,**changes},body)
            self.assertEqual(code,403)
        self.assertEqual(self.app.catalog.projects(),[])
        code,value=self.request('POST','/hermes-workspace/api/rpc',valid,body)
        self.assertEqual(code,200);self.assertEqual(value['result']['label'],'test')

    def test_unknown_method_boolean_version_duplicate_keys_and_depth_fail(self):
        valid={'Host':f'127.0.0.1:{PORT}','Origin':ORIGIN,'Cookie':'hermes_session=fixture-cookie','X-Hermes-CSRF':self.app.csrf,'Content-Type':'application/json'}
        bodies=[json.dumps({'version':True,'method':'status.read','fields':{}}),json.dumps({'version':1,'method':'sudo','fields':{}}),'{"version":1,"version":1,"method":"status.read","fields":{}}']
        for body in bodies:
            code,_=self.request('POST','/hermes-workspace/api/rpc',valid,body);self.assertEqual(code,409)


class OutsideJobLifecycle(unittest.TestCase):
    def test_real_pidfd_admission_replay_queue_cancel_and_next_worker(self):
        from native import jobs
        with tempfile.TemporaryDirectory() as directory,patch.object(jobs,'DATA',Path(directory)),patch.dict(sys.modules,{
            'supervisor':SimpleNamespace(protected=lambda p:None),
            'backend':SimpleNamespace(artifacts_current=lambda:True),
            'window':SimpleNamespace(active=lambda:True,state=lambda:{'deadline':time.monotonic()+1800})}):
            control=SimpleNamespace(cleanup=lambda run:{'status':'ok'})
            manager=jobs.Jobs(control)
            entered=threading.Event();release=threading.Event()
            def execute(job):
                manager.event(job,'running','Owned fixture entered');entered.set();release.wait(3)
                manager.event(job,'review_ready','Owned fixture complete')
            manager.execute=execute
            payload=NativeWorkspaceContracts().payload()
            result=manager.submit(payload,os.getpid());self.assertEqual(result['state'],'queued')
            self.assertTrue(entered.wait(2))
            with self.assertRaises(ValueError):manager.submit(payload,os.getpid())
            second={**payload,'job_id':'d'*32}
            manager.submit(second,os.getpid());manager.cancel(second['job_id'])
            self.assertEqual(manager.public(second['job_id'])['state'],'cancelled')
            release.set();manager.worker.join(3);manager.check_owners()
            self.assertEqual(manager.public(payload['job_id'])['state'],'review_ready')
            self.assertEqual(manager.owners,{})
            third={**payload,'job_id':'e'*32};manager.submit(third,os.getpid())
            manager.worker.join(3);manager.check_owners()
            self.assertEqual(manager.public(third['job_id'])['state'],'review_ready')
            self.assertEqual(manager.owners,{})


class ImmutableArtifactProof(unittest.TestCase):
    def test_actual_byte_verification_cached_status_and_content_drift(self):
        from native import backend
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'models').mkdir();(root/'backend-b9980').mkdir()
            model=root/'models/normal.gguf';model.write_bytes(b'owned fixture not a model')
            binary=root/'backend-b9980/libfixture.so';binary.write_bytes(b'owned fixture not executable')
            def entry(path):return {'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            lock=root/'lock.json';lock.write_text(json.dumps({'models':{'normal':entry(model)},'backend_files':[{'name':binary.name,**entry(binary)}]}))
            def metadata(path):
                info=Path(path).lstat();return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns
            with patch.object(backend,'DATA',root),patch.object(backend,'ARTIFACT_LOCK',lock),patch.object(backend,'ARTIFACT_PROOF',root/'proof.json'),patch.object(backend,'ARTIFACT_LOCK_SHA',hashlib.sha256(lock.read_bytes()).hexdigest()),patch.dict(sys.modules,{'evidence':SimpleNamespace(identity=metadata)}):
                self.assertFalse(backend.artifacts_current())
                self.assertEqual(backend.verify_artifacts()['verified_files'],2)
                with patch('hashlib.file_digest',side_effect=AssertionError('status must not rehash artifacts')):
                    for _ in range(100):self.assertTrue(backend.artifacts_current())
                model.write_bytes(b'changed owned fixture')
                self.assertFalse(backend.artifacts_current())
                with self.assertRaises(RuntimeError):backend.verify_artifacts()


class ReviewedApplyBoundaries(unittest.TestCase):
    def test_apply_requires_imported_base_and_refuses_original_drift(self):
        from workspace.jobs import Jobs
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'selected';source.mkdir();target=source/'program.py';target.write_text('print(1)\n');target.chmod(0o755)
            catalog=Catalog(root/'catalog')
            try:
                project=catalog.create('Owned apply fixture')['id']
                preview=catalog.import_preview(project,source);catalog.import_commit(project,preview['ticket'])
                session=catalog.session(project,'normal');snapshot=catalog.snapshot(project)['files'];job='7'*32
                candidate='print(2)\n'
                record={'id':job,'state':'review_ready','exported':True,'snapshot':snapshot,
                    'files':[{'path':'program.py','text':candidate,'bytes':len(candidate),'sha256':hashlib.sha256(candidate.encode()).hexdigest()}],
                    'validation':{'passed':True,'kind':'offline_owned_receipt_fixture'}}
                catalog.db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(job,session['id'],'review_ready',json.dumps(record)));catalog.db.commit()
                with patch('workspace.jobs.NativeClient.available',return_value=False):
                    review=Jobs(catalog).call('patch.prepare',{'job_id':job})
                    self.assertIsNotNone(review['review_ticket']);self.assertIn('+print(2)',review['diff'])
                    target.write_text('user edit\n')
                    with self.assertRaises(ValueError):Jobs(catalog).call('patch.apply',{'review_ticket':review['review_ticket']})
                    self.assertEqual(target.read_text(),'user edit\n')
                    target.write_text('print(1)\n')
                    result=Jobs(catalog).call('patch.apply',{'review_ticket':review['review_ticket']})
                    self.assertTrue(result['applied']);self.assertEqual(target.read_text(),candidate);self.assertEqual(target.stat().st_mode&0o777,0o755)
                    with self.assertRaises(ValueError):Jobs(catalog).call('patch.apply',{'review_ticket':review['review_ticket']})
                    # An admitted edited copy is not the same base as the
                    # imported original; its diff must not get an apply ticket.
                    target.write_text('print(1)\n');different='print(3)\n';record['snapshot']=[{'path':'program.py','text':different,'bytes':len(different),'sha256':hashlib.sha256(different.encode()).hexdigest()}]
                    catalog.db.execute('UPDATE jobs SET record=? WHERE id=?',(json.dumps(record),job));catalog.db.commit()
                    self.assertIsNone(Jobs(catalog).call('patch.prepare',{'job_id':job})['review_ticket'])
            finally:catalog.db.close()


if __name__=='__main__':unittest.main()
