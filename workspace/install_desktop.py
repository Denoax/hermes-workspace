"""Reversible normal-user entry/service install and exact single-pin replacement."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
STATE=Path.home()/'.local/state/hermes-workspace'
PIN=Path.home()/'.config/quickshell/kona/sidebar/shell.qml'
OLD='["brave", "kitty", "dolphin", "steam", "code", "paseo"]'
NEW='["brave", "kitty", "dolphin", "hermes-workspace", "code", "paseo"]'


def main():
    if os.geteuid()==0:raise SystemExit('normal_user_installation_only')
    os.umask(0o077);STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    register=STATE/'desktop-install.json'
    if register.exists():raise RuntimeError('registered_installation_already_exists')
    before=PIN.read_bytes();text=before.decode()
    if text.count(OLD)!=1:raise RuntimeError('expected_six_pin_baseline_changed')
    entry=Path.home()/'.local/share/applications/hermes-workspace.desktop'
    launcher=Path.home()/'.local/bin/hermes-workspace'
    router=Path.home()/'.local/bin/hermes-lab-worker'
    unit=Path.home()/'.config/systemd/user/hermes-workspace.service'
    for p in [entry,launcher,router,unit]:
        if p.exists() or p.is_symlink():raise RuntimeError('preserve_existing_target:'+p.name)
    (STATE/'sidebar-before.qml').write_bytes(before)
    files={launcher:('#!/bin/sh\nexec /usr/bin/python3 -I '+str(ROOT/'workspace/launcher.py')+'\n',0o700),
      router:('#!/bin/sh\nexec /usr/bin/python3 -I '+str(ROOT/'workspace/router.py')+' "$@"\n',0o700),
      entry:('[Desktop Entry]\nType=Application\nName=Hermes\nComment=Local isolated Hermes workspace\nExec='+str(launcher)+'\nIcon=applications-development\nTerminal=false\nCategories=Development;\nStartupWMClass=brave-127.0.0.1__hermes-workspace-Default\n',0o644),
      unit:('[Unit]\nDescription=Local Hermes workspace data UI\n[Service]\nExecStart=/usr/bin/python3 -I '+str(ROOT/'workspace/server.py')+'\nWorkingDirectory='+str(ROOT)+'\nUMask=0077\nNoNewPrivileges=yes\nPrivateTmp=yes\nRestart=on-failure\nRestartSec=3\n[Install]\nWantedBy=default.target\n',0o600)}
    installed=[]
    for p,(content,mode) in files.items():
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('x') as f:f.write(content)
        p.chmod(mode);installed.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'device':p.stat().st_dev,'inode':p.stat().st_ino})
    subprocess.run(['/usr/bin/desktop-file-validate',str(entry)],check=True)
    PIN.write_text(text.replace(OLD,NEW))
    installed.append({'path':str(PIN),'sha256':hashlib.sha256(PIN.read_bytes()).hexdigest(),'device':PIN.stat().st_dev,'inode':PIN.stat().st_ino,'restore':'sidebar-before.qml','before_sha256':hashlib.sha256(before).hexdigest()})
    register.write_text(json.dumps({'version':1,'files':installed,'source':str(ROOT),'Steam_installed_unchanged':True},indent=2)+'\n')
    subprocess.run(['/usr/bin/systemctl','--user','daemon-reload'],check=True)
    print('Installed Hermes entry, launcher and view-only local service; replaced exactly the Steam pin.')


if __name__=='__main__':main()
