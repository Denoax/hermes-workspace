"""Additive presentation state does not change old authority or data contracts."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from workspace.catalog import Catalog
from workspace.server import Application


class PresentationState(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'catalog'
        self.catalog = Catalog(self.root)
        self.addCleanup(self.catalog.db.close)
        self.project = self.catalog.create('Owned project')
        self.session = self.catalog.session(self.project['id'], 'normal')

    def test_old_session_insert_and_first_message_title_preserve_transcript(self):
        self.catalog.message(self.session['id'], 'user', 'Review  this\nfile <script>literal</script>')
        before = self.catalog.history(self.session['id'])
        self.assertEqual(self.catalog.sessions()[0]['title'], 'Review this file <script>literal</script>')
        self.catalog.rename(self.session['id'], 'A real title')
        self.assertEqual(self.catalog.sessions()[0]['title'], 'A real title')
        self.assertEqual(self.catalog.history(self.session['id']), before)
        self.assertEqual(len(self.catalog.db.execute('SELECT * FROM sessions').fetchone()), 3)

    def test_title_and_presentation_reject_unknown_fields_or_ids(self):
        for title in ['', 'x\n', 'a' * 81, None]:
            with self.subTest(title=title), self.assertRaises(ValueError):
                self.catalog.rename(self.session['id'], title)
        with self.assertRaises(ValueError): self.catalog.rename('0' * 32, 'Title')
        with self.assertRaises(ValueError): self.catalog.save_view({'shell': 'ls'})
        app = Application(self.root)
        self.addCleanup(app.catalog.db.close)
        with self.assertRaises(ValueError): app.call('session.rename', {'session_id': self.session['id'], 'title': 'T', 'execute': True})

    def test_session_drafts_are_separate_and_survive_reopen(self):
        other = self.catalog.session(self.project['id'], 'abliterated')
        self.catalog.save_draft(self.session['id'], 'Keep my draft', 'python')
        self.catalog.save_draft(other['id'], 'Different draft', 'cpp')
        reopened = Catalog(self.root)
        self.addCleanup(reopened.db.close)
        self.assertEqual(reopened.draft(self.session['id']), {'text': 'Keep my draft', 'mode': 'python'})
        self.assertEqual(reopened.draft(other['id']), {'text': 'Different draft', 'mode': 'cpp'})
        self.assertEqual(self.catalog.history(self.session['id']), [])

    def test_view_editor_restore_and_cross_project_mismatch(self):
        state = {'project_id': self.project['id'], 'session_id': self.session['id'], 'file_path': 'src/file.py',
                 'editor': {'text': '<img onerror=literal>', 'sha256': 'a' * 64}, 'files_open': True,
                 'arm': 'normal', 'task_kind': 'chat', 'theme': 'light', 'motion': 'reduced'}
        self.catalog.save_view(state)
        reopened = Catalog(self.root)
        self.addCleanup(reopened.db.close)
        self.assertEqual(reopened.view(), state)
        other = self.catalog.create('Other')
        with self.assertRaises(ValueError): self.catalog.save_view({**state, 'project_id': other['id']})
        with self.assertRaises(ValueError): self.catalog.save_view({**state, 'file_path': '../secret'})
        with self.assertRaises(ValueError): self.catalog.save_view({**state, 'editor': {'text': 'x' * 32769, 'sha256': 'a' * 64}})

    def test_additive_schema_keeps_existing_ids_and_rows(self):
        # Simulate the previous deployed schema and reopen using the new code.
        self.catalog.db.execute('DROP TABLE session_titles')
        self.catalog.db.execute('DROP TABLE view_state')
        self.catalog.db.execute('DROP TABLE drafts')
        self.catalog.db.commit()
        before = self.catalog.db.execute('SELECT * FROM sessions').fetchall()
        reopened = Catalog(self.root)
        self.addCleanup(reopened.db.close)
        self.assertEqual(reopened.db.execute('SELECT * FROM sessions').fetchall(), before)
        self.assertEqual(reopened.sessions()[0]['title'], 'New conversation')


if __name__ == '__main__': unittest.main()
