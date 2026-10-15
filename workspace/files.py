"""Directory-fd anchored UTF-8 data access, shared by import and review."""
import hashlib
import os
from pathlib import PurePosixPath
import stat

MAX_FILE = 1024 * 1024
DENIED = {'.git', '.ssh', '.gnupg', '.hermes', '.codex', '.paseo', '.env',
          'node_modules', '__pycache__', 'private-state', 'answer_keys.json',
          'grading.py', 'scoring.py', 'id_rsa', 'id_ed25519', 'credentials.json', 'auth.json'}
DENIED.update({'secrets.json','secrets.yaml','secrets.yml','token.json','tokens.json','credentials'})


def parts(name):
    if type(name) is not str or not name or len(name.encode()) > 512 or '\\' in name or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('invalid_relative_path')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') or p in DENIED or p.startswith('.') or p.endswith(('.pem','.key','.p12','.pfx'))
                                 for p in name.split('/')):
        raise ValueError('path_outside_workspace')
    return path.parts


def mount_id(fd):
    with open('/proc/self/fdinfo/'+str(fd)) as source:
        return next(line for line in source if line.startswith('mnt_id:'))


class Files:
    def __init__(self, root):
        root=os.path.abspath(root)
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for component in root.split('/')[1:]:
                if not component:continue
                child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=child
            self.fd=fd
        except BaseException:os.close(fd);raise
        self.device = os.fstat(self.fd).st_dev
        self.mount = mount_id(self.fd)

    def close(self):
        os.close(self.fd)

    def parent(self, name, create=False):
        components = parts(name)
        fd = os.dup(self.fd)
        try:
            for component in components[:-1]:
                if create:
                    try: os.mkdir(component, 0o700, dir_fd=fd)
                    except FileExistsError: pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = child
                if os.fstat(fd).st_dev != self.device or mount_id(fd) != self.mount:
                    raise ValueError('mount_escape')
            return fd, components[-1]
        except BaseException:
            os.close(fd)
            raise

    def read(self, name):
        parent, leaf = self.parent(name)
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE:
                    raise ValueError('regular_single_link_bounded_file_required')
                if before.st_dev != self.device or mount_id(fd) != self.mount:
                    raise ValueError('mount_escape')
                chunks=[];size=0
                while block := os.read(fd, 65536):
                    size += len(block)
                    if size > MAX_FILE: raise ValueError('file_limit')
                    chunks.append(block)
                after = os.fstat(fd)
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError('file_changed_during_read')
                data = b''.join(chunks); text = data.decode('utf-8')
                if '\0' in text: raise ValueError('binary_file')
                return {'text': text, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            finally: os.close(fd)
        finally: os.close(parent)

    def write(self, name, text, expected=None, preserve_mode=False):
        if type(text) is not str or '\0' in text or len(text.encode()) > MAX_FILE:
            raise ValueError('bounded_UTF8_text_required')
        parent, leaf = self.parent(name, create=True)
        temporary = '.write-'+os.urandom(12).hex()
        try:
            if expected is not None:
                if self.read(name)['sha256'] != expected: raise ValueError('file_drift')
                metadata=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                if metadata.st_uid!=os.getuid():raise ValueError('normal_user_owned_file_required')
            else:
                try: os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError: pass
                else: raise ValueError('expected_hash_required_for_existing_file')
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                if preserve_mode and expected is not None:os.fchmod(fd,metadata.st_mode&0o777)
                with os.fdopen(fd, 'wb') as out: out.write(text.encode()); out.flush(); os.fsync(out.fileno())
                # Repeat drift check immediately before the anchored atomic rename.
                if expected is not None and self.read(name)['sha256'] != expected: raise ValueError('file_drift')
                if expected is None:
                    os.link(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                    os.unlink(temporary, dir_fd=parent)
                else: os.rename(temporary, leaf, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try: os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError: pass
        finally: os.close(parent)
        return self.read(name)

    def tree(self):
        result=[];nodes=0;bytes_seen=0
        def visit(fd, prefix):
            nonlocal nodes,bytes_seen
            for name in sorted(os.listdir(fd)):
                nodes+=1
                if nodes>4000:raise ValueError('tree_node_limit')
                relative=prefix+name
                try: parts(relative)
                except ValueError: continue
                info=os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child=os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        if mount_id(child)!=self.mount: raise ValueError('mount_escape')
                        visit(child, relative+'/')
                    finally: os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    bytes_seen+=info.st_size
                    if bytes_seen>64*1024*1024:raise ValueError('tree_byte_limit')
                    self.read(relative);result.append(relative)
                    if len(result)>2000:raise ValueError('file_count_limit')
                else: raise ValueError('unsupported_file_type')
        visit(self.fd,'')
        return result
