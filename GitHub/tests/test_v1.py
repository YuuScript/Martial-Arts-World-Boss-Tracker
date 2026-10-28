"""Focused V1.0 announcement, state and data-preservation checks."""
import copy,unittest
from boss_rules import enrich,REGIONS,SPECIAL_KILLS,SPECIAL_SPAWNS
from detection import Detector
from model import BossTimer,Reading,EventGate,QiState
from storage import migrate
from test_tracker import line

class V1Tests(unittest.TestCase):
    def entries(self):
        names=['Ye Wuxian, the Stringless Bow','The Warden-Colossus of the Maw','Lü Jiugong, Master of the Shattered Array','Bonewrath, the War-Qilin of the Ninefold Lord','Marshal Tie Yan, the Burnt Marshal','Sad Cultivator, Keeper of the Unfinished Farewell','Suanni, the Dragon King’s Fifth Son','The Sleeping Colossus','Yu Wukuang, the Mad Jade Disciple','Kulong, the Withered Dragon','Tianma, the Thunder Stallion','Mo Qingshan, the Deviated','Sword Wraith of Cloudbreak Peak','Qiongyu, the White-Jade Dragon','Patriarch Lou Kunshan','The Stair-Bell Warden']
        return enrich([dict(id=str(i),name=n,duration=600,mechanic='standard',pinned=False,color='#aabbcc') for i,n in enumerate(names)])
    def test_every_special_variant_and_wrapped_notification(self):
        entries=self.entries();detector=Detector(entries)
        for kind,rules in [('killed',SPECIAL_KILLS),('spawned',SPECIAL_SPAWNS)]:
            for owner,clauses in rules:
                with self.subTest(owner=owner,kind=kind):
                    text='. '.join(clauses)
                    expected=next(e['id'] for e in entries if owner in __import__('boss_rules').normalized(e['name']))
                    self.assertIn(Reading(expected,kind),detector.parse([line(t,y=100+i*23) for i,t in enumerate(clauses)]))
    def test_special_interaction_timers(self):
        entries=self.entries();detector=Detector(entries)
        for name,text,seconds in [('The Sleeping Colossus','Sleeping · it can be woken again in 29:26',1766),('Sword Wraith','A nameless sword · still for 4:54',294)]:
            entry=next(e for e in entries if e['name'].startswith(name))
            self.assertIn(Reading(entry['id'],'countdown',seconds),detector.parse([line(text)]))
        entry=next(e for e in entries if e.get('mechanic')=='colossus')
        self.assertIn(Reading(entry['id'],'spawned'),detector.parse([line('Sleeping · step into the crater to wake it')]))
    def test_wukong_no_countdown_and_fifteen_minute_timeout(self):
        entry=next(e for e in self.entries() if e.get('mechanic')=='wukong');timer=BossTimer(entry)
        self.assertEqual(timer.state(0),'Waiting for notification')
        self.assertFalse(timer.observe(Reading(entry['id'],'countdown',50),0,0))
        timer.observe(Reading(entry['id'],'spawned'),100,100)
        timer.observe(Reading(entry['id'],'spawned'),200,200)
        self.assertEqual(timer.state(999),'Spawned');self.assertEqual(timer.state(1000),'Waiting for notification')
        timer.observe(Reading(entry['id'],'spawned'),1100,1100);timer.observe(Reading(entry['id'],'killed'),1200,1200)
        self.assertEqual(timer.state(1204),'KILLED');self.assertEqual(timer.state(1205),'Waiting for notification');self.assertIsNone(timer.deadline)
    def test_kill_duplicate_does_not_restart_or_reflash(self):
        timer=BossTimer(self.entries()[0]);timer.observe(Reading('0','killed'),100,100)
        deadline=timer.deadline
        self.assertFalse(timer.observe(Reading('0','killed'),110,110));self.assertEqual(timer.deadline,deadline);self.assertEqual(timer.kill_until,105)
        gate=EventGate();self.assertTrue(gate.accept('0:killed',100));self.assertFalse(gate.accept('0:killed',110));self.assertTrue(gate.accept('1:killed',110));self.assertTrue(gate.accept('0:killed',116))
    def test_chaos_and_void_exhaustion(self):
        detector=Detector(self.entries())
        for kind,text in [('void','The Void has closed.'),('chaos','The Chaos has closed. Heaven and earth stitch shut again.')]:
            self.assertIn(Reading('qi',kind+'_end'),detector.parse([line(text)]))
            qi=QiState();qi.activate(kind,0,0,'Eastern Fog');qi.exhaust(kind,10)
            self.assertEqual(qi.state(14),kind.title()+' Qi Exhausted');self.assertEqual(qi.state(15),'None Detected')
    def test_loot_is_not_a_kill(self):
        detector=Detector(self.entries())
        for text in ['Goober obtained a scroll from Kulong, the Withered Dragon!','+198 cultivation (defeated The Roc Matriarch)','Bonewrath’s violet skull obtained by a player']:
            self.assertEqual(detector.parse([line(text)]),[])
    def test_regions_and_unicode_preserve_existing_data(self):
        entries=self.entries();before=copy.deepcopy(entries);data=migrate(dict(bosses=entries,custom='preserved'))
        self.assertEqual(data['custom'],'preserved')
        for old in before:self.assertTrue(any(all(e.get(k)==v for k,v in old.items()) for e in data['bosses']))
        lu=next(e for e in entries if 'Jiugong' in e['name']);self.assertEqual(Detector(entries).identify('Lu Jiugong'),lu['id'])
        self.assertEqual(lu['region'],REGIONS[2]);self.assertEqual(entries[0]['region'],REGIONS[3])
        self.assertEqual(next(e for e in entries if 'Sword Wraith' in e['name'])['region'],REGIONS[0])

    def test_wukong_dynamic_location(self):
        detector=Detector(self.entries());entry=next(e for e in self.entries() if e.get('mechanic')=='wukong')
        for location in ('Tianshui City','Willowgate','New Unknown Place'):
            text='A giant of jade has come down on 報 '+location+'. His pressure lies over the whole West.'
            self.assertIn(Reading(entry['id'],'spawned',location=location),detector.parse([line(text)]))
