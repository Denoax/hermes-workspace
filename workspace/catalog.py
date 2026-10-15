"""Durable owner-only project/session catalog; never a host execution service."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from workspace.files import Files

ID = re.compile(r'[0-9a-f]{32}')


def identifier(value):
    if type(value) is not str or not ID.fullmatch(value): raise ValueError('invalid_registered_id')
    return value


class Catalog:
    def __init__(self, root):
        self.root=Path(root);self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_uid!=os.getuid() or self.root.stat().st_mode&0o077:
            raise PermissionError('private_owned_workspace_root_required')
        self.db=sqlite3.connect(self.root/'catalog.sqlite3',check_same_thread=False)
        self.lock=threading.RLock()
        self.db.executescript('''CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,label TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,project TEXT NOT NULL,arm TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,session TEXT NOT NULL,role TEXT NOT NULL,text TEXT NOT NULL,job TEXT);
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,session TEXT NOT NULL,state TEXT NOT NULL,record TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY,project TEXT NOT NULL,source TEXT NOT NULL,manifest TEXT NOT NULL,expires REAL NOT NULL);''')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS origins(project TEXT PRIMARY KEY,path TEXT NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,job TEXT NOT NULL,project TEXT NOT NULL,record TEXT NOT NULL,expires REAL NOT NULL);''')
        # Additive presentation state keeps the original three-column sessions compatible.
        self.db.executescript('''CREATE TABLE IF NOT EXISTS session_titles(session TEXT PRIMARY KEY,title TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS view_state(id INTEGER PRIMARY KEY CHECK(id=1),state TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS drafts(scope TEXT PRIMARY KEY,text TEXT NOT NULL,mode TEXT NOT NULL);''')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS folder_meta(project TEXT PRIMARY KEY,parent TEXT,color TEXT NOT NULL DEFAULT 'blue');
          CREATE TABLE IF NOT EXISTS chat_runs(id TEXT PRIMARY KEY,session TEXT NOT NULL,model TEXT NOT NULL,
            state TEXT NOT NULL,settings TEXT NOT NULL,created REAL NOT NULL,error TEXT,identity TEXT);
          CREATE TABLE IF NOT EXISTS chat_events(run TEXT NOT NULL,seq INTEGER NOT NULL,event TEXT NOT NULL,PRIMARY KEY(run,seq));
          CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY,name TEXT NOT NULL,mime TEXT NOT NULL,
            bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,created REAL NOT NULL,metadata TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS turn_attachments(run TEXT NOT NULL,attachment TEXT NOT NULL,PRIMARY KEY(run,attachment));''')
        (self.root/'catalog.sqlite3').chmod(0o600)
        from workspace.reset import recover_moves
        recover_moves(self)

    def create(self,label):
        if type(label) is not str or not 1<=len(label.strip())<=80 or any(ord(c)<32 for c in label): raise ValueError('invalid_project_label')
        project=uuid.uuid4().hex
        with self.lock:
            base=self.root/'projects'/project
            for name in ['input','workspace','outputs','runs']:(base/name).mkdir(parents=True,mode=0o700)
            self.db.execute('INSERT INTO projects VALUES (?,?)',(project,label.strip()));self.db.commit()
        return {'id':project,'label':label.strip()}

    def projects(self):
        with self.lock:return [{'id':r[0],'label':r[1],'parent':r[2],'color':r[3] or 'blue'} for r in self.db.execute('SELECT p.id,p.label,m.parent,m.color FROM projects p LEFT JOIN folder_meta m ON m.project=p.id ORDER BY p.rowid LIMIT 1000')]

    def files(self,project,kind='workspace'):
        identifier(project)
        if kind not in ('workspace','input'):raise ValueError('invalid_scope')
        with self.lock:
            if not self.db.execute('SELECT 1 FROM projects WHERE id=?',(project,)).fetchone():raise ValueError('unknown_project')
        return Files(self.root/'projects'/project/kind)

    def session(self,project,arm):
        if arm not in ('normal','abliterated'):raise ValueError('unknown_pinned_model')
        if project is not None:
            files=self.files(project);files.close()
        session=uuid.uuid4().hex
        with self.lock:self.db.execute('INSERT INTO sessions VALUES (?,?,?)',(session,project or '',arm));self.db.commit()
        return {'id':session,'project':project,'arm':arm}

    def sessions(self):
        with self.lock:
            rows=self.db.execute('''SELECT s.id,s.project,s.arm,t.title,
              (SELECT text FROM messages WHERE session=s.id AND role='user' ORDER BY id LIMIT 1)
              FROM sessions s LEFT JOIN session_titles t ON t.session=s.id ORDER BY s.rowid DESC LIMIT 1000''').fetchall()
            return [{'id':r[0],'project':r[1] or None,'arm':r[2],
                     'title':r[3] or (' '.join(r[4].split())[:60] if r[4] else 'New conversation')} for r in rows]

    def session_record(self,session):
        identifier(session)
        with self.lock:row=self.db.execute('SELECT project,arm FROM sessions WHERE id=?',(session,)).fetchone()
        if not row:raise ValueError('unknown_session')
        return {'id':session,'project':row[0] or None,'arm':row[1]}

    def rename(self,session,title):
        self.session_record(session)
        if type(title) is not str or not 1<=len(title.strip())<=80 or any(ord(c)<32 for c in title):
            raise ValueError('invalid_conversation_title')
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO session_titles VALUES (?,?)',(session,title.strip()));self.db.commit()
        return {'title':title.strip()}

    def view(self):
        with self.lock:row=self.db.execute('SELECT state FROM view_state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def save_view(self,state):
        keys={'project_id','session_id','file_path','editor','files_open','arm','task_kind','theme','motion'}
        if type(state) is not dict or set(state)!=keys:raise ValueError('invalid_view_state')
        project=state['project_id'];session=state['session_id']
        if project is not None:self.files(project).close()
        if session is not None:
            if self.session_record(session)['project']!=project:raise ValueError('session_project_mismatch')
        if state['arm'] not in ('normal','abliterated') or state['task_kind'] not in ('chat','python','cpp') or state['theme'] not in ('dark','light') or state['motion'] not in ('system','reduced') or type(state['files_open']) is not bool:
            raise ValueError('invalid_view_preferences')
        if state['file_path'] is not None:
            from workspace.files import parts
            parts(state['file_path'])
            if project is None:raise ValueError('file_project_required')
        editor=state['editor']
        if editor is not None:
            if type(editor) is not dict or set(editor)!={'text','sha256'} or state['file_path'] is None or type(editor['text']) is not str or len(editor['text'].encode())>32768 or type(editor['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',editor['sha256']):
                raise ValueError('invalid_editor_draft')
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO view_state VALUES (1,?)',(json.dumps(state),));self.db.commit()
        return {'saved':True}

    def draft(self,scope):
        self.session_record(scope)
        with self.lock:row=self.db.execute('SELECT text,mode FROM drafts WHERE scope=?',(scope,)).fetchone()
        return {'text':row[0],'mode':row[1]} if row else {'text':'','mode':'chat'}

    def save_draft(self,scope,text,mode):
        self.session_record(scope)
        if type(text) is not str or len(text.encode())>48000 or mode not in ('chat','python','cpp'):raise ValueError('invalid_composer_draft')
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?)',(scope,text,mode));self.db.commit()
        return {'saved':True}

    def history(self,session):
        self.session_record(session)
        with self.lock:
            rows=list(self.db.execute('SELECT role,text,job FROM messages WHERE session=? ORDER BY id DESC LIMIT 100',(session,)))
        return [{'role':r[0],'text':r[1],'job':r[2]} for r in reversed(rows)]

    def message(self,session,role,text,job=None):
        self.session_record(session)
        if role not in ('user','assistant','event') or type(text) is not str or len(text.encode())>32768:raise ValueError('invalid_message')
        with self.lock:self.db.execute('INSERT INTO messages(session,role,text,job) VALUES (?,?,?,?)',(session,role,text,job));self.db.commit()

    def snapshot(self,project):
        files=self.files(project)
        try:
            result=[{'path':name,**files.read(name)} for name in files.tree()]
            if len(result)>16 or sum(x['bytes'] for x in result)>32768:raise ValueError('job_snapshot_limit_16_files_32_KiB')
            raw=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
            return {'files':result,'sha256':hashlib.sha256(raw).hexdigest()}
        finally:files.close()

    def import_preview(self,project,selected):
        self.files(project).close()
        selected=Path(selected)
        if not selected.is_absolute() or selected==Path.home() or any(x in {'.hermes','.codex','.paseo','.ssh','.config','.local','.var','.cache','mani-vmlab-data','private-state'} for x in selected.parts):raise ValueError('sensitive_import_root')
        source=Files(selected)
        try:
            manifest={name:source.read(name)['sha256'] for name in source.tree()}
            total=sum(source.read(name)['bytes'] for name in manifest)
            if total>64*1024*1024:raise ValueError('import_size_limit')
        finally:source.close()
        ticket=uuid.uuid4().hex
        with self.lock:self.db.execute('INSERT INTO imports VALUES (?,?,?,?,?)',(ticket,project,str(selected),json.dumps(manifest),time.time()+300));self.db.commit()
        return {'ticket':ticket,'files':list(manifest),'bytes':total,'ignored':['credential metadata, .git, dependencies, answer keys']}

    def import_commit(self,project,ticket):
        identifier(ticket)
        with self.lock:
            row=self.db.execute('SELECT source,manifest,expires FROM imports WHERE id=? AND project=?',(ticket,project)).fetchone()
            if not row or row[2]<time.time():raise ValueError('import_ticket_expired_or_unknown')
            manifest=json.loads(row[1]);source=Files(row[0]);target=self.files(project);original=self.files(project,'input')
            try:
                if target.tree() or original.tree():raise ValueError('import_requires_empty_project')
                data={name:source.read(name) for name in manifest}
                if set(source.tree())!=set(manifest) or any(data[name]['sha256']!=digest for name,digest in manifest.items()):raise ValueError('source_changed_since_preview')
                for name,item in data.items():original.write(name,item['text']);target.write(name,item['text'])
                info=os.fstat(source.fd)
                self.db.execute('INSERT INTO origins VALUES (?,?,?,?)',(project,row[0],info.st_dev,info.st_ino))
                self.db.execute('DELETE FROM imports WHERE id=?',(ticket,));self.db.commit()
            finally:source.close();target.close();original.close()
        return {'imported':len(data),'project':project}
