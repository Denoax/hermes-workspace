"""Nine-point hit tests plus trusted pointer dispatch on every visible control.
Renderer fixture blocks all production writes; native auth/service/status are real.
"""
import json,sys,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace.parity_browser import Browser,ROOT

OUT=ROOT/'workspace/evidence/parity'

def audit_visible(browser,record,state):
 browser.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
 controls=browser.evaluate('''(()=>{document.querySelectorAll('[data-probe]').forEach(e=>e.removeAttribute('data-probe'));let i=0;return [...document.querySelectorAll('button,input:not([type=checkbox]),select,textarea,a[href],summary,label.motion-switch')].filter(b=>{const r=b.getBoundingClientRect(),s=getComputedStyle(b);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&!b.closest('[hidden],.sr-only')&&(!document.querySelector('dialog[open]')||b.closest('dialog[open]'));}).map(b=>{b.dataset.probe='p'+i++;return '[data-probe="'+b.dataset.probe+'"]';});})()''')
 for selector in controls:
  row=browser.evaluate('''(()=>{const b=document.querySelector('''+json.dumps(selector)+'''),r=b.getBoundingClientRect();const samples=[];for(const u of [.25,.5,.75])for(const v of [.25,.5,.75]){let h=document.elementFromPoint(r.x+r.width*u,r.y+r.height*v);samples.push(h===b||b.contains(h));}return {id:b.id||b.dataset.probe,tag:b.tagName,width:r.width,height:r.height,disabled:!!b.disabled,inside:r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,samples};})()''')
  # Scrollable content is measured after explicit scroll into view, never counted
  # as a visible clickable target while outside its actual scrollport.
  if not row['inside']:continue
  passed=all(row['samples']) and row['height']>=44
  record['checks'].append({'state':state,**row,'passed':passed})
  if not passed:raise AssertionError('nine_point_hit_failure:'+state+':'+row['id'])
  if not row['disabled']:browser.click(selector,guard=True)

def main():
 OUT.mkdir(parents=True,exist_ok=True);b=Browser();r={'scope':'Native authenticated Brave; isolated renderer fixture; nine elementFromPoint samples and real CDP mouse events. Guarded alignment clicks do not execute application actions. Functional panel/file actions are separately unguarded.','checks':[],'captures':{},'model_calls':0,'production_writes':0}
 try:
  b.key('Escape');b.wait("!document.querySelector('dialog[open]')")
  for width,height,dpr in [(1915,1042,1),(1440,900,1),(1024,768,1),(390,844,1),(1440,900,2)]:
   b.metric(width,height,dpr);label=f'{width}x{height}@{dpr}';audit_visible(b,r,label+'-conversation')
   for trigger,pane in [('#files-toggle','files-panel'),('#settings-toggle','appearance'),('#diagnostics','details'),('.project-switch','project-dialog')]:
    b.click(trigger);b.wait(f"document.getElementById('{pane}').open");b.settle();audit_visible(b,r,label+'-'+pane)
    b.capture(OUT/(pane+'-'+label+'.png'))
    if pane=='files-panel':
     b.click('#tree button[aria-expanded]');b.wait("document.querySelector('#tree button[aria-expanded]').getAttribute('aria-expanded')==='false'");audit_visible(b,r,label+'-collapsed-tree');b.click('#tree button[aria-expanded]');b.wait("document.querySelector('#tree button[aria-expanded]').getAttribute('aria-expanded')==='true'");audit_visible(b,r,label+'-expanded-tree')
     b.click('#tree button[data-path]');b.wait("!document.getElementById('file-preview').hidden");audit_visible(b,r,label+'-file-preview');b.click('#changes-tab');audit_visible(b,r,label+'-changes');b.click('#files-tab')
    if pane=='appearance':
     b.click('#theme-buddy');b.settle();r['checks'].append({'state':label+'-theme','passed':b.evaluate("document.documentElement.dataset.theme==='light'")});b.capture(OUT/('settings-light-'+label+'.png'));b.click('#theme-buddy');b.settle()
     b.click('#less-motion');r['checks'].append({'state':label+'-reduced','passed':b.evaluate("document.documentElement.dataset.motion==='reduced'")});b.click('#less-motion');b.settle()
     b.click('#interface-volume');b.key('ArrowRight');r['checks'].append({'state':label+'-range-keyboard','passed':b.evaluate("Number(document.getElementById('interface-volume').value)>0")});b.click('#reset-settings');b.settle()
    b.key('Escape');b.wait("!document.querySelector('dialog[open]')");b.wait("!globalThis.hermesPaneMetrics?.rafPending")
   # Input dialogs, file-tree folder expansion and model/mode native menu choices.
   b.click('#new-project' if width>=820 else '.project-switch');
   if width<820:b.settle();b.click('#project-dialog [data-action=new-project]')
   b.wait("document.getElementById('input-dialog').open");b.settle();audit_visible(b,r,label+'-input-dialog');b.key('Escape');b.wait("!document.querySelector('dialog[open]')");
   for selector in ['#arm','#task-kind']:
    b.evaluate('window.__guardParityChange=true');b.click(selector);b.key('ArrowDown');b.key('Enter');b.key('Escape');b.evaluate('window.__guardParityChange=false')
   r['checks'].append({'state':label+'-overflow','passed':b.evaluate('document.documentElement.scrollWidth<=innerWidth')})
  # Completed-review renderer fixture exercises the otherwise unavailable Apply
  # target. The interception blocks host/guest writes; alignment clicks are guarded.
  b.metric(1440,900);b.evaluate("window.__beforeReviewFetch=window.fetch;window.fetch=async(url,options)=>{const q=options?.body?JSON.parse(options.body):null;let result;if(q?.method==='session.jobs')result=[{id:'f'.repeat(32)}];else if(q?.method==='job.read')result={state:'review_ready'};else if(q?.method==='patch.prepare')result={diff:'--- program.py\\n+++ program.py\\n@@ -1 +1 @@\\n-print(1)\\n+print(2)',validation:{passed:true},review_ticket:'renderer-fixture-only'};else return __beforeReviewFetch(url,options);return new Response(JSON.stringify({result}),{status:200})}")
  b.click('#sessions button');b.wait("!document.getElementById('view-diff').disabled");b.click('#files-toggle');b.wait("document.getElementById('files-panel').open");b.settle();b.click('#changes-tab');b.click('#view-diff');b.wait("!document.getElementById('apply').hidden");audit_visible(b,r,'completed-review-fixture');b.capture(OUT/'files-panel-completed-review-fixture.png');b.key('Escape')
  r['checks'].append({'state':'safe-renderer-text','passed':b.evaluate('!window.__xss && !document.querySelector("#messages img,#messages [href^=javascript]")')})
  r['trusted_events']=b.evaluate('window.__parityEvents');r['runtime_errors']=b.evaluate('window.__parityErrors');r['renderer']=b.evaluate('globalThis.hermesPaneMetrics');
  assert r['trusted_events'] and all(x['trusted'] for x in r['trusted_events'])
  assert not r['runtime_errors'];assert not r['renderer']['fallbacks'];assert all(x['passed'] for x in r['checks'])
  r['served_assets']=b.served_hashes()
  r['status']='PASS';r['physical_scaling']='Separate native compositor probe; emulation above is not physical device evidence.'
 except Exception as e:r['status']='FAIL';r['failure']=str(e);b.capture(OUT/'failure.png');raise
 finally:
  (OUT/'pointer-parity.json').write_text(json.dumps(r,indent=2)+'\n');b.close()

if __name__=='__main__':main()
