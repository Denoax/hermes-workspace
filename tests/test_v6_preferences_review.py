"""Preference composition/filter/cleanup fixtures; no app/browser/native calls."""
import copy
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from scripts import v6_preferences_review as preferences


def sample(mode,native_modal=False):
    style={'display':'block','visibility':'visible','opacity':'1','color':'rgb(0,0,0)',
           'background':'rgb(255,255,255)','border':'rgb(0,0,0)','backdrop':'none',
           'animation':'none','transition':'0s','scroll':'auto','forced_adjust':'auto'}
    return {'surface':style.copy(),'rect':{'x':20,'y':20,'width':200,'height':150},
            'backdrop':style.copy(),'viewport':{'left':0,'top':0,'width':1320,'height':900},
            'control':{'center_hit':True,'tag':'BUTTON','style':style.copy()},
            'native_modal':native_modal,'focus_inside':True,'range':style.copy(),
            'rim':{**style,'display':'none','opacity':'0'},'saved_motion':'reduced'}


class Browser:
    def __init__(self):self.feature=None;self.theme='dark';self.calls=[];self.expose=True
    def call(self,method,fields):
        self.calls.append((method,copy.deepcopy(fields)))
        if method!='Emulation.setEmulatedMedia':raise AssertionError('Only media emulation allowed')
        self.feature=fields['features'][0]['name'] if fields['features'] else None
    def evaluate(self,source):
        if 'preference_surface_missing' in source:
            return sample(self.feature,'dialog' in source)
        if source=='document.documentElement.dataset.motion':return 'reduced'
        if source.startswith('matchMedia('):return self.expose
        if '.map(([name,query])' in source:
            return {name:self.expose and feature==self.feature for name,feature,_ in preferences.PREFERENCES}
        if 'localStorage.getItem' in source:return {'owned_storage':'unchanged'}
        if '#prompt' in source:return 'owned harmless draft'
        if '#model-picker' in source:return 'normal'
        if 'scrollTop' in source:return {'top':0,'left':0}
        raise AssertionError('Unexpected fixture observation: '+source[:70])
    def wait(self,source):pass


class Review:
    def __init__(self):
        self.b=Browser();self.rows=[];self.frames=[];self.actions=[];self.fail_modal=False;self.fail_close=False
        self.capture=lambda name,selector:self.frames.append((name,selector))
    def _guard(self):pass
    def rpc(self,method,fields):
        if method=='view.read':return {'session_id':'a'*32,'theme':self.b.theme,'motion':'reduced'}
        if method=='draft.read':return {'text':'owned harmless draft','mode':'chat'}
        raise AssertionError('Unexpected RPC; no mutation allowed')
    def close(self):
        self.actions.append('close')
        if self.fail_close:raise RuntimeError('fixture_close_failed')
    def click(self,selector):
        self.actions.append(('click',selector));self.assert_settings(selector)
    @staticmethod
    def assert_settings(selector):
        if selector!='#settings-toggle':raise AssertionError('Only Settings opener allowed')
    def popover(self,trigger,surface,**kwargs):
        self.actions.append(('popover',trigger));self.capture('popover-'+surface[1:],surface)
    def modal_opened(self,label,**kwargs):
        if self.fail_modal:raise RuntimeError('fixture_modal_failed')
        self.capture('modal-settings','dialog[open][aria-label="Settings"]')
    def sheets(self):
        self.capture('surface-files','dialog[open]');self.capture('surface-details','dialog[open]')
    def theme(self,color):self.b.theme=color


