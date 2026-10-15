"""Real Wayland scale/cursor checks; always restore the original display mode."""
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace.parity_browser import Browser
from workspace import launcher

def command(*args):return subprocess.check_output(args,text=True,timeout=6).strip()
def clients():return json.loads(command('hyprctl','clients','-j'))
def monitors():return json.loads(command('hyprctl','monitors','-j'))
def dispatch(code):return command('hyprctl','dispatch',code)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--port',type=int,choices=(18791,18793),default=18793);args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True,mode=0o700)
    if subprocess.run(['pgrep','-x','hyprlock'],capture_output=True).returncode==0:
        blocked={'status':'BLOCKED','reason':'Native session is locked; no unlock or security change attempted.','display_changes':'none in this attempt','earlier_native_checks':'see native/native.json'}
        (out/'native.json').write_text(json.dumps(blocked,indent=2)+'\n');print(json.dumps(blocked));raise SystemExit(2)
    launcher.ORIGIN='http://127.0.0.1:'+str(args.port);b=Browser('local-chat-native',headed=True,fixture=False,quiet=True)
    report={'kind':'actual Wayland compositor and native cursor/key injection; no device emulation; not physical human approval','scales':[],'status':'IN_PROGRESS'};original=None;watchdog=None
    try:
        marker='Hermes native pointer review '+os.urandom(4).hex();b.evaluate('document.title='+json.dumps(marker));time.sleep(.2)
        # Restored review profiles can have multiple windows with the same PID.
        # Identify the exact CDP target's native surface, not the first PID match.
        client=next(c for c in clients() if c.get('title')==marker and launcher.owns_browser(c['pid']));address=client['address'];assert re.fullmatch(r'0x[0-9a-f]+',address)
        window='address:'+address;monitor=next(m for m in monitors() if m['id']==client['monitor']);original={k:monitor[k]for k in ['name','width','height','x','y','scale','refreshRate']}
        mode=f"{original['width']}x{original['height']}@{original['refreshRate']:.3f}"
        def rule(scale):return 'hl.monitor({output='+json.dumps(original['name'])+',mode='+json.dumps(mode)+',position='+json.dumps(str(original['x'])+'x'+str(original['y']))+',scale='+str(scale)+'})'
        restore=rule(original['scale'])
        watchdog=subprocess.Popen([sys.executable,'-c','import subprocess,time;time.sleep(55);subprocess.run(["hyprctl","eval",'+repr(restore)+'],timeout=6)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        b.evaluate("window.__nativeMove=null;window.__nativeClicks=[];addEventListener('pointermove',e=>window.__nativeMove={x:e.clientX,y:e.clientY,trusted:e.isTrusted,id:e.target.closest('button')?.id||null},true);addEventListener('click',e=>window.__nativeClicks.push({id:e.target.closest('button')?.id,trusted:e.isTrusted}),true)")
        for scale in (1,2):
            command('hyprctl','eval',rule(scale));time.sleep(.5)
            observed=next(m for m in monitors() if m['name']==original['name']);assert abs(observed['scale']-scale)<.01
            client=next(c for c in clients() if c['address']==address)
            if client.get('fullscreen'):
                mode_name='maximized' if client['fullscreen']==1 else 'fullscreen'
                dispatch('hl.dsp.window.fullscreen({window='+json.dumps(window)+',mode='+json.dumps(mode_name)+',action="toggle"})')
            if not client.get('floating'):dispatch('hl.dsp.window.float({window='+json.dumps(window)+',action="toggle"})')
            dispatch('hl.dsp.window.resize({window='+json.dumps(window)+',x=910,y=500,relative=false})');dispatch('hl.dsp.window.center({window='+json.dumps(window)+'})');dispatch('hl.dsp.focus({window='+json.dumps(window)+'})');time.sleep(.5);b.call('Page.bringToFront')
            client=next(c for c in clients() if c['address']==address);previous=None
            for attempt in range(20):
                points=[]
                for dx,dy in ((450,140),(530,220)):
                    gx=client['at'][0]+dx;gy=client['at'][1]+dy;dispatch(f'hl.dsp.cursor.move({{x={gx},y={gy}}})');time.sleep(.08);p=b.evaluate('window.__nativeMove')
                    if p:points.append((gx,gy,p))
                if len(points)!=2:continue
                report.setdefault('calibration_readbacks',[]).append({'scale':scale,'attempt':attempt,'points':points})
                cx=points[1][2]['x']-points[0][2]['x'];cy=points[1][2]['y']-points[0][2]['y']
                if not cx or not cy:continue
                sx=80/cx;sy=80/cy;ox=points[0][0]-points[0][2]['x']*sx;oy=points[0][1]-points[0][2]['y']*sy;current=[sx,sy,ox,oy]
                if abs(sx-1)<.015 and abs(sy-1)<.015 and previous and max(abs(a-c)for a,c in zip(previous,current))<1:break
                previous=current
            else:raise RuntimeError('native_cursor_mapping_not_stable')
            row={'compositor_scale':scale,'Wayland':not client.get('xwayland'),'browser':b.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})'),'samples':[]};report['scales'].append(row)
            rect=b.rect('#settings-toggle')
            for u in (.25,.5,.75):
                for v in (.25,.5,.75):
                    x=rect['x']+rect['width']*u;y=rect['y']+rect['height']*v;dispatch(f'hl.dsp.cursor.move({{x={round(ox+x*sx)},y={round(oy+y*sy)}}})');time.sleep(.025);p=b.evaluate('window.__nativeMove')
                    row['samples'].append({'trusted':p['trusted'],'target':p['id'],'CSS_error':[round(p['x']-x,3),round(p['y']-y,3)]})
            assert all(p['trusted'] and p['target']=='settings-toggle' and max(map(abs,p['CSS_error']))<=1.5 for p in row['samples'])
            for state in ('down','up'):dispatch('hl.dsp.send_key_state({window='+json.dumps(window)+',mods="",key="mouse:272",state='+json.dumps(state)+'})')
            b.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'");time.sleep(.2)
            row['native_click']=b.evaluate("window.__nativeClicks.some(e=>e.id==='settings-toggle'&&e.trusted)");assert row['native_click']
            b.capture(out/f'native-{scale}x.png');rect=b.rect('dialog[open]');b.capture(out/f'native-{scale}x-edge.png',{'x':rect['x'],'y':rect['y'],'width':rect['width'],'height':rect['height'],'scale':1})
            b.key('Escape');b.wait("!document.querySelector('dialog[open]')")
        report['status']='PASS'
    except Exception as error:report.update(status='FAIL',error=str(error));raise
    finally:
        if original:
            command('hyprctl','eval',restore);time.sleep(.3);m=next(m for m in monitors() if m['name']==original['name']);report['scale_and_position_restored']=m['scale']==original['scale'] and m['x']==original['x'] and m['y']==original['y']
            if report['scale_and_position_restored'] and watchdog:watchdog.terminate();watchdog.wait(timeout=3)
        (out/'native.json').write_text(json.dumps(report,indent=2)+'\n');b.close()

if __name__=='__main__':main()
