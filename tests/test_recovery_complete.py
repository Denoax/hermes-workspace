import hashlib
from pathlib import Path
import tempfile
import os
from unittest.mock import patch
import unittest
from native.recovery import Recovery,fingerprint,SYSTEM_UNITS,USER_UNIT


class Services:
    def __init__(self,root):self.root=root;self.events=[]
    def close_window(self):self.events.append('normal_restored')
    def stop(self,unit,user=False):self.events.append('stop:'+unit)
    def close_workspace_browser(self):self.events.append('owned_browser_closed')
    def reload(self):
        self.events.append('reload')
        for unit in ['mani-vmlab-inference-window.service','mani-vmlab-supervisor.service']:
            assert not (self.root/'etc/systemd/system'/unit).exists()
        assert (self.root/'usr/local/lib/mani-vmlab/window.py').exists()
    def retire_account(self,item):self.events.append('retire:'+item['name'])


class CompleteRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);files=[]
        names=['/etc/systemd/system/mani-vmlab-inference-window.service',
               '/etc/systemd/system/mani-vmlab-supervisor.service',
               '/run/systemd/system/mani-vmlab-backend.service',
               '/usr/local/lib/mani-vmlab/window.py',
               '/home/mani/.config/systemd/user/hermes-workspace.service',
               '/home/mani/.local/bin/hermes-lab-worker',
               '/home/mani/.config/quickshell/kona/sidebar/shell.qml']
        for name in names:
            p=self.root/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text('installed')
            item=fingerprint(p);item['path']=name;files.append(item)
        backup='/home/mani-vmlab-data/workspace-recovery/pin-before'
        p=self.root/backup.lstrip('/');p.parent.mkdir(parents=True);p.write_text('original Steam pin')
        pin=files[-1];pin.update(action='restore',backup=backup,before_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),before_mode=0o600)
        self.register={'version':1,'files':files,'accounts':[{'name':'mani-vmlab-model','uid':958,'created':True},
             {'name':'mani-vmlab-vm','uid':959,'created':True}],
             'retained':['original weights','copied weights','signed package recovery','images','raw evidence','source']}
        self.services=Services(self.root);self.recovery=Recovery(self.register,self.services,self.root)

    def test_full_lifecycle_orders_hooks_before_code_and_restores_exact_pin(self):
        self.assertTrue(self.recovery.plan()['ready'])
        result=self.recovery.remove();self.assertEqual(result['status'],'removed_registered_installation')
        self.assertEqual(self.services.events[0],'normal_restored')
        self.assertIn('reload',self.services.events)
        self.assertEqual((self.root/'home/mani/.config/quickshell/kona/sidebar/shell.qml').read_text(),'original Steam pin')
        self.assertFalse((self.root/'usr/local/lib/mani-vmlab/window.py').exists())
        self.assertEqual(len(result['retained']),6)

    def test_production_activation_hook_is_removed_before_reload_and_runtime_code(self):
        from native.recovery import PRODUCTION_ENABLE
        for name in ['/etc/systemd/system/hermes-workspace-runtime.socket',
                     '/etc/systemd/system/hermes-workspace-runtime.service',
                     '/etc/systemd/system/mani-vmlab-supervisor.socket',
                     '/usr/local/lib/mani-vmlab-setup/production_setup.py']:
            p=self.root/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text('registered v4 fixture')
            item=fingerprint(p);item['path']=name;self.register['files'].append(item)
        p=self.root/str(PRODUCTION_ENABLE).lstrip('/');p.parent.mkdir(parents=True)
        p.symlink_to('/etc/systemd/system/hermes-workspace-runtime.socket')
        info=p.lstat()
        link={'path':str(PRODUCTION_ENABLE),'kind':'symlink','device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'target':os.readlink(p)}
        self.register['namespaces']=[link]
        original_reload=self.services.reload
        def reload():
            self.assertFalse(p.is_symlink())
            self.assertTrue((self.root/'usr/local/lib/mani-vmlab-setup/production_setup.py').exists())
            original_reload()
        self.services.reload=reload
        # File identity and root-only ownership checks are covered separately;
        # this fixture normalizes only ownership for an unprivileged test run.
        def namespace(path):
            actual=Path(path).lstat()
            return {'path':str(path),'kind':'symlink','device':actual.st_dev,'inode':actual.st_ino,'uid':actual.st_uid,'target':os.readlink(path)}
        with patch('native.recovery.namespace_record',side_effect=namespace):
            result=Recovery(self.register,self.services,self.root).remove()
        self.assertIn(str(PRODUCTION_ENABLE),result['removed'])
        self.assertLess(self.services.events.index('stop:hermes-workspace-runtime.socket'),self.services.events.index('stop:hermes-workspace-runtime.service'))
        self.assertLess(self.services.events.index('stop:mani-vmlab-supervisor.socket'),self.services.events.index('stop:mani-vmlab-supervisor.service'))
        self.assertFalse((self.root/'usr/local/lib/mani-vmlab-setup/production_setup.py').exists())

    def test_production_enable_link_cannot_target_an_unrelated_unit(self):
        self.register['namespaces']=[{'path':'/etc/systemd/system/sockets.target.wants/hermes-workspace-runtime.socket','kind':'symlink','target':'/etc/systemd/system/other.service'}]
        with self.assertRaisesRegex(ValueError,'exact_production_socket_enable_link'):
            Recovery(self.register,self.services,self.root)

    def test_drift_refuses_before_services_or_files_are_changed(self):
        p=self.root/'etc/systemd/system/mani-vmlab-inference-window.service';p.write_text('new user change')
        with self.assertRaises(RuntimeError):self.recovery.remove()
        self.assertEqual(self.services.events,[])
        self.assertTrue((self.root/'usr/local/lib/mani-vmlab/window.py').exists())

    def test_packaged_identities_arbitrary_paths_and_missing_hooks_rejected(self):
        self.register['accounts'].append({'name':'qemu','uid':960,'created':True})
        with self.assertRaises(ValueError):Recovery(self.register,self.services,self.root)
        self.register['accounts'].pop()
        self.register['files'][0]['path']='/etc/shadow'
        with self.assertRaises(ValueError):Recovery(self.register,self.services,self.root)

    def test_symlink_ancestor_refuses_before_root_mutation(self):
        parent=self.root/'home/mani/.local/bin';real=parent.with_name('real-bin');parent.rename(real);parent.symlink_to(real,target_is_directory=True)
        with self.assertRaises(OSError):self.recovery.remove()
        self.assertEqual(self.services.events,[])

    def test_backup_drift_does_not_restore_wrong_bytes(self):
        (self.root/'home/mani-vmlab-data/workspace-recovery/pin-before').write_text('changed backup')
        with self.assertRaises(RuntimeError):self.recovery.remove()
        self.assertEqual(self.services.events,[])


if __name__=='__main__':unittest.main()
