"""Actual-pin streaming/cancellation and service-death retry, never a fixture server."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc
from workspace.models import normal_identity
from workspace.server import normal_profile_unchanged

def main():
 p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--case',choices=('cancel','retry'),required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
 report={'status':'IN_PROGRESS','case':args.case,'scope':'actual production pin18791; trusted Send/Cancel/Retry','samples':[]};target=args.output/(args.case+'.json');b=ProductionPin()
 def save():target.write_text(json.dumps(report,indent=2)+'\n')
 def snapshot():return rpc(b,'chat.snapshot',{'session_id':report['session_id']})
 def latest():
  snap=snapshot();run=snap['runs'][-1];answer=''.join(m['text'] for m in snap['messages']if m['role']=='assistant'and m.get('job')==run['id']);return snap,run,answer
 try:
  report['pin']=b.identity;b.click('#new-session');time.sleep(.3)
  arm='normal' if args.case=='cancel'else'abliterated'
  b.evaluate("(()=>{const e=document.querySelector('#model-picker');e.value="+json.dumps(arm)+";e.dispatchEvent(new Event('change',{bubbles:true}))})()")
  prompt=('Count from 1 to 10000, with one integer per line. Do not abbreviate or stop early.' if args.case=='cancel'else 'Reply with exactly: production-retry-preserved')
  b.click('#prompt');b.call('Input.insertText',{'text':prompt});b.wait("!document.querySelector('#send').disabled");b.click('#send');start=time.monotonic()
  # A fresh, unique prompt identifies this positively owned test turn.
  digest=hashlib.sha256(prompt.encode()).hexdigest();deadline=start+300
  while time.monotonic()<deadline:
   view=rpc(b,'view.read',{});sid=view.get('session_id')
   if sid:
    snap=rpc(b,'chat.snapshot',{'session_id':sid})
    matches=[r for r in snap['runs']if r['settings']['prompt_sha256']==digest]
    if matches:report.update(session_id=sid,run_id=matches[-1]['id']);save();break
   time.sleep(.1)
  else:raise TimeoutError('no admitted production run')
  if args.case=='retry':
   snap,run,answer=latest();assert not answer and run['state']not in('completed','failed','cancelled'),run
   report['before_restart']=run
   subprocess.run(['systemctl','--user','restart','hermes-workspace.service'],check=True,timeout=25)
   b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'",timeout=30)
   deadline=time.monotonic()+210
   while time.monotonic()<deadline:
    ready=rpc(b,'readiness.read',{});snap,run,answer=latest()
    if run['state']=='failed'and ready['state']=='ready':break
    time.sleep(.5)
   assert run['state']=='failed'and not answer,run
   report['genuine_failure']=run;report['before_retry_message_count']=len(snap['messages']);save()
   b.wait("[...document.querySelectorAll('button')].some(e=>e.textContent.trim()==='Retry this turn'&&!e.disabled)",timeout=20)
   b.evaluate("[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='Retry this turn').dataset.probe='retry-real'");b.click('[data-probe="retry-real"]')
   # The click starts an async request. Observe its acknowledgement before
   # treating the preserved pre-retry failed state as the retry's outcome.
   acknowledged=time.monotonic()+12
   while time.monotonic()<acknowledged:
    _,changed,_=latest()
    if changed['created']!=run['created']:break
    time.sleep(.1)
   else:raise RuntimeError('retry_not_accepted')
  deadline=time.monotonic()+330;last=0;cancelled_at=None
  while time.monotonic()<deadline:
   snap,run,answer=latest();now=time.monotonic()-start
   if not report['samples']or report['samples'][-1]['characters']!=len(answer):report['samples'].append({'seconds':round(now,3),'characters':len(answer),'state':run['state']});save()
   if args.case=='cancel'and len(answer)>45 and run['state']=='generating'and cancelled_at is None:
    b.wait("!!document.querySelector('#cancel-response')");b.capture(args.output/'streaming-before-cancel.png');b.click('#cancel-response');cancelled_at=time.monotonic();report['cancel_at_seconds']=now
   if run['state']in('completed','failed','cancelled'):break
   if time.monotonic()-last>10:print(json.dumps({'case':args.case,'state':run['state'],'characters':len(answer),'seconds':int(now)}),flush=True);last=time.monotonic()
   time.sleep(.15 if args.case=='cancel'else .5)
  report['final_run']=run;report['answer_prefix']=answer[:300];report['activity']=snap.get('activity',[]);save()
  if args.case=='cancel':
   assert cancelled_at and run['state']=='cancelled',run;report['cancel_ack_seconds']=time.monotonic()-cancelled_at
   assert len([s for s in report['samples']if s['characters']])>=2,'no real stream increments observed'
  else:
   assert run['state']=='completed'and 'production-retry-preserved'in answer,run
   assert run['id']==report['run_id']and len(snap['runs'])==1 and len([m for m in snap['messages']if m['role']=='user'])==1,'retry duplicated the turn'
   report['same_turn_no_duplicate']=True
  report['normal_after']=normal_identity();assert normal_profile_unchanged();report['four_normal_hashes_unchanged']=True
  b.capture(args.output/(args.case+'-production.png'));report['status']='PASS'
 except Exception as error:
  report.update(status='FAIL',error=str(error));b.capture(args.output/(args.case+'-failure.png'));raise
 finally:save();b.close()
 print(json.dumps({'case':args.case,'status':report['status']}))
if __name__=='__main__':main()
