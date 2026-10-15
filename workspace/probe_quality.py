"""Small native-browser cost sample and guarded editor negative controls."""
import base64
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workspace import launcher


def main():
    before = Path(sys.argv[1])
    out = ROOT / 'workspace/evidence/overhaul'
    launcher.PROFILE = launcher.PROFILE.parent / 'hermes-overhaul-quality'
    pipe, process = launcher.browser(headless=True)
    record = {'scope': 'native Brave headless at 1440x900, DPR1, warm page, no inference', 'checks': {}, 'cost_samples': {}}
    record['asset_sha256'] = {name: hashlib.sha256((ROOT/'workspace/ui'/name).read_bytes()).hexdigest() for name in ['index.html','app.js','style.css']}
    saved_view = None
    try:
        target = next(x for x in pipe.call('Target.getTargets')['targetInfos'] if x['type'] == 'page' and x.get('url', '').startswith(launcher.ORIGIN))
        session = pipe.call('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True})['sessionId']
        version=pipe.call('Browser.getVersion');record['browser']={'product':version['product'],'protocolVersion':version['protocolVersion']}
        pipe.call('Page.enable', {}, session)
        pipe.call('Runtime.enable', {}, session)
        pipe.call('Performance.enable', {}, session)
        pipe.call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False}, session)
        def evaluate(code):
            r = pipe.call('Runtime.evaluate', {'expression': code, 'returnByValue': True, 'awaitPromise': True}, session)
            if r.get('exceptionDetails'): raise RuntimeError('browser evaluation error')
            return r.get('result', {}).get('value')
        def wait(code):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if evaluate(code): return
                time.sleep(.1)
            raise RuntimeError('browser state deadline')
        def rpc(method, fields=None):
            return evaluate("(async()=>{let b=await(await fetch('/hermes-workspace/api/bootstrap')).json();let r=await fetch('/hermes-workspace/api/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Hermes-CSRF':b.csrf},body:JSON.stringify({version:1,method:"+json.dumps(method)+",fields:"+json.dumps(fields or {})+"})});let data=await r.json();if(!r.ok)throw Error(data.error);return data.result})()")
        def metrics(): return {m['name']: m['value'] for m in pipe.call('Performance.getMetrics', {}, session)['metrics']}
        wait("document.getElementById('connection').textContent==='Connected'")
        saved_view = rpc('view.read')
        # The baseline source is delivered privately to the harness via a fixed path.
        # Only the three UI GETs are intercepted. All data/auth still use the live service.
        def serve(message):
            if message['method'] != 'Fetch.requestPaused': return
            p = message['params']; path = p['request']['url'].removeprefix(launcher.ORIGIN)
            names = {'/hermes-workspace': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            pipe.counter += 1
            if path in names:
                name, mime = names[path]
                req = {'id': pipe.counter, 'method': 'Fetch.fulfillRequest', 'sessionId': session,
                       'params': {'requestId': p['requestId'], 'responseCode': 200, 'responseHeaders': [{'name':'Content-Type','value':mime}],
                                  'body': base64.b64encode((before / name).read_bytes()).decode()}}
            else: req = {'id': pipe.counter, 'method': 'Fetch.continueRequest', 'sessionId': session, 'params': {'requestId': p['requestId']}}
            raw = json.dumps(req).encode() + b'\0'
            while raw: raw = raw[os.write(pipe.write, raw):]
        for version in ([] if '--editor-only' in sys.argv else ['baseline', 'overhaul']):
            if version == 'baseline':
                pipe.on_event = serve; pipe.call('Fetch.enable', {'patterns': [{'urlPattern': launcher.ORIGIN + '/*', 'requestStage': 'Request'}]}, session)
            else:
                pipe.call('Fetch.disable', {}, session); pipe.on_event = None
            pipe.call('Page.reload', {}, session); time.sleep(.7)
            wait("document.getElementById('connection').textContent.toLowerCase().includes('connected')")
            evaluate("document.querySelector('#projects button').click()")
            time.sleep(.5); evaluate("document.querySelector('#sessions button').click()")
            time.sleep(.5)
            idle, interaction = [], []
            for _ in range(3):
                start = metrics(); time.sleep(1.2); end = metrics()
                idle.append({k: end.get(k, 0) - start.get(k, 0) for k in ['TaskDuration', 'ScriptDuration', 'LayoutDuration', 'RecalcStyleDuration']})
                start = metrics()
                for i in [1, 0, 1, 0]:
                    evaluate(f'document.querySelectorAll("#projects button")[{i}].click()')
                    time.sleep(.3)
                end = metrics(); interaction.append({k: end.get(k, 0) - start.get(k, 0) for k in ['TaskDuration', 'ScriptDuration', 'LayoutDuration', 'RecalcStyleDuration']})
            record['cost_samples'][version] = {'idle_1_2_seconds': idle, 'four_project_selections': interaction}
        record['cost_summary'] = {v: {work: {'task_seconds_median': statistics.median(x['TaskDuration'] for x in rows), 'task_seconds_max': max(x['TaskDuration'] for x in rows)} for work, rows in groups.items()} for v, groups in record['cost_samples'].items()}
        record['limitations'] = 'Three small descriptive CDP TaskDuration samples; this is not OS CPU utilization; different layouts and persistence work are intentional. No GPU timings, frame-rate claims, physical device or causal optimization claim.'
        # Actual computed colors, including the fully composited selected-button colors.
        def luminance(rgb):
            channels = [int(c) / 255 for c in rgb[4:-1].split(',')[:3]]
            channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2]
        record['contrast'] = {}
        for theme in ['dark', 'light']:
            evaluate("document.getElementById('theme').value=" + json.dumps(theme) + ";document.getElementById('theme').dispatchEvent(new Event('change'))")
            pairs = evaluate("[['body',document.body,document.body],['muted',document.getElementById('composer-state'),document.body],['primary',document.getElementById('start-window'),document.getElementById('start-window')]].map(([name,f,b])=>({name,color:getComputedStyle(f).color,background:getComputedStyle(b).backgroundColor}))")
            ratios = []
            for p in pairs:
                a, b = sorted([luminance(p['color']), luminance(p['background'])]); p['ratio'] = (b + .05) / (a + .05); ratios.append(p)
            record['contrast'][theme] = ratios
        record['checks']['text_contrast_at_least_4_5'] = all(p['ratio'] >= 4.5 for rows in record['contrast'].values() for p in rows)
        if record['cost_samples']: (out / 'quality-cost.json').write_text(json.dumps(record, indent=2) + '\n')
        # Preserve and restore the selected editor; negative save uses an intentionally stale hash.
        p = rpc('workspace.list')[0]; s = next(x for x in rpc('session.list') if x['project'] == p['id'])
        name = rpc('workspace.files', {'project_id': p['id']})['files'][0]
        content = rpc('workspace.file.read', {'project_id': p['id'], 'relative_path': name})
        state = {'project_id':p['id'], 'session_id':s['id'], 'file_path':name,
                 'editor':{'text':content['text'] + '\n# Unsaved UI recovery probe\n', 'sha256':content['sha256']},
                 'files_open':True, 'arm':s['arm'], 'task_kind':'chat', 'theme':'dark', 'motion':'system'}
        time.sleep(1);rpc('view.write', {'state': state}); pipe.call('Page.reload', {}, session); time.sleep(.8)
        wait("document.getElementById('file-text').value.includes('Unsaved UI recovery probe')")
        record['checks']['editor_draft_reconnect'] = True
        state['editor']['sha256'] = '0' * 64
        time.sleep(1.1);rpc('view.write', {'state':state}); pipe.call('Page.reload', {}, session); time.sleep(.8)
        wait("document.getElementById('file-preview').hidden===false")
        evaluate("document.getElementById('save-file').click()")
        wait("!document.getElementById('file-error').hidden")
        record['checks']['actionable_file_error'] = evaluate("document.getElementById('file-error').textContent.includes('File changed since review')")
        record['checks']['stale_editor_save_rejected'] = rpc('workspace.file.read', {'project_id':p['id'], 'relative_path':name})['sha256'] == content['sha256']
        (out / 'live-file-drift-error.png').write_bytes(base64.b64decode(pipe.call('Page.captureScreenshot', {}, session)['data']))
        # Current renderer: no ongoing animation or render-loop workload was introduced.
        record['checks']['no_canvas_or_ambient_animation'] = evaluate("document.querySelectorAll('canvas,video').length===0 && document.getAnimations().length===0")
        record['all_passed'] = all(record['checks'].values())
        (out / 'quality-validation.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record, indent=2))
    except Exception as error:
        record['error']=str(error)
        record['diagnostic']=evaluate("({state:document.getElementById('composer-state')?.textContent,fileError:document.getElementById('file-error')?.textContent,marker:document.getElementById('file-text')?.value.includes('Unsaved UI recovery probe'),open:document.getElementById('file-preview')?.hidden})")
        (out / 'quality-failure.json').write_text(json.dumps(record,indent=2)+'\n')
        raise
    finally:
        if saved_view is not None:
            time.sleep(1.1)
            try: rpc('view.write', {'state': saved_view})
            except (OSError, RuntimeError): pass
        try: pipe.call('Browser.close')
        except (OSError, RuntimeError, TimeoutError): pass
        os.close(pipe.read); os.close(pipe.write)


if __name__ == '__main__': main()
