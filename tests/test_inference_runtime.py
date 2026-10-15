import importlib.util
import json
import os
import socket
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from lab.relay import Relay,validate_request
from lab.report import request_usage
from lab.state import RunStore

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('tested_'+name,ROOT/'native'/(name+'.py'))
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class OutsideControlContracts(unittest.TestCase):
    def test_failed_transport_terminates_dedicated_compute(self):
        class FailedConnection:
            sock=None
            def request(self,*args):raise OSError('owned transport failure')
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory:
            store=RunStore(Path(directory)/'state');run=store.create();calls=[]
            relay=Relay(store,run,'test',18082,connection_factory=lambda seconds:FailedConnection(),
                        cancel_backend=lambda:calls.append('stopped'))
            with self.assertRaises(OSError):
                relay.infer(json.dumps({'model':'test','messages':[{'role':'user','content':'synthetic'}]}).encode(),
                            store.token(run),'a'*32)
            self.assertIn('stopped',calls)
            self.assertTrue(relay.events[-1]['cancelled'])

    def test_expired_window_cannot_be_revived_by_heartbeat(self):
        window=module('window')
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json'
            state.write_text(json.dumps({'status':'active','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                                         'normal_quiesced':True,'deadline':100,'heartbeat':99}))
            with patch.object(window,'STATE',state),patch.object(window.time,'monotonic',return_value=100):
                self.assertFalse(window.active())
                with self.assertRaises(RuntimeError):window.beat()
            self.assertEqual(json.loads(state.read_text())['heartbeat'],99)

    def test_mask_publication_requires_effective_systemd_mask(self):
        window=module('window')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state.json';state.write_text('{}')
            with patch.object(window,'DIRECTORY',root),patch.object(window,'STATE',state),\
                 patch.object(window,'MASK_DIRECTORY',root),\
                 patch.object(window,'mask_directory',side_effect=lambda:(os.open(root,os.O_RDONLY),root.stat())),\
                 patch.object(window,'command'),patch.object(window,'normal_command',return_value=b'loaded\n'):
                with self.assertRaisesRegex(RuntimeError,'runtime_mask_not_effective'):window.create_mask()
            mask=json.loads(state.read_text())['runtime_mask']
            self.assertEqual((root/window.NORMAL).lstat().st_ino,mask['inode'])
            self.assertEqual((root/window.NORMAL).readlink(),Path('/dev/null'))

    def test_mask_collision_preserves_existing_override(self):
        window=module('window')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state.json';state.write_text('{}')
            override=root/window.NORMAL;override.write_text('existing user override')
            with patch.object(window,'DIRECTORY',root),patch.object(window,'STATE',state),\
                 patch.object(window,'mask_directory',side_effect=lambda:(os.open(root,os.O_RDONLY),root.stat())),\
                 patch.object(window,'command') as reload:
                with self.assertRaises(FileExistsError):window.create_mask()
                reload.assert_not_called()
            self.assertEqual(override.read_text(),'existing user override')

    def test_stop_and_cleanup_share_one_complete_lifecycle_lock(self):
        supervisor=module('supervisor')
        with tempfile.TemporaryDirectory() as directory:
            control=supervisor.Supervisor.__new__(supervisor.Supervisor)
            control.store=RunStore(Path(directory)/'state');run=control.store.create()
            first_inside=threading.Event();second_attempting=threading.Event();release=threading.Event();second_inside=threading.Event()
            def first():
                with control.lifecycle(run):first_inside.set();release.wait(3)
            def second():
                first_inside.wait(3);second_attempting.set()
                with control.lifecycle(run):second_inside.set()
            a=threading.Thread(target=first);b=threading.Thread(target=second)
            a.start();b.start()
            try:
                self.assertTrue(second_attempting.wait(3));self.assertFalse(second_inside.wait(0.05))
            finally:
                release.set();a.join(3);b.join(3)
            self.assertTrue(second_inside.is_set());self.assertFalse(a.is_alive() or b.is_alive())

    def test_simultaneous_compute_stops_serialize_and_remove_socket_once(self):
        backend=module('backend')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'window').mkdir();path=root/'backend.sock'
            with socket.socket(socket.AF_UNIX) as channel:channel.bind(str(path))
            first_inside=threading.Event();second_attempt=threading.Event();release=threading.Event();entered=[];errors=[]
            def fake_stop(*args,**kwargs):
                entered.append(threading.current_thread().name)
                if len(entered)==1:first_inside.set();release.wait(3)
            def stop(second=False):
                if second:first_inside.wait(3);second_attempt.set()
                try:backend.stop()
                except Exception as error:errors.append(error)
            with patch.object(backend,'DATA',root),patch.object(backend,'SOCKET',path),\
                 patch.object(backend.subprocess,'check_output',return_value=b'loaded'),\
                 patch.object(backend.subprocess,'run',side_effect=fake_stop),\
                 patch.object(backend.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid())):
                a=threading.Thread(target=stop);b=threading.Thread(target=stop,args=(True,));a.start();b.start()
                try:
                    self.assertTrue(second_attempt.wait(3));self.assertEqual(len(entered),1)
                finally:release.set();a.join(3);b.join(3)
            self.assertEqual(errors,[]);self.assertEqual(len(entered),2);self.assertFalse(path.exists())

    def test_processing_observer_rejects_pre_request_journal_entries(self):
        probe=module('model_probe')
        old=b'{"__MONOTONIC_TIMESTAMP":"99000000"}\n'
        new=b'{"__MONOTONIC_TIMESTAMP":"100000001"}\n'
        self.assertFalse(probe.processing_log_after(old,100))
        self.assertTrue(probe.processing_log_after(old+new,100))

    def test_retry_never_silently_renews_an_expired_selected_window(self):
        smoke=module('run_smoke')
        prior={'status':'closed','boot_id':'owned-boot','deadline':100}
        self.assertEqual(smoke.retry_deadline(prior,'owned-boot',99),100)
        with self.assertRaisesRegex(RuntimeError,'chosen_window_expired'):
            smoke.retry_deadline(prior,'owned-boot',100)
        self.assertIsNone(smoke.retry_deadline(prior,'owned-boot',100,fresh_window=True))

    def test_native_thinking_off_continuation_maps_only_the_fixed_backend_switch(self):
        request={'model':'test','messages':[{'role':'user','content':'synthetic continuation'}],
                 'max_tokens':1024,'reasoning_effort':'none'}
        mapped=validate_request(json.dumps(request).encode(),'test')
        self.assertEqual(mapped['chat_template_kwargs'],{'enable_thinking':False})
        self.assertNotIn('reasoning_effort',mapped);self.assertEqual(mapped['max_tokens'],1024)
        for extra in ({'reasoning_effort':'high'},{'reasoning_effort':None},
                      {'chat_template_kwargs':{'enable_thinking':False}}):
            with self.assertRaises(ValueError):validate_request(json.dumps({**request,**extra}).encode(),'test')

    def test_malformed_authenticated_retry_retains_its_budget_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            store=RunStore(Path(directory)/'state');run=store.create()
            relay=Relay(store,run,'test',18082,connection_factory=lambda seconds:self.fail('must not dispatch'))
            with self.assertRaises(ValueError):relay.infer(b'{"host_command":"denied"}',store.token(run),'b'*32)
            self.assertEqual(store.read(run)['calls'],1)
            self.assertEqual(store.read(run)['tokens_reserved'],1024)
            self.assertEqual(relay.events[-1]['outcome'],'denied')
            self.assertEqual(relay.events[-1]['reason'],'invalid_request_fields')

    def test_continuation_usage_includes_truncated_and_final_requests(self):
        result={'relay_events':[{'outcome':'completed','finish_reason':'length',
            'usage':{'prompt_tokens':582,'completion_tokens':1024}},
            {'outcome':'completed','finish_reason':'stop','usage':{'prompt_tokens':601,'completion_tokens':28}},
            {'outcome':'denied'}]}
        usage=request_usage(result)
        self.assertEqual(usage['prompt_tokens'],1183);self.assertEqual(usage['completion_tokens'],1052)
        self.assertEqual(usage['model_calls'],2);self.assertEqual(usage['finish_reasons'],['length','stop'])


if __name__=='__main__':unittest.main()
