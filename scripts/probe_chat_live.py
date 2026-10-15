"""Real local inference through the authenticated rendered UI, isolated catalog.

Use with serve_chat_acceptance.py. This script never substitutes model replies.
Only the harmless generated test conversation is written into the evidence.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workspace import launcher
from workspace.parity_browser import Browser

def rpc(browser, method, fields):
    for attempt in range(3):
        try:return browser.evaluate('window.__liveRpc('+json.dumps(method)+','+json.dumps(fields)+')')
        except RuntimeError as error:
            if 'rate_limit' not in str(error) or attempt==2:raise
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--arm', choices=['normal', 'abliterated'], required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    launcher.ORIGIN = 'http://127.0.0.1:18793'
    browser = Browser('local-chat-live-' + args.arm, fixture=False,quiet=True)
    def prepare():
        browser.evaluate("(async()=>{const b=await(await fetch('/hermes-workspace/api/bootstrap')).json();window.__liveRpc=async(method,fields)=>{const r=await fetch('/hermes-workspace/api/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Hermes-CSRF':b.csrf},body:JSON.stringify({version:1,method,fields})});const d=await r.json();if(d.error)throw Error(d.error);return d.result;};})()")
    prepare()
    evidence = {'kind': 'actual installed model; rendered UI Send; isolated catalog',
                'arm': args.arm, 'runs': [], 'status': 'IN_PROGRESS'}
    target = args.output / (args.arm + '.json')

    def save():
        target.write_text(json.dumps(evidence, indent=2) + '\n')

    def send(prompt):
        browser.click('#prompt')
        browser.call('Input.insertText', {'text': prompt})
        before = rpc(browser, 'session.list', {})
        browser.click('#send')
        started = time.monotonic()
        sid = None
        run = None
        first_seen = None
        snapshots = []
        deadline = started + 330
        progress = started
        while time.monotonic() < deadline:
            sessions = rpc(browser, 'session.list', {})
            sid = sessions[0]['id'] if sessions else None
            if sid:
                snap = rpc(browser, 'chat.snapshot', {'session_id': sid})
                run = snap['runs'][-1] if snap['runs'] else None
                answer = ''.join(m['text'] for m in snap['messages'] if m['role'] == 'assistant' and run and m.get('job') == run['id'])
                if answer and first_seen is None:
                    first_seen = time.monotonic() - started
                if answer and (not snapshots or len(answer) > snapshots[-1]['characters']):
                    snapshots.append({'seconds': round(time.monotonic()-started, 3), 'characters': len(answer)})
                if run and run['settings']['prompt_sha256']==hashlib.sha256(prompt.encode()).hexdigest() and run['state'] in ('completed', 'failed', 'cancelled'):
                    result = {'prompt': prompt, 'run': run, 'answer': answer,
                              'observed_first_text_seconds': first_seen,
                              'observed_total_seconds': time.monotonic()-started,
                              'stream_samples': snapshots}
                    evidence['runs'].append(result)
                    save()
                    print(json.dumps({'arm': args.arm, 'state': run['state'], 'answer': answer[:240], 'error': run.get('error')}), flush=True)
                    if run['state'] != 'completed':
                        raise RuntimeError('live_' + run['state'] + ':' + str(run.get('error')))
                    browser.wait("!document.querySelector('#cancel-response')")
                    return sid, result
            if time.monotonic()-progress > 10:
                print(json.dumps({'arm': args.arm, 'state': run['state'] if run else 'awaiting_ui', 'elapsed': int(time.monotonic()-started)}), flush=True)
                progress = time.monotonic()
            time.sleep(.7)
        raise TimeoutError('actual_chat_deadline')

    try:
        browser.metric(1440, 900)
        browser.click('#new-session')
        time.sleep(1)
        browser.evaluate("(()=>{const e=document.querySelector('#model-picker');e.value="+json.dumps(args.arm)+";e.dispatchEvent(new Event('change',{bubbles:true}))})()")
        nonce = 'cedar-' + str(time.time_ns())[-7:]
        sid, first = send('Remember this harmless verification word: '+nonce+'. Reply with that word and one short greeting.')
        assert nonce in first['answer'], 'first_answer_semantics_failed'
        browser.call('Page.reload')
        browser.wait("document.getElementById('connection')?.textContent==='Connected'")
        prepare()
        time.sleep(1)
        browser.wait("document.querySelector('.message.assistant')?.textContent.includes("+json.dumps(nonce)+")")
        sid2, second = send('What exact verification word did I ask you to remember? Reply with only the word.')
        assert sid == sid2 and nonce in second['answer'], 'contextual_followup_semantics_failed'
        assert len(rpc(browser,'chat.snapshot',{'session_id':sid})['runs']) == 2, 'duplicate_run'
        browser.capture(args.output/(args.arm+'-conversation.png'))
        evidence['reload_persistence'] = True
        evidence['contextual_followup'] = True
        evidence['no_duplicate_runs'] = True
        evidence['status'] = 'PASS'
    except Exception as error:
        evidence['status'] = 'FAIL'
        evidence['error'] = str(error)
        raise
    finally:
        save()
        browser.close()


if __name__ == '__main__':
    main()
