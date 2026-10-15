"""Transactional conversations, replayable ordered events and folder organization."""
import hashlib,json,time,uuid
from workspace.catalog import identifier

TERMINAL={'completed','cancelled','failed'}
COLORS=('blue','orange','green','purple','rose','slate')


class Conversations:
    def __init__(self,catalog):self.c=catalog

    def run(self,run_id):
        identifier(run_id)
        with self.c.lock:r=self.c.db.execute('SELECT id,session,model,state,settings,created,error,identity FROM chat_runs WHERE id=?',(run_id,)).fetchone()
        if r is None:raise ValueError('unknown_chat_run')
        return dict(zip(('id','session','model','state','settings','created','error','identity'),
                        [*r[:4],json.loads(r[4]),*r[5:7],json.loads(r[7]) if r[7] else None]))

    def admit(self,run_id,session,model,prompt,reasoning,attachments,search_query=None):
        identifier(run_id);self.c.session_record(session)
        if type(prompt) is not str or not 1<=len(prompt.encode())<=12000:raise ValueError('message_requires_1_to_12000_bytes')
        if reasoning not in ('off','on') or type(attachments) is not list or len(attachments)>8 or len(set(attachments))!=len(attachments):raise ValueError('invalid_turn_settings')
        for a in attachments:identifier(a)
        if search_query is not None and (type(search_query) is not str or not 1<=len(search_query.strip())<=200 or any(ord(c)<32 for c in search_query)):raise ValueError('invalid_explicit_search_query')
        settings={'reasoning':reasoning,'attachments':attachments,'search_query':search_query,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
        with self.c.lock:
            old=self.c.db.execute('SELECT id FROM chat_runs WHERE id=?',(run_id,)).fetchone()
            if old:
                r=self.run(run_id)
                if (r['session'],r['model'],r['settings'])!=(session,model,settings):raise ValueError('idempotency_key_conflict')
                return r,False
            if self.c.db.execute("SELECT 1 FROM chat_runs WHERE session=? AND state NOT IN ('completed','cancelled','failed')",(session,)).fetchone():raise RuntimeError('conversation_already_running')
            for a in attachments:
                if not self.c.db.execute('SELECT 1 FROM attachments WHERE id=?',(a,)).fetchone():raise ValueError('unknown_attachment')
            with self.c.db:
                self.c.db.execute('INSERT INTO chat_runs VALUES (?,?,?,?,?,?,NULL,NULL)',(run_id,session,model,'queued',json.dumps(settings),time.time()))
                self.c.db.execute('INSERT INTO messages(session,role,text,job) VALUES (?,?,?,?)',(session,'user',prompt,run_id))
                for a in attachments:self.c.db.execute('INSERT INTO turn_attachments VALUES (?,?)',(run_id,a))
                self._event(run_id,{'type':'state','state':'queued','label':'Queued'})
            return self.run(run_id),True

    def _event(self,run_id,event):
        seq=self.c.db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM chat_events WHERE run=?',(run_id,)).fetchone()[0]
        event={'run_id':run_id,'seq':seq,**event};self.c.db.execute('INSERT INTO chat_events VALUES (?,?,?)',(run_id,seq,json.dumps(event)))
        return event

    def event(self,run_id,event):
        with self.c.lock,self.c.db:return self._event(run_id,event)

    def state(self,run_id,state,label=None,error=None,identity=None):
        with self.c.lock,self.c.db:
            current=self.run(run_id)
            if current['state'] in TERMINAL:return
            self.c.db.execute('UPDATE chat_runs SET state=?,error=?,identity=COALESCE(?,identity) WHERE id=?',
                              (state,error,json.dumps(identity) if identity else None,run_id))
            self._event(run_id,{'type':'state','state':state,'label':label or state.capitalize(),'error':error})

    def append(self,run_id,text):
        if type(text) is not str or not text:return
        with self.c.lock,self.c.db:
            r=self.run(run_id)
            row=self.c.db.execute("SELECT id,length(CAST(text AS BLOB)) FROM messages WHERE job=? AND role='assistant'",(run_id,)).fetchone()
            if (row[1] if row else 0)+len(text.encode())>32768:raise ValueError('reply_output_limit')
            if row:self.c.db.execute('UPDATE messages SET text=text||? WHERE id=?',(text,row[0]))
            else:self.c.db.execute('INSERT INTO messages(session,role,text,job) VALUES (?,?,?,?)',(r['session'],'assistant',text,run_id))
            self._event(run_id,{'type':'delta','text':text})

    def events(self,run_id,after):
        self.run(run_id)
        if type(after) is not int or not 0<=after<=100000:raise ValueError('invalid_event_cursor')
        with self.c.lock:return [json.loads(r[0]) for r in self.c.db.execute('SELECT event FROM chat_events WHERE run=? AND seq>? ORDER BY seq LIMIT 256',(run_id,after))]

    def session_runs(self,session):
        self.c.session_record(session)
        with self.c.lock:ids=[r[0] for r in self.c.db.execute('SELECT id FROM chat_runs WHERE session=? ORDER BY created',(session,))]
        return [self.run(i) for i in ids]

    def folder(self,project,label,parent,color):
        identifier(project);self.c.files(project).close()
        if type(label) is not str or not 1<=len(label.strip())<=80 or any(ord(c)<32 for c in label) or color not in COLORS:raise ValueError('invalid_folder')
        if parent is not None:self.c.files(parent).close()
        with self.c.lock,self.c.db:
            p=parent;seen={project}
            while p is not None:
                if p in seen:raise ValueError('folder_cycle')
                seen.add(p);r=self.c.db.execute('SELECT parent FROM folder_meta WHERE project=?',(p,)).fetchone();p=r[0] if r else None
            self.c.db.execute('UPDATE projects SET label=? WHERE id=?',(label.strip(),project))
            self.c.db.execute('INSERT OR REPLACE INTO folder_meta VALUES (?,?,?)',(project,parent,color))
        return {'saved':True}

    def move_session(self,session,project):
        self.c.session_record(session)
        if project is not None:self.c.files(project).close()
        with self.c.lock,self.c.db:self.c.db.execute('UPDATE sessions SET project=? WHERE id=?',(project or '',session))
        return {'saved':True}

    def delete_records(self,projects,sessions):
        """Caller owns cancellation, the SQL transaction and recoverable file moves."""
        for i in [*projects,*sessions]:identifier(i)
        with self.c.lock:
            for session in sessions:
                if self.c.db.execute("SELECT 1 FROM chat_runs WHERE session=? AND state NOT IN ('completed','cancelled','failed')",(session,)).fetchone():raise RuntimeError('cancel_active_conversation_first')
                jobs=[r[0] for r in self.c.db.execute('SELECT id FROM jobs WHERE session=?',(session,))]
                for job in jobs:self.c.db.execute('DELETE FROM reviews WHERE job=?',(job,))
                runs=[r[0] for r in self.c.db.execute('SELECT id FROM chat_runs WHERE session=?',(session,))]
                for run in runs:
                    self.c.db.execute('DELETE FROM chat_events WHERE run=?',(run,));self.c.db.execute('DELETE FROM turn_attachments WHERE run=?',(run,))
                for table,column in [('chat_runs','session'),('messages','session'),('jobs','session'),('session_titles','session'),('drafts','scope'),('sessions','id')]:
                    self.c.db.execute(f'DELETE FROM {table} WHERE {column}=?',(session,))
            for project in projects:
                # New records outside a captured reset scope survive, detached.
                self.c.db.execute("UPDATE sessions SET project='' WHERE project=?",(project,))
                self.c.db.execute('UPDATE folder_meta SET parent=NULL WHERE parent=?',(project,))
                for table,column in [('folder_meta','project'),('origins','project'),('imports','project'),('reviews','project'),('projects','id')]:
                    self.c.db.execute(f'DELETE FROM {table} WHERE {column}=?',(project,))
            row=self.c.db.execute('SELECT state FROM view_state WHERE id=1').fetchone()
            if row:
                state=json.loads(row[0])
                if state.get('project_id') in projects or state.get('session_id') in sessions:
                    state.update(project_id=None,session_id=None,file_path=None,editor=None,files_open=False)
                    self.c.db.execute('UPDATE view_state SET state=? WHERE id=1',(json.dumps(state),))
        return {'deleted_projects':len(projects),'deleted_conversations':len(sessions)}
