"""Unprivileged translator and immutable exports; no host candidate execution."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from lab.native_client import NativeClient,public_snapshot
from lab.workspace_contract import canonical_id
from workspace.files import Files


class Jobs:
    def __init__(self,catalog):self.catalog=catalog

    def local(self,job):
        canonical_id(job)
        with self.catalog.lock:
            row=self.catalog.db.execute('SELECT session,record FROM jobs WHERE id=?',(job,)).fetchone()
        if not row:raise ValueError('unknown_owned_job')
        session=self.catalog.session_record(row[0])
        return session,json.loads(row[1])

    def read(self,job):
        session,_=self.local(job);client=NativeClient(timeout=15)
        native=None
        try:
            if client.available():
                reply=client.call('workspace_read',version=1,job_id=job)
                if reply.get('status')=='ok':native=reply
        except (OSError,RuntimeError):pass
        # Provider waits cannot own the catalog: Stop and Revoke need it too.
        # Re-read after I/O because another tab may have exported or deleted the
        # job meanwhile. Scope and the export cursor move under this one lock.
        with self.catalog.lock,self.catalog.db:
            current,old=self.local(job)
            if current!=session:raise ValueError('job_scope_changed_during_poll')
            return self._merge_read(job,current,old,native)

    def _merge_read(self,job,session,old,native):
        """Caller holds the catalog lock and transaction; no native I/O here."""
        previous=old.get('last_sequence',0)
        record=old
        if native is not None:
            if native.get('project_id')!=session['project'] or native.get('session_id')!=session['id']:raise ValueError('native_scope_mismatch')
            sequence=max((event['sequence'] for event in native.get('events',[])),default=0)
            # Concurrent replies can arrive in reverse order. An old snapshot
            # must not regress the durable cursor or erase an exported result.
            terminal=('review_ready','failed','cancelled','blocked')
            finalized=(old.get('status')=='ok' and old.get('state') in terminal and native.get('state') not in terminal)
            loses_export=(old.get('exported') and native.get('evidence_kind')!='actual_guest_Hermes_workspace_job')
            stale=sequence<previous or finalized or loses_export
            if not stale:record=native
        elif record.get('state') not in ('review_ready','failed','cancelled','blocked'):
            record={**record,'state':'recovery_pending','reason':'Native supervisor closed; awaiting protected final receipt.'}
        if record.get('project_id',session['project'])!=session['project'] or record.get('session_id',session['id'])!=session['id']:
            raise ValueError('native_scope_mismatch')
        record['snapshot']=old.get('snapshot',[])
        if record.get('exported') is not True and old.get('exported') is True:record['exported']=True
        messages=[]
        if record.get('evidence_kind')=='actual_guest_Hermes_workspace_job' and not old.get('exported'):
            # Revalidate the project before creating any export directories.
            self.catalog.files(session['project']).close()
            directory=self.catalog.root/'projects'/session['project']/'outputs'/job
            directory.mkdir(mode=0o700,exist_ok=True)
            output=Files(directory)
            try:
                for item in record.get('files',[]):
                    try:existing=output.read(item['path'])
                    except FileNotFoundError:output.write(item['path'],item['text'])
                    else:
                        if existing['sha256']!=item['sha256']:raise ValueError('artifact_drift')
                    (directory/item['path']).chmod(0o400)
            finally:output.close()
            record['exported']=True
            if record.get('answer'):messages.append(('assistant',record['answer']))
            for event in record.get('tool_events',[]):
                text=event['tool']+' completed in '+format(event['wall_seconds'],'.3f')+' s.\n'+json.dumps(event['result'],ensure_ascii=False)
                messages.append(('event',text[:16000]))
        for event in record.get('events',[]):
            if event['sequence']>previous:messages.append(('event',event['detail']))
        record['last_sequence']=max(previous,max((x['sequence'] for x in record.get('events',[])),default=previous))
        for role,text in messages:
            if type(text) is not str or len(text.encode())>32768:raise ValueError('invalid_message')
            self.catalog.db.execute('INSERT INTO messages(session,role,text,job) VALUES (?,?,?,?)',(session['id'],role,text,job))
        # The exported marker, event cursor and history share one commit.
        self.catalog.db.execute('UPDATE jobs SET state=?,record=? WHERE id=?',(record['state'],json.dumps(record),job))
        safe={key:value for key,value in record.items() if key not in ('files','payload','tool_events','relay_events')}
        return safe

    def call(self,method,fields):
        c=self.catalog
        if method=='job.submit':
            session=c.session_record(fields['session_id']);snapshot=c.snapshot(session['project'])
            if snapshot['sha256']!=fields['snapshot_sha256']:raise ValueError('workspace_changed_before_admission')
            job=canonical_id(fields['client_job_id'])
            payload={'version':1,'job_id':job,'session_id':session['id'],'project_id':session['project'],
                'arm':session['arm'],'prompt':fields['prompt'],'task_kind':fields['task_kind'],
                'authority':'read' if fields['task_kind']=='chat' else 'candidate',
                'snapshot':snapshot['files'],'snapshot_sha256':snapshot['sha256']}
            from lab.workspace_contract import submit
            submit(payload)
            with c.lock:
                if c.db.execute('SELECT 1 FROM jobs WHERE id=?',(job,)).fetchone():raise ValueError('duplicate_job')
                record={'id':job,'state':'starting','snapshot_sha256':snapshot['sha256'],'snapshot':snapshot['files']}
                c.db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(job,session['id'],'starting',json.dumps(record)));c.db.commit()
            try:result=NativeClient(timeout=15).call('workspace_submit',version=1,payload=payload)
            except (OSError,RuntimeError) as error:
                with c.lock:
                    record.update(state='blocked',reason=type(error).__name__)
                    c.db.execute('UPDATE jobs SET state=?,record=? WHERE id=?',('blocked',json.dumps(record),job));c.db.commit()
                raise RuntimeError('Start a qualified bounded Lab window before submitting.') from error
            if result.get('status')!='ok':
                record.update(state='blocked',reason=result.get('error','Native job admission denied'))
                with c.lock:
                    c.db.execute('UPDATE jobs SET state=?,record=? WHERE id=?',('blocked',json.dumps(record),job));c.db.commit()
                raise RuntimeError(record['reason'])
            c.message(session['id'],'user',fields['prompt'],job)
            return {'id':job,'state':result['state']}
        if method=='job.read':return self.read(fields['job_id'])
        if method=='job.cancel':
            self.local(fields['job_id'])
            return NativeClient(timeout=15).call('workspace_cancel',version=1,job_id=fields['job_id'])
        if method=='artifact.read':
            session,record=self.local(fields['job_id']);self.read(fields['job_id']);session,record=self.local(fields['job_id'])
            items={item['path']:item for item in record.get('files',[])}
            if fields['artifact_id'] not in items:raise ValueError('unknown_registered_artifact')
            files=Files(c.root/'projects'/session['project']/'outputs'/fields['job_id'])
            try:value=files.read(fields['artifact_id'])
            finally:files.close()
            if value['sha256']!=items[fields['artifact_id']]['sha256']:raise ValueError('artifact_drift')
            return value
        if method=='patch.prepare':
            self.read(fields['job_id']);session,record=self.local(fields['job_id'])
            if record['state']!='review_ready':raise ValueError('job_not_ready_for_review')
            before={item['path']:item for item in record.get('snapshot',[])}
            # Native public records omit input data. Recover the exact admitted
            # immutable snapshot from the normal-user job row, never from model text.
            if not before:
                original=c.files(session['project'],'input')
                try:before={name:{'path':name,**original.read(name)} for name in original.tree()}
                finally:original.close()
            changed=[item for item in record.get('files',[]) if item['path'] not in before or item['sha256']!=before[item['path']]['sha256']]
            diff=''.join(''.join(difflib.unified_diff(before.get(item['path'],{}).get('text','').splitlines(keepends=True),item['text'].splitlines(keepends=True),fromfile=item['path'],tofile=item['path'])) for item in changed)
            ticket=None
            with c.lock:
                origin=c.db.execute('SELECT path,device,inode FROM origins WHERE project=?',(session['project'],)).fetchone()
            immutable=c.files(session['project'],'input')
            try:imported={name:immutable.read(name)['sha256'] for name in immutable.tree()}
            finally:immutable.close()
            if len(changed)==1 and origin and record.get('validation',{}).get('passed') is True:
                target=changed[0]
                # This diff describes the admitted copy. Applying it to the
                # source is safe only when that base is still the imported base.
                if target['path'] in before and imported.get(target['path'])==before[target['path']]['sha256']:
                    original=Files(origin[0])
                    try:
                        info=os.fstat(original.fd)
                        if (info.st_dev,info.st_ino)!=(origin[1],origin[2]) or original.read(target['path'])['sha256']!=before[target['path']]['sha256']:raise ValueError('original_repository_drift')
                    finally:original.close()
                    ticket=uuid.uuid4().hex
                    plan={'source':origin[0],'device':origin[1],'inode':origin[2],'path':target['path'],
                        'expected':before[target['path']]['sha256'],'text':target['text'],'candidate':target['sha256']}
                    with c.lock:c.db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',(ticket,fields['job_id'],session['project'],json.dumps(plan),time.time()+300));c.db.commit()
            return {'diff':diff,'validation':record.get('validation'),'review_ticket':ticket,'apply_scope':'one existing validated file; drift checked; no host execution'}
        if method=='patch.apply':
            ticket=canonical_id(fields['review_ticket'])
            with c.lock:
                row=c.db.execute('SELECT record,expires FROM reviews WHERE id=?',(ticket,)).fetchone()
                if not row or row[1]<time.time():raise ValueError('review_ticket_expired_or_unknown')
                plan=json.loads(row[0]);original=Files(plan['source'])
                try:
                    info=os.fstat(original.fd)
                    if (info.st_dev,info.st_ino)!=(plan['device'],plan['inode']):raise ValueError('original_directory_drift')
                    result=original.write(plan['path'],plan['text'],plan['expected'],preserve_mode=True)
                    if result['sha256']!=plan['candidate']:raise ValueError('applied_hash_mismatch')
                finally:original.close()
                c.db.execute('DELETE FROM reviews WHERE id=?',(ticket,));c.db.commit()
            return {'applied':True,'sha256':result['sha256']}
        raise ValueError('unknown_job_operation')
