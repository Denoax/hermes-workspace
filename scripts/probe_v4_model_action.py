"""A real model proposes a scoped read; trusted UI approval supplies authority."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc


def main():
 parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args();args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
 known=json.loads((args.output.parent/'permissions/permissions.json').read_text());sid=known['session_id'];project=known['project_id']
 report={'status':'IN_PROGRESS','session_id':sid,'project_id':project,'scope':'actual model tool delta, production pin18791, human-facing approval UI','runs':[]};b=ProductionPin()
 def save():(args.output/'model-action.json').write_text(json.dumps(report,indent=2)+'\n')
 def send(prompt):
  before={r['id']for r in rpc(b,'chat.snapshot',{'session_id':sid})['runs']}
  b.click('#prompt');b.key('a','KeyA',2);b.call('Input.insertText',{'text':prompt});b.wait("!document.querySelector('#send').disabled");b.click('#send');start=time.monotonic();end=start+180
  while time.monotonic()<end:
   snap=rpc(b,'chat.snapshot',{'session_id':sid});rows=[r for r in snap['runs']if r['id']not in before]
   if rows and rows[-1]['state']in('completed','failed','cancelled'):
    run=rows[-1];report['runs'].append(run);save();assert run['state']=='completed',run
    return snap,run
   time.sleep(.3)
  raise TimeoutError('actual model action turn deadline')
 try:
  report['pin']=b.identity;state=rpc(b,'view.read',{});state.update(project_id=project,session_id=sid,arm='normal');rpc(b,'view.write',{'state':state});b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'")
  b.wait("document.querySelector('#permissions-mode')?.value==='ask'")
  prior={a['id']for a in rpc(b,'permissions.read',{'session_id':sid})['actions']}
  snap,run=send('Use the workspace_read function to read program.py in this selected workspace. Do not invent its contents before reading the file.')
  actions=[a for a in rpc(b,'permissions.read',{'session_id':sid})['actions']if a['id']not in prior];assert len(actions)==1 and actions[0]['type']=='workspace.read',actions
  action=actions[0];assert action['state']=='pending' and action['run_id']==run['id'];report['model_proposal']=action;save()
  b.wait("[...document.querySelectorAll('.approval-card')].some(e=>e.dataset.state==='pending'&&e.textContent.includes('program.py'))")
  b.evaluate("(()=>{const card=[...document.querySelectorAll('.approval-card')].find(e=>e.dataset.state==='pending'&&e.textContent.includes('program.py'));const button=[...card.querySelectorAll('button')].find(e=>e.textContent.trim()==='Allow once');button.dataset.probe='model-allow-once';button.scrollIntoView({block:'center'})})()")
  b.capture(args.output/'model-read-awaiting-approval.png');b.click('[data-probe="model-allow-once"]')
  deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   result=next(a for a in rpc(b,'permissions.read',{'session_id':sid})['actions']if a['id']==action['id'])
   if result['state']=='completed':break
   time.sleep(.2)
  assert result['state']=='completed',result;report['actual_read_receipt']=result;b.key('Escape')
  snap,run=send('What exact print statement did the real file read return? Reply with that statement only.')
  answer=''.join(m['text']for m in snap['messages']if m['role']=='assistant'and m.get('job')==run['id']);report['answer']=answer
  assert 'hermes-v4-local-copy'in answer,'model did not use the actual observation'
  b.capture(args.output/'actual-tool-observation-answer.png');report['status']='PASS'
 except Exception as error:
  report.update(status='FAIL',error=str(error));b.capture(args.output/'model-action-failure.png');raise
 finally:save();b.close()
 print(json.dumps({'status':report['status'],'turns':len(report['runs'])}))
if __name__=='__main__':main()
