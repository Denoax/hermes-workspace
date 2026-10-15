"""Real production permission decisions; only new, positively tracked test records."""
import argparse,hashlib,json,os,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc

def uid():return uuid.uuid4().hex

def main():
 p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--resume',action='store_true');args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
 report={'status':'IN_PROGRESS','scope':'actual pin and authenticated production RPC; operator decisions via trusted UI pointer','checks':{},'sessions':[],'actions':[]};b=ProductionPin()
 def save(): (args.output/'permissions.json').write_text(json.dumps(report,indent=2)+'\n')
 def denied(method,fields):
  try:rpc(b,method,fields)
  except RuntimeError as e:return str(e)
  raise AssertionError('protected operation unexpectedly succeeded: '+method)
 def button(text,scope='document'):
  key='v4-'+uid();b.evaluate("(()=>{const e=[..."+scope+".querySelectorAll('button')].find(e=>e.textContent.trim()==="+json.dumps(text)+");if(!e)throw Error('button missing');e.scrollIntoView({block:'center'});e.dataset.probe="+json.dumps(key)+"})()");b.click('[data-probe="'+key+'"]')
 def change(selector,value):b.evaluate("(()=>{const e=document.querySelector("+json.dumps(selector)+");e.value="+json.dumps(value)+";e.dispatchEvent(new Event('change',{bubbles:true}))})()")
 def request(action,sid=None):
  row=rpc(b,'permissions.request',{'session_id':sid or report['session_id'],'run_id':None,'request_id':uid(),'action':action});report['actions'].append(row['id']);save();return row
 def choose(row,decision):
  b.wait("[...document.querySelectorAll('.approval-card')].some(e=>e.textContent.includes("+json.dumps(row['action'].get('path',row['action'].get('query','')))+")&&e.dataset.state==='pending')",timeout=12)
  key='a'+uid();b.evaluate("(()=>{const e=[...document.querySelectorAll('.approval-card')].find(e=>e.dataset.state==='pending'&&e.textContent.includes("+json.dumps(row['action'].get('path',row['action'].get('query','')))+"));e.scrollIntoView({block:'center'});e.dataset.probe="+json.dumps(key)+"})()")
  b.capture(args.output/(row['action']['type'].replace('.','-')+'-approval.png'))
  button(decision,"document.querySelector('[data-probe=\""+key+"\"]')")
  end=time.monotonic()+35
  while time.monotonic()<end:
   actions=rpc(b,'permissions.read',{'session_id':report['session_id']})['actions'];current=next(a for a in actions if a['id']==row['id'])
   if current['state'] in ('completed','denied','failed','revoked'):return current
   time.sleep(.4)
  raise RuntimeError('approval result deadline')
 try:
  if args.resume:
   report=json.loads((args.output/'permissions.json').read_text());report.update(status='IN_PROGRESS');report.pop('error',None)
   state=rpc(b,'view.read',{});state.update(project_id=report['project_id'],session_id=report['session_id'],arm='normal');rpc(b,'view.write',{'state':state})
   b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'")
   policy=rpc(b,'permissions.read',{'session_id':report['session_id']});assert policy['mode']=='chat_only'and not policy['grants'];report['checks']['revocation_removed_session_grant']=True
   change('#permissions-mode','ask');b.wait("document.querySelector('#permissions-mode').value==='ask'")
  else:
   report['pin']=b.identity;b.click('#new-session');change('#model-picker','normal');b.click('[aria-label="New folder"]');b.wait("!!document.querySelector('dialog input')")
   b.click('dialog input');b.call('Input.insertText',{'text':'Hermes v4 verification copies'});button('Create folder',"document.querySelector('dialog')");b.wait("!document.querySelector('dialog[open]')")
   change('#permissions-mode','ask');b.wait("document.querySelector('#permissions-mode')?.value==='ask'",timeout=15)
   view=rpc(b,'view.read',{});sid=view['session_id'];project=view['project_id'];assert sid and project;report.update(session_id=sid,project_id=project);report['sessions'].append(sid);save()
   # Modes are actual UI choices. A direct dispatcher attempt cannot override them.
   change('#permissions-mode','chat_only');b.wait("document.querySelector('#permissions-mode').value==='chat_only'")
   row=request({'type':'workspace.write','path':'forbidden.txt','text':'must not exist','expected_sha256':None});assert row['state']=='denied'
   report['checks']['chat_only_dispatch_denied']=denied('actions.execute',{'session_id':sid,'action_id':row['id']})
   report['checks']['legacy_API_denied']=denied('workspace.file.write',{'project_id':project,'relative_path':'bypass.txt','text':'denied','expected_sha256':None})
   report['checks']['microphone_app_denied']=denied('recording.authorize',{'session_id':sid})
   change('#permissions-mode','ask');b.wait("document.querySelector('#permissions-mode').value==='ask'")
   row=request({'type':'workspace.write','path':'denied.txt','text':'must not exist','expected_sha256':None});rejected=choose(row,'Deny');assert rejected['state']=='denied'
   report['checks']['explicit_deny_enforced']=denied('actions.execute',{'session_id':sid,'action_id':row['id']})
   text='print("hermes-v4-local-copy")\n';row=request({'type':'workspace.write','path':'program.py','text':text,'expected_sha256':None});written=choose(row,'Allow once');assert written['state']=='completed',written
   assert written['result']['sha256']==hashlib.sha256(text.encode()).hexdigest();report['checks']['allow_once_workspace_write']=written
   replay=rpc(b,'actions.execute',{'session_id':sid,'action_id':row['id']});assert replay['result']==written['result'];report['checks']['execution_replay_stable']=True
   b.key('Escape');row=request({'type':'workspace.read','path':'program.py'});read=choose(row,'Allow for this session');assert read['state']=='completed' and read['result']['text']==text
   report['checks']['scoped_session_read']=True;b.key('Escape')
   second=request({'type':'workspace.read','path':'program.py'});assert second['state']=='allowed';assert rpc(b,'actions.execute',{'session_id':sid,'action_id':second['id']})['state']=='completed'
   other=rpc(b,'session.create',{'project_id':project,'arm':'normal'})['id'];report['sessions'].append(other);save()
   report['checks']['wrong_conversation_denied']=denied('actions.execute',{'session_id':other,'action_id':second['id']})
   report['checks']['path_escape_denied']=denied('permissions.request',{'session_id':sid,'run_id':None,'request_id':uid(),'action':{'type':'workspace.read','path':'../escape.txt'}})
   workspace=Path.home()/'HermesLab/projects'/project/'workspace';outside=args.output/'outside-test.txt';outside.write_text('owned escape fixture\n');(workspace/'escape-link.txt').symlink_to(outside)
   try:report['checks']['symlink_escape_denied']=denied('permissions.request',{'session_id':sid,'run_id':None,'request_id':uid(),'action':{'type':'workspace.read','path':'escape-link.txt'}})
   finally:(workspace/'escape-link.txt').unlink();outside.unlink()
   b.click('#settings-toggle');b.wait("document.querySelector('dialog h2')?.textContent==='Settings'");button('Revoke session grants',"document.querySelector('dialog')");b.key('Escape')
   row=request({'type':'workspace.read','path':'program.py'});assert row['state']=='denied';report['checks']['revocation_removed_session_grant']=True
   change('#permissions-mode','ask');b.wait("document.querySelector('#permissions-mode').value==='ask'")
  search=request({'type':'search.wikipedia','query':'KVM Linux'});searched=choose(search,'Allow once');report['checks']['actual_Wikipedia_search']=searched
  assert searched['state']=='completed' and searched['result']['sources'],searched
  b.capture(args.output/'permissions-result.png');report['status']='PASS'
 except Exception as error:
  report.update(status='FAIL',error=str(error));b.capture(args.output/'permissions-failure.png');raise
 finally:save();b.close()
 print(json.dumps({'status':report['status'],'checks':len(report['checks'])}))
if __name__=='__main__':main()
