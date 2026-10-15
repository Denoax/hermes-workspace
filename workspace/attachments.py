"""Inert bounded attachments. No user filename is ever a filesystem selector."""
import hashlib,json,os,re,stat,time,uuid
from pathlib import Path
from workspace.catalog import identifier

LIMIT=8*1024*1024


class Attachments:
    def __init__(self,catalog):
        self.c=catalog;self.root=catalog.root/'attachments';self.root.mkdir(mode=0o700,exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_uid!=os.getuid() or self.root.stat().st_mode&0o077:raise PermissionError('private_attachment_store_required')

    def upload(self,source,size,name,mime):
        if type(size) is not int or not 0<size<=LIMIT:raise ValueError('attachment_size_limit_8_MiB')
        if type(name) is not str or not 1<=len(name)<=160 or '/' in name or '\\' in name or any(ord(c)<32 for c in name) or name in ('.','..'):raise ValueError('invalid_attachment_name')
        if mime not in ('text/plain','image/png','image/jpeg','image/webp','audio/webm','audio/ogg','audio/wav','audio/mp4'):raise ValueError('unsupported_attachment_type')
        with self.c.lock:
            count,total=self.c.db.execute('SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM attachments').fetchone()
            if count>=256 or total+size>128*1024*1024:raise ValueError('attachment_store_quota')
            aid=uuid.uuid4().hex;target=self.root/(aid+'.bin');fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                digest=hashlib.sha256();remaining=size;head=b''
                with os.fdopen(fd,'wb') as output:
                    while remaining:
                        raw=source.read(min(65536,remaining))
                        if not raw:raise ValueError('upload_disconnected')
                        if len(head)<64:head+=raw[:64-len(head)]
                        output.write(raw);digest.update(raw);remaining-=len(raw)
                    output.flush();os.fsync(output.fileno())
                valid=(mime=='text/plain' or mime=='image/png' and head.startswith(b'\x89PNG\r\n\x1a\n') or mime=='image/jpeg' and head.startswith(b'\xff\xd8\xff') or mime=='image/webp' and head.startswith(b'RIFF') and head[8:12]==b'WEBP' or mime=='audio/webm' and head.startswith(b'\x1aE\xdf\xa3') or mime=='audio/ogg' and head.startswith(b'OggS') or mime=='audio/wav' and head.startswith(b'RIFF') and head[8:12]==b'WAVE' or mime=='audio/mp4' and head[4:8]==b'ftyp')
                if not valid:raise ValueError('attachment_content_type_mismatch')
                if mime=='text/plain':
                    if size>32768:raise ValueError('text_context_limit_32_KiB')
                    text=target.read_text(encoding='utf-8')
                    if '\x00' in text:raise ValueError('binary_text_attachment')
                self.c.db.execute('INSERT INTO attachments VALUES (?,?,?,?,?,?,?)',(aid,name,mime,size,digest.hexdigest(),time.time(),'{}'));self.c.db.commit()
                return self.get(aid)
            except BaseException:target.unlink(missing_ok=True);raise

    def get(self,aid):
        identifier(aid)
        with self.c.lock:r=self.c.db.execute('SELECT id,name,mime,bytes,sha256,metadata FROM attachments WHERE id=?',(aid,)).fetchone()
        if r is None:raise ValueError('unknown_attachment')
        return dict(zip(('id','name','mime','bytes','sha256','metadata'),[*r[:5],json.loads(r[5])]))

    def read(self,aid):
        item=self.get(aid);path=self.root/(aid+'.bin');fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            i=os.fstat(f.fileno())
            if not stat.S_ISREG(i.st_mode) or i.st_uid!=os.getuid() or i.st_size!=item['bytes']:raise ValueError('attachment_identity_changed')
            data=f.read(LIMIT+1)
        if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('attachment_hash_changed')
        return item,data

    def context(self,aid):
        item,data=self.read(aid)
        if item['mime']=='text/plain':return item,data.decode('utf-8')
        if item['mime'].startswith('audio/') and item['metadata'].get('transcript'):return item,item['metadata']['transcript']
        raise ValueError('selected_text_model_cannot_understand_this_attachment')

    def transcribe(self,aid):
        from workspace.voice import transcribe
        item,_=self.read(aid)
        if not item['mime'].startswith('audio/'):raise ValueError('audio_attachment_required')
        metadata=transcribe(self.root/(aid+'.bin'))
        with self.c.lock,self.c.db:self.c.db.execute('UPDATE attachments SET metadata=? WHERE id=?',(json.dumps(metadata),aid))
        return self.get(aid)
