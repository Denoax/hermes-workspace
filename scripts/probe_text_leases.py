"""Actual idle native lease expiry and active normal-model owner-death revocation."""
import argparse,http.client,json,os,subprocess,sys,time,uuid,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.native_client import NativeClient
from workspace.models import normal_identity


def child(mode):
    native=NativeClient(timeout=310);job=uuid.uuid4().hex;started=time.monotonic();proof,transport=native.text_connection(job,'normal')
    transport.settimeout(45)
    connection=http.client.HTTPConnection('admitted-local-normal',timeout=45);connection.sock=transport
    if mode=='heartbeat-loss':
        connection.request('GET','/health');response=connection.getresponse();assert json.loads(response.read())['status']=='ok'
        time.sleep(31);connection.close();ack=native.call('chat_release',job_id=job)
        print(json.dumps({'job_id':job,'actual_text_characters':0,'case':'idle lease expiry; no compute claim','revocation_seconds':time.monotonic()-started,'ack':ack}),flush=True);return
    payload={'model':proof['identity']['model_alias'],'messages':[{'role':'user','content':'Write a long numbered list of at least 300 different interesting science facts. Continue until the limit.'}], 'stream':True,'max_tokens':1024,'chat_template_kwargs':{'enable_thinking':False}}
    characters=0;first=None;requests=0
    try:
        # A short reply can finish before the fixed 30-second heartbeat lease.
        # Reuse the one admitted native connection for sequential requests,
        # each still <=1024 tokens, until independent revocation interrupts it.
        # This is a native ownership probe, not a single UI conversation run.
        while time.monotonic()-started<45 and requests<3:
            connection.request('POST','/v1/chat/completions',json.dumps(payload),{'Content-Type':'application/json'});response=connection.getresponse();assert response.status==200;requests+=1
            while line:=response.readline(65536):
                if not line.startswith(b'data:') or line[5:].strip()==b'[DONE]':continue
                part=json.loads(line[5:]);delta=(part.get('choices') or [{}])[0].get('delta',{}).get('content')
                if delta:
                    characters+=len(delta)
                    if first is None:
                        first=time.monotonic()-started
                        if mode=='owner-death':
                            print(json.dumps({'job_id':job,'actual_text_characters':characters,'first_text_seconds':first}),flush=True);os._exit(0)
    except (OSError,http.client.HTTPException):pass
    finally:connection.close()
    ack=native.call('chat_release',job_id=job)
    print(json.dumps({'job_id':job,'actual_text_characters':characters,'first_text_seconds':first,'bounded_requests_under_one_native_lease':requests,'revocation_seconds':time.monotonic()-started,'ack':ack}),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('output',nargs='?',type=Path);p.add_argument('--child',choices=('heartbeat-loss','owner-death'));args=p.parse_args()
    if args.child:child(args.child);return
    if args.output is None:p.error('output required')
    rows=[];before=normal_identity()
    for mode in ('heartbeat-loss','owner-death'):
        started=time.monotonic();result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',mode],check=True,capture_output=True,text=True,timeout=65)
        row=json.loads(result.stdout.strip());row['mode']=mode;end=time.monotonic()+10
        while True:
            with urllib.request.urlopen('http://127.0.0.1:8080/slots',timeout=2) as response:slots=json.load(response)
            if all(s['is_processing'] is False for s in slots):break
            if time.monotonic()>end:raise RuntimeError('actual_compute_not_idle_after_owner_revocation')
            time.sleep(.1)
        row['compute_idle']=True;row['observed_total_seconds']=time.monotonic()-started
        if mode=='owner-death':row['ack']=NativeClient().call('chat_release',job_id=row['job_id'])
        rows.append(row)
    after=normal_identity();report={'kind':'actual idle heartbeat lease expiry plus actual installed normal Qwen pidfd compute revocation','status':'PASS' if rows[1]['actual_text_characters']>0 and all(r['compute_idle'] and r['ack'].get('compute_idle_acknowledged') and r['ack'].get('terminal')=='cancelled' for r in rows) else 'FAIL','cases':rows,'normal_identity_unchanged':before==after,'absolute_300_second_limit':'not exhausted in this probe','heartbeat_expiry_during_active_generation':'not proven; earlier replies finished before 30 seconds, retained in history'}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    if report['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
