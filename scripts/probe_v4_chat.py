"""Three connected turns via the real Hermes pin. RPCs observe, never send."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_local_chat import rpc as request_read


def rpc(browser,method,fields):
    for attempt in range(4):
        try:return request_read(browser,method,fields)
        except RuntimeError as error:
            if 'rate_limit' not in str(error) or attempt==3:raise
            time.sleep(.65*(attempt+1))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--arm',choices=('normal','abliterated'),required=True)
    parser.add_argument('--resume-failed',action='store_true')
    parser.add_argument('--turns',type=int,choices=(1,3),default=3)
    args=parser.parse_args();args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
    evidence={'status':'IN_PROGRESS','arm':args.arm,'scope':'actual desktop pin, production catalog and port18791; no isolated server','runs':[]}
    target=args.output/(args.arm+'.json')
    def save():target.write_text(json.dumps(evidence,indent=2)+'\n')
    prior=json.loads(target.read_text()) if args.resume_failed else None
    b=ProductionPin()
    try:
        evidence['pin']=b.identity
        ready=rpc(b,'readiness.read',{});evidence['initial_readiness']=ready
        if ready['state']!='ready' and not prior:raise RuntimeError('production_admission_not_ready')
        if prior:
            state=rpc(b,'view.read',{});state.update(project_id=next(s['project'] for s in rpc(b,'session.list',{}) if s['id']==prior['session_id']),session_id=prior['session_id'],arm=args.arm)
            rpc(b,'view.write',{'state':state});b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'")
            evidence['genuine_failed_attempt']=prior['runs'][0]['run']
        else:b.click('#new-session')
        existing_sessions={s['id'] for s in rpc(b,'session.list',{})}
        # Model selection uses the actual UI change handler; Send below uses
        # trusted pointer dispatch. Identity is attested by the native lease.
        b.evaluate("(()=>{const e=document.querySelector('#model-picker');e.value="+json.dumps(args.arm)+";e.dispatchEvent(new Event('change',{bubbles:true}))})()")
        nonce=prior['verification_word'] if prior else 'maple-'+str(time.time_ns())[-8:]
        prompts=[f'Remember this harmless verification word: {nonce}. Reply with only that word.',
                 'What exact verification word did I ask you to remember? Reply with only the word.',
                 'Reply with that same verification word followed by :3. No extra explanation.'][:args.turns]
        evidence.update(verification_word=nonce,test_prompts=prompts);save()
        sid=prior['session_id'] if prior else None
        for index,prompt in enumerate(prompts):
            if index:
                b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'")
                b.wait("!!document.querySelector('.message.assistant')")
            started=time.monotonic()
            if prior and index==0:
                current=rpc(b,'chat.snapshot',{'session_id':sid})['runs'][0]
                if current['state']=='failed':
                    b.wait("[...document.querySelectorAll('button')].some(e=>e.textContent.trim()==='Retry this turn'&&!e.disabled)",timeout=20)
                    b.evaluate("[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='Retry this turn').dataset.probe='retry-real'")
                    b.click('[data-probe="retry-real"]')
                    until=time.monotonic()+12
                    while time.monotonic()<until:
                        changed=rpc(b,'chat.snapshot',{'session_id':sid})['runs'][0]
                        if changed['created']!=current['created']:break
                        time.sleep(.1)
                    else:raise RuntimeError('retry_not_accepted')
                else:evidence['reconnected_existing_retry']=True
            else:
                b.click('#prompt');b.call('Input.insertText',{'text':prompt})
                b.wait("!document.querySelector('#send').disabled",timeout=20)
                b.click('#send')
                if index==0:b.key('Enter')  # Actual repeated Send cannot duplicate.
            digest=hashlib.sha256(prompt.encode()).hexdigest();deadline=started+330
            samples=[];states=[];first=None;row=None;answer='';last_progress=started
            while time.monotonic()<deadline:
                if sid is None:
                    view=rpc(b,'view.read',{});candidate=view.get('session_id')
                    if candidate and candidate not in existing_sessions:sid=candidate
                if sid:
                    snap=rpc(b,'chat.snapshot',{'session_id':sid})
                    matches=[r for r in snap['runs'] if r['settings']['prompt_sha256']==digest]
                    if matches:
                        row=matches[-1]
                        answer=''.join(m['text'] for m in snap['messages'] if m['role']=='assistant' and m.get('job')==row['id'])
                        now=time.monotonic()-started
                        if not states or states[-1]['state']!=row['state']:states.append({'state':row['state'],'seconds':round(now,3)})
                        if answer and first is None:first=now
                        if answer and (not samples or samples[-1]['characters']!=len(answer)):samples.append({'seconds':round(now,3),'characters':len(answer)})
                        if row['state'] in ('completed','failed','cancelled'):break
                if time.monotonic()-last_progress>10:
                    print(json.dumps({'arm':args.arm,'turn':index+1,'state':row['state'] if row else 'awaiting UI','elapsed':int(time.monotonic()-started)}),flush=True);last_progress=time.monotonic()
                time.sleep(.5)
            else:raise TimeoutError('production_turn_deadline')
            result={'prompt':prompt,'answer':answer,'run':row,'states':states,'observed_first_text_seconds':first,'observed_total_seconds':time.monotonic()-started,'stream_samples':samples,'activity':snap.get('activity',[])}
            evidence['runs'].append(result);evidence['session_id']=sid;save()
            print(json.dumps({'arm':args.arm,'turn':index+1,'state':row['state'],'answer':answer[:180],'error':row.get('error')}),flush=True)
            assert row['state']=='completed',row.get('error')
            assert nonce in answer,'production_answer_context_semantics_failed'
            assert row['identity']['arm']==args.arm,'wrong_native_model_arm'
            if index==2:assert '3' in answer,'third_turn_semantics_failed'
            if prior and index==0:
                assert row['id']==prior['runs'][0]['run']['id'],'retry_changed_run_id'
                evidence['same_failed_turn_retried_without_duplicate']=True
            assert len(rpc(b,'chat.snapshot',{'session_id':sid})['runs'])==index+1,'duplicated_production_turn'
            b.wait("!document.querySelector('#cancel-response')")
        b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'")
        b.wait("document.querySelector('.message.assistant')?.textContent.includes("+json.dumps(nonce)+")")
        # Use the real navigation filter so public evidence never includes an
        # unrelated conversation title. This changes presentation only.
        b.click('.rail-search input');b.key('a','KeyA',2)
        b.call('Input.insertText',{'text':nonce})
        b.wait("[...document.querySelectorAll('.session-row>button:first-child')].every(e=>e.textContent.includes("+json.dumps(nonce)+"))")
        evidence['capture_navigation_filter']=nonce
        b.capture(args.output/(args.arm+'-production.png'))
        evidence.update(status='PASS',reload_persistence=True,connected_turns=len(prompts),no_duplicate_runs=True)
    except Exception as error:
        evidence.update(status='FAIL',error=str(error))
        try:b.capture(args.output/(args.arm+'-failure.png'))
        except Exception:pass
        raise
    finally:save();b.close()


if __name__=='__main__':main()
