import copy,json,tempfile,unittest
from pathlib import Path
from storage import Store,DEFAULT_BOSSES,migrate
from model import BossTimer,Reading,QiState,EventGate,GameLifecycle,GREEN,RED
from detection import Detector


def line(text,x=100,y=100,width=400):
 return [[[x,y],[x+width,y],[x+width,y+20],[x,y+20]],text,.99]


class DetectionTests(unittest.TestCase):
 def setUp(self): self.detector=Detector(copy.deepcopy(DEFAULT_BOSSES))
 def test_arbitrary_registered_boss(self):
  detector=Detector([dict(id='custom',name='Azure Mountain Guardian',duration=600,mechanic='standard')])
  self.assertEqual(detector.parse([line('Azure Mountain Guardian has fallen!')]),[Reading('custom','killed')])
  self.assertEqual(detector.parse([line('Azure Mountain Guardian'),line('Returns in 8:02',y=130)]),[Reading('custom','countdown',482)])
 def test_split_time(self):
  self.assertEqual(self.detector.parse([line('Qiongyu, the White-Jade Dragon'),line('Returns in',x=180,y=130,width=90),line('14:01',x=275,y=130,width=50)]),[Reading('jade','countdown',841)])
 def test_unregistered_or_invalid_text_does_not_start_timer(self):
  self.assertEqual(self.detector.parse([line('Unknown Boss has fallen!')]),[])
  self.assertEqual(self.detector.parse([line('Tianma'),line('Returns in 1:99',y=130)]),[])
 def test_qi_requires_specific_notification(self):
  self.assertEqual(self.detector.parse([line('Primordial Chaos qi has welled up on the highest summit')]),[Reading('qi','chaos')])
  self.assertEqual(self.detector.parse([line('Chaos/Void Qi'),line('Chaos Qi Detected!',y=130)]),[])
 def test_void_location_wraps_and_changes_without_hardcoded_places(self):
  for place in ('Tianhe Gate Foothills','Azure Mountain Pass','Old King’s Rest'):
   readings=self.detector.parse([line('The Void has opened in the '+place+': black as ink, rimmed in red.')])
   self.assertEqual(readings,[Reading('qi','void',location=place)])
  readings=self.detector.parse([line('The Void has opened in the Tianhe Gate'),line('報 Foothills: black as ink, rimmed in red.',y=125)])
  self.assertEqual(readings,[Reading('qi','void',location='Tianhe Gate Foothills')])
 def test_void_needs_complete_announcement_not_our_hud(self):
  self.assertEqual(self.detector.parse([line('Void Qi Detected!'),line('Tianhe Gate Foothills',y=125)]),[])
  self.assertEqual(self.detector.parse([line('The Void has opened in the Tianhe Gate')]),[Reading('qi','void')])
  self.assertEqual(self.detector.parse([line('The Void has opened in the Tianhe Gate'),line('Foothills: black as ink',y=500)]),[Reading('qi','void')])
 def test_void_closed_requires_announcement(self):
  self.assertEqual(self.detector.parse([line('The Void has closed.')]),[Reading('qi','void_end')])
  self.assertEqual(self.detector.parse([line('Someone says the Void has closed?')]),[])
  self.assertEqual(self.detector.parse([line('Chaos Qi Exhausted')]),[])
 def test_chaos_notification_supports_eastern_fog_variant(self):
  message='Heaven and earth come unstitched deep in the eastern fog: Primordial Chaos qi has welled up. Every cultivator in the Reaches will want it.'
  self.assertEqual(self.detector.parse([line(message)]),[Reading('qi','chaos',location='eastern fog')])
 def test_chaos_summit_location_and_unknown_location(self):
  message='Heaven and earth come unstitched on the highest summit: Primordial Chaos qi has welled up.'
  self.assertEqual(self.detector.parse([line(message)]),[Reading('qi','chaos',location='highest summit')])
  reading=self.detector.parse([line('Primordial Chaos qi has welled up on the highest summit')])[0]
  self.assertEqual(reading.location,'')
 def test_case_and_punctuation(self):
  self.assertEqual(self.detector.identify('Tianma'),'tianma')
  self.assertEqual(self.detector.identify('tianma'),'tianma')
  self.assertEqual(self.detector.identify('Qiongyu the White Jade Dragon'),'jade')


