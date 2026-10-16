"""Browser-emulated preferences inside root's existing guarded owned-A review.

No browser/server/record creation, OS setting change, saved motion preference,
model/policy request or explicit audio API. Outer OwnedInteractions owns restoration
of the view/theme/global attachments/composing intent and all capture paths.
"""
import json
import re

from scripts.v6_surface_review import capture_context,compare_context,require

PREFERENCES = (
    ('reduced-motion','prefers-reduced-motion','reduce'),
    ('reduced-transparency','prefers-reduced-transparency','reduce'),
    ('forced-colors','forced-colors','active'),
    ('high-contrast','prefers-contrast','more'),
)
THEMES = ('dark','light')


def selected_preferences(names=None):
    if names is None:return PREFERENCES
    require(isinstance(names,(tuple,list)) and 0<len(names)<=len(PREFERENCES)
            and all(isinstance(name,str) for name in names) and len(set(names))==len(names),
            'bounded_unique_preference_names_required')
    known={row[0]:row for row in PREFERENCES}
    require(all(name in known for name in names),'fixed_preference_name_required')
    return tuple(known[name] for name in names)


def media_state(browser):
    return browser.evaluate('Object.fromEntries('+json.dumps([(name,'('+feature+': '+value+')') for name,feature,value in PREFERENCES])+
                            '.map(([name,query])=>[name,matchMedia(query).matches]))')


def sample_surface(browser,selector):
    """Read styles/rectangles only; never export user text, file names or input."""
    return browser.evaluate('''(()=>{const e=document.querySelector('''+json.dumps(selector)+''');if(!e)throw Error('preference_surface_missing');
      const style=(node,pseudo=null)=>{if(!node)return null;const c=getComputedStyle(node,pseudo);return {
        display:c.display,visibility:c.visibility,opacity:c.opacity,color:c.color,background:c.backgroundColor,
        border:c.borderColor,backdrop:c.backdropFilter,animation:c.animationName,transition:c.transitionDuration,
        scroll:c.scrollBehavior,forced_adjust:c.forcedColorAdjust}};
      const control=e.querySelector('[data-action="close-dialog"]')||e.querySelector('[role="menuitem"]:not(:disabled),input:not(:disabled),button:not(:disabled)');
      const r=control?.getBoundingClientRect(),hit=r?document.elementFromPoint(r.x+r.width/2,r.y+r.height/2):null;
      const v=visualViewport;return {surface:style(e),rect:e.getBoundingClientRect().toJSON(),
        backdrop:style(e,'::backdrop'),viewport:{left:v?.offsetLeft??0,top:v?.offsetTop??0,width:v?.width??innerWidth,height:v?.height??innerHeight},
        control:control?{tag:control.tagName,role:control.getAttribute('role'),style:style(control),rect:r.toJSON(),
          center_hit:!!hit&&(hit===control||control.contains(hit))}:null,
        focus_inside:e.contains(document.activeElement),native_modal:e.matches('dialog:modal'),
        range:style(e.querySelector('#reasoning-effort')),rim:style(document.querySelector('.metal-rim i')),
        saved_motion:document.documentElement.dataset.motion}})()''')


def assess_sample(sample,mode):
    rect,view=sample['rect'],sample['viewport']
    margins={'left':rect['x']-view['left'],'top':rect['y']-view['top'],
             'right':view['left']+view['width']-rect['x']-rect['width'],
             'bottom':view['top']+view['height']-rect['y']-rect['height']}
    require(all(value>=7.5 for value in margins.values()),'emulated_preference_surface_exceeds_8px_bounds')
    panel=sample['surface']
    require(panel['display']!='none' and panel['visibility']=='visible' and float(panel['opacity'])>0,
            'emulated_preference_surface_not_visible')
    require(sample['control'] and sample['control']['center_hit'],'emulated_preference_control_not_hittable')
    if sample['native_modal']:
        require(sample['focus_inside'],'emulated_preference_modal_focus_outside')
    if mode=='reduced-transparency':
        require(panel['backdrop'] in ('none','') and sample['backdrop']['backdrop'] in ('none',''),
                'reduced_transparency_surface_or_backdrop_blur_survived')
        if sample['rim']:
            require(sample['rim']['animation']=='none' and float(sample['rim']['opacity'])==0,
                    'reduced_transparency_reflection_work_survived')
    if mode=='reduced-motion':
        require(all(name.strip()=='none' for name in panel['animation'].split(','))
                and all(float(value.strip().removesuffix('s'))==0 for value in panel['transition'].split(',')),
                'reduced_motion_surface_CSS_work_survived')
        if sample['rim']:require(sample['rim']['animation']=='none','reduced_motion_reflection_work_survived')
    if mode=='forced-colors':
        require(panel['color']!=panel['background'],'forced_colors_surface_foreground_equals_background')
        if sample['range']:
            require(float(sample['range']['opacity'])>0 and sample['range']['forced_adjust']=='auto',
                    'forced_colors_native_range_fallback_missing')
        if sample['rim']:require(sample['rim']['display']=='none','forced_colors_reflection_fallback_missing')
    return {'status':'PASS_COMPUTED_AND_GEOMETRY_ONLY','margins_CSS_px':margins,
            'contrast_certification':False,'continuous_motion_review':False}


