"""Read-only matched captures of the existing owned portfolio build and Hermes."""
import json,time,hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace.parity_browser import Browser,ROOT
OUT=ROOT/'workspace/evidence/parity'
def main():
 b=Browser('matched-reference');r={'reference':'Existing local portfolio dist served read-only at 127.0.0.1:18793; no edits or deployment','conditions':[]}
 try:
  for width,height in [(1440,900),(390,844)]:
   for theme in ['dark','light']:
    b.metric(width,height);b.call('Page.navigate',{'url':'http://127.0.0.1:18793/'});b.wait("!!document.querySelector('.utility-toggle, .theme-toggle')");b.evaluate("document.getElementById('fixture-watermark')?.remove()");b.evaluate('document.fonts.ready');time.sleep(.3)
    if width>=820 and b.evaluate('document.documentElement.dataset.colorTheme')!=theme:
     b.click('.theme-toggle');time.sleep(.5)
    visible=b.evaluate("[...document.querySelectorAll('button')].some(e=>{const r=e.getBoundingClientRect();return e.textContent.trim()==='Settings'&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('button')===e})")
    if not visible:
     b.click('[aria-label="Portfolio menu"]');b.wait("[...document.querySelectorAll('button')].some(e=>{const r=e.getBoundingClientRect();return e.textContent.trim()==='Settings'&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('button')===e})")
    b.evaluate("[...document.querySelectorAll('button')].find(e=>{const r=e.getBoundingClientRect();return e.textContent.trim()==='Settings'&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('button')===e}).id='reference-settings-trigger'");b.click('#reference-settings-trigger');b.wait("[...document.querySelectorAll('#experience-settings[open]')].some(e=>e.getBoundingClientRect().width>0)");time.sleep(1.1)
    if b.evaluate('document.documentElement.dataset.colorTheme')!=theme:b.click('.theme-toggle');time.sleep(.5)
    path=OUT/f'portfolio-{theme}-{width}.png';b.capture(path)
    row={'viewport':[width,height],'DPR':b.evaluate('devicePixelRatio'),'theme':b.evaluate('document.documentElement.dataset.colorTheme'),'reference_capture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_geometry':b.evaluate("(()=>{const p=[...document.querySelectorAll('#experience-settings[open]')].find(e=>e.getClientRects().length);if(!p)return null;const s=getComputedStyle(p),h=getComputedStyle(p.querySelector('h2'));return {width:p.getBoundingClientRect().width,radius:s.borderRadius,heading:{size:h.fontSize,weight:h.fontWeight},film:s.getPropertyValue('--settings-film')}})()")}
    b.call('Page.navigate',{'url':'http://127.0.0.1:18791/hermes-workspace'});b.wait("document.getElementById('connection')?.textContent==='Connected'");b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");b.settle()
    if b.evaluate('document.documentElement.dataset.theme')!=theme:b.click('#theme-buddy');b.settle()
    path=OUT/f'hermes-{theme}-{width}.png';b.capture(path);row['hermes_capture_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();row['Hermes_geometry']=b.evaluate("(()=>{const p=document.getElementById('appearance'),s=getComputedStyle(p),h=getComputedStyle(p.querySelector('h2'));return {width:p.getBoundingClientRect().width,radius:s.borderRadius,heading:{size:h.fontSize,weight:h.fontWeight},film:s.getPropertyValue('--glass-film')}})()");r['conditions'].append(row);b.key('Escape')
  r['served_assets']=b.served_hashes()
  r['status']='CAPTURED matched conditions; human visual approval separate'
 finally:(OUT/'reference-comparison.json').write_text(json.dumps(r,indent=2)+'\n');b.close()
if __name__=='__main__':main()
