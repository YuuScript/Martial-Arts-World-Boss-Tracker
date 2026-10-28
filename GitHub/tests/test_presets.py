"""Preset snapshot boundaries and deletion persistence."""
import copy,unittest
from presets import save_preset,merged_library
from storage import migrate
class PresetTests(unittest.TestCase):
    def test_snapshot_is_independent_and_runtime_is_excluded(self):
        config=migrate({});config['timers']={'jade':{'deadline':123}}
        saved=save_preset(config,'West Region','#a987f5')
        before=copy.deepcopy(saved);config['bosses'][0]['name']='Changed';config['bosses'][0]['color']='#123456'
        self.assertEqual(saved,before);self.assertNotIn('timers',saved)
        restored=merged_library(config['bosses'],saved);self.assertEqual(restored[0]['name'],before['bosses'][0]['name'])
        with self.assertRaises(ValueError):save_preset(config,' west REGION ','#ffffff')
        with self.assertRaises(ValueError):save_preset(config,'  ','#ffffff')
    def test_load_keeps_new_entries_and_can_restore_deleted_entry(self):
        config=migrate({});saved=save_preset(config,'Original','#ffffff');removed=config['bosses'].pop(0)
        config['bosses'].append(dict(id='new',name='New Boss',color='#123456',duration=120,pinned=True,mechanic='standard'))
        result=merged_library(config['bosses'],saved)
        self.assertTrue(any(e['id']==removed['id'] for e in result));self.assertFalse(next(e for e in result if e['id']=='new')['pinned'])
    def test_deleted_wukong_is_not_readded_and_presets_survive_migration(self):
        config=migrate({});save_preset(config,'Saved','#123456')
        config['bosses']=[e for e in config['bosses'] if e['id']!='wukong'];config['deleted_boss_ids']=['wukong']
        loaded=migrate(config);self.assertFalse(any(e['id']=='wukong' for e in loaded['bosses']));self.assertEqual(loaded['presets'],config['presets'])