class PreferenceReview(unittest.TestCase):
    def test_filter_accepts_only_bounded_unique_named_preferences(self):
        self.assertEqual(len(preferences.selected_preferences()),4)
        self.assertEqual(preferences.selected_preferences(['forced-colors']), (preferences.PREFERENCES[2],))
        for names in ([],['unknown'],['forced-colors','forced-colors'],'forced-colors',True):
            with self.subTest(names=names),self.assertRaises(RuntimeError):preferences.selected_preferences(names)

    def test_computed_checks_reject_real_bounds_hit_focus_and_fallback_defects(self):
        good=sample('forced-colors',True);self.assertEqual(preferences.assess_sample(good,'forced-colors')['status'],'PASS_COMPUTED_AND_GEOMETRY_ONLY')
        changes=[lambda s:s['rect'].update(x=1),lambda s:s['control'].update(center_hit=False),
                 lambda s:s.update(focus_inside=False),lambda s:s['range'].update(opacity='0')]
        for mutate in changes:
            value=copy.deepcopy(good);mutate(value)
            with self.subTest(value=value),self.assertRaises(RuntimeError):preferences.assess_sample(value,'forced-colors')
        value=sample('reduced-transparency');value['surface']['backdrop']='blur(28px)'
        with self.assertRaisesRegex(RuntimeError,'blur_survived'):preferences.assess_sample(value,'reduced-transparency')
        value=sample('reduced-motion');value['surface']['transition']='0.2s'
        with self.assertRaisesRegex(RuntimeError,'CSS_work_survived'):preferences.assess_sample(value,'reduced-motion')

    def test_all_four_preferences_cover_both_themes_and_restore_media_and_capture(self):
        review=Review();original=review.capture
        result=preferences.review_preferences(review,assert_owned_a=lambda:None,set_theme=review.theme)
        self.assertEqual(result['status'],'PASS_SCOPED_EMULATED_TECHNICAL')
        self.assertEqual({(row['mode'],row['theme']) for row in result['states']},
                         {(mode,color) for mode,_,_ in preferences.PREFERENCES for color in preferences.THEMES})
        self.assertEqual(review.b.calls[-1],('Emulation.setEmulatedMedia',{'features':[]}))
        self.assertIs(review.capture,original);self.assertTrue(result['saved_motion_unchanged'])
        self.assertEqual(result['saved_motion_before'],'reduced')
        self.assertTrue(all(row['preservation']['status']=='PASS' for row in result['states']))
        self.assertFalse(any('reduced_motion' in str(action) for action in review.actions))
        self.assertEqual(len(review.frames),40)

    def test_primary_surface_failure_still_clears_emulation_and_restores_callback(self):
        review=Review();original=review.capture;review.fail_modal=True
        with self.assertRaisesRegex(RuntimeError,'fixture_modal_failed'):
            preferences.review_preferences(review,assert_owned_a=lambda:None,set_theme=review.theme,names=['forced-colors'])
        self.assertIs(review.capture,original);self.assertIsNone(review.b.feature)
        self.assertEqual(review.rows[0]['status'],'FAIL');self.assertEqual(review.rows[0]['cleanup']['clear_CDP_media']['status'],'PASS')

    def test_failed_overlay_cleanup_does_not_skip_media_cleanup_or_report_success(self):
        review=Review();review.fail_close=True;original=review.capture
        with self.assertRaisesRegex(RuntimeError,'cleanup_failed_outer_recovery'):
            preferences.review_preferences(review,assert_owned_a=lambda:None,set_theme=review.theme,names=['reduced-motion'])
        self.assertIsNone(review.b.feature);self.assertIs(review.capture,original)
        self.assertEqual(review.rows[0]['cleanup']['close_surfaces']['status'],'FAIL')
        self.assertEqual(review.rows[0]['cleanup']['clear_CDP_media']['status'],'PASS')

    def test_unsupported_media_is_blocked_and_harmless_guard_precedes_capture(self):
        review=Review();review.b.expose=False
        result=preferences.review_preferences(review,assert_owned_a=lambda:None,set_theme=review.theme,names=['reduced-transparency'])
        self.assertEqual(result['status'],'PARTIAL_EMULATED');self.assertEqual(len(result['states']),2)
        self.assertTrue(all(row['status']=='BLOCKED' for row in result['states']));self.assertEqual(review.frames,[])
        review=Review();counter=[0]
        def guard():
            counter[0]+=1
            if counter[0]==4:raise RuntimeError('owned_A_changed_no_capture')
        with self.assertRaisesRegex(RuntimeError,'owned_A_changed_no_capture'):
            preferences.review_preferences(review,assert_owned_a=guard,set_theme=review.theme,names=['high-contrast'])
        self.assertEqual(review.frames,[]);self.assertIsNone(review.b.feature)


if __name__=='__main__':unittest.main()
