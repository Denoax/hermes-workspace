"""Keyboard tree behavior in a labelled renderer fixture, with no file reads."""
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workspace import launcher


def main():
    launcher.PROFILE=launcher.PROFILE.parent/'hermes-overhaul-tree'
    pipe,process=launcher.browser(headless=True)
    saved=None;record={'scope':'nested tree renderer fixture; no catalog files created, no model or native job','checks':{}}
    try:
        target=next(x for x in pipe.call('Target.getTargets')['targetInfos'] if x['type']=='page' and x.get('url','').startswith(launcher.ORIGIN))
        s=pipe.call('Target.attachToTarget',{'targetId':target['targetId'],'flatten':True})['sessionId']
        def evaluate(code):
            value=pipe.call('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True},s)
            if value.get('exceptionDetails'):raise RuntimeError('tree fixture evaluation')
            return value.get('result',{}).get('value')
        def rpc(method,fields=None):
            return evaluate("(async()=>{let b=await(await fetch('/hermes-workspace/api/bootstrap')).json();let r=await fetch('/hermes-workspace/api/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Hermes-CSRF':b.csrf},body:JSON.stringify({version:1,method:"+json.dumps(method)+",fields:"+json.dumps(fields or {})+"})});let data=await r.json();if(!r.ok)throw Error(data.error);return data.result})()")
        def key(name,code):
            pipe.call('Input.dispatchKeyEvent',{'type':'keyDown','key':name,'windowsVirtualKeyCode':code},s)
            pipe.call('Input.dispatchKeyEvent',{'type':'keyUp','key':name,'windowsVirtualKeyCode':code},s)
        time.sleep(.7);saved=rpc('view.read')
        evaluate("window.__originalFetch=fetch;window.fetch=async(url,options)=>{let q=options?.body?JSON.parse(options.body):null;if(q?.method==='workspace.files')return new Response(JSON.stringify({result:{files:['src/program.py','src/utils.py','README.md'],snapshot_sha256:null}}));return __originalFetch(url,options)};document.querySelector('#projects button').click()")
        deadline=time.monotonic()+10
        while not evaluate("document.querySelector('#tree [aria-expanded]')!==null"):
            if time.monotonic()>deadline:raise RuntimeError('tree rendering deadline')
            time.sleep(.1)
        evaluate("document.getElementById('files-toggle').click()");time.sleep(.3)
        evaluate("document.querySelector('#tree [aria-expanded]').focus()")
        key('ArrowLeft',37);record['checks']['collapse']=evaluate("document.activeElement.getAttribute('aria-expanded')==='false'")
        key('ArrowRight',39);record['checks']['expand']=evaluate("document.activeElement.getAttribute('aria-expanded')==='true'")
        key('ArrowRight',39);record['checks']['first_child']=evaluate("document.activeElement.dataset.path==='src/program.py'")
        key('ArrowDown',40);record['checks']['next_file']=evaluate("document.activeElement.dataset.path==='src/utils.py'")
        key('ArrowLeft',37);record['checks']['parent']=evaluate("document.activeElement.hasAttribute('aria-expanded')")
        key('End',35);record['checks']['end']=evaluate("document.activeElement.dataset.path==='README.md'")
        key('Home',36);record['checks']['home']=evaluate("document.activeElement.hasAttribute('aria-expanded')")
        key('r',82);record['checks']['typeahead']=evaluate("document.activeElement.dataset.path==='README.md'")
        record['all_passed']=all(record['checks'].values())
        (ROOT/'workspace/evidence/overhaul/tree-fixture-validation.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
    finally:
        if saved:
            try:
                evaluate('window.fetch=window.__originalFetch||window.fetch');time.sleep(1.1);rpc('view.write',{'state':saved})
            except (RuntimeError,OSError):pass
        pipe.call('Browser.close');os.close(pipe.read);os.close(pipe.write)


if __name__=='__main__':main()
