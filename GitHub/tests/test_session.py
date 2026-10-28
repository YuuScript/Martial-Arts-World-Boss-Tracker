"""Focused checks for independent resizing, fresh startup and stale spawns."""
import copy,tempfile,time,tkinter as tk,unittest
from pathlib import Path
from types import SimpleNamespace as Event
from unittest.mock import patch
from model import BossTimer,Reading,GOLD
from storage import DEFAULT_BOSSES,Store
from detection import Detector,chaos_location
from tracker import App
from win_capture import window_rectangle

class SessionTests(unittest.TestCase):
    def test_spawn_reset_deadline_and_newest_first(self):
        old=BossTimer(copy.deepcopy(DEFAULT_BOSSES[0]));new=BossTimer(copy.deepcopy(DEFAULT_BOSSES[1]))
        old.observe(Reading('jade','countdown',10),100,100)
        self.assertEqual(old.state(110),'Spawned')
        new.observe(Reading('bow','spawned'),120,120)
        new.observe(Reading('bow','spawned'),140,140)
        self.assertEqual(new.spawned_at,120)
        self.assertLess(new.sort_key(150),old.sort_key(150))
        self.assertEqual(old.state(289.99),'Spawned')
        self.assertEqual(old.state(290),'Reset');self.assertEqual(old.color(290),GOLD)
        self.assertEqual(old.state(293),'Need entry');self.assertIsNone(old.deadline)
        new.observe(Reading('bow','countdown',300),301,301)
        self.assertEqual(new.state(301),'countdown');self.assertIsNone(new.reset_until)

    def test_kraken_kill_restarts_saved_altar_cooldown(self):
        timer=BossTimer(copy.deepcopy(DEFAULT_BOSSES[2]))
        timer.observe(Reading('kraken','killed'),100,100)
        self.assertEqual(timer.state(104),'KILLED');self.assertEqual(timer.state(105),'countdown');self.assertEqual(timer.remaining(105),472)
        timer.observe(Reading('kraken','countdown',40),110,110)
        self.assertEqual(timer.state(150),'Can spawn');self.assertEqual(timer.state(1000),'Can spawn')

    def test_brought_down_and_location_correction(self):
        def line(text,y):return ([[100,y],[900,y],[900,y+25],[100,y+25]],text,.97)
        readings=Detector(DEFAULT_BOSSES).parse([line('BG_NorthernBlade, Goober, ICY, Rooster, lunger2 brought',100),line('down Old Thunder, the Stormcliff Kraken!',128)])
        self.assertIn(Reading('kraken','killed'),readings)
        self.assertEqual(chaos_location('Heaven and earth come unstitched deep in the castern fog: Primordial Chaos qi has welled up.'),'eastern fog')
        self.assertEqual(chaos_location('Heaven and earth come unstitched in the Unknown Valley: Primordial Chaos qi has welled up.'),'Unknown Valley')

    def test_startup_and_independent_resize(self):
        with tempfile.TemporaryDirectory(dir='work') as folder,patch.object(tk.Tk,'deiconify'),patch.object(tk.Toplevel,'deiconify'),patch.object(App,'scan'),patch.object(App,'tick'):
            store=Store(Path(folder));store.data['timers']={'jade':{'deadline':time.time()+600,'spawned':True}};store.save()
            original=copy.deepcopy(store.data['bosses']);app=App(base=Path(folder))
            try:
                self.assertTrue(all(t.state(time.monotonic())==('Waiting for notification' if t.entry.get('mechanic')=='wukong' else 'Need entry') for t in app.timers.values()))
                self.assertEqual(app.entries,original)
                app.set_ui_scale(.65,persist=False);app.open_index();win=app.index_window
                initial=window_rectangle(win);index_scale=win._window_scale
                before=(app.width,app.outer_height,app.scale,app.viewport)
                with patch('tracker.window_rectangle',return_value=(50,50,app.width,app.outer_height)):
                    app.start_resize(Event(x_root=100,y_root=100),'e')
                app.resize(Event(x_root=160,y_root=100));app.flush_resize();app.end_resize(None)
                self.assertEqual(app.scale,before[2]);self.assertEqual(app.outer_height,before[1]);self.assertGreater(app.width,before[0])
                self.assertEqual(window_rectangle(win),initial);self.assertEqual(win._window_scale,index_scale)
                old_view=app.viewport
                with patch('tracker.window_rectangle',return_value=(50,50,app.width,app.outer_height)):
                    app.start_resize(Event(x_root=100,y_root=100),'s')
                app.resize(Event(x_root=100,y_root=160));app.flush_resize();app.end_resize(None)
                self.assertGreater(app.viewport,old_view);self.assertEqual(app.scale,before[2])
                hud=(app.width,app.outer_height,app.scale)
                win.set_scale(.8,persist=False)
                self.assertEqual((app.width,app.outer_height,app.scale),hud)
                before=win._window_scale
                win._begin_resize(Event(x_root=100,y_root=100),'e');win._resize_move(Event(x_root=130,y_root=100));win._end_resize(None)
                self.assertEqual(win._window_scale,before)
                win._begin_resize(Event(x_root=100,y_root=100),'se');win._resize_move(Event(x_root=130,y_root=130));win._end_resize(None)
                self.assertGreater(win._window_scale,before)
                self.assertEqual((app.width,app.outer_height,app.scale),hud)
                app.persist();saved=Store(Path(folder)).data
                self.assertEqual(saved['bosses'],original);self.assertEqual(saved['hud_units'],app.hud_units)
                self.assertIn('index',saved['panel_scales'])
            finally:app.close()

if __name__=='__main__':unittest.main()