class RegistryAndTimeTests(unittest.TestCase):
 def test_time_shortcuts_and_invalid_values(self):
  from tracker import input_duration
  for text,seconds in [('3',180),('3.50',230),('3:50',230),('0:01',1),('1440',86400)]:self.assertEqual(input_duration(text),seconds)
  for text in ('3:75','3.75','3.5','-3','3..50','0','1440:01','NaN'):
   with self.assertRaises(ValueError):input_duration(text)
 def test_alias_short_names_and_ambiguity(self):
  entries=[dict(id='jiao',name='Jiao, The Flood Dragon',alias='River Guardian'),dict(id='jade',name='Qiongyu, the White-Jade Dragon',alias='Jade Guardian')]
  detector=Detector(entries)
  self.assertEqual(detector.identify('Jiao'),'jiao')
  self.assertEqual(detector.identify('River Guardian'),'jiao')
  self.assertIsNone(detector.identify('Dragon'))
  ambiguous=Detector(entries+[dict(id='other',name='Jiao, The River Dragon')])
  self.assertIsNone(ambiguous.identify('Jiao'))
 def test_collision_checks_and_search(self):
  from registry import check_name_conflicts,filtered_entries
  entries=[dict(id='jiao',name='Jiao, The Flood Dragon',alias='River Guardian',pinned=False)]
  with self.assertRaises(ValueError):check_name_conflicts(dict(id='new',name=entries[0]['name'],alias=''),entries)
  warnings=check_name_conflicts(dict(id='new',name='Another Boss',alias='River Guardian'),entries)
  self.assertTrue(warnings)
  check_name_conflicts(dict(id='jiao',name='Jiao, The Flood Dragon',alias='Jiao'),entries)
  self.assertEqual(filtered_entries(entries,'river')[0]['id'],'jiao')
 def test_jiao_alias_priority_preserves_specific_full_name(self):
  entries=[dict(id='jiao',name='Jiao, The Flood Dragon',alias='Jiao',alias_override=True),dict(id='blind',name='The Blind Jiao, Coiled Round the Deep Vein',alias='Jiao')]
  detector=Detector(entries)
  self.assertEqual(detector.identify('Jiao'),'jiao')
  self.assertEqual(detector.identify(entries[1]['name']),'blind')
  self.assertEqual(detector.identify('The Blind Jiao'),'blind')
  self.assertEqual(detector.identify('Blind Jiao'),'blind')
 def test_panel_geometry_stays_on_screen(self):
  from panels import bounded_geometry
  self.assertEqual(bounded_geometry((-100,900,600,500),(0,0,1920,1080)),(0,580,600,500))


class ReferenceScaleTests(unittest.TestCase):
 def test_reference_dimensions_and_dpi(self):
  from ui_scale import dimensions
  for scale,size in ((1,(900,745)),(.75,(675,559)),(.6,(540,447)),(.5,(450,372))):self.assertEqual(dimensions(scale),size)
  self.assertEqual(dimensions(.75,144),(1012,838))
 def test_no_white_outline_on_fill(self):
  import painting
  color='#3970af';im=painting.surface(200,20,painting.mix(color,'#ffffff',.1),color,None,7)
  visible=[pixel for pixel in im.getdata() if pixel[3]>200]
  self.assertLess(max(max(pixel[:3]) for pixel in visible),220)


class ReaderCacheTests(unittest.TestCase):
 def test_identical_pixels_reuse_ocr_without_restarting_countdown(self):
  from screen_reader import ScreenReader
  from PIL import Image
  from unittest.mock import patch
  reader=ScreenReader(DEFAULT_BOSSES);image=Image.new('RGB',(40,40),'black');now=[100]
  with patch.object(reader,'discovery',return_value=[Reading('jade','countdown',90)]) as discover,patch('screen_reader.time.monotonic',side_effect=lambda:now[0]):
   self.assertEqual(reader.read(image)[0].seconds,90)
   now[0]=105
   self.assertEqual(reader.read(image)[0].seconds,85)
   self.assertEqual(discover.call_count,1)
   reader.configure(DEFAULT_BOSSES);reader.read(image)
   self.assertEqual(discover.call_count,2)


