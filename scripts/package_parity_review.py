"""Complete allowlisted UI review ZIP, with safe extraction and every payload hash."""
import argparse,hashlib,json,re,stat,tempfile,zipfile
from pathlib import Path,PurePosixPath
from package_review import source_files,SUFFIXES
NAME='MANI_HERMES_PORTFOLIO_PARITY_REVIEW'
TEXT={'.py','.js','.mjs','.ts','.css','.html','.md','.txt','.json','.log','.csv','.patch','.sh','.svg','.c','.yaml','.jsonl'}
BINARY={'.png','.mp4','.webm','.ttf','.woff2','.wav'}

def verify(archive,destination):
 with zipfile.ZipFile(archive)as z:
  names=z.namelist()
  if len(names)!=len(set(names))or z.testzip():raise ValueError('duplicate_or_CRC_error')
  for entry in z.infolist():
   p=PurePosixPath(entry.filename)
   if p.is_absolute()or'..'in p.parts or stat.S_ISLNK(entry.external_attr>>16):raise ValueError('unsafe_member')
  z.extractall(destination);root=Path(destination)/NAME;verified=set()
  for line in(root/'SHA256SUMS.txt').read_text().splitlines():
   expected,name=line.split('  ',1);p=PurePosixPath(name)
   if p.is_absolute()or'..'in p.parts or not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('unsafe_checksum')
   if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:raise ValueError('payload_drift:'+name)
   verified.add(NAME+'/'+name)
  if verified!=set(names)-{NAME+'/SHA256SUMS.txt'}:raise ValueError('unchecked_payload')
  return root,len(verified)

def package(project,review,output):
 payload={}
 for path,relative in source_files(project):payload['source/'+relative.as_posix()]=path.read_bytes()
 for directory in ['workspace','tests','scripts','native']:
  for path in sorted((project/directory).rglob('*')):
   relative=path.relative_to(project)
   if not path.is_file()or path.is_symlink()or any(p in {'evidence','__pycache__','node_modules','.git'}for p in relative.parts):continue
   if path.suffix in TEXT or directory=='workspace'and path.suffix in BINARY:payload['source/'+relative.as_posix()]=path.read_bytes()
 for path in sorted((project/'results').rglob('*')):
  if path.is_file()and not path.is_symlink()and path.suffix in SUFFIXES:payload['results/'+path.relative_to(project/'results').as_posix()]=path.read_bytes()
 # Explicit final evidence; exploratory and misleadingly named draft captures
 # stay private. Corrected failures are preserved separately in history/.
 prefixes=('files-panel-','appearance-','details-','project-dialog-','settings-light-', 'compositor-','hermes-','portfolio-dark-','portfolio-light-','native-edge-dpr')
 names={'pointer-parity.json','native-compositor.json','cost.json','motion.json','reference-comparison.json','sound-audition.json','preservation.json','native-pin-final.json','motion-light-settings.png','motion-files.png','unedited-motion.mp4','unedited-motion-with-audio.mp4'}
 for path in sorted((project/'workspace/evidence/parity').iterdir()):
  if path.name in names or path.name.startswith(prefixes)and path.suffix=='.png':payload['evidence/'+path.name]=path.read_bytes()
 for path in sorted(review.rglob('*')):
  if path.is_file()and not path.is_symlink():
   if path.suffix not in TEXT|BINARY and path.name!='desktop-entry.before':raise ValueError('unlisted_review_type')
   payload[path.relative_to(review).as_posix()]=path.read_bytes()
 for name,data in payload.items():
  if len(data)>64*1024*1024:raise ValueError('member_limit')
  if PurePosixPath(name).suffix in BINARY:continue
  text=data.decode('utf-8')
  if re.search(r'(?m)^-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----',text):raise ValueError('private_key_detected')
  if any(x in name.lower()for x in ['client-cookie','catalog.sqlite','browser-profile','.env']):raise ValueError('private_path')
 source={n.removeprefix('source/'):hashlib.sha256(d).hexdigest()for n,d in sorted(payload.items())if n.startswith('source/')}
 tree=hashlib.sha256(''.join(h+'  '+n+'\n'for n,h in source.items()).encode()).hexdigest()
 payload['implementation.json']=(json.dumps({'source_tree_sha256':tree,'source_files':source,'scope':'Current complete allowlisted source; baseline Git HEAD is not a commit of these dirty files.','private_state_exported':False},indent=2)+'\n').encode()
 payload['SHA256SUMS.txt']=''.join(hashlib.sha256(d).hexdigest()+'  '+n+'\n'for n,d in sorted(payload.items())).encode()
 with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
  for name,data in sorted(payload.items()):
   info=zipfile.ZipInfo(NAME+'/'+name);info.external_attr=(stat.S_IFREG|(0o700 if name=='source/labctl'else 0o600))<<16;info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
 with tempfile.TemporaryDirectory(prefix='parity-verify-')as d:_,count=verify(output,d)
 return {'ZIP':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'verified_payloads':count,'source_tree_sha256':tree}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(package(a.project,a.review,a.output),indent=2))