def review_preferences(review,*,assert_owned_a,set_theme,names=None):
    """Compose with SurfaceReview; caller supplies existing guarded captures.

    Use a fresh CDP media baseline (or clear the caller's earlier overrides
    before entry). Effective four-query baseline is checked again after clear.
    Root's outer OwnedInteractions cleanup restores the theme/view and storage;
    this helper deliberately never writes those values or a motion setting.
    """
    preferences=selected_preferences(names)
    require(callable(assert_owned_a) and callable(set_theme) and callable(review.capture),
            'owned_A_guard_theme_and_existing_capture_callbacks_required')
    assert_owned_a();review._guard()
    browser=review.b;original_capture=review.capture
    baseline=media_state(browser)
    saved_motion=browser.evaluate('document.documentElement.dataset.motion')
    result={'kind':'browser_emulated_preferences','status':'IN_PROGRESS','states':[],'cleanup':{},
            'scope':'CDP media emulation + computed styles + existing native surface focus/input checks on owned A only.',
            'not_proven':['OS preferences','physical input/device/assistive technology','human visual/motion approval',
                          'GPU/presentation timing','live model/microphone/guest execution','contrast certification'],
            'effective_media_before':baseline,'saved_motion_before':saved_motion,'saved_motion_unchanged':False,
            'reduced_motion_attribution':'Saved reduced motion remains active when already selected; CSS readback alone does not isolate the media query from that saved preference.'}
    review.rows.append(result)
    active=None
    try:
        for mode,feature,value in preferences:
            result['phase']='media:'+mode
            browser.call('Emulation.setEmulatedMedia',{'features':[{'name':feature,'value':value}]})
            supported=browser.evaluate('matchMedia('+json.dumps('('+feature+': '+value+')')+').matches')
            if not supported:
                result['states'].extend({'mode':mode,'theme':color,'status':'BLOCKED',
                    'reason':'browser_did_not_expose_requested_media_query'} for color in THEMES)
                browser.call('Emulation.setEmulatedMedia',{'features':[]})
                continue
            for color in THEMES:
                active={'mode':mode,'feature':feature,'value':value,'theme':color,'status':'IN_PROGRESS','samples':[]}
                result['states'].append(active)
                result['phase']='surfaces:'+mode+':'+color
                assert_owned_a();review.close();set_theme(color)
                browser.wait('document.documentElement.dataset.theme==='+json.dumps(color))
                require(browser.evaluate('document.documentElement.dataset.motion')==saved_motion,'saved_motion_preference_changed')
                assert_owned_a();before=capture_context(browser,review.rpc)
                def capture(name,selector):
                    assert_owned_a();review._guard()
                    computed=sample_surface(browser,selector)
                    sample={'name':name,'computed':computed,'assessment':{'status':'IN_PROGRESS'}}
                    active['samples'].append(sample)
                    sample['assessment']=assess_sample(computed,mode)
                    # The existing callback performs root's positive harmless-A
                    # and nonce filter check before any pixels are acquired.
                    original_capture('preference-'+mode+'-'+color+'-'+name,selector)
                review.capture=capture
                review.popover('#plus-menu','#composer-actions')
                review.popover('#effort-toggle','#effort-options',menu=False)
                review.click('#settings-toggle')
                review.modal_opened('Settings',return_selector='#settings-toggle')
                review.sheets()
                assert_owned_a()
                preservation=compare_context(before,capture_context(browser,review.rpc))
                require(preservation['status']=='PASS','preference_surfaces_changed_owned_A_context')
                require(browser.evaluate('document.documentElement.dataset.motion')==saved_motion,'saved_motion_preference_changed')
                active.update(status='PASS_SCOPED_EMULATED_TECHNICAL',preservation=preservation)
            browser.call('Emulation.setEmulatedMedia',{'features':[]})
        result['status']='PARTIAL_EMULATED' if any(row['status']=='BLOCKED' for row in result['states']) else 'PASS_SCOPED_EMULATED_TECHNICAL'
    except BaseException as error:
        result['status']='FAIL'
        if active is not None and active['status']=='IN_PROGRESS':active['status']='FAIL'
        code=str(error)
        result['error_category']=type(error).__name__
        result['error_code']=code if re.fullmatch('[a-zA-Z][a-zA-Z0-9_]{0,159}',code) else 'preference_review_failed'
        raise
    finally:
        failures=[]
        for name,operation in (('close_surfaces',review.close),
                               ('clear_CDP_media',lambda:browser.call('Emulation.setEmulatedMedia',{'features':[]})),
                               ('owned_A',assert_owned_a)):
            try:operation();result['cleanup'][name]={'status':'PASS'}
            except BaseException as error:
                result['cleanup'][name]={'status':'FAIL','error_category':type(error).__name__};failures.append(error)
        review.capture=original_capture
        try:
            result['effective_media_restored']=media_state(browser)
            require(result['effective_media_restored']==baseline,'initial_effective_media_not_restored')
            result['saved_motion_unchanged']=browser.evaluate('document.documentElement.dataset.motion')==saved_motion
            require(result['saved_motion_unchanged'],'saved_motion_preference_changed')
            result['cleanup']['media_and_motion_readback']={'status':'PASS'}
        except BaseException as error:
            result['cleanup']['media_and_motion_readback']={'status':'FAIL','error_category':type(error).__name__};failures.append(error)
        if failures:
            result['status']='FAIL'
            raise RuntimeError('preference_cleanup_failed_outer_recovery_required') from failures[0]
    return result
