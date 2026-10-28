"""Integration checks with every window withdrawn: no desktop input or capture."""
import copy
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tracker import App
from ui_theme import ActionButton
from model import Reading, GameLifecycle
from storage import Store, DEFAULT_BOSSES
from win_capture import Hotkey, move_window, window_rectangle, hwnd_for, u


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class HiddenIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='work')
        self.patches=[patch('storage.bundled_catalog',return_value=copy.deepcopy(DEFAULT_BOSSES)),
                      patch.object(tk.Tk,'deiconify',lambda self:None),
                      patch.object(tk.Toplevel,'deiconify',lambda self:None),
                      patch.object(App,'tick',lambda self:None)]
        for item in self.patches: item.start()
        self.app=App(demo=True,base=Path(self.temp.name))
        self.app.demo=False

    def tearDown(self):
        if not self.app.stop.is_set(): self.app.close()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def assert_hidden(self):
        self.assertFalse(u.IsWindowVisible(hwnd_for(self.app.root)))
        for win in self.app.children:
            if win.winfo_exists(): self.assertFalse(u.IsWindowVisible(hwnd_for(win)))

    def button(self,parent,label):
        return next(w for w in descendants(parent) if isinstance(w,(tk.Button,ActionButton)) and w.cget('text')==label)

    def test_index_edit_add_pin_color_and_restart_preserve_timer(self):
        app=self.app;original=app.timers['jade'].deadline
        app.open_index();ui=app.index_ui;jade=next(e for e in app.entries if e['id']=='jade')
        ui.pin(jade);self.assertFalse(jade['pinned'])
        ui.edit(jade);self.button(ui.editor,'Set a Color').invoke()
        ui.picker.hex.set('#69A7FF');ui.picker.apply()
        self.assertEqual(app.color_overrides['jade'],'#69A7FF')
        self.assertNotEqual(jade['color'],'#69A7FF')
        self.button(ui.editor,'Save changes').invoke()
        ui.edit(None);ui.form['name'].set('Azure Guardian');ui.form['alias'].set('Azure Watcher')
        self.button(ui.editor,'Add boss').invoke()
        app.index_window.close_panel();app.persist()
        data=Store(Path(self.temp.name)).data
        saved=next(e for e in data['bosses'] if e['id']=='jade')
        self.assertFalse(saved['pinned']);self.assertEqual(saved['color'],'#69A7FF')
        self.assertTrue(any(e['alias']=='Azure Watcher' for e in data['bosses']))
        self.assertEqual(original,app.timers['jade'].deadline)
        app.open_index();self.assert_hidden()

    def test_lock_unlock_retains_exit_and_native_window_styles(self):
        app=self.app
        for _ in range(3):
            app.toggle_lock(); self.assertTrue(app.locked)
            self.assertTrue(u.GetWindowLongW(hwnd_for(app.root),-20)&0x20)
            self.assertFalse(u.GetWindowLongW(hwnd_for(app.unlock_window),-20)&0x20)
            self.button(app.unlock_window,'Unlock').invoke(); self.assertFalse(app.locked)
            self.assertFalse(u.GetWindowLongW(hwnd_for(app.root),-20)&0x20)
        self.assertTrue(u.GetWindowLongW(hwnd_for(app.root),-20)&0x40000)
        app.toggle_lock(); self.button(app.unlock_window,'Exit').invoke()
        self.assertTrue(app.stop.is_set())

    def test_list_height_width_scroll_and_events_are_independent(self):
        app=self.app
        for e in app.entries: e['pinned']=True
        app.changed(); bottom_height=app.bottom.cget('height')
        app.config['visible_rows']=1; app.layout(force=True)
        self.assertEqual(app.bottom.cget('height'),bottom_height)
        self.assertEqual(app.scroll.winfo_manager(),'pack')
        app.scroll_list('moveto',1)
        self.assertGreater(app.body.yview()[0],0)
        now=time.monotonic()
        app.handle_readings(now,[Reading('jade','killed'),Reading('qi','chaos')],now+.4)
        deadline=app.timers['jade'].deadline
        app.handle_readings(now+1,[Reading('jade','killed'),Reading('qi','chaos')],now+1.4)
        self.assertEqual(deadline,app.timers['jade'].deadline)
        self.assertEqual(app.qi.expires,now+900)
        app.draw_body(now+1.4); app.draw_bottom(now+1.4)
        app.reset()
        self.assertEqual(len(app.entries),8)
        self.assertIsNone(app.timers['jade'].deadline)
        self.assertEqual(app.qi.state(now),'None Detected')
        self.assert_hidden()

    def test_reference_scales_and_coalesced_resize_persist(self):
        from ui_scale import dimensions
        app=self.app
        for scale in (1,.75,.6,.5):
            app.set_ui_scale(scale)
            self.assertEqual((app.width,app.outer_height),dimensions(scale,app.dpi))
            self.assertEqual(app.config['ui_scale'],scale)
        app.set_ui_scale(.75)
        with patch('tracker.window_rectangle',return_value=(50,50,app.width,app.outer_height)):
            app.start_resize(SimpleNamespace(x_root=100,y_root=100),'se')
        before=app.ui_scale
        with patch.object(app,'layout',wraps=app.layout) as layout:
            for x in range(100,160):app.resize(SimpleNamespace(x_root=x,y_root=100))
            self.assertEqual(layout.call_count,0)
            app.flush_resize();self.assertEqual(layout.call_count,1)
        self.assertGreater(app.ui_scale,before);app.end_resize(None)
        saved=Store(Path(self.temp.name)).data
        self.assertEqual(saved['ui_scale'],app.ui_scale)
        self.assertAlmostEqual(app.width/app.outer_height,900/745,delta=.003)
        self.assert_hidden()

    def test_reference_layout_long_names_do_not_overlap_subtitles(self):
        app=self.app
        for entry in app.entries:entry['pinned']=True
        app.entries[0]['name']='Qiongyu, the White-Jade Dragon With An Extra Long Registered Name'
        for scale in (1,.75,.6,.5):
            app.set_ui_scale(scale)
            width=app.width-app.px(16)
            with patch.object(app.body,'winfo_width',return_value=width):app.draw_body(time.monotonic())
            rows={timer.entry['name']:(y,h,nh) for timer,y,h,nh in app.rows(width)}
            for item,name in app.body._text_items.items():
                if name in rows:
                    y,height,name_height=rows[name];bounds=app.body.bbox(item)
                    self.assertLess(bounds[3],y+height-app.px(55))
                    self.assertGreaterEqual(bounds[0],0);self.assertLess(bounds[2],width-app.px(160))
        self.assert_hidden()

    def test_index_scaling_preserves_editor_draft_and_reuses_window(self):
        from tkinter import font as tkfont
        app=self.app;app.open_index();ui=app.index_ui;win=ui.window
        ui.edit(app.entries[0]);ui.form['alias'].set('Draft alias')
        self.button(ui.editor,'Set a Color').invoke();picker=ui.picker
        win.set_scale(1);large=abs(tkfont.Font(ui.rows['jade']['label'],font=ui.rows['jade']['label'].cget('font')).cget('size'))
        win.set_scale(.5);small=abs(tkfont.Font(ui.rows['jade']['label'],font=ui.rows['jade']['label'].cget('font')).cget('size'))
        self.assertAlmostEqual(large/small,2,delta=.12);self.assertEqual(ui.form['alias'].get(),'Draft alias')
        self.assertEqual(picker.square_image.width(),round(220*.75*app.dpi/96))
        ui.window.close_panel();app.open_index();self.assertIs(app.index_window,win);self.assertIsNone(ui.editor)
        self.assert_hidden()

    def test_unchanged_hud_skips_repaint_and_search_keeps_rows(self):
        app=self.app;now=time.monotonic();app.draw_body(now);items=app.body.find_all()
        app.draw_body(now);self.assertEqual(app.body.find_all(),items)
        app.open_index();ui=app.index_ui
        ui.update_row(app.entries[0])
        with patch.object(ui.rows['jade']['surface'],'redraw') as draw:
            ui.query.set('jade');ui.filter_now();draw.assert_not_called()
        self.assert_hidden()

    def test_inline_color_cancel_invalid_input_and_rgb_apply(self):
        app=self.app;original=app.entries[0]['color'];app.open_index();ui=app.index_ui
        ui.edit(app.entries[0]);before=len(app.children)
        self.button(ui.editor,'Set a Color').invoke();picker=ui.picker
        self.assertEqual(len(app.children),before)
        picker.hex.set('#invalid');self.assertFalse(picker.apply());self.assertTrue(picker.error.get())
        picker.rgb.set('64, 128, 240');self.assertTrue(picker.apply())
        self.assertEqual(app.entries[0]['color'],original)
        self.assertEqual(app.color_overrides[app.entries[0]['id']],'#4080F0')
        self.button(ui.editor,'Cancel').invoke()
        self.assertNotIn(app.entries[0]['id'],app.color_overrides)
        self.assertEqual(app.entries[0]['color'],original);self.assert_hidden()

    def test_void_state_location_duplicate_and_border_only(self):
        app=self.app;now=round(time.monotonic())+.05
        reading=Reading('qi','void',location='Tianhe Gate Foothills')
        app.handle_readings(now,[reading],now)
        deadline=app.qi.expires
        app.handle_readings(now+1,[reading],now+1)
        self.assertEqual(app.qi.expires,deadline)
        self.assertEqual(app.qi.location,'Tianhe Gate Foothills')
        app.layout(force=True);app.draw_bottom(now)
        labels=list(app.bottom._text_items.values())
        self.assertIn('Void Qi Detected!',labels)
        self.assertIn('Tianhe Gate Foothills',labels)
        self.assertIn('Chaos/ Void Qi Tracker',labels)
        self.assertTrue(any(app.bottom.type(i)=='polygon' for i in app.bottom.find_all()))
        app.persist()
        restored=Store(Path(self.temp.name)).data['qi']
        self.assertEqual(restored['location'],'Tianhe Gate Foothills')
        app.handle_readings(now+20,[Reading('qi','chaos')],now+20)
        self.assertEqual(app.qi.state(now+21),'Chaos Qi Detected!')
        self.assertEqual(app.qi.location,'')
        self.assert_hidden()

    def test_exhaustion_duplicate_does_not_extend_alert(self):
        app=self.app;now=time.monotonic()
        app.handle_readings(now,[Reading('qi','void',location='Tianhe Gate Foothills')],now)
        app.handle_readings(now+10,[Reading('qi','void_end')],now+10)
        app.handle_readings(now+12,[Reading('qi','void_end')],now+12)
        self.assertEqual(app.qi.flash_until,now+15)
        self.assertEqual(app.qi.state(now+15),'None Detected')
        app.handle_readings(now+16,[Reading('qi','void_end')],now+16)
        self.assertEqual(app.qi.state(now+16),'None Detected')
        app.draw_bottom(now+11)
        self.assert_hidden()

    def test_missing_location_fills_later_without_restarting_event(self):
        app=self.app;now=time.monotonic()
        app.handle_readings(now,[Reading('qi','void')],now)
        deadline=app.qi.expires;flash=app.qi.flash_until
        app.layout(force=True);app.draw_bottom(now)
        labels=list(app.bottom._text_items.values())
        self.assertIn('Location Not Found',labels)
        app.handle_readings(now+2,[Reading('qi','void',location='Tianhe Gate Foothills')],now+2)
        self.assertEqual(app.qi.location,'Tianhe Gate Foothills')
        self.assertEqual(app.qi.expires,deadline);self.assertEqual(app.qi.flash_until,flash)
        app.handle_readings(now+30,[Reading('qi','chaos',location='eastern fog')],now+30)
        app.layout(force=True);app.draw_bottom(now+30)
        labels=list(app.bottom._text_items.values())
        self.assertIn('eastern fog',labels)
        self.assertIn('Chaos Qi Detected!',labels)
        self.assertNotIn('Location Not Found',labels)
        self.assert_hidden()

    def test_pin_sections_search_keep_row_widgets_and_geometry(self):
        app=self.app;app.open_index();ui=app.index_ui
        for entry in app.entries:ui.update_row(entry)
        original={key:row['surface'] for key,row in ui.rows.items()}
        dimensions=window_rectangle(ui.window)
        row=app.entries[0];ui.pin(row);ui.pin(row)
        self.assertEqual(window_rectangle(ui.window),dimensions)
        self.assertEqual(original,{key:r['surface'] for key,r in ui.rows.items()})
        self.assertEqual(ui.rows[row['id']]['pin'].cget('bg'),'#1d5a41')
        row['alias']='Dragon Watcher';ui.query.set('watch');ui.filter_now()
        self.assertEqual(ui.visible_ids,[row['id']])
        ui.query.set('');ui.filter_now()
        expected=sorted(app.entries,key=lambda e:(not e['pinned'],e['name'].casefold()))
        self.assertEqual(ui.visible_ids,[e['id'] for e in expected])
        unknown=next(e for e in app.entries if not e['duration'])
        self.assertEqual(ui.rows[unknown['id']]['duration'].cget('text'),'Error! - Set a timer')
        self.assert_hidden()

    def test_alias_conflict_warns_but_can_save_and_full_duplicates_stay_blocked(self):
        app=self.app;app.open_index();ui=app.index_ui;before=len(app.entries)
        ui.edit(None);ui.form['name'].set(app.entries[0]['name'])
        self.button(ui.editor,'Add boss').invoke()
        self.assertEqual(len(app.entries),before);self.assertIn('already exists',ui.form_error.get())
        ui.form['name'].set('Another Boss');ui.form['alias'].set('Qiongyu');ui.alias_override.set(True)
        self.button(ui.editor,'Add boss').invoke()
        self.assertEqual(len(app.entries),before+1);self.assertTrue(app.entries[-1]['alias_override'])

    def test_timer_shorthand_and_remembered_panel_position(self):
        app=self.app;app.manual('jade')
        app.manual_value.set('3.50');self.assertEqual(app.manual_feedback.get(),'Will set: 3:50')
        app.manual_value.set('3:75');self.assertIn('Seconds',app.manual_feedback.get())
        app.manual_value.set('3');self.button(app.manual_window,'Set Timer').invoke()
        self.assertAlmostEqual(app.timers['jade'].remaining(time.monotonic()),180,delta=1)
        app.open_index();rect=window_rectangle(app.index_window)
        app.index_window.close_panel();saved=app.config['reference_windows']['index']['rect']
        self.assertEqual(list(rect),saved)
        app.open_index();self.assertEqual(list(window_rectangle(app.index_window)),saved)
        self.assert_hidden()

    def test_header_and_joke_have_separate_vertical_rows(self):
        app=self.app;app.layout(force=True)
        self.assertEqual(app.joke.cget('text'),'(Wallahi No virus)')
        self.assertEqual(app.joke.cget('font'),app.credit.cget('font'))
        self.assertEqual(app.joke.cget('fg'),'#ffaa55')
        self.assertGreater(int(app.joke.place_info()['y']),int(app.credit.place_info()['y']))
        self.assertGreater(int(app.controls.place_info()['y']),int(app.title.place_info()['y']))
        self.assertGreater(int(app.controls.place_info()['y']),app.close_button.winfo_reqheight())

    def test_buttons_do_not_resize_or_reframe_the_hud_or_index(self):
        app=self.app;app.open_index();ui=app.index_ui
        hud=window_rectangle(app.root);index=window_rectangle(ui.window)
        with patch('tracker.custom_header') as reframe:
            for entry in app.entries:ui.pin(entry)
            ui.edit(app.entries[0]);self.button(ui.editor,'Set a Color').invoke()
            ui.picker.hex.set('#66aaff');ui.picker.apply();self.button(ui.editor,'Save changes').invoke()
            ui.query.set('dragon');ui.filter_now();ui.query.set('');ui.filter_now()
            app.toggle_lock();app.toggle_lock();app.reset();app.layout()
            self.assertEqual(window_rectangle(app.root),hud)
            self.assertEqual(window_rectangle(ui.window),index)
            reframe.assert_not_called()
        self.assert_hidden()

    def test_scan_indicator_and_details_follow_focus(self):
        app=self.app;app.last_scanned=time.monotonic();app.scan_seconds=.6;app.scan_mode='focused'
        app.update_scan_focus(True);app.draw_bottom(time.monotonic())
        self.assertTrue(app.scan_active);self.assertIn('Active',app.scan_label.cget('text'))
        app.update_scan_focus(False);app.draw_bottom(time.monotonic())
        self.assertFalse(app.scan_active);self.assertEqual(app.scan_label.cget('fg'),'#ffdc6b')
        texts=list(app.bottom._text_items.values())
        self.assertTrue(any('Last Scanned' in t for t in texts));self.assertFalse(any('Chaos exhaustion' in t for t in texts))

    def test_scroll_after_unpin_search_and_editor_changes(self):
        from model import BossTimer
        app=self.app
        for i in range(30):
            entry=dict(id=f'extra{i}',name=f'Scroll Boss {i:02}',alias=f'Alias {i:02}',color='#a9d9ff',pinned=True,duration=600,mechanic='standard')
            app.entries.append(entry);app.timers[entry['id']]=BossTimer(entry)
        app.open_index();ui=app.index_ui;app.root.update_idletasks();ui.sync_scroll()
        ui.canvas.yview_moveto(.5);before=ui.canvas.yview()[0]
        ui.pin(app.entries[-1]);app.root.update_idletasks();ui.sync_scroll()
        ui.wheel(SimpleNamespace(delta=-120));self.assertGreater(ui.canvas.yview()[0],before)
        ui.query.set('Scroll Boss');ui.filter_now();app.root.update_idletasks()
        self.assertAlmostEqual(ui.canvas.yview()[0],0,places=2)
        ui.wheel(SimpleNamespace(delta=-120));self.assertGreater(ui.canvas.yview()[0],0)
        with patch.object(ui.scroll,'winfo_height',return_value=400):ui.scroll.press(SimpleNamespace(y=395))
        self.assertGreater(ui.canvas.yview()[0],.5)
        self.assert_hidden()

    def test_jiao_alias_saves_and_timer_access_is_in_index(self):
        from model import BossTimer
        app=self.app
        for entry in (dict(id='jiao',name='Jiao, The Flood Dragon',alias='',color='#6acaff',pinned=True,duration=600,mechanic='standard'),dict(id='blind',name='The Blind Jiao, Coiled Round the Deep Vein',alias='',color='#c8afff',pinned=False,duration=900,mechanic='standard')):
            app.entries.append(entry);app.timers[entry['id']]=BossTimer(entry)
        app.open_index();ui=app.index_ui;ui.edit(app.entries[-2]);ui.form['alias'].set('Jiao');ui.alias_override.set(True)
        self.button(ui.editor,'Save changes').invoke();self.assertEqual(app.entries[-2]['alias'],'Jiao')
        ui.edit(app.entries[-2]);self.button(ui.editor,'Set Timer').invoke();self.assertTrue(app.manual_window.winfo_exists())
        app.draw_body(time.monotonic());self.assertNotIn('Set Timer',app.body._text_items.values());self.assert_hidden()

    def test_background_index_build_keeps_placeholders_and_uses_batches(self):
        app=self.app;app.open_index();ui=app.index_ui
        identity={key:row['surface'] for key,row in ui.rows.items()}
        before=sum('label' in row for row in ui.rows.values())
        if ui.build_pending:ui.window.after_cancel(ui.build_pending);ui.build_pending=None
        ui.build_batch()
        after=sum('label' in row for row in ui.rows.values())
        self.assertLessEqual(after-before,1);self.assertEqual(identity,{key:r['surface'] for key,r in ui.rows.items()})
        self.assert_hidden()

    def test_scale_controls_use_five_percent_steps_and_keep_timer_data(self):
        app=self.app;app.open_index();deadline=app.timers['jade'].deadline
        self.button(app.index_window,'−').invoke();self.assertAlmostEqual(app.index_ui.scale*96/app.dpi,.95)
        self.button(app.index_window,'+').invoke();self.assertAlmostEqual(app.index_ui.scale*96/app.dpi,1)
        app.set_ui_scale(.1);self.assertEqual(app.ui_scale,.5)
        app.set_ui_scale(2);self.assertEqual(app.ui_scale,1)
        self.assertEqual(app.timers['jade'].deadline,deadline)
        self.assert_hidden()

    def test_hidden_wrapper_moves_without_resizing_or_showing(self):
        app=self.app
        original=window_rectangle(app.root)[2:]
        self.assertEqual(original[0],app.width,"No stale native-frame padding around the HUD")
        for x,y in [(100,150),(250,300),(-80,200),(45,90)]:
            move_window(app.root,x,y)
            app.root.update_idletasks()
            rect=window_rectangle(app.root)
            self.assertEqual(rect[:2],(x,y))
            self.assertEqual(rect[2:],original)
            self.assert_hidden()

    def test_native_frame_coalesces_invalidation_without_region_replacement(self):
        app=self.app;app.open_index()
        for win in (app.root,app.index_window):
            frame=win.native_frame
            self.assertEqual(frame.attributes.get(2),2)
            self.assertEqual(frame.attributes.get(33),2)
            win.update_idletasks();before=frame.paint_flushes
            with patch('window_style.u.RedrawWindow',return_value=1) as paint:
                for i in range(100):frame.queue_paint()
                win.update_idletasks()
                self.assertEqual(frame.paint_flushes-before,1)
                flags=paint.call_args.args[-1]
                self.assertFalse(flags & (0x0004|0x0100|0x0080)) # no erase / synchronous paint
            self.assertEqual(frame.region_updates,0)
        self.assert_hidden()

    def test_native_text_and_filled_entry_at_reference_scales(self):
        from tkinter import font as tkfont
        from PIL import ImageTk
        from ui_theme import RichLabel
        app=self.app;app.open_index();ui=app.index_ui
        jade=next(e for e in app.entries if e['id']=='jade');ui.update_row(jade)
        for scale in (.5,.75,1):
            app.set_ui_scale(scale,persist=False)
            app.root.update_idletasks()
            for label in (app.title,app.credit,ui.rows['jade']['label']):
                self.assertIsInstance(label,RichLabel)
                self.assertFalse(label.cget('image'))
                self.assertLess(int(label.tk.splitlist(label.cget('font'))[1]),0)
            app._draw_signatures.clear();app.draw_body(time.monotonic())
            items=[i for i in app.body.find_all() if app.body.type(i)=='text']
            self.assertTrue(items)
            self.assertTrue(any('White-Jade' in app.body.itemcget(i,'text') for i in items))
            entry=ui.search;entry.redraw(SimpleNamespace(width=round(450*scale),height=round(42*scale)))
            pixels=ImageTk.getimage(entry._image)
            self.assertEqual(pixels.getchannel('A').getextrema(),(255,255))
            self.assertEqual(entry.entry.cget('bg'),entry.fill)
            self.assertEqual(pixels.size,(round(450*scale),round(42*scale)))
        self.assert_hidden()

    def test_card_surface_is_retained_when_geometry_has_not_changed(self):
        app=self.app;app.open_index();ui=app.index_ui
        jade=next(e for e in app.entries if e['id']=='jade');ui.update_row(jade)
        surface=ui.rows['jade']['surface'];surface.redraw()
        items=surface.find_all();image=surface._surface_image
        for _ in range(20):surface.redraw()
        self.assertEqual(items,surface.find_all());self.assertIs(image,surface._surface_image)
        self.assertEqual(len(surface.find_withtag('surface')),1)
        from ui_theme import CardFrame,cached_image
        import painting
        other=CardFrame(ui.inner)
        bitmap=painting.surface(400,50);key=('shared-regression',400,50)
        self.assertIs(cached_image(surface,bitmap,key),cached_image(other,bitmap,key))
        other.destroy()
        self.assert_hidden()


    def test_v1_region_sections_pin_geometry_and_header_fit(self):
        from boss_rules import REGIONS
        app=self.app;app.open_index();ui=app.index_ui
        app.root.update_idletasks();before=window_rectangle(ui.window)
        entry=next(e for e in app.entries if not e['pinned'] and e.get('mechanic')!='wukong')
        region=entry['region'];self.assertIn(region,REGIONS)
        self.assertTrue(ui.region_headers[region].winfo_manager())
        surface=ui.rows[entry['id']]['surface']
        ui.pin(entry);app.root.update_idletasks();ui.sync_scroll()
        packed=list(ui.inner.pack_slaves());self.assertLess(packed.index(surface),packed.index(ui.headers[1]))
        self.assertEqual(window_rectangle(ui.window),before)
        ui.pin(entry);app.root.update_idletasks();self.assertEqual(window_rectangle(ui.window),before)
        for scale in (.5,.75,1):
            app.set_ui_scale(scale,persist=False);app.root.update_idletasks()
            for label in (app.credit,app.joke):
                self.assertGreaterEqual(label.winfo_height(),label.winfo_reqheight())
            self.assertLess(app.joke.winfo_y()+app.joke.winfo_height(),app.controls.winfo_y())
        self.assert_hidden()

    def test_v1_qi_gold_border_colors_and_location_spacing(self):
        app=self.app;now=time.monotonic();now=round(now)+.05
        for kind,color in [('chaos','#ff848c'),('void','#d5a2ff')]:
            app.qi.activate(kind,now,now,'Stonewind Spires');app.layout(force=True);app.draw_bottom(now)
            items=app.bottom.find_all()
            status=next(i for i in items if app.bottom.type(i)=='text' and app.bottom.itemcget(i,'text')==kind.title()+' Qi Detected!')
            location=next(i for i in items if app.bottom.type(i)=='text' and app.bottom.itemcget(i,'text')=='Stonewind Spires')
            self.assertEqual(app.bottom.itemcget(status,'fill'),color)
            self.assertLess(app.bottom.bbox(status)[3],app.bottom.bbox(location)[1])
            self.assertTrue(any(app.bottom.type(i)=='polygon' and app.bottom.itemcget(i,'outline')=='#f5ce72' for i in items))
        self.assert_hidden()


    def test_v11_preset_overlays_never_reflow_either_window(self):
        app=self.app;app.open_index();ui=app.index_ui;app.root.update_idletasks();ui.sync_scroll()
        hud=window_rectangle(app.root);index=window_rectangle(ui.window);region=ui.canvas.cget('scrollregion');view=ui.canvas.yview();hud_height=app.viewport
        app.open_presets();app.root.update_idletasks();menu=app.preset_menu
        self.assertEqual(menu.frame.winfo_manager(),'place');self.assertFalse(menu.closed)
        self.assertEqual(window_rectangle(app.root),hud);self.assertEqual(app.viewport,hud_height)
        menu.close();ui.open_save_preset();app.root.update_idletasks();popup=ui.preset_overlay
        self.assertEqual(popup.frame.winfo_manager(),'place')
        popup.colors();app.root.update_idletasks()
        self.assertEqual(window_rectangle(app.root),hud);self.assertEqual(window_rectangle(ui.window),index)
        self.assertEqual(ui.canvas.cget('scrollregion'),region);self.assertEqual(ui.canvas.yview(),view)
        self.assertLessEqual(popup.frame.winfo_x()+popup.frame.winfo_width(),ui.window.winfo_width())
        self.assertLessEqual(popup.frame.winfo_y()+popup.frame.winfo_height(),ui.window.winfo_height())
        popup.name.set('Test preset');popup.preview('#c787f5');popup.save();self.assertTrue(popup.closed)
        for scale in (.5,.75,1):
            app.set_ui_scale(scale,persist=False);ui.window.set_scale(scale,persist=False);app.root.update_idletasks()
            before=(window_rectangle(app.root),window_rectangle(ui.window),ui.canvas.cget('scrollregion'))
            ui.open_save_preset();app.root.update_idletasks();ui.preset_overlay.colors();app.root.update_idletasks()
            self.assertEqual((window_rectangle(app.root),window_rectangle(ui.window),ui.canvas.cget('scrollregion')),before)
            ui.preset_overlay.close()
        self.assertEqual(app.config['presets'][0]['name'],'Test preset');self.assertEqual(app.config['presets'][0]['color'],'#c787f5')
        app.open_presets();app.root.update_idletasks();menu=app.preset_menu
        crosses=[w for w in descendants(menu.body) if isinstance(w,ActionButton) and w.cget('text')=='×']
        self.assertEqual(len(crosses),1);self.assertEqual(crosses[0].cget('fg'),'#ff848c')
        marker,color=menu.color_marks[0]
        self.assertEqual(color,'#c787f5');self.assertGreaterEqual(marker._image.width(),10)
        self.assertEqual(marker._image.width(),marker._image.height())
        crosses[0].invoke();self.assertEqual(app.config['presets'],[])
        self.assert_hidden()

    def test_v11_delete_and_preset_restore_preserve_other_timers(self):
        app=self.app;app.open_index();ui=app.index_ui
        preset=app.save_preset('All bosses','#ffffff');entry=app.entries[0];key=entry['id'];other=app.entries[1]['id']
        now=time.monotonic();app.timers[other].observe(Reading(other,'countdown',300),now,now);deadline=app.timers[other].deadline
        app.root.update_idletasks();before=window_rectangle(ui.window);ui.edit(entry)
        delete=self.button(ui.editor,'Delete tracker');delete.invoke();delete.invoke();app.root.update_idletasks()
        self.assertNotIn(key,app.timers);self.assertNotIn(key,ui.rows);self.assertNotIn(key,[e['id'] for e in app.entries])
        self.assertEqual(window_rectangle(ui.window),before);self.assertEqual(app.timers[other].deadline,deadline)
        with patch.object(app,'demo',False):app.persist()
        self.assertNotIn(key,[e['id'] for e in Store(Path(self.temp.name)).data['bosses']])
        other_entry=next(e for e in app.entries if e['id']==other)
        app.apply_preset(preset['id']);self.assertIn(key,app.timers);self.assertEqual(app.timers[other].deadline,deadline)
        self.assertIs(other_entry,next(e for e in app.entries if e['id']==other))
        ui.update_row(other_entry);was_pinned=other_entry['pinned'];ui.rows[other]['pin'].invoke()
        self.assertEqual(next(e for e in app.entries if e['id']==other)['pinned'],not was_pinned)
        self.assert_hidden()

    def test_v11_toolbar_center_divider_and_native_labels(self):
        app=self.app
        for scale in (.5,.75,1):
            app.set_ui_scale(scale,persist=False);app.root.update_idletasks()
            center=app.controls.winfo_x()+app.controls.winfo_width()/2
            self.assertAlmostEqual(center,app.header.winfo_width()/2,delta=2)
            self.assertGreater(app.toolbar_divider.winfo_y(),app.controls.winfo_y()+app.controls.winfo_height())
            for button in app.controls.winfo_children():
                texts=[i for i in button.find_all() if button.type(i)=='text'];self.assertEqual(len(texts),1)
                if button.cget('text') in ('Lock','Index','Reset'):self.assertTrue(hasattr(button,'_icon_image'))
        self.assert_hidden()


    def test_v12_overlay_content_is_clipped_inside_its_border(self):
        app=self.app;app.open_index();ui=app.index_ui
        for scale in (.5,.75,1):
            app.set_ui_scale(scale,persist=False);ui.window.set_scale(scale,persist=False);app.root.update_idletasks()
            ui.open_save_preset();app.root.update_idletasks();popup=ui.preset_overlay
            for expanded in (False,True):
                if expanded:popup.colors()
                app.root.update_idletasks()
                frame=popup.frame;x,y=frame.coords(frame.item)
                width=float(frame.itemcget(frame.item,'width'));height=float(frame.itemcget(frame.item,'height'))
                self.assertGreater(height,0,'The embedded panel must have a bounded height')
                self.assertEqual(frame._surface_key[2],0)
                self.assertEqual(frame.cget('bg'),frame.content.cget('bg'))
                self.assertGreaterEqual(x,4);self.assertGreaterEqual(y,4)
                self.assertLessEqual(x+width,frame.winfo_width()-4)
                self.assertLessEqual(y+height,frame.winfo_height()-4)
                self.assertEqual(popup.name_box.grid_info()['row'],popup.color_row.grid_info()['row'])
                self.assertAlmostEqual(popup.name_box.winfo_y()+popup.name_box.winfo_height()/2,popup.color_row.winfo_y()+popup.color_row.winfo_height()/2,delta=2)
                self.assertTrue(hasattr(popup,'_title_image'))
            popup.close()
        self.assert_hidden()

    def test_v12_headerless_dropdown_square_close_and_save_icons(self):
        app=self.app;app.open_index();ui=app.index_ui
        for scale in (.5,.75,1):
            app.set_ui_scale(scale,persist=False);ui.window.set_scale(scale,persist=False);app.root.update_idletasks()
            before=(window_rectangle(app.root),window_rectangle(ui.window))
            app.preset_button.invoke();app.root.update_idletasks();menu=app.preset_menu
            self.assertIsNone(menu.header)
            self.assertFalse(any(isinstance(w,ActionButton) and w.cget('text')=='×' for w in descendants(menu.frame)))
            app.preset_button.invoke();self.assertTrue(menu.closed)
            self.assertEqual(app.close_button.winfo_width(),app.close_button.winfo_height())
            for button in (app.preset_button,ui.save_preset_button):
                self.assertEqual(button.icon_name,'Save');self.assertTrue(hasattr(button,'_icon_image'))
            self.assertEqual((window_rectangle(app.root),window_rectangle(ui.window)),before)
        self.assert_hidden()

    def test_v12_delete_tracker_requires_second_click_and_cancel_disarms(self):
        app=self.app;app.open_index();ui=app.index_ui;entry=app.entries[0]
        ui.edit(entry);app.root.update_idletasks();button=self.button(ui.editor,'Delete tracker')
        before=(window_rectangle(ui.window),button.winfo_width(),button.winfo_height())
        button.invoke();app.root.update_idletasks()
        self.assertEqual(button.cget('text'),'Confirm?');self.assertIn(entry['id'],app.timers)
        self.assertEqual((window_rectangle(ui.window),button.winfo_width(),button.winfo_height()),before)
        ui.cancel();ui.edit(entry);button=self.button(ui.editor,'Delete tracker')
        button.invoke();self.assertIn(entry['id'],app.timers)
        button.invoke();self.assertNotIn(entry['id'],app.timers)
        self.assert_hidden()

    def test_kill_from_slower_lane_survives_newer_countdown(self):
        app=self.app;now=time.monotonic();timer=app.timers['kraken']
        app.handle_readings(now+1,[Reading('kraken','countdown',450)],now+2)
        app.handle_readings(now,[Reading('kraken','killed')],now+2)
        self.assertEqual(timer.state(now+2),'KILLED')
        self.assertEqual(timer.deadline,now+timer.entry['duration']-3)
        deadline=timer.deadline;kill_until=timer.kill_until
        app.handle_readings(now-1,[Reading('kraken','countdown',20)],now+3)
        app.handle_readings(now+.5,[Reading('kraken','killed')],now+3)
        self.assertEqual(timer.deadline,deadline);self.assertEqual(timer.kill_until,kill_until)
        app.handle_readings(now+10,[Reading('kraken','spawned')],now+10)
        app.handle_readings(now+9,[Reading('kraken','killed')],now+11)
        self.assertEqual(timer.state(now+11),'Spawned')
        self.assert_hidden()

class ExitShortcutTests(unittest.TestCase):
    def test_hotkey_edges_do_not_retoggle_while_held(self):
        held=set(); key=Hotkey(lambda code:0x8000 if code in held else 0)
        self.assertFalse(key.pressed())
        held.update((0x11,0x12,ord('T')))
        self.assertTrue(key.pressed()); self.assertFalse(key.pressed())
        held.clear(); self.assertFalse(key.pressed())
        held.update((0x11,0x12,ord('T'))); self.assertTrue(key.pressed())

    def test_game_exit_requires_prior_presence_and_grace_period(self):
        life=GameLifecycle()
        self.assertFalse(life.should_exit(False,0))
        self.assertFalse(life.should_exit(True,1))
        self.assertFalse(life.should_exit(False,2))
        self.assertFalse(life.should_exit(False,4))
        self.assertTrue(life.should_exit(False,5))


if __name__=='__main__': unittest.main()


