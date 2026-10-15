"""Actual authenticated renderer/pointer checks. Does not submit inference."""
import argparse,base64,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workspace.parity_browser import Browser

def rpc(browser,method,fields):
    return browser.evaluate("(async()=>{const b=await(await fetch('/hermes-workspace/api/bootstrap')).json();const r=await fetch('/hermes-workspace/api/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Hermes-CSRF':b.csrf},body:JSON.stringify({version:1,method:"+json.dumps(method)+",fields:"+json.dumps(fields)+"})});const d=await r.json();if(d.error)throw Error(d.error);return d.result})()")


def main():
 p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
 b=Browser('local-chat-visual',fixture=False,quiet=True);rows=[];original=rpc(b,'view.read',{})
 try:
  b.evaluate("window.__pointerEvidence=[];document.addEventListener('click',e=>{const button=e.target.closest('button');if(button)window.__pointerEvidence.push({id:button.id,trusted:e.isTrusted})},true)")
  for width,height in [(1440,900),(1024,768),(390,844)]:
   b.metric(width,height);b.evaluate('new Promise(r=>setTimeout(r,250))');b.evaluate('document.fonts.ready')
   for theme in ['dark','light']:
    if b.evaluate('document.documentElement.dataset.theme')!=theme:
     if width<720:b.click('.mobile-toggle');b.wait("document.querySelector('.sidebar').classList.contains('mobile-open')")
     b.click('#theme-buddy');b.wait('document.documentElement.dataset.theme==='+json.dumps(theme))
     if width<720:b.click('.mobile-close')
    b.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
    before=b.rect('.toolbar-actions');samples=[]
    for n in range(10):
     b.click('#files-toggle');b.wait("!!document.querySelector('dialog[open]')")
     after=b.rect('.toolbar-actions');samples.append({'open':True,'dx':after['x']-before['x'],'dy':after['y']-before['y']})
     b.key('Escape');b.wait("!document.querySelector('dialog[open]')")
     after=b.rect('.toolbar-actions');samples.append({'open':False,'dx':after['x']-before['x'],'dy':after['y']-before['y']})
    assert all(abs(s['dx'])<=1 and abs(s['dy'])<=1 for s in samples)
    hits=b.evaluate("(()=>{const e=document.querySelector('#files-toggle'),r=e.getBoundingClientRect();return [0.15,0.5,0.85].flatMap(u=>[0.15,0.5,0.85].map(v=>!!document.elementFromPoint(r.x+r.width*u,r.y+r.height*v)?.closest('#files-toggle')))})()")
    assert all(hits)
    composer=b.rect('#composer');target=90 if width>720 else 110
    assert (88<=composer['height']<=104) if width>720 else (112<=composer['height']<=128)
    overflow=b.evaluate('document.documentElement.scrollWidth>innerWidth');assert not overflow
    b.evaluate('new Promise(r=>setTimeout(r,200))')
    image=b.call('Page.captureScreenshot',{'format':'png'})['data'];(args.output/f'{theme}-{width}.png').write_bytes(base64.b64decode(image))
    rows.append({'viewport':[width,height],'theme':theme,'composer_height':composer['height'],'header_cycles':10,'settled_positions':samples,'hit_tests':hits,'horizontal_overflow':overflow})
  # Switching panels uses real pointer input; the header remains reachable.
  b.click('#files-toggle');b.wait("!!document.querySelector('dialog[open]')");b.click('#settings-toggle');b.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'");b.key('Escape')
  b.click('#plus-menu');b.wait("!!document.querySelector('[role=menu]')");b.key('Escape');b.click('[aria-label="Reasoning effort"]');b.wait("!!document.querySelector('#reasoning-effort')");b.key('Escape')
  pointer=b.evaluate('window.__pointerEvidence');assert pointer and all(e['trusted'] for e in pointer)
  record={'status':'PASS','kind':'actual authenticated browser and protocol pointer input; not physical-device or human approval','viewports':rows,'pointer_events':pointer,'source':'workspace/ui/dist'}
  (args.output/'browser.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'status':'PASS','composer_heights':[r['composer_height'] for r in rows],'trusted_clicks':len(pointer)}))
 finally:
  if original:rpc(b,'view.write',{'state':original})
  b.close()

if __name__=='__main__':main()
