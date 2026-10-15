"""Read-only final installed-app/source/preservation audit; never exports auth."""
import argparse,hashlib,json,os,sqlite3,subprocess,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workspace.parity_browser import Browser
from workspace.models import normal_identity
from workspace.server import normal_profile_unchanged
from scripts.probe_local_chat import rpc


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--before',type=Path,required=True);args=p.parse_args()
    b=Browser('local-chat-delivery',fixture=False,quiet=True)
    try:
        projects=rpc(b,'workspace.list',{});sessions=rpc(b,'session.list',{});assert not projects and not sessions
        models=rpc(b,'models.list',{});assert {m['id'] for m in models}=={'normal','abliterated'}
        routes={'/hermes-workspace':ROOT/'workspace/ui/index.html','/assets/app.js':ROOT/'workspace/ui/dist/app.js','/assets/app.css':ROOT/'workspace/ui/dist/app.css','/interface-audio.mjs':ROOT/'workspace/ui/interface-audio.mjs'}
        for name in ('soft-press','soft-close'):routes['/sounds/'+name+'.wav']=ROOT/'workspace/ui/sounds'/(name+'.wav')
        served=b.evaluate("(async()=>{const out={};for(const path of "+json.dumps(list(routes))+ "){const r=await fetch(path);if(!r.ok)throw Error('served artifact missing');const d=await crypto.subtle.digest('SHA-256',await r.arrayBuffer());out[path]=[...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,'0')).join('');}return out;})()")
        for route,path in routes.items():assert served[route]==hashlib.sha256(path.read_bytes()).hexdigest()
        def observe_audio():
            b.evaluate("window.__cues=[];const play=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(...a){if(this.src.includes('/sounds/'))__cues.push({file:this.src.split('/').at(-1),volume:this.volume});return play.apply(this,a)}")
        initial_sound=b.evaluate("localStorage.getItem('hermes-ui:sounds')")
        if initial_sound=='off':b.click('#sound-toggle')
        observe_audio();b.click('#files-toggle');b.key('Escape');cues=b.evaluate('window.__cues');assert len(cues)==1 and cues[0]['volume']==.12
        b.click('#sound-toggle');b.click('#files-toggle');b.key('Escape');assert len(b.evaluate('window.__cues'))==1
        b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'");observe_audio()
        b.click('#files-toggle');b.key('Escape');assert not b.evaluate('window.__cues')
        b.click('#sound-toggle');b.click('#settings-toggle');b.click('[aria-label="Close Settings"]');assert [v['file'] for v in b.evaluate('window.__cues')]==['soft-press.wav','soft-close.wav']
        b.evaluate("localStorage."+('removeItem' if initial_sound is None else 'setItem')+"('hermes-ui:sounds'"+('' if initial_sound is None else ','+json.dumps(initial_sound))+")")
        samples={n:hashlib.sha256((ROOT/'workspace/ui/sounds'/n).read_bytes()).hexdigest() for n in ['soft-press.wav','soft-close.wav']}
        assert all(samples[n]==hashlib.sha256((args.before/'workspace/ui/sounds'/n).read_bytes()).hexdigest() for n in samples)
        with urllib.request.urlopen('http://127.0.0.1:8080/slots',timeout=3) as response:slots=json.load(response)
        assert all(s['is_processing'] is False for s in slots);assert normal_profile_unchanged()
        native=json.loads(Path('/var/lib/mani-vmlab-review/text-chat-installed.json').read_text());assert native['source_pack_sha256']=='766142c86543e30b61d7667cc5846ea3c61974a644903ca3ba2b3c0306911d4b'
        sock=Path('/run/mani-vmlab/control.sock').stat();assert sock.st_uid==0 and sock.st_mode&0o777==0o660
        def state(unit,user=False):return subprocess.run(['systemctl',*(['--user'] if user else []),'is-active',unit],capture_output=True,text=True,timeout=5).stdout.strip()
        assert state('manibot-llama.service',True)=='active';assert state('mani-vmlab-inference-window.service')=='inactive';assert state('mani-vmlab-backend.service')=='inactive'
        result={'status':'PASS','production_projects':len(projects),'production_conversations':len(sessions),'normal':normal_identity(),'four_normal_hashes_unchanged':True,'normal_compute_idle':True,'candidate_and_window_inactive':True,'model_inventory':[{'id':m['id'],'sha256':m['sha256'],'state':m['state'],'reasoning':m['reasoning']} for m in models],'served_sha256':served,'accepted_sound_samples_unchanged':samples,'sound_checks':{'one_cue_per_trusted_click':True,'no_Escape_chatter':True,'mute_survives_reload':True,'close_sample_correct':True,'volume':.12,'output':'isolated null sink; not a new physical audition'},'native_installation':native,'operator_socket_mode':'root:mani 0660','authentication_exported':False}
        args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'PASS','production_empty':True,'normal_healthy_and_idle':True,'served_files_verified':len(served)}))
    finally:b.close()

if __name__=='__main__':main()
