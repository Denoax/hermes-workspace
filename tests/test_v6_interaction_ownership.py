"""Hermetic ownership/storage tests; importing these never launches the app."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name('owned_v6_interactions.py')
if not MODULE.exists():
    MODULE = Path(__file__).resolve().parents[1]/'scripts/owned_v6_interactions.py'
spec = importlib.util.spec_from_file_location('owned_v6_interactions_under_test', MODULE)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.nonce='V6interaction-0123456789ab'
        self.a='a'*32
        self.d='d'*32
        self.p='1'*32
        self.case={'nonce':self.nonce,'created_ids':[self.a,self.d,self.p],
                   'records':{'A':{'id':self.a,'kind':'conversation','title':self.nonce+' · Conversation A','project':self.p},
                              'D':{'id':self.d,'kind':'conversation','title':self.nonce+' · Conversation D','project':self.p}}}
        self.rows=[{k:v for k,v in row.items() if k!='kind'} for row in self.case['records'].values()]

    def empty(self, **overrides):
        values={'snapshot':{'messages':[],'runs':[]},'draft':{'text':'','mode':'chat'},'jobs':[],'raw_selection':None}
        values.update(overrides)
        return review.disposable(self.case,'D',self.rows,**values)

    def test_exact_recorded_owned_empty_D_is_the_only_returned_target(self):
        self.assertEqual(self.empty(),self.d)

    def test_unknown_or_unrecorded_id_is_rejected(self):
        self.case['created_ids'].remove(self.d)
        with self.assertRaisesRegex(RuntimeError,'created_inventory'):
            self.empty()

    def test_changed_name_or_parent_is_preserved(self):
        for field,value in [('title','User renamed this'),('project','f'*32)]:
            with self.subTest(field=field):
                rows=copy.deepcopy(self.rows)
                next(row for row in rows if row['id']==self.d)[field]=value
                with self.assertRaises(RuntimeError):
                    review.owned_row(self.case,'D',rows)

    def test_bad_nonce_duplicate_receipt_or_wrong_id_shape_fails_closed(self):
        variants=[]
        bad=copy.deepcopy(self.case);bad['nonce']='V6interaction-arbitrary';variants.append(bad)
        bad=copy.deepcopy(self.case);bad['created_ids'].append(self.d);variants.append(bad)
        bad=copy.deepcopy(self.case);bad['records']['D']['id']=42;variants.append(bad)
        for case in variants:
            with self.subTest(case=case),self.assertRaises(RuntimeError):
                review.owned_row(case,'D',self.rows)

    def test_A_cannot_be_substituted_for_the_empty_delete_case(self):
        self.case['records']['D']=copy.deepcopy(self.case['records']['A'])
        with self.assertRaisesRegex(RuntimeError,'draft_owner_cannot_be_deleted'):
            self.empty()

    def test_acquired_history_runs_jobs_and_drafts_all_prevent_delete(self):
        for mutation in [{'snapshot':{'messages':[{'text':'new'}],'runs':[]}},
                         {'snapshot':{'messages':[],'runs':[{'state':'completed'}]}},
                         {'jobs':[{'id':'job'}]},{'draft':{'text':'newer draft','mode':'chat'}},
                         {'raw_selection':json.dumps({'version':1,'ids':['b'*32]})}]:
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):
                self.empty(**mutation)

    def test_malformed_selection_never_proves_emptiness(self):
        for raw in ['{','[]',json.dumps({'version':1,'ids':[{}]}),json.dumps({'version':1,'ids':['x']})]:
            with self.subTest(raw=raw),self.assertRaises(RuntimeError):
                self.empty(raw_selection=raw)

    def test_missing_and_duplicate_rows_fail_closed(self):
        for rows in [[],self.rows+[self.rows[-1]]]:
            with self.subTest(rows=rows),self.assertRaises(RuntimeError):
                review.owned_row(self.case,'D',rows)


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.p='1'*32
        self.original={'hermes:new-draft':None,review.NEW_SELECTION:None,review.INTENT:None,
                       'hermes-ui:sounds':'on','hermes-ui:interface-volume':'12',
                       'hermes:draft-attachments:v1:'+'a'*32:None}

    def test_only_known_empty_bookkeeping_and_owned_intent_may_be_reconciled(self):
        current={**self.original,'hermes:new-draft':'',review.NEW_SELECTION:json.dumps({'version':1,'ids':[],'revision':'fresh'}),
                 review.INTENT:json.dumps({'version':1,'project_id':self.p})}
        result=review.presentation_changes(self.original,current,{self.p})
        self.assertEqual(set(result),{'hermes:new-draft',review.NEW_SELECTION,review.INTENT})
        self.assertTrue(all(item['value'] is None for item in result.values()))

    def test_new_text_or_attachments_are_preserved_instead_of_restored(self):
        for key,value in [('hermes:new-draft','user text'),
                          (review.NEW_SELECTION,json.dumps({'version':1,'ids':['b'*32]}))]:
            current={**self.original,key:value}
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                review.presentation_changes(self.original,current,{self.p})

    def test_sound_and_original_scope_state_cannot_be_overwritten(self):
        for key in ['hermes-ui:sounds','hermes-ui:interface-volume','hermes:draft-attachments:v1:'+'a'*32]:
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                review.presentation_changes(self.original,{**self.original,key:'changed'},{self.p})

    def test_unexpected_composing_scope_version_or_shape_is_preserved(self):
        for value in [{'version':1,'project_id':'f'*32},{'version':2,'project_id':self.p},
                      {'version':1,'project_id':self.p,'extra':True},None]:
            raw=json.dumps(value)
            with self.subTest(value=value),self.assertRaises(RuntimeError):
                review.presentation_changes(self.original,{**self.original,review.INTENT:raw},{self.p})

    def test_original_nonempty_composing_intent_is_restored_from_known_probe_state(self):
        original={**self.original,review.INTENT:json.dumps({'version':1,'project_id':'e'*32})}
        changes=review.presentation_changes(original,self.original,{self.p})
        self.assertEqual(changes[review.INTENT]['value'],original[review.INTENT])

    def test_storage_inventory_changes_abort_restoration(self):
        current={**self.original,'untracked':'value'}
        with self.assertRaisesRegex(RuntimeError,'inventory_changed'):
            review.presentation_changes(self.original,current,{self.p})


class BrowserFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent=Path(self.tmp.name)
        self.payload='Harmless café context\n'.encode()

    def test_browser_visible_copy_matches_bytes_and_cleans_only_its_owned_file(self):
        unrelated=self.parent/'unrelated.txt';unrelated.write_text('keep')
        fixture=review.BrowserVisibleFixture(self.parent,self.payload)
        self.assertEqual(fixture.path.parent.parent,self.parent)
        self.assertEqual(fixture.path.read_bytes(),self.payload)
        self.assertEqual(fixture.path.stat().st_mode&0o777,0o600)
        fixture.cleanup();fixture.cleanup()
        self.assertFalse(fixture.root.exists());self.assertEqual(unrelated.read_text(),'keep')

    def test_modified_or_new_fixture_contents_are_preserved(self):
        for mutation in ('changed_bytes','additional_file'):
            with self.subTest(mutation=mutation):
                fixture=review.BrowserVisibleFixture(self.parent,self.payload)
                if mutation=='changed_bytes':fixture.path.write_text('newer text')
                else:(fixture.root/'newer.txt').write_text('keep newer file')
                with self.assertRaises(RuntimeError):fixture.cleanup()
                self.assertTrue(fixture.root.exists())

    def test_replaced_fixture_symlink_cannot_delete_its_target(self):
        fixture=review.BrowserVisibleFixture(self.parent,self.payload)
        target=self.parent/'keep.txt';target.write_text('preserve')
        fixture.path.unlink();fixture.path.symlink_to(target)
        with self.assertRaises(RuntimeError):fixture.cleanup()
        self.assertEqual(target.read_text(),'preserve')


class CaseCreationTests(unittest.TestCase):
    def test_precreation_inventory_is_captured_before_any_new_session(self):
        projects=[]
        original=[{'id':'a'*32,'project':None,'arm':'normal','title':'untouched A'},
                  {'id':'b'*32,'project':None,'arm':'normal','title':'untouched B'}]
        sessions=copy.deepcopy(original)
        next_id=[0]
        def issue():
            next_id[0]+=1
            return format(next_id[0],'032x')
        def rpc(method,fields=None):
            fields=fields or {}
            if method=='workspace.list':return copy.deepcopy(projects)
            if method=='workspace.create':
                row={'id':issue(),'label':fields['label'],'parent':None,'color':'blue'};projects.append(row)
                return {key:row[key] for key in ('id','label')}
            if method=='folder.update':
                next(row for row in projects if row['id']==fields['project_id']).update(parent=fields['parent'],label=fields['label'],color=fields['color'])
                return True
            if method=='session.list':return copy.deepcopy(sessions)
            if method=='session.create':
                row={'id':issue(),'title':'New conversation','project':fields['project_id'],'arm':fields['arm']};sessions.append(row)
                return {key:row[key] for key in ('id','project','arm')}
            if method=='session.rename':
                next(row for row in sessions if row['id']==fields['session_id'])['title']=fields['title'];return True
            if method=='chat.snapshot':return {'messages':[],'runs':[]}
            if method=='draft.read':return {'text':'','mode':'chat'}
            if method=='session.jobs':return []
            raise AssertionError(method)
        owned=review.OwnedInteractions.__new__(review.OwnedInteractions)
        owned.case={'nonce':'V6interaction-0123456789ab','created_ids':[],'records':{}}
        owned.rpc=rpc;owned.save=lambda:None
        owned.create()
        self.assertEqual(owned.case['before_session_ids'],['a'*32,'b'*32])
        created=owned.case['created_session_ids']
        self.assertEqual(len(created),4);self.assertEqual(len(set(created)),4)
        self.assertFalse(set(created)&set(owned.case['before_session_ids']))
        self.assertEqual(sessions[:2],original)


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        nonce='V6interaction-0123456789ab'
        records={}
        for index,role in enumerate(('P','Q','A','B','D','E'),1):
            records[role]={'id':format(index,'032x'),'kind':'project' if role in ('P','Q') else 'conversation'}
            if role in ('P','Q'):
                records[role].update(label=nonce+' · Project '+role,parent=records['P']['id'] if role=='Q' else None)
            else:records[role].update(title=nonce+' · Conversation '+role,project=records['P']['id'])
        case={'nonce':nonce,'created_ids':[row['id'] for row in records.values()],
              'created_session_ids':[records[role]['id'] for role in ('A','B','D','E')],
              'before_session_ids':['f'*32],'records':records}
        self.prior={'case':case,'checks':{name:True for name in ('empty_A_is_conversation','new_conversation_visible_and_focused',
                    'composing_reload_and_breadcrumb_overview','B_staged_rename_move_Cancel_preserves_A_and_B','explicit_B_Save_keeps_viewed_A_unchanged')}}
        self.prior['checks']['A_genuine_UTF8_draft_and_attachment']={'id':'c'*32,'sha256':'d'*64,'draft_sha256':'e'*64}
        self.projects=[row for row in records.values() if row['kind']=='project']
        self.sessions=[row for row in records.values() if row['kind']=='conversation']

    def test_exact_previous_case_is_reused_without_relabeling_or_new_ids(self):
        result=review.continuation_case(self.prior,self.projects,self.sessions)
        self.assertEqual(result,self.prior['case']);self.assertIsNot(result,self.prior['case'])

    def test_incomplete_prior_B_proof_cannot_be_skipped(self):
        del self.prior['checks']['explicit_B_Save_keeps_viewed_A_unchanged']
        with self.assertRaisesRegex(RuntimeError,'prior_B_sequence_not_complete'):
            review.continuation_case(self.prior,self.projects,self.sessions)

    def test_user_changed_Q_name_is_preserved_instead_of_adopted(self):
        rows=copy.deepcopy(self.projects);rows[1]['label']='newer user rename'
        with self.assertRaises(RuntimeError):review.continuation_case(self.prior,rows,self.sessions)

    def test_creation_inventory_cannot_claim_an_original_or_missing_precreation_scope(self):
        for mutation in ('original_id','missing_before'):
            prior=copy.deepcopy(self.prior)
            if mutation=='original_id':prior['case']['before_session_ids'].append(prior['case']['records']['D']['id'])
            else:del prior['case']['before_session_ids']
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):
                review.continuation_case(prior,self.projects,self.sessions)


if __name__=='__main__':
    unittest.main()
