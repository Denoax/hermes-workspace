"""Actual disposable user-systemd stop-order regression, without models/root."""
import argparse,json,os,subprocess,time,uuid
from pathlib import Path


def run(argv,check=True):return subprocess.run(argv,check=check,capture_output=True,text=True,timeout=8)


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();rows=[]
    for label,ordering in [('baseline_with_After',True),('corrected_without_After',False)]:
        prefix='hermes-chat-order-'+uuid.uuid4().hex[:10];owner=prefix+'-owner.service';guard=prefix+'-guard.service'
        try:
            run(['systemd-run','--user','--unit='+owner,'--property=RemainAfterExit=yes','/usr/bin/true'])
            stop='/usr/bin/timeout 2s /usr/bin/systemctl --user stop '+owner
            argv=['systemd-run','--user','--unit='+guard,'--property=RemainAfterExit=yes','--property=ExecStopPost='+stop]
            if ordering:argv.append('--property=After='+owner)
            run([*argv,'/usr/bin/true']);started=time.monotonic();result=run(['systemctl','--user','stop',guard],check=False)
            state=run(['systemctl','--user','show',guard,'-p','Result','--value']).stdout.strip()
            rows.append({'case':label,'exit':result.returncode,'unit_result':state,'seconds':time.monotonic()-started})
        finally:
            run(['systemctl','--user','stop',guard,owner],check=False);run(['systemctl','--user','reset-failed',guard,owner],check=False)
    report={'kind':'actual disposable user-systemd lifecycle; no native model/VM evidence','cases':rows,'status':'PASS' if rows[0]['unit_result']=='exit-code' and rows[1]['unit_result']=='success' else 'FAIL'}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    if report['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
