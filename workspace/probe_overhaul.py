"""Rendered live UI evidence; fixtures never enter the production catalog."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workspace import launcher


def main():
    evidence = ROOT / 'workspace/evidence/overhaul'
    evidence.mkdir(parents=True, exist_ok=True)
    launcher.PROFILE = launcher.PROFILE.parent / 'hermes-overhaul-probe'
    pipe, process = launcher.browser(headless=True)
    record = {'scope': 'authenticated installed UI, plus explicitly labelled renderer fixtures',
              'GPU_window_opened': False, 'model_calls': 0, 'checks': {}, 'captures': {}}
    try:
        target = next(x for x in pipe.call('Target.getTargets')['targetInfos'] if x.get('type') == 'page' and x.get('url', '').startswith(launcher.ORIGIN))
        session = pipe.call('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True})['sessionId']
        pipe.call('Page.enable', {}, session)
        pipe.call('Runtime.enable', {}, session)
        def evaluate(code):
            result = pipe.call('Runtime.evaluate', {'expression': code, 'returnByValue': True, 'awaitPromise': True}, session)
            if result.get('exceptionDetails'): raise RuntimeError('Browser evaluation: ' + result['exceptionDetails']['text'])
            return result.get('result', {}).get('value')
        def wait(code):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if evaluate(code): return
                time.sleep(.1)
            raise RuntimeError('Browser state deadline: ' + code)
        def click(selector): evaluate(f'document.querySelector({json.dumps(selector)}).click()')
        def metric(width, height):
            pipe.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': width < 600}, session)
        def capture(name):
            time.sleep(.22)
            data = base64.b64decode(pipe.call('Page.captureScreenshot', {'format': 'png'}, session)['data'])
            (evidence / name).write_bytes(data); record['captures'][name] = hashlib.sha256(data).hexdigest()
        def key(key, code=None, modifiers=0):
            pipe.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': key, 'code': code or key, 'modifiers': modifiers, 'windowsVirtualKeyCode': {'Escape':27,'Tab':9,'k':75}.get(key,0)}, session)
            pipe.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': key, 'code': code or key, 'modifiers': modifiers, 'windowsVirtualKeyCode': {'Escape':27,'Tab':9,'k':75}.get(key,0)}, session)
        metric(1915, 1042); wait("document.getElementById('connection').textContent==='Connected'")
        evaluate("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
        # Use owned existing review data only. Nothing is seeded or deleted.
        evaluate("window.__errors=[];addEventListener('error',e=>__errors.push(e.message));addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)))")
        capture('live-dark-1915.png')
        click('#projects button'); wait("document.getElementById('sessions').querySelector('button')!==null")
        click('#sessions button'); wait("document.querySelector('#sessions [aria-current=true]') && document.getElementById('composer-state').textContent.includes('Native setup needed')")
        record['checks']['truthful_disabled_send'] = evaluate("document.getElementById('send').disabled && !document.getElementById('start-window').disabled")
        record['checks']['auth_and_fonts'] = evaluate("document.fonts.check('16px \"Hermes Sans\"') && document.fonts.check('44px \"Hermes Display\"')")
        evaluate("document.getElementById('prompt').value='';document.getElementById('prompt').focus()")
        pipe.call('Input.insertText', {'text': 'Review program.py and keep the original files.'}, session)
        time.sleep(.65)
        for width, height in [(1440, 900), (1024, 768), (390, 844)]:
            metric(width, height); capture('live-dark-' + str(width) + '.png')
            record['checks']['overflow_' + str(width)] = evaluate('document.documentElement.scrollWidth<=innerWidth')
            record['checks']['toolbar_and_composer_' + str(width)] = evaluate("['files-toggle','start-window','stop','prompt'].every(id=>{let r=document.getElementById(id).getBoundingClientRect();return r.width>0&&r.height>=44&&r.right<=innerWidth&&r.bottom<=innerHeight})")
        metric(1440, 900)
        with tempfile.TemporaryDirectory(prefix='overhaul-recording-', dir=launcher.STATE) as directory:
            frames = []
            def event(message):
                if message['method'] != 'Page.screencastFrame': return
                value = message['params']; stamp = value['metadata'].get('timestamp', time.time())
                name = Path(directory) / ('%04d.jpg' % len(frames)); name.write_bytes(base64.b64decode(value['data'])); frames.append((name, stamp))
                pipe.counter += 1
                ack = {'id': pipe.counter, 'method': 'Page.screencastFrameAck', 'params': {'sessionId': value['sessionId']}, 'sessionId': session}
                raw = json.dumps(ack).encode() + b'\0'
                while raw: raw = raw[os.write(pipe.write, raw):]
            pipe.on_event = event
            pipe.call('Page.startScreencast', {'format': 'jpeg', 'quality': 88, 'maxWidth': 1440, 'maxHeight': 900, 'everyNthFrame': 1}, session)
            click('[data-action=projects]'); time.sleep(.3); evaluate('document.title')
            click('#project-results button'); time.sleep(.35); evaluate('document.title')
            click('#sessions button'); time.sleep(.4)
            evaluate("document.getElementById('prompt').focus()")
            pipe.call('Input.insertText', {'text': ' Check the bounds.'}, session); time.sleep(.4)
            click('#files-toggle'); time.sleep(.4)
            if evaluate("!!document.querySelector('#tree button[data-path]')"):
                evaluate("document.querySelector('#tree button[data-path]').focus()");click('#tree button[data-path]'); wait("!document.getElementById('file-preview').hidden")
                record['checks']['file_selection_preserves_focus'] = evaluate("document.activeElement.dataset.path===document.getElementById('file-label').textContent && document.activeElement.getAttribute('aria-current')==='true'")
                capture('live-file-1440.png')
            click('#files-close'); time.sleep(.05); click('#files-toggle'); time.sleep(.06); click('#files-close'); time.sleep(.3)
            record['checks']['drawer_focus_return'] = evaluate("document.activeElement.id==='files-toggle' && !document.getElementById('files-panel').open")
            click('#files-toggle'); time.sleep(.3); click('#files-close'); time.sleep(.3)
            for _ in range(8): evaluate('document.title'); time.sleep(.12)
            pipe.call('Page.stopScreencast', {}, session); pipe.on_event = None
            rows = []
            for i, (name, stamp) in enumerate(frames):
                rows.append("file '" + str(name) + "'")
                if i + 1 < len(frames): rows.append('duration ' + str(max(.01, frames[i+1][1] - stamp)))
            rows.append("file '" + str(frames[-1][0]) + "'")
            concat = Path(directory) / 'frames.txt'; concat.write_text('\n'.join(rows) + '\n')
            video = evidence / 'live-interaction.mp4'
            subprocess.run(['/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat), '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-fps_mode', 'vfr', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True, timeout=60)
            record['recording'] = {'kind': 'continuous native CDP screencast, unedited variable cadence', 'frames': len(frames), 'seconds': frames[-1][1] - frames[0][1], 'sha256': hashlib.sha256(video.read_bytes()).hexdigest(), 'continuous_playback_human_approval': False}
        metric(390, 844); click('#files-toggle'); time.sleep(.25)
        record['checks']['mobile_modal'] = evaluate("document.getElementById('files-panel').matches(':modal')")
        evaluate("document.getElementById('files-close').focus()")
        key('Tab', modifiers=8)
        record['checks']['mobile_focus_trap'] = evaluate("!!document.activeElement.closest('#files-panel')")
        capture('live-files-390.png'); key('Escape')
        record['checks']['escape_focus_return'] = evaluate("document.activeElement.id==='files-toggle' && !document.getElementById('files-panel').open")
        key('k', 'KeyK', 2); wait("document.getElementById('project-dialog').open")
        record['checks']['projects_shortcut'] = True; key('Escape')
        metric(1440, 900); click('#diagnostics'); wait("document.getElementById('details').open")
        record['checks']['historical_failures_preserved'] = evaluate("document.getElementById('details-summary').textContent.includes('B08 failed')")
        capture('live-details.png'); key('Escape'); click('#start-window'); wait("document.getElementById('details').open")
        record['checks']['start_only_displays_command'] = evaluate("document.getElementById('details-text').textContent.includes('sudo')")
        capture('live-native-command.png'); key('Escape')
        # Appearance persists in the authenticated server store, not browser storage.
        click('[data-action=appearance]'); wait("document.getElementById('appearance').open")
        evaluate("document.getElementById('theme').value='light';document.getElementById('theme').dispatchEvent(new Event('change'))")
        key('Escape'); time.sleep(.35)
        for width, height in [(1915, 1042), (1440, 900), (1024, 768), (390, 844)]:
            metric(width, height); capture('live-light-' + str(width) + '.png')
        pipe.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]}, session)
        record['checks']['system_reduced_motion'] = evaluate("getComputedStyle(document.documentElement).getPropertyValue('--duration').trim()==='0ms'")
        metric(1440, 900)
        # Reload and restart exercise the actual catalog and fresh CSRF bootstrap.
        pipe.call('Page.reload', {}, session); time.sleep(.7)
        wait("document.getElementById('connection').textContent==='Connected'")
        record['checks']['draft_and_appearance_reload'] = evaluate("document.getElementById('prompt').value.includes('Check the bounds') && document.documentElement.dataset.theme==='light'")
        subprocess.run(['/usr/bin/systemctl', '--user', 'restart', 'hermes-workspace.service'], check=True, timeout=10)
        time.sleep(2.7); wait("document.getElementById('connection').textContent==='Connected'")
        record['checks']['service_restart_reconnect'] = True
        record['checks']['console_clean'] = evaluate('!window.__errors || window.__errors.length===0')
        record['checks']['no_window_opened'] = evaluate("!document.getElementById('start-window').disabled")
        # Labelled fixture data exercises rendering and diff layout only; no backend authority.
        pipe.call('Emulation.setEmulatedMedia', {'features': []}, session)
        evaluate("document.querySelector('[data-action=appearance]').click()")
        evaluate("document.getElementById('theme').value='dark';document.getElementById('theme').dispatchEvent(new Event('change'))")
        key('Escape'); time.sleep(.3)
        fixture = [{'role': 'user', 'text': 'Review [program.py](program.py). Preserve the original file.'},
                   {'role': 'assistant', 'text': 'Renderer fixture only. This is not a model response.\n\n```python\ndef clamp(value):\n    return min(100, max(0, value))\n```\nLiteral text: <img src=x onerror=window.__xss=1>\n[Unsafe](javascript:alert(1))\n' + 'Long text ' * 110},
                   {'role': 'event', 'text': 'read_file fixture\nLiteral tool output <svg onload=window.__xss=1>'}]
        evaluate("window.__originalFetch=window.fetch;window.fetch=async (url,options)=>{const q=options?.body?JSON.parse(options.body):null;if(q?.method==='session.history')return new Response(JSON.stringify({result:"+json.dumps(fixture)+"}),{status:200});return __originalFetch(url,options)};let banner=document.createElement('p');banner.id='fixture-label';banner.textContent='RENDERER FIXTURE ONLY · no model or native job';banner.className='error';document.querySelector('.composer-wrap').prepend(banner)")
        click('#sessions button'); time.sleep(.5); evaluate("document.getElementById('messages').scrollTop=0"); capture('fixture-conversation-1440.png')
        record['checks']['safe_fixture_rendering'] = evaluate("!window.__xss && document.querySelectorAll('#messages img,#messages svg,#messages [href^=javascript]').length===0 && !!document.querySelector('#messages pre code') && !!document.querySelector('#messages details')")
        evaluate("document.getElementById('files-toggle').click();document.getElementById('changes-tab').click();document.getElementById('diff').textContent=\"--- program.py\\n+++ program.py\\n@@ -1 +1 @@\\n-return value\\n+return min(100, max(0, value))\";document.getElementById('validation').textContent='Renderer fixture only. No native validation or apply ticket.'")
        capture('fixture-diff-1440.png')
        record['checks']['fixture_apply_unavailable'] = evaluate("document.getElementById('apply').hidden")
        metric(390, 844); capture('fixture-diff-390.png'); key('Escape')
        evaluate("document.getElementById('messages').scrollTop=0");capture('fixture-conversation-390.png')
        record['fixture_viewport'] = evaluate("({width:innerWidth,height:innerHeight,app:document.getElementById('app').getBoundingClientRect().height,composer:document.getElementById('composer').getBoundingClientRect().toJSON()})")
        record['checks']['long_conversation_composer_visible'] = record['fixture_viewport']['composer']['bottom'] <= record['fixture_viewport']['height']
        record['served_assets'] = {}
        for name in ['index.html','app.js','style.css','fonts/BebasNeue.ttf','fonts/DMSans.ttf']:
            route = '/hermes-workspace' if name == 'index.html' else '/' + name
            with urllib.request.urlopen(launcher.ORIGIN + route,timeout=2) as response: served=response.read()
            record['served_assets'][name] = hashlib.sha256(served).hexdigest()
            assert served == (ROOT / 'workspace/ui' / name).read_bytes()
        record['all_passed'] = all(record['checks'].values())
        record['production_conversation_gap'] = 'The production catalog contains no messages or jobs. Conversation/diff screenshots are explicitly labelled isolated renderer fixtures. No model response or native apply proof is claimed.'
        (evidence / 'browser-validation.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record, indent=2))
        return 0 if record['all_passed'] else 2
    except Exception as error:
        record['error'] = str(error); record['all_passed'] = False
        (evidence / 'browser-validation-failure.json').write_text(json.dumps(record, indent=2) + '\n')
        raise
    finally:
        (evidence / 'browser-validation-last.json').write_text(json.dumps(record, indent=2) + '\n')
        try: pipe.call('Browser.close')
        except (OSError, RuntimeError, TimeoutError): pass
        os.close(pipe.read); os.close(pipe.write)


if __name__ == '__main__': raise SystemExit(main())
