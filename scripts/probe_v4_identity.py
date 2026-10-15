"""Read-only source, served-build, host identity and recovery proof for the real pin."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc
from workspace.models import normal_identity
from workspace.server import normal_profile_unchanged
from lab.native_client import NativeClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result={'status':'IN_PROGRESS','scope':'Existing desktop pin, production catalog and authenticated port18791; no inference or replacement server'}
    b=ProductionPin()
    try:
        result['pin']=b.identity
        result['readiness']=rpc(b,'readiness.read',{})
        assert result['readiness']['state']=='ready',result['readiness']
        assert result['readiness']['control']['socket_uid']==0
        assert result['readiness']['control']['parent_uid']==0
        result['models']=rpc(b,'models.list',{})
        assert {m['id'] for m in result['models']}=={'normal','abliterated'}
        expected=json.loads((ROOT/'workspace/ui/dist/identities.json').read_text())
        result['served_sha256']=b.evaluate("(async()=>{const out={};for(const n of ['app.js','app.css']){const r=await fetch('/assets/'+n,{cache:'no-store'});if(!r.ok)throw Error('asset request failed');const h=await crypto.subtle.digest('SHA-256',await r.arrayBuffer());out[n]=[...new Uint8Array(h)].map(v=>v.toString(16).padStart(2,'0')).join('')}return out})()")
        assert result['served_sha256']==expected,'served_build_differs_from_manifest'
        assert all(hashlib.sha256((ROOT/'workspace/ui/dist'/n).read_bytes()).hexdigest()==h for n,h in expected.items())
        result['normal_after']=normal_identity()
        assert normal_profile_unchanged()
        result['four_normal_hashes_unchanged']=True
        with urllib.request.urlopen('http://127.0.0.1:8080/slots',timeout=3) as response:
            result['normal_compute_idle']=all(not row.get('is_processing') for row in json.load(response))
        assert result['normal_compute_idle']
        native=NativeClient(timeout=3).call('status')
        result['native']=native
        facts=native['observed_facts']
        assert not facts['owned_fleet_active'] and not facts['inference_window_active']
        result['unauthenticated_bootstrap_status']=None
        try:
            urllib.request.urlopen('http://127.0.0.1:18791/hermes-workspace/api/bootstrap',timeout=3)
        except urllib.error.HTTPError as error:
            result['unauthenticated_bootstrap_status']=error.code
        assert result['unauthenticated_bootstrap_status']==401
        pid=int(subprocess.check_output(['/usr/bin/systemctl','show','hermes-workspace-runtime.service','-p','MainPID','--value'],text=True,timeout=3))
        proc=Path('/proc')/str(pid)
        status=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines() if ':' in line)
        argv=(proc/'cmdline').read_bytes().split(b'\0')
        assert str(ROOT/'workspace/server.py').encode() in argv
        result['service']={'pid':pid,'source':str(ROOT/'workspace/server.py'),'uid':status['Uid'].split(),'gid':status['Gid'].split(),'capabilities':status['CapEff'].strip(),'no_new_privileges':status['NoNewPrivs'].strip(),'uid_map':(proc/'uid_map').read_text().strip()}
        assert result['service']['uid']==['1000']*4 and result['service']['capabilities']=='0000000000000000' and result['service']['no_new_privileges']=='1'
        result['listener']=subprocess.check_output(['/usr/bin/ss','-H','-ltn','sport = :18791'],text=True,timeout=3).strip()
        assert '127.0.0.1:18791' in result['listener'] and '0.0.0.0:18791' not in result['listener']
        result['status']='PASS'
    except Exception as error:
        result.update(status='FAIL',error=str(error))
        raise
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        b.close()
    print(json.dumps({'status':result['status'],'served_sha256':result['served_sha256'],'normal_context':result['normal_after']['context']}))


if __name__=='__main__':main()
