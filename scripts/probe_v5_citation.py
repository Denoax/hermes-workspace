"""Actual18791 assistant citation observer; one owned normal-model turn, no execution by default."""
import argparse, hashlib, json, os, re, subprocess, sys, time, uuid
from pathlib import Path
from urllib.parse import urlsplit
ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'completed','failed','cancelled'}
def check(value, code):
    if not value: raise RuntimeError(code)
def actions_case(document):
    """Accept only a real completed provider action in an explicitly created case."""
    check(isinstance(document,dict),'real_actions_object_required')
    case = document.get('case', {}); check(isinstance(case,dict),'owned_case_object_required'); nonce = case.get('nonce','')
    check(bool(re.fullmatch(r'V5review-[0-9a-f]{8}-actions-[0-9a-f]{8}',nonce)), 'owned_action_nonce_required')
    sid,pid = case.get('permission_session'),case.get('project_id')
    check(all(isinstance(x,str) and re.fullmatch(r'[a-f0-9]{32}',x) for x in (sid,pid)) and sid in case.get('created_session_ids',[]),'positive_owned_case_IDs_required')
    action = document.get('checks',{}).get('real_Wikipedia_search',{})
    result = action.get('result',{}); attachment = result.get('attachment',{})
    sources = result.get('sources',[])
    check(action.get('state')=='completed' and result.get('provider')=='Wikipedia','completed_real_Wikipedia_action_required')
    check(isinstance(attachment,dict) and bool(re.fullmatch(r'[a-f0-9]{32}',attachment.get('id',''))),'existing_search_attachment_required')
    check(isinstance(sources,list) and 1<=len(sources)<=4,'bounded_real_sources_required')
    for source in sources:
        check(isinstance(source,dict) and isinstance(source.get('id'),str) and 0<len(source['id'])<=128 and isinstance(source.get('title'),str) and source['title'].strip(),'source_identity_required')
        check(isinstance(source.get('url'),str),'source_URL_required');url = urlsplit(source['url'])
        check(url.scheme=='https' and url.hostname=='en.wikipedia.org' and not url.username and not url.password and not url.port and url.path.startswith('/wiki/'),'canonical_Wikipedia_source_required')
    check(len({s['id'] for s in sources})==len(sources),'unique_source_IDs_required')
    return case, attachment['id'], sources

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actions',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--app-root',type=Path,default=ROOT);p.add_argument('--execute-production-probe',action='store_true');p.add_argument('--preview-only',type=Path);a=p.parse_args()
    check(a.execute_production_probe and os.geteuid()!=0,'explicit_normal_operator_execution_required')
    check(not a.actions.is_symlink() and a.actions.stat().st_size<2*1024*1024,'bounded_real_actions_receipt_required')
    case,aid,sources=actions_case(json.loads(a.actions.read_text()));sid,pid,nonce=case['permission_session'],case['project_id'],case['nonce']
    root=a.app_root.resolve(strict=True);sys.path.insert(0,str(root))
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import close_panels,prepare,input_text,move,native_pointer_check,enable_native_input
    from workspace.chat import wait_for_normal_recovery
    from workspace.server import normal_profile_unchanged
    from workspace.capture import NativeWindowRecording
    check(not any(x.is_symlink() for x in (a.output,*a.output.parents)),'output_symlink_refused');a.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    check(a.output.stat().st_uid==os.getuid() and not a.output.stat().st_mode&0o077,'private_output_required');target=a.output/'citation.json';check(not target.exists(),'new_output_required')
    digest=lambda x:hashlib.sha256(x).hexdigest()
    r={'status':'IN_PROGRESS','scope':'actual18791; existing genuine search attachment and one real normal-model turn','session_id':sid,'project_id':pid,'attachment_id':aid,'sources':sources,'actions_sha256':digest(a.actions.read_bytes()),'probe_sha256':digest(Path(__file__).read_bytes()),'new_sessions':0,'new_attachments':0,'captures':[],'cleanup':{},'human_approval':'PENDING','physical_input':'NOT_CLAIMED'}
    b=recording=None;initial=draft=storage=own_storage=None;run_id=None;leave_open=False;cursor=None;selection_touched=False;original_filter=''
    own_key='hermes:draft-attachments:v1:'+sid
    def save():target.write_text(json.dumps(r,indent=2)+'\n');target.chmod(0o600)
    def ev(s):return b.evaluate(s)
    def cleanup(name,fn):
        try:r['cleanup'][name]=fn()
        except Exception as e:r['cleanup'][name]={'error_type':type(e).__name__,'code':str(e) if str(e).isidentifier() else 'cleanup_failed'};r['status']='FAIL'
    def tooltip_settled():
        # Observe computed values; do not force opacity or stop the spring.
        proof=ev('''(()=>new Promise(resolve=>{const end=performance.now()+2500;let last=null,stable=0,rows=[];function sample(){const e=document.querySelector('[data-slot="web-search-citation"] [role="tooltip"]');if(e){const c=getComputedStyle(e),q=e.getBoundingClientRect(),m=new DOMMatrixReadOnly(c.transform==='none'?undefined:c.transform),v={opacity:+c.opacity,transform:c.transform,filter:c.filter,x:q.x,y:q.y,width:q.width,height:q.height};stable=last&&v.opacity>=.995&&Math.abs(m.a-1)<=.002&&Math.abs(m.d-1)<=.002&&Math.abs(m.f)<=.25&&(c.filter==='none'||c.filter==='blur(0px)')&&['x','y','width','height'].every(k=>Math.abs(v[k]-last[k])<=.25)?stable+1:0;last=v;rows.push(v);if(rows.length>48)rows.shift();if(stable>=4)return resolve({status:'settled',rows})}if(performance.now()>end)return resolve({status:'timeout',rows});requestAnimationFrame(sample)}requestAnimationFrame(sample)}))()''')
        r.setdefault('tooltip_attempts',[]).append(proof);save();check(proof['status']=='settled','citation_tooltip_not_settled');return proof
    def tooltip_bounds():
        result=ev('(()=>{const e=document.querySelector(\'[data-slot="web-search-citation"] [role="tooltip"]\'),c=document.querySelector(".workspace-body").getBoundingClientRect(),r=e.getBoundingClientRect(),snippet=e.querySelector(".line-clamp-3"),s=snippet&&getComputedStyle(snippet),q=snippet?.getBoundingClientRect();return {tooltip:r.toJSON(),clip:c.toJSON(),snippet:snippet?{height:q.height,line_height:parseFloat(s.lineHeight),scroll_height:snippet.scrollHeight,client_height:snippet.clientHeight}:null,visible:r.top>=Math.max(0,c.top)-.5&&r.bottom<=Math.min(innerHeight,c.bottom)+.5&&r.left>=Math.max(0,c.left)-.5&&r.right<=Math.min(innerWidth,c.right)+.5}})()')
        check(result['visible'],'citation_tooltip_clipped_by_workspace')
        snippet=result['snippet'];check(snippet and snippet['height']<=snippet['line_height']*3+.5,'citation_real_snippet_not_clamped_to_three_lines')
        return result

    def capture(name):
        check(rpc(b,'view.read',{})['session_id']==sid and ev('document.querySelector(".rail-search input").value')==nonce,'capture_owned_scope_required')
        path=a.output/(name+'.png');b.capture(path);r['captures'].append({'file':path.name,'sha256':digest(path.read_bytes())});save()
    save()
    try:
        b=ProductionPin();r['pin']=b.identity;b.reload_ready();prepare(b);initial=rpc(b,'view.read',{});original_filter=ev('document.querySelector(".rail-search input").value')
        draft=rpc(b,'draft.read',{'session_id':initial['session_id']}) if initial.get('session_id') else None
        keys=['hermes-ui:sounds','hermes-ui:interface-volume','hermes:new-draft','hermes:draft-attachments:v1:new','hermes:draft-attachments:v1:'+(initial.get('session_id') or 'new'),own_key]
        storage=ev('Object.fromEntries('+json.dumps(keys)+'.map(k=>[k,localStorage.getItem(k)]))')
        # Unknown unsaved text/attachment UI is preserved by leaving its document open.
        if ev('!!document.querySelector("#cancel-response,.recording-indicator")') or ev('document.querySelector("#prompt").value')!=(draft['text'] if draft else (storage.get('hermes:new-draft') or '')) or ev('document.querySelectorAll("#composer .attachment,.attachment-issues").length'):
            leave_open=True;raise RuntimeError('unowned_unsent_input_preserved')
        actual=next((s for s in rpc(b,'session.list',{}) if s['id']==sid),None);project=next((x for x in rpc(b,'workspace.list',{}) if x['id']==pid),None)
        check(actual and actual['project']==pid and actual['title']==nonce+' · Permission checks' and project and project['label']==nonce+' · Action review','actual_owned_case_identity_mismatch')
        snap=rpc(b,'chat.snapshot',{'session_id':sid});check(not snap['runs'] and not snap['messages'],'owned_permission_case_has_prior_conversation')
        metadata=rpc(b,'attachment.metadata',{'id':aid});canonical=metadata.get('metadata',{}).get('search',{})
        check(canonical.get('provider')=='Wikipedia' and canonical.get('sources')==sources,'canonical_attachment_does_not_match_real_provider_result')
        # The permission/search case can retain an unsent draft. Preserve it
        # and attach its verified result in one newly identified conversation.
        preview=None
        if a.preview_only:
            check(not a.preview_only.is_symlink() and a.preview_only.stat().st_size<2*1024*1024,'bounded_existing_citation_receipt_required')
            preview=json.loads(a.preview_only.read_text())
            check(preview['actions_sha256']==r['actions_sha256'] and preview['attachment_id']==aid and preview['source_permission_session_id']==sid,'previous_citation_scope_mismatch')
            sid=preview['session_id'];check(re.fullmatch(r'[a-f0-9]{32}',sid),'previous_created_session_ID_required')
            found=next((x for x in rpc(b,'session.list',{}) if x['id']==sid),None)
            check(found and found['project']==pid and found['title']==nonce+' · Citation check','previous_created_citation_case_changed')
            r.update(session_id=sid,source_permission_session_id=case['permission_session'],new_sessions=0,preview_only_receipt_sha256=digest(a.preview_only.read_bytes()),new_response_generated=False)
        else:
            existing={row['id'] for row in rpc(b,'session.list',{})}
            created=rpc(b,'session.create',{'project_id':pid,'arm':'normal'})
            check(created['id'] not in existing and re.fullmatch(r'[a-f0-9]{32}',created['id']),'new_owned_citation_session_required')
            r['source_permission_session_id']=sid;sid=created['id'];r['session_id']=sid;r['new_sessions']=1;save()
            rpc(b,'session.rename',{'session_id':sid,'title':nonce+' · Citation check'})
        own_key='hermes:draft-attachments:v1:'+sid;keys.append(own_key);storage[own_key]=ev('localStorage.getItem('+json.dumps(own_key)+')')
        check(storage[own_key] is None,'new_citation_scope_already_has_selection')
        check(normal_profile_unchanged(),'normal_four_configuration_pins_changed');r['normal_before']=wait_for_normal_recovery(timeout=120)
        r['source_sha256']={n:digest((root/n).read_bytes()) for n in ['workspace/frontend/src/MessageMarkdown.tsx','workspace/frontend/src/lib/citations.ts','workspace/frontend/src/components/web-search.tsx','workspace/ui/dist/app.js','workspace/ui/dist/app.css']}
        r['served_sha256']=ev('(async()=>{const o={};for(const n of ["app.js","app.css"]){const q=await fetch("/assets/"+n,{cache:"no-store"});if(!q.ok)throw Error("served_asset_missing");o[n]=[...new Uint8Array(await crypto.subtle.digest("SHA-256",await q.arrayBuffer()))].map(v=>v.toString(16).padStart(2,"0")).join("")}return o})()')
        check(all(r['served_sha256'][n]==r['source_sha256']['workspace/ui/dist/'+n] for n in ('app.js','app.css')),'served_build_mismatch')
        rpc(b,'view.write',{'state':{**initial,'session_id':sid,'project_id':pid,'arm':'normal','task_kind':'chat'}})
        # Restore a selection pointing only to the existing server-verified attachment;
        # no upload,metadata,response or search result is manufactured.
        if preview:
            ev('localStorage.setItem("hermes-ui:sounds","off")');b.reload_ready();prepare(b);input_text(b,'.rail-search input',nonce)
            snap=rpc(b,'chat.snapshot',{'session_id':sid});run_id=preview['run_id'];row=rpc(b,'chat.read',{'run_id':run_id})
            check(row['session']==sid and row['settings']['prompt_sha256']==preview['prompt_sha256'],'previous_real_citation_run_changed')
            r.update(run_id=run_id,prompt_sha256=preview['prompt_sha256'])
        else:
            ev('localStorage.setItem('+json.dumps(own_key)+','+json.dumps(json.dumps({'version':1,'revision':uuid.uuid4().hex,'ids':[aid]}))+')');selection_touched=True
            ev('localStorage.setItem("hermes-ui:sounds","off")');b.reload_ready();prepare(b);input_text(b,'.rail-search input',nonce)
            b.wait('document.querySelectorAll("#composer .attachment").length===1&&!document.querySelector("#prompt").disabled&&document.querySelector("#model-picker").value==="normal"')
            ready=rpc(b,'readiness.read',{});check(ready['state']=='ready' and ready['models']['normal']['available'],'protected_normal_admission_unavailable')
            prompt='Use the attached Wikipedia results. Write one short factual sentence about source 1 and append [1] to cite source 1. No other text.'
            r['prompt_sha256']=digest(prompt.encode());input_text(b,'#prompt',prompt);b.wait('!document.querySelector("#send").disabled');b.click('#send');started=time.monotonic()
            while time.monotonic()-started<180:
                snap=rpc(b,'chat.snapshot',{'session_id':sid});row=next((x for x in snap['runs'] if x['settings']['prompt_sha256']==r['prompt_sha256']),None)
                if row:
                    run_id=row['id'];r['run_id']=run_id;save()
                    if row['state'] in TERMINAL:break
                time.sleep(.5)
            else:raise TimeoutError('actual_citation_turn_deadline')
        check(row['state']=='completed' and row['identity']['arm']=='normal' and row['identity']['context']==65536 and len(snap['runs'])==1,'real_normal_turn_not_completed_once')
        check(row['settings'].get('attachments')==[aid],'submitted_real_search_attachment_mismatch')
        answer=''.join(m['text'] for m in snap['messages'] if m['role']=='assistant' and m.get('job')==run_id);r['answer_sha256']=digest(answer.encode());r['run']=row
        check('[1]' in answer,'actual_model_did_not_emit_citation');b.wait('!!document.querySelector(".message.assistant [data-slot=web-search-citation]>a")')
        selector='.message.assistant [data-slot="web-search-citation"]>a';check(ev('document.querySelector('+json.dumps(selector)+').href')==sources[0]['url'],'actual_inline_citation_href_mismatch')
        close_panels(b);prepare(b);b._native_coordinates=None;proof=native_pointer_check(b);check(proof['status']=='PASS','native_pointer_not_qualified');r['native_pointer']=proof;cursor=b._native_initial_cursor;enable_native_input(b)
        ev('document.querySelector('+json.dumps(selector)+').scrollIntoView({block:"center"})');recording=NativeWindowRecording(b,a.output/'citation-native-unedited.mp4')
        r['citation_node_retained_during_idle']=ev('(async()=>{const a=document.querySelector('+json.dumps(selector)+');await new Promise(resolve=>setTimeout(resolve,4200));return a===document.querySelector('+json.dumps(selector)+')&&a.isConnected})()')
        check(r['citation_node_retained_during_idle'],'citation_remounted_during_idle_poll_window')
        rect=b.rect(selector);move(b,rect['x']+rect['width']/2,rect['y']+rect['height']/2);r['hover_settled']=tooltip_settled();r['hover_bounds']=tooltip_bounds();capture('citation-native-hover')
        move(b,20,100);b.wait('!document.querySelector("[data-slot=web-search-citation] [role=tooltip]")')
        ev('(()=>{const target=document.querySelector('+json.dumps(selector)+'),all=[...document.querySelectorAll("a[href],button,input,select,textarea,[tabindex=\\"0\\"]")].filter(e=>!e.disabled&&e.getClientRects().length),i=all.indexOf(target);if(i<1)throw Error("citation_Tab_anchor_missing");all[i-1].focus();window.__citationTab=[];addEventListener("keydown",e=>{if(e.key==="Tab")window.__citationTab.push({trusted:e.isTrusted,key:e.key})},{once:true})})()')
        b.key('Tab');check(ev('document.activeElement===document.querySelector('+json.dumps(selector)+')&&document.activeElement.matches(":focus-visible")&&window.__citationTab.some(e=>e.trusted)'),'actual_Tab_focus_not_proven')
        r['keyboard_settled']=tooltip_settled();r['keyboard_bounds']=tooltip_bounds();capture('citation-Tab-focus');b.key('Tab');recording.hold(.4);r['recording']=recording.finish();recording=None
        before=snap;b.reload_ready();prepare(b);input_text(b,'.rail-search input',nonce);check(rpc(b,'chat.snapshot',{'session_id':sid})==before,'history_changed_after_reload');b.wait('!!document.querySelector('+json.dumps(selector)+')');check(ev('document.querySelector('+json.dumps(selector)+').href')==sources[0]['url'],'persisted_citation_source_changed');capture('citation-after-reload')
        r['status']='PASS_SCOPED_TECHNICAL'
    except Exception as e:r.update(status='FAIL',error_type=type(e).__name__,code=str(e) if str(e).isidentifier() else 'citation_probe_failed')
    finally:
        if recording:cleanup('partial_recording',lambda:recording.finish())
        if b:
            def stop_own():
                if run_id and rpc(b,'chat.read',{'run_id':run_id})['state'] not in TERMINAL:rpc(b,'chat.cancel',{'run_id':run_id})
                return True
            cleanup('cancel_only_own_active_run',stop_own)
            def recovery():
                r['normal_after']=wait_for_normal_recovery(timeout=120);check(r['normal_after']['context']==65536 and normal_profile_unchanged(),'normal_recovery_or_four_pins_failed');return True
            cleanup('normal_recovery_and_four_pins',recovery)
            def restore():
                nonlocal leave_open
                if storage and not leave_open:
                    # Never overwrite a draft or selection changed by another
                    # operator while the bounded observer was running.
                    current=ev('Object.fromEntries('+json.dumps(keys)+'.map(k=>[k,localStorage.getItem(k)]))')
                    unchanged=[k for k in keys if k not in (own_key,'hermes-ui:sounds')]
                    if any(current[k]!=storage[k] for k in unchanged) or current['hermes-ui:sounds'] not in (storage['hermes-ui:sounds'],'off') or (selection_touched and rpc(b,'draft.read',{'session_id':sid})['text']):
                        leave_open=True;raise RuntimeError('concurrent_original_or_owned_input_preserved')
                    if selection_touched and current[own_key]:
                        ids=json.loads(current[own_key]).get('ids')
                        if ids not in ([],[aid]):leave_open=True;raise RuntimeError('concurrent_owned_attachment_selection_preserved')

                    for key in (own_key,'hermes-ui:sounds','hermes-ui:interface-volume'):
                        if key==own_key and not selection_touched:continue
                        before=storage[key];ev('localStorage.'+('removeItem('+json.dumps(key)+')' if before is None else 'setItem('+json.dumps(key)+','+json.dumps(before)+')'))
                    rpc(b,'view.write',{'state':initial});b.reload_ready();input_text(b,'.rail-search input',original_filter)
                    check(rpc(b,'view.read',{})==initial,'initial_view_not_restored')
                    if draft:check(rpc(b,'draft.read',{'session_id':initial['session_id']})==draft,'original_draft_changed')
                return True
            cleanup('original_view_draft_selection_sound',restore)
            if isinstance(r['cleanup'].get('original_view_draft_selection_sound'),dict):leave_open=True
            def close_native():
                native=getattr(b,'_native_input',None)
                if native:native.close()
                if cursor:subprocess.run(['/usr/bin/hyprctl','dispatch',f'hl.dsp.cursor.move({{x={round(cursor["x"])},y={round(cursor["y"])}}})'],capture_output=True,check=True,timeout=4)
                return True
            cleanup('native_input_and_cursor',close_native)
            cleanup('pin',lambda:b.detach_preserving_document() if leave_open else b.close())
        save()
    print(json.dumps({'status':r['status'],'report':str(target),'session_id':sid,'run_id':run_id}),flush=True)
    if r['status']!='PASS_SCOPED_TECHNICAL':raise SystemExit(2)
if __name__=='__main__':main()