class StateTests(unittest.TestCase):
 def test_kill_five_seconds_does_not_delay_deadline(self):
  timer=BossTimer(copy.deepcopy(DEFAULT_BOSSES[0]))
  timer.observe(Reading('jade','killed'),100,102)
  self.assertEqual(timer.deadline,997)
  self.assertEqual(timer.state(106.99),'KILLED')
  self.assertEqual(timer.state(107),'countdown')
  self.assertEqual(timer.remaining(107),890)
 def test_name_only_reads_remaining_without_inventing_full_time(self):
  timer=BossTimer(copy.deepcopy(DEFAULT_BOSSES[3]))
  timer.observe(Reading('roc','countdown',897),100,101)
  self.assertEqual(timer.remaining(102),895)
  self.assertIsNone(timer.entry['duration'])
  self.assertEqual(timer.progress(102),0)
  timer.observe(Reading('roc','killed'),200,201)
  self.assertEqual(timer.state(202),'KILLED')
  self.assertEqual(timer.state(206),'Need entry')
 def test_progress_fills_and_colors(self):
  timer=BossTimer(copy.deepcopy(DEFAULT_BOSSES[0]))
  timer.observe(Reading('jade','countdown',900),0,0)
  self.assertEqual(timer.progress(0),0)
  self.assertEqual(timer.progress(450),.5)
  self.assertEqual(timer.progress(900),1)
  self.assertEqual(timer.color(840),GREEN)
 def test_pinning_and_editing_preserve_deadline(self):
  entry=copy.deepcopy(DEFAULT_BOSSES[0]); timer=BossTimer(entry)
  timer.observe(Reading('jade','countdown',300),100,100)
  entry['pinned']=False; entry['name']='Changed Name'; entry['color']='#123456'; entry['duration']=1200
  self.assertEqual(timer.deadline,400)
 def test_kraken_spawn_priority(self):
  timer=BossTimer(copy.deepcopy(DEFAULT_BOSSES[2]))
  timer.observe(Reading('kraken','countdown',10),0,0)
  self.assertEqual(timer.state(10),'Can spawn')
  timer.observe(Reading('kraken','spawned'),11,11)
  timer.observe(Reading('kraken','countdown',470),12,12)
  self.assertEqual(timer.state(13),'Spawned')
 def test_dedup_continuous_and_short_ocr_gaps(self):
  gate=EventGate()
  self.assertTrue(gate.accept('jade:killed',100))
  for now in range(101,151): self.assertFalse(gate.accept('jade:killed',now))
  self.assertFalse(gate.accept('jade:killed',154))
  self.assertTrue(gate.accept('jade:killed',1000))
 def test_qi_is_exclusive_expires_and_flashes_for_twelve(self):
  qi=QiState(); qi.activate('chaos',100,102)
  self.assertEqual(qi.state(110),'Chaos Qi Detected!')
  self.assertEqual(qi.flash_until,114)
  qi.activate('void',200,201,'Summit')
  self.assertEqual(qi.state(300),'Void Qi Detected!')
  self.assertEqual(qi.location,'Summit')
  self.assertEqual(qi.state(1100),'None Detected')
 def test_exhaustion_flashes_for_five_then_clears_and_persists(self):
  qi=QiState();qi.activate('void',100,100,'Tianhe Gate Foothills')
  self.assertTrue(qi.exhaust('void',200))
  self.assertEqual(qi.state(204.99),'Void Qi Exhausted')
  self.assertEqual(qi.flash_until,205)
  self.assertEqual(qi.state(205),'None Detected')
  saved=qi.snapshot(202,1000)
  restored=QiState();restored.restore(saved,10,1001)
  self.assertEqual(restored.state(10),'Void Qi Exhausted')
  self.assertEqual(restored.state(12),'None Detected')
  restored.activate('chaos',20,20)
  self.assertFalse(restored.exhaust('void',21))
  self.assertEqual(restored.state(22),'Chaos Qi Detected!')
 def test_restore_uses_elapsed_wall_time(self):
  entry=copy.deepcopy(DEFAULT_BOSSES[0]); timer=BossTimer(entry)
  timer.observe(Reading('jade','countdown',600),100,100)
  snapshot=timer.snapshot(110,10000)
  restored=BossTimer(entry); restored.restore(snapshot,20,10060)
  self.assertEqual(restored.remaining(20),530)
 def test_gate_restores_without_retrigger(self):
  gate=EventGate(); gate.accept('qi:chaos',100)
  saved=gate.snapshot(101,1000)
  restored=EventGate(); restored.restore(saved,10,1001)
  self.assertFalse(restored.accept('qi:chaos',10))
 def test_sort_known_timers_before_unknown(self):
  timers=[BossTimer(copy.deepcopy(e)) for e in DEFAULT_BOSSES[:3]]
  timers[0].observe(Reading('jade','countdown',200),0,0)
  timers[1].observe(Reading('bow','countdown',100),0,0)
  self.assertEqual([t.entry['id'] for t in sorted(timers,key=lambda t:t.sort_key(0))],['bow','jade','kraken'])


class PersistenceTests(unittest.TestCase):
 def test_migration_is_non_destructive_idempotent(self):
  old=dict(durations={'jade':840,'bow':900,'kraken':480},opacity=.8,scale=.7,custom_setting={'value':42})
  migrated=migrate(old)
  self.assertEqual(migrated['bosses'][0]['duration'],840)
  self.assertEqual(migrated['custom_setting'],old['custom_setting'])
  self.assertEqual(migrate(migrated),migrated)
  self.assertNotIn('bosses',old)
 def test_backup_add_edit_and_restart(self):
  with tempfile.TemporaryDirectory(dir='work') as temp:
   folder=Path(temp)
   old={'durations':{'jade':900},'scale':.82,'opacity':.9}
   (folder/'settings.json').write_text(json.dumps(old))
   store=Store(folder)
   store.data['bosses'][0]['pinned']=False
   store.data['bosses'][0]['color']='#123456'
   store.data['visible_rows']=5
   store.data['bosses'].append(dict(id='added',name='New Boss',duration=200,color='#abcdef',pinned=True,mechanic='standard'))
   store.save()
   loaded=Store(folder)
   self.assertEqual(len(loaded.data['bosses']),9)
   self.assertEqual(loaded.data['bosses'][0]['color'],'#123456')
   self.assertFalse(loaded.data['bosses'][0]['pinned'])
   self.assertEqual(loaded.data['visible_rows'],5)
   self.assertEqual(json.loads((folder/'settings.before-tracker.json').read_text()),old)
 def test_invalid_settings_are_not_overwritten(self):
  with tempfile.TemporaryDirectory(dir='work') as temp:
   path=Path(temp)/'settings.json'; path.write_text('{ invalid')
   with self.assertRaises(json.JSONDecodeError): Store(Path(temp))
   self.assertEqual(path.read_text(),'{ invalid')


if __name__=='__main__': unittest.main()
