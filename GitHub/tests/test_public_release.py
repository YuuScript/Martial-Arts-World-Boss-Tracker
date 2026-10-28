"""Public distribution defaults and personal-data isolation."""
import json, tempfile, unittest
from pathlib import Path
from storage import Store, bundled_catalog

class PublicReleaseTests(unittest.TestCase):
    def test_fresh_player_library_and_empty_private_state(self):
        with tempfile.TemporaryDirectory(dir='work') as folder:
            store=Store(Path(folder));data=store.data
            self.assertEqual(len(data['bosses']),50)
            self.assertEqual({b['id'] for b in data['bosses'] if b['pinned']},{'jade','bow','kraken'})
            for field in ('timers','events','qi','windows'):self.assertEqual(data[field],{})
            self.assertEqual(data['presets'],[])
            self.assertEqual(len({b['id'] for b in data['bosses']}),50)
    def test_neighbor_settings_are_never_imported(self):
        with tempfile.TemporaryDirectory(dir='work') as folder:
            base=Path(folder);(base/'old').mkdir();(base/'new').mkdir()
            (base/'old/settings.json').write_text('{"presets":[{"name":"PRIVATE"}]}')
            self.assertEqual(Store(base/'new').data['presets'],[])
    def test_existing_users_keep_custom_library_and_presets(self):
        with tempfile.TemporaryDirectory(dir='work') as folder:
            store=Store(Path(folder));store.data['bosses'][0]['name']='Custom Guardian'
            store.data['bosses'][0]['color']='#123456';store.data['presets']=[{'name':'Mine','entries':[]}];store.save()
            restored=Store(Path(folder)).data
            self.assertEqual(restored['bosses'][0]['name'],'Custom Guardian')
            self.assertEqual(restored['bosses'][0]['color'],'#123456')
            self.assertEqual(restored['presets'],[{'name':'Mine','entries':[]}])
