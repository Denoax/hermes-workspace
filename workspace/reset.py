"""Scoped recoverable app-record deletion; imported original directories stay untouched."""
import json,os,sqlite3,stat,time,uuid
from workspace.catalog import identifier
from workspace.conversations import Conversations,TERMINAL


def delete_content(app,kind,record_id):
    identifier(record_id)
    if kind not in ('project','conversation'):raise ValueError('unknown_delete_scope')
    c=app.catalog;projects=[];sessions=[]
    if kind=='conversation':c.session_record(record_id);sessions=[record_id]
    else:
        rows=c.projects()
        if not any(r['id']==record_id for r in rows):raise ValueError('unknown_project')
        projects=[record_id]
        while True:
            children=[r['id'] for r in rows if r['parent'] in projects and r['id'] not in projects]
            if not children:break
            projects.extend(children)
        # Deletion captures the complete scope, independent of the navigation
        # page limit; older conversations must not survive detached by accident.
        with c.lock:sessions=[r[0] for project in projects for r in c.db.execute('SELECT id FROM sessions WHERE project=?',(project,))]
    with app.chat.lock:
        with c.lock:
            owned_jobs=[r[0] for session in sessions for r in c.db.execute("SELECT id FROM jobs WHERE session=? AND state NOT IN ('review_ready','cancelled','failed','blocked')",(session,))]
        if owned_jobs:
            from workspace.jobs import Jobs
            jobs=Jobs(c)
            for job in owned_jobs:jobs.call('job.cancel',{'job_id':job})
            end=time.monotonic()+15
            while owned_jobs:
                owned_jobs=[job for job in owned_jobs if jobs.read(job).get('state') not in ('review_ready','cancelled','failed','blocked')]
                if not owned_jobs:break
                if time.monotonic()>end:raise RuntimeError('owned_guarded_job_cleanup_pending_no_content_deleted')
                time.sleep(.1)
        for session in sessions:
            for run in app.chat.store.session_runs(session):
                if run['state'] not in TERMINAL:app.chat.cancel(run['id'])
        deadline=time.monotonic()+15
        while any(r['state'] not in TERMINAL for s in sessions for r in app.chat.store.session_runs(s)):
            if time.monotonic()>deadline:raise RuntimeError('compute_cleanup_pending_no_content_deleted')
            time.sleep(.05)
        with c.lock:
            for session in sessions:
                if c.db.execute("SELECT 1 FROM jobs WHERE session=? AND state NOT IN ('review_ready','cancelled','failed','blocked')",(session,)).fetchone():raise RuntimeError('finish_owned_guarded_jobs_before_deletion')
            return delete_captured(c,projects,sessions)


def write_scope(batch,scope):
    target=batch/'scope.json';temporary=batch/'scope.tmp'
    with temporary.open('w') as out:json.dump(scope,out);out.flush();os.fsync(out.fileno())
    temporary.replace(target)


def recover_moves(c):
    trash=c.root/'trash'
    if not trash.exists():return
    if trash.is_symlink() or trash.stat().st_uid!=os.getuid():raise ValueError('owned_trash_required')
    for batch in trash.iterdir():
        if not batch.is_dir() or batch.is_symlink():continue
        path=batch/'scope.json'
        if not path.exists():continue
        scope=json.loads(path.read_text())
        if scope.get('phase') in ('committed','rolled_back'):continue
        for project in scope['projects']:
            identifier(project);source=batch/project;target=c.root/'projects'/project
            if c.db.execute('SELECT 1 FROM projects WHERE id=?',(project,)).fetchone() and source.exists() and not target.exists():source.rename(target)
        for aid in scope.get('attachments',[]):
            identifier(aid);source=batch/(aid+'.bin');target=c.root/'attachments'/(aid+'.bin')
            if c.db.execute('SELECT 1 FROM attachments WHERE id=?',(aid,)).fetchone() and source.exists() and not target.exists():source.rename(target)
        still_present=any(c.db.execute('SELECT 1 FROM sessions WHERE id=?',(s,)).fetchone() for s in scope['sessions']) or any(c.db.execute('SELECT 1 FROM projects WHERE id=?',(p,)).fetchone() for p in scope['projects'])
        scope['phase']='rolled_back' if still_present else 'committed';write_scope(batch,scope)


def delete_captured(c,projects,sessions):
    """Capture IDs outside this function; retries never widen to new work."""
    for value in [*projects,*sessions]:identifier(value)
    trash=c.root/'trash';trash.mkdir(mode=0o700,exist_ok=True)
    if trash.is_symlink() or trash.stat().st_uid!=os.getuid():raise ValueError('owned_trash_required')
    batch=trash/uuid.uuid4().hex;batch.mkdir(mode=0o700);moved=[]
    scope={'projects':projects,'sessions':sessions,'attachments':[],'phase':'prepared'}
    with c.lock:
        backup=sqlite3.connect(batch/'catalog.sqlite3');c.db.backup(backup);backup.close()
        write_scope(batch,scope)
        try:
            c.db.execute('BEGIN IMMEDIATE')
            aids={r[0] for s in sessions for r in c.db.execute('SELECT t.attachment FROM turn_attachments t JOIN chat_runs r ON r.id=t.run WHERE r.session=?',(s,))}
            for project in projects:
                source=c.root/'projects'/project
                if not source.exists():continue
                info=source.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('preserve_unverified_project_root')
                source.rename(batch/project);moved.append((batch/project,source))
            result=Conversations(c).delete_records(projects,sessions)
            for aid in aids:
                if c.db.execute('SELECT 1 FROM turn_attachments WHERE attachment=?',(aid,)).fetchone():continue
                scope['attachments'].append(aid);write_scope(batch,scope)
                source=c.root/'attachments'/(aid+'.bin')
                if source.exists():source.rename(batch/source.name);moved.append((batch/source.name,source))
                c.db.execute('DELETE FROM attachments WHERE id=?',(aid,))
            write_scope(batch,scope);c.db.commit()
        except BaseException:
            c.db.rollback()
            for source,target in reversed(moved):source.rename(target)
            scope['phase']='rolled_back';write_scope(batch,scope)
            raise
        # Commit acknowledgement is independent of optional receipt persistence.
        scope['phase']='committed'
        warning=None
        try:write_scope(batch,scope)
        except OSError:warning='Deletion committed; recovery journal will be reconciled on restart.'
        return {**result,'recoverable':True,**({'warning':warning} if warning else {})}
