"""Martial Arts World - Tracker: persistent boss Index and screenshot OCR HUD."""
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
import copy
import json
import logging
import math
from pathlib import Path
import queue
import re
import sys
import threading
import time
import uuid
import tkinter as tk
import painting
from boss_rules import VERSION
from ui_scale import bounded_scale,resize_scale,style_tree
from panels import work_area
from window_style import decorate_window,edge_at,edge_cursor
from tkinter import font as tkfont, messagebox, simpledialog, ttk
from storage import Store
from model import BossTimer, EventGate, QiState, GameLifecycle, Reading, GREEN, RED, GOLD
from detection import parse_clock
from win_capture import Hotkey, custom_header, allow_capture, click_through, window_rectangle, roblox_window_exists, move_window, repaint, game_window

BASE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
RESOURCES=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
from ui_theme import BG, PANEL, TEXT, MUTED, BORDER, ACCENT, rounded, card, CardFrame, ActionButton, RichLabel, RoundedEntry, SlimScrollbar, rich_text



def duration_text(seconds):
    return '' if seconds is None else f'{int(seconds)//60}:{int(seconds)%60:02d}'


def input_duration(value):
    value=value.strip()
    if not value: return None
    match=re.fullmatch(r'(\d{1,4})(?:[.:]([0-5]\d))?',value)
    if not match: raise ValueError('Use minutes, M.SS or M:SS. Seconds must be 00–59.')
    seconds=int(match[1])*60+int(match[2] or 0)
    if not 1<=seconds<=86400: raise ValueError('Use a duration from 0:01 to 1440:00.')
    return seconds


class App:
    def __init__(self, demo=False, base=None):
        self.demo=demo
        self.root=tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.title('Martial Arts World - Tracker '+VERSION)
        icon=RESOURCES/'assets'/'tracker.ico'
        if icon.is_file():self.root.iconbitmap(default=str(icon))
        self.root.configure(bg=BG)
        self.root.resizable(False,False)
        self.root.attributes('-topmost',True)
        self.store=Store(base or BASE)
        self.config=self.store.data
        self.ui_scale=float(self.config['ui_scale'])
        self.hud_units=list(self.config.get('hud_units',[900,745]))
        try:
            ctypes.windll.user32.GetDpiForWindow.argtypes=[ctypes.wintypes.HWND]
            ctypes.windll.user32.GetDpiForWindow.restype=ctypes.c_uint
            self.dpi=ctypes.windll.user32.GetDpiForWindow(self.root.winfo_id()) or 96
        except Exception:self.dpi=96
        self.scale=self.ui_scale*self.dpi/96
        self.resize_pending=None;self.resize_event=None
        self._draw_signatures={}
        self._rows_key=None;self._row_layout=[]
        self.root.attributes('-alpha',float(self.config.get('ui_opacity',.95)))
        self.entries=self.config['bosses']
        now,wall=time.monotonic(),time.time()
        self.timers={entry['id']:BossTimer(entry) for entry in self.entries}
        # A new session starts unknown; the saved library/preferences are retained.
        self.qi=QiState(); self.qi.restore(self.config['qi'],now,wall)
        self.gate=EventGate()
        self.states={key:timer.state(now) for key,timer in self.timers.items()}
        self.events=queue.Queue()
        self.stop=threading.Event()
        self.data_lock=threading.Lock()
        self.revision=0
        self.scan_entries=copy.deepcopy(self.entries)
        self.masks=[]
        self.locked=False
        self.unlock_window=None
        self.index_window=None
        self.color_picker=None
        self.preset_menu=None
        self.color_overrides={}
        self.last_scanned=None
        self.scan_seconds=None
        self.scan_mode='Starting'
        self.scan_error=False
        self._font_cache={}
        self._layout_inputs=None
        self.manual_window=None
        self.children=[]
        self.hotkey=Hotkey()
        self.lifecycle=GameLifecycle()
        self.next_game_check=0
        self.next_focus_check=0
        self.next_save=now+5
        self.last_capture=None
        self.reading_times={}
        self.scan_active=False
        self.status='Loading text reader…'
        self.drag=None
        self.resize_drag=None
        self._layout_signature=None
        self._save_error=''
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.bind('<Alt-F4>',lambda event:self.close())
        self.root.bind('<Map>',lambda event:self.root.after(20,self.style_window) if event.widget==self.root else None)
        self.build_ui()
        if demo:
            for key,seconds in [('jade',157),('bow',364),('kraken',48)]:
                if key in self.timers: self.timers[key].observe(Reading(key,'countdown',seconds),now,now,'preview')
            self.status='Design preview — example timers'
            self.scan_active=True
        else:
            threading.Thread(target=self.scan,daemon=True).start()
        position=self.config.get('hud_position',[45,90]);self.root.geometry(f'{position[0]:+d}{position[1]:+d}')
        self.layout(force=True)
        self.root.deiconify()
        self.root.update_idletasks()
        x,y=window_rectangle(self.root)[:2];left,top,right,bottom=work_area(x,y)
        move_window(self.root,max(left,min(x,right-self.width)),max(top,min(y,bottom-self.outer_height)))
        self.style_window()
        self.tick()

    def px(self,value): return max(1,round(value*self.scale))

    def font(self,size=10,bold=False):
        return ('Segoe UI',-max(7,round(size*self.scale)),'bold' if bold else 'normal')

    def button(self,parent,text,command,small=False):
        font=self.font(22,True) if parent.winfo_toplevel()==self.root else ('Segoe UI',10)
        button=ActionButton(parent,text,command,font)
        if parent.winfo_toplevel()==self.root:button._ui_factor=self.scale;button.draw()
        return button

    def build_ui(self):
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('Tracker.Vertical.TScrollbar',background=BORDER,troughcolor=BG,bordercolor=BG,lightcolor=BG,darkcolor=BG,arrowcolor=TEXT,width=10)
        self.window_border=decorate_window(self.root)
        self.shell=tk.Frame(self.root,bg=BG)
        self.shell.place(x=2,y=2,relwidth=1,width=-4,relheight=1,height=-4)
        self.header=tk.Frame(self.shell,bg=BG)
        self.header.pack(fill='x')
        self.title=RichLabel(self.header,text='Martial Arts World - Tracker '+VERSION,bg=BG,fg='#ffdd45',anchor='w')
        self.credit=RichLabel(self.header,text='By Yuu.',bg=BG,fg='#ffdd45',anchor='w')
        self.joke=RichLabel(self.header,text='(Wallahi No virus)',bg=BG,fg='#ffaa55',anchor='w')
        for label in (self.title,self.credit,self.joke):label.configure(borderwidth=0,highlightthickness=0,padx=0,pady=0)
        self.close_button=self.button(self.header,'×',self.close,True);self.close_button.square=True;self.close_button.draw()
        self.controls=tk.Frame(self.header,bg=BG)
        for text,command in [('Lock',self.toggle_lock),('Index',self.open_index),('Presets ▾',self.open_presets),('Reset',self.reset)]:
            button=self.button(self.controls,text,command,True);button.smooth_icon=True;button.draw();button.pack(side='left',padx=2)
            if text=='Presets ▾':self.preset_button=button;button.icon_name='Save';button.draw()
        self.toolbar_divider=tk.Frame(self.header,bg=BORDER)
        for widget in (self.header,self.title,self.credit,self.joke):
            widget.bind('<ButtonPress-1>',self.start_drag)
            widget.bind('<B1-Motion>',self.move)
            widget.bind('<ButtonRelease-1>',self.end_drag)
        self.list_frame=tk.Frame(self.shell,bg=BG)
        self.list_frame.pack(fill='x')
        self.list_frame.pack_propagate(False)
        self.body=tk.Canvas(self.list_frame,bg=BG,highlightthickness=0)
        self.scroll=SlimScrollbar(self.list_frame,command=self.scroll_list)
        self.body.configure(yscrollcommand=self.scroll.set)
        self.body.pack(side='left',fill='both',expand=True)
        self.body.bind('<MouseWheel>',self.wheel)
        self.body.bind('<Button-1>',self.body_click)
        self.divider=tk.Frame(self.shell,bg='#536071',height=1)
        self.divider.pack(fill='x',padx=5,pady=4)
        self.bottom=tk.Canvas(self.shell,bg=BG,highlightthickness=0)
        self.bottom.pack(fill='x')
        self.footer=tk.Frame(self.shell,bg=BG)
        self.footer.pack(fill='x')
        self.scan_label=tk.Label(self.footer,text='Auto Active Scan',bg=BG,fg=MUTED,anchor='w')
        self.scan_label.pack(side='left',padx=7)
        self.shortcut=tk.Label(self.footer,text='Ctrl + Alt + T — Lock / Unlock',bg=BG,fg=TEXT,anchor='e')
        self.shortcut.pack(side='right',padx=7)

        self.root.bind('<Motion>',lambda e:self.root.configure(cursor=edge_cursor(edge_at(self.root,e))),add='+')
        self.root.bind('<ButtonPress-1>',lambda e:self.start_resize(e,edge_at(self.root,e)) if edge_at(self.root,e) else None,add='+')
        self.root.bind('<B1-Motion>',lambda e:self.resize(e) if self.resize_drag else None,add='+')
        self.root.bind('<ButtonRelease-1>',lambda e:self.end_resize(e) if self.resize_drag else None,add='+')

    def start_resize(self,event,edge):
        if self.locked: return
        self.drag=None
        x,y,width,height=window_rectangle(self.root)
        self.resize_drag=dict(edge=edge,mx=event.x_root,my=event.y_root,x=x,y=y,w=width,h=height,scale=self.scale,ui_scale=self.ui_scale,rows=self.config['visible_rows'],units=self.hud_units[:])

    def resize(self,event):
        if not self.resize_drag or self.locked:return
        self.resize_event=(event.x_root,event.y_root)
        if self.resize_pending is None:self.resize_pending=self.root.after(16,self.flush_resize)

    def flush_resize(self):
        if self.resize_pending is not None:self.root.after_cancel(self.resize_pending);self.resize_pending=None
        if not self.resize_event or not self.resize_drag:return
        d=self.resize_drag;x,y=self.resize_event;self.resize_event=None
        self.body._fast_resize=True;self.bottom._fast_resize=True
        dx=x-d['mx'];dy=y-d['my'];edge=d['edge']
        if len(edge)==2:
            self.ui_scale=round(resize_scale(d['ui_scale'],d['w'],d['h'],dx,dy,edge),3)
            self.config['ui_scale']=self.ui_scale
            self.scale=self.ui_scale*self.dpi/96
            self.hud_units=d['units'][:]
        else:
            width=max(round(680*d['scale']),d['w']+(-dx if edge=='w' else dx)) if edge in ('e','w') else d['w']
            height=max(round(470*d['scale']),d['h']+(-dy if edge=='n' else dy)) if edge in ('n','s') else d['h']
            self.hud_units=[width/d['scale'],height/d['scale']]
        self.layout();self.draw_body(time.monotonic());self.draw_bottom(time.monotonic())
        width,height=self.width,self.outer_height
        nx=d['x']+d['w']-width if 'w' in d['edge'] else d['x'];ny=d['y']+d['h']-height if 'n' in d['edge'] else d['y']
        left,top,right,bottom=work_area(nx,ny)
        move_window(self.root,max(left,min(nx,right-width)),max(top,min(ny,bottom-height)))

    def end_resize(self,event):
        self.flush_resize();self.resize_drag=None
        self.body._fast_resize=False;self.bottom._fast_resize=False;self._draw_signatures.clear()
        self.draw_body(time.monotonic());self.draw_bottom(time.monotonic())
        self.config['hud_units']=self.hud_units[:];self.config['hud_position']=list(window_rectangle(self.root)[:2]);self.persist();repaint(self.root)

    def style_panel(self,widget):
        style_tree(widget,getattr(widget.winfo_toplevel(),'_window_scale',self.scale)*1.5)

    def set_ui_scale(self,value,persist=True,panels=True):
        self.ui_scale=bounded_scale(value);self.config['ui_scale']=self.ui_scale
        self.scale=self.ui_scale*self.dpi/96
        self.layout(force=True);self.draw_body(time.monotonic());self.draw_bottom(time.monotonic())
        # HUD scaling never resizes an independent menu.
        if persist:self.persist()

    def wrapped_lines(self,text,font,width):
        item=self.body.create_text(0,0,text=text,font=font,anchor='nw',width=width)
        bounds=self.body.bbox(item)
        self.body.delete(item)
        return max(1,math.ceil((bounds[3]-bounds[1])/font.metrics('linespace')))

    def style_window(self):
        if not self.stop.is_set():
            custom_header(self.root)

    def pinned(self):
        now=time.monotonic()
        return sorted((timer for timer in self.timers.values() if timer.entry['pinned']),key=lambda timer:timer.sort_key(now))

    def measured_font(self,definition):
        if definition not in self._font_cache:self._font_cache[definition]=tkfont.Font(self.root,font=definition)
        return self._font_cache[definition]

    def rows(self,width):
        pinned=self.pinned();key=(round(width),self.scale,tuple((t.entry['id'],t.entry['name']) for t in pinned))
        if key==self._rows_key:return self._row_layout
        self._rows_key=key;result=[];y=0
        available=max(self.px(200),width-self.px(230))
        for timer in pinned:
            font=self.measured_font(self.font(34,True))
            name_height=self.wrapped_lines(timer.entry['name'],font,available)*font.metrics('linespace')
            height=max(self.px(140),name_height+self.px(98))
            result.append((timer,y,height,name_height));y+=height
        self._row_layout=result;self.content_height=y
        return result

    def layout(self,force=False):
        inputs=(self.scale,tuple(self.hud_units),tuple((e['id'],e['name'],e['pinned']) for e in self.entries),self.qi.location,self.qi.kind)
        if not force and inputs==self._layout_inputs:return
        self._layout_inputs=inputs
        left,top,right,bottom=work_area(self.root.winfo_x(),self.root.winfo_y())
        fit=min(1,(right-left)/(self.hud_units[0]*self.dpi/96),(bottom-top)/(self.hud_units[1]*self.dpi/96))
        self.scale=min(self.ui_scale,fit)*self.dpi/96
        self.width=self.px(self.hud_units[0]);self.outer_height=self.px(self.hud_units[1]);self.root._window_scale=self.scale
        self.header_height=self.px(170);self.bottom_height=self.px(150);self.footer_height=self.px(44)
        self.qi_title_height=self.px(28);self.qi_status_height=self.px(42)
        qi_width=self.width*.47-self.px(85)
        status_font=self.measured_font(self.font(34,True))
        status_lines=max(self.wrapped_lines(t,status_font,qi_width) for t in ('Chaos Qi Detected!','Void Qi Detected!','Chaos Qi Exhausted'))
        self.qi_location_y=self.px(57)+status_lines*status_font.metrics('linespace')+self.px(12)
        font=self.measured_font(self.font(24,True))
        location_height=self.wrapped_lines(self.qi.location or 'Location Not Found',font,qi_width)*font.metrics('linespace')
        self.bottom_height=max(self.bottom_height,self.qi_location_y+location_height+self.px(18))
        self.viewport=max(self.px(140),self.outer_height-self.header_height-self.bottom_height-self.footer_height-self.px(13))
        self.row_height=self.px(140);self.timer_width=self.px(170)
        self.shell.place_configure(x=self.px(2),y=self.px(2),width=-self.px(4),height=-self.px(4))
        self.header.configure(height=self.header_height)
        self.title.configure(font=self.font(42,True),wraplength=self.width-self.px(110),justify='left')
        self.title.place(x=self.px(26),y=self.px(14))
        title_font=self.measured_font(self.font(42,True))
        title_h=self.wrapped_lines('Martial Arts World - Tracker '+VERSION,title_font,self.width-self.px(110))*title_font.metrics('linespace')
        credit_y=self.px(14)+title_h+self.px(4)
        credit_h=self.measured_font(self.font(20)).metrics('linespace')
        self.title_height=title_h;self.credit_height=credit_h
        self.credit.configure(font=self.font(20));self.credit.place(x=self.px(28),y=credit_y,height=credit_h)
        self.joke.configure(font=self.font(20));self.joke.place(x=self.px(28),y=credit_y+credit_h+self.px(2),height=credit_h)
        self.close_button._ui_factor=self.scale;self.close_button.configure(font=self.font(30));self.close_button.place(relx=1,x=-self.px(22),y=self.px(18),anchor='ne')
        for button in self.controls.winfo_children():
            button._ui_factor=self.scale;button.configure(font=self.font(22,True));button.pack_configure(padx=self.px(8));button.draw()
        self.controls_height=self.px(46)
        controls_y=credit_y+2*credit_h+self.px(12)
        self.header_height=controls_y+self.controls_height+self.px(12)
        self.header.configure(height=self.header_height)
        self.viewport=max(self.px(140),self.outer_height-self.header_height-self.bottom_height-self.footer_height-self.px(13))
        if not self.locked:self.controls.place(relx=.5,y=controls_y,anchor='n')
        self.toolbar_divider.place(x=self.px(14),y=self.header_height-self.px(2),width=self.width-self.px(28),height=max(1,self.px(1)))
        self.list_frame.configure(height=self.viewport)
        self.body._ui_factor=self.scale;self.bottom._ui_factor=self.scale;self.scroll._ui_factor=self.scale;self.scroll.configure(width=self.px(12))
        self.scroll.pack(side='right',fill='y')
        self.body.pack_configure(side='left',fill='both',expand=True)
        self.rows(self.width-self.px(16))
        self.body.configure(scrollregion=(0,0,self.width,max(self.viewport,self.content_height)),yscrollincrement=self.px(18))
        self.bottom.configure(height=self.bottom_height)
        self.divider.configure(height=max(1,self.px(1)));self.divider.pack_configure(padx=self.px(14),pady=self.px(4))
        self.footer.configure(height=self.footer_height);self.footer.pack_propagate(False)
        self.scan_label.configure(font=self.font(20));self.scan_label.pack_configure(padx=self.px(18))
        self.shortcut.configure(font=self.font(18));self.shortcut.pack_configure(padx=self.px(18))
        if window_rectangle(self.root)[2:]!=(self.width,self.outer_height):self.root.geometry(f'{self.width}x{self.outer_height}')
        self._draw_signatures.clear()
        self.config['hud_dimensions']=[self.width,self.outer_height];self.config['hud_dpi']=self.dpi
        if self.locked:self.show_unlock()

    def start_drag(self,event):
        if edge_at(self.root,event):return
        self.drag=(event.x_root-self.root.winfo_x(),event.y_root-self.root.winfo_y())
    def move(self,event):
        if self.drag and not self.locked:
            x,y=event.x_root-self.drag[0],event.y_root-self.drag[1]
            left,top,right,bottom=work_area(x,y)
            move_window(self.root,max(left,min(x,right-self.width)),max(top,min(y,bottom-self.outer_height)))
    def end_drag(self,event):
        self.drag=None
        try:
            dpi=ctypes.windll.user32.GetDpiForWindow(self.root.winfo_id()) or self.dpi
            if dpi!=self.dpi:self.dpi=dpi;self.set_ui_scale(self.ui_scale)
        except AttributeError:pass
        self.config['hud_position']=list(window_rectangle(self.root)[:2]);self.persist()
        repaint(self.root)
    def scroll_list(self,*args):
        self.body.yview(*args); self.draw_body(time.monotonic())
    def wheel(self,event):
        self.body.yview_scroll(-1 if event.delta>0 else 1,'units')
        self.draw_body(time.monotonic())
        return 'break'
    def body_click(self,event):
        for tag in self.body.gettags('current'):
            if tag.startswith('set:'): self.manual(tag[4:]); break

    def outlined_text(self,canvas,x,y,text,color,font,anchor='w',tag='',width=None):
        rich_text(canvas,x,y,text,color,font,anchor,width,tag)

    def draw_body(self,now):
        canvas=self.body;width=self.width-self.px(16)
        # Draw against the requested layout, not the previous Configure size.
        rows=self.rows(width);start=canvas.canvasy(0);end=start+self.viewport
        visible=[row for row in rows if row[1]+row[2]>=start and row[1]<=end]
        signature=(width,start,self.scale,tuple((t.entry['id'],t.entry['name'],self.color_overrides.get(t.entry['id'],t.entry['color']),t.state(now),t.spawn_location,t.remaining(now),round(t.progress(now)*width),(t.state(now) in ('Reset','KILLED') or now<t.alert_until) and int(now*4)%2) for t,_,_,_ in visible))
        if self._draw_signatures.get('body')==signature:return
        self._draw_signatures['body']=signature;canvas.delete('all');canvas._text_items={}
        if not rows:
            self.outlined_text(canvas,width/2,self.px(60),'Pin bosses in Index to show them here.',MUTED,self.font(24),anchor='center');return
        from ui_theme import cached_image
        for timer,y,height,name_height in visible:
            key=timer.entry['id'];state=timer.state(now);chosen=self.color_overrides.get(key,timer.entry['color'])
            flashing=(state in ('KILLED','Reset') or now<timer.alert_until) and int(now*4)%2==0
            card(canvas,self.px(12),y+self.px(5),width-self.px(12),y+height-self.px(5),RED if state=='KILLED' else GOLD if state=='Reset' else GREEN,flashing)
            right=width-self.px(30)
            self.outlined_text(canvas,self.px(30),y+self.px(17),timer.entry['name'],painting.vibrant(chosen),self.font(34,True),anchor='nw',width=width-self.px(230))
            value=duration_text(timer.remaining(now)) if state=='countdown' else ('Waiting' if state=='Waiting for notification' else state)
            self.outlined_text(canvas,right,y+self.px(20),value,timer.color(now),self.font(40 if state=='countdown' else 32,True),anchor='ne')
            subtitle='Respawn countdown'
            if timer.entry.get('mechanic')=='wukong':subtitle='Waiting for notification' if state=='Waiting for notification' else 'Defeat detected' if state=='KILLED' else 'Location: '+(timer.spawn_location or 'Location Not Found')
            elif state=='KILLED':subtitle='Respawn restarted' if timer.entry.get('duration') else 'Waiting for a countdown'
            elif state=='Reset':subtitle='Waiting for a fresh reading'
            elif state=='Need entry':subtitle='No timer detected yet'
            elif state=='Can spawn':subtitle='Calling Altar ready'
            elif state=='Spawned':subtitle='Arrival detected' if timer.spawned else 'Countdown complete'
            elif timer.entry.get('mechanic')=='kraken':subtitle='Calling Altar cooldown'
            elif not timer.entry.get('duration'):subtitle='Full duration unknown'
            self.outlined_text(canvas,self.px(30),y+self.px(25)+name_height,subtitle,MUTED,self.font(24),anchor='nw')
            if timer.entry.get('mechanic')=='wukong':continue
            bar_width=round(right-self.px(30));bar_height=self.px(20);bar_y=y+height-self.px(34)
            fill=round((bar_width-2)*timer.progress(now))
            if getattr(canvas,'_fast_resize',False):
                rounded(canvas,self.px(30),bar_y,right,bar_y+bar_height,self.px(8),fill='#30434e',outline='#435966')
                if fill>1:rounded(canvas,self.px(30)+1,bar_y+1,self.px(30)+1+fill,bar_y+bar_height-1,self.px(7),fill=chosen,outline='')
            else:
                image=painting.surface(bar_width,bar_height,'#30434e','#263943','#435966',self.px(8))
                canvas.create_image(self.px(30),bar_y,anchor='nw',image=cached_image(canvas,image,('track',image.size,self.scale)))
                fill=round((bar_width-2)*timer.progress(now))
                if fill>1:
                    image=painting.surface(fill,max(2,bar_height-2),painting.mix(chosen,'#ffffff',.10),chosen,None,self.px(7))
                    canvas.create_image(self.px(30)+1,bar_y+1,anchor='nw',image=cached_image(canvas,image,('fill',key,image.size,chosen,self.scale)))
            canvas.configure(scrollregion=(0,0,width,max(self.viewport,self.content_height)))

    def draw_bottom(self,now):
        from ui_theme import cached_image
        c=self.bottom;state=self.qi.state(now)
        flash=now<self.qi.flash_until and int(now*4)%2==0
        age='Never' if self.last_scanned is None else 'just now' if now-self.last_scanned<1 else f'{int(now-self.last_scanned)}s ago'
        info=self._save_error or f'{self.status}\nLast Scanned: {age}'+('' if self.scan_seconds is None else f'\nScan: {self.scan_seconds:.2f}s · {self.scan_mode}')
        signature=(self.width,self.bottom_height,self.scale,state,self.qi.location,flash,info,self.scan_active,self.scan_error)
        if self._draw_signatures.get('bottom')==signature:return
        self._draw_signatures['bottom']=signature;c.delete('all');c._text_items={}
        width=self.width-self.px(4);mid=width*.47
        card(c,self.px(14),self.px(5),mid-self.px(6),self.bottom_height-self.px(5),RED if 'Exhausted' in state else GOLD,flash)
        if flash:
            rounded(c,self.px(14),self.px(5),mid-self.px(6),self.bottom_height-self.px(5),self.px(12),fill='',outline=RED if 'Exhausted' in state else GOLD,width=max(2,self.px(3)))
        card(c,mid+self.px(8),self.px(5),width-self.px(14),self.bottom_height-self.px(5))
        self.outlined_text(c,self.px(34),self.px(22),'Chaos/ Void Qi Tracker',TEXT,self.font(24,True),anchor='nw')
        self.outlined_text(c,self.px(34),self.px(57),state,RED if 'Exhausted' in state or self.qi.kind=='chaos' else '#d5a2ff' if self.qi.kind=='void' else TEXT,self.font(34,True),anchor='nw',width=mid-self.px(55))
        if state in ('Void Qi Detected!','Chaos Qi Detected!'):
            location=self.qi.location or 'Location Not Found'
            icon_size=self.px(22)
            icon=painting.location_pin(icon_size,GREEN)
            c.create_image(self.px(34),self.qi_location_y,anchor='nw',image=cached_image(c,icon,('location-pin',icon_size,GREEN)))
            self.outlined_text(c,self.px(66),self.qi_location_y,location,TEXT,self.font(24,True),anchor='nw',width=mid-self.px(85))
        self.outlined_text(c,mid+self.px(30),self.px(22),info,MUTED,self.font(20),anchor='nw',width=width-mid-self.px(60))
        self.scan_label.configure(text='●  Active Scanning' if self.scan_active else '●  Scan error' if self.scan_error else '●  Paused — game not focused',fg=GREEN if self.scan_active else RED if self.scan_error else '#ffdc6b')

    def show_unlock(self):
        if not self.unlock_window or not self.unlock_window.winfo_exists():
            badge=tk.Toplevel(self.root)
            badge.withdraw(); badge.overrideredirect(True); badge.attributes('-topmost',True); badge.configure(bg=BG); badge.attributes('-alpha',self.config.get('ui_opacity',.95))
            self.button(badge,'Unlock',self.toggle_lock,True).pack(side='left',padx=2,pady=2)
            self.button(badge,'Exit',self.close,True).pack(side='left',padx=2,pady=2)
            self.unlock_window=badge
        badge=self.unlock_window
        for button in badge.winfo_children():button._ui_factor=self.scale;button.configure(font=self.font(22,True))
        badge.update_idletasks()
        x=self.root.winfo_rootx()+self.root.winfo_width()-badge.winfo_reqwidth()-self.px(9)
        y=self.root.winfo_rooty()+self.px(83)
        badge.geometry(f'+{max(0,x)}+{max(0,y)}')
        badge.deiconify(); badge.update_idletasks(); click_through(badge,False); allow_capture(badge); badge.lift()

    def toggle_lock(self):
        if self.preset_menu and not self.preset_menu.closed:self.preset_menu.close()
        if self.locked:
            if not click_through(self.root,False): return
            self.locked=False
            if self.unlock_window: self.unlock_window.withdraw()
            self.layout(force=True)
        else:
            self.controls.place_forget()
            self.show_unlock()
            if click_through(self.root,True): self.locked=True
            else:
                self.unlock_window.withdraw(); self.layout(force=True)

    def manual(self,key):
        if self.manual_window and self.manual_window.winfo_exists():self.manual_window.close_panel()
        win=self.panel('Set Timer',340,285,key='set_timer');self.manual_window=win
        tk.Label(win,text=self.timers[key].entry['name'],bg=BG,fg=self.timers[key].entry['color'],font=('Segoe UI',11,'bold'),wraplength=310,justify='left').pack(fill='x',padx=14,pady=5)
        tk.Label(win,text='Remaining time',bg=BG,fg=MUTED,anchor='w').pack(fill='x',padx=14)
        value=tk.StringVar();message=tk.StringVar(value='Minutes, M.SS or M:SS')
        box=RoundedEntry(win,textvariable=value,bg=PANEL,fg=TEXT,insertbackground=TEXT,font=('Segoe UI',13),relief='flat',highlightthickness=1,highlightbackground=BORDER);box.pack(fill='x',padx=14,pady=5)
        feedback=tk.Label(win,textvariable=message,bg=BG,fg=TEXT,font=('Segoe UI',11,'bold'),wraplength=310);feedback.pack(fill='x',padx=14,pady=6)
        def preview(*args):
            try:
                seconds=input_duration(value.get());message.set('Will set: '+duration_text(seconds) if seconds else 'Minutes, M.SS or M:SS');feedback.configure(fg=TEXT)
            except ValueError as exc:message.set(str(exc));feedback.configure(fg=RED)
        def save():
            try:
                seconds=input_duration(value.get())
                if seconds is None:raise ValueError('Enter a remaining time.')
                now=time.monotonic()
                if not self.timers[key].observe(Reading(key,'countdown',seconds),now,now,'manual'):raise ValueError('Time exceeds the full respawn duration.')
                self.revision+=1;self.persist();win.close_panel()
            except ValueError as exc:message.set(str(exc));feedback.configure(fg=RED)
        value.trace_add('write',preview);box.bind('<Return>',lambda event:save())
        actions=tk.Frame(win,bg=BG);actions.pack(fill='x',padx=14,pady=8)
        self.button(actions,'Set Timer',save).pack(side='right');self.button(actions,'Cancel',win.close_panel).pack(side='right',padx=5)
        self.manual_value=value;self.manual_feedback=message
        self.finish_panel(win)

    def reset(self):
        self.timers={entry['id']:BossTimer(entry) for entry in self.entries}
        self.states={key:'Need entry' for key in self.timers}
        self.qi=QiState(); self.gate=EventGate()
        self.revision+=1
        self.last_capture=None;self.reading_times={}
        self.status='Timers and Qi cleared; Index entries retained.'
        self.persist()

    def changed(self):
        self.revision+=1
        with self.data_lock: self.scan_entries=copy.deepcopy(self.entries)
        self.persist(); self.layout(force=True)

    def finish_panel(self,win):
        self.style_panel(win);win.update_idletasks();custom_header(win);win.deiconify()

    def panel(self,title,width=620,height=620,key=None,resizable=False):
        from panels import make_panel
        return make_panel(self,title,width,height,key,resizable)

    def delete_boss(self,key):
        if key not in self.timers:return
        if self.manual_window and self.manual_window.winfo_exists():self.manual_window.close_panel()
        ui=getattr(self,'index_ui',None)
        if ui and ui.window.winfo_exists():ui.cancel()
        self.entries[:]=[e for e in self.entries if e['id']!=key]
        deleted=self.config.setdefault('deleted_boss_ids',[])
        if key not in deleted:deleted.append(key)
        if self.timers[key].entry.get('mechanic')=='wukong' and 'wukong' not in deleted:deleted.append('wukong')
        self.timers.pop(key,None);self.states.pop(key,None);self.color_overrides.pop(key,None)
        self.reading_times={k:v for k,v in self.reading_times.items() if k[0]!=key}
        self.gate.events={k:v for k,v in self.gate.events.items() if not k.startswith(key+':')}
        if ui and ui.window.winfo_exists():
            row=ui.rows.pop(key,None)
            if row:row['surface'].destroy()
            ui.refresh()
        self.changed()

    def save_preset(self,name,color):
        from presets import save_preset
        preset=save_preset(self.config,name,color);self.persist()
        return preset

    def delete_preset(self,key):
        self.config['presets'][:]=[p for p in self.config.get('presets',[]) if p['id']!=key]
        self.persist()

    def apply_preset(self,key):
        from presets import merged_library
        preset=next((p for p in self.config.get('presets',[]) if p['id']==key),None)
        if preset is None:return
        entries=merged_library(self.entries,preset)
        ui=getattr(self,'index_ui',None)
        if ui and ui.window.winfo_exists():ui.cancel()
        existing={entry['id']:entry for entry in self.entries}
        # Retained Index row callbacks reference these objects; preserve identity.
        for index,entry in enumerate(entries):
            if entry['id'] in existing:
                live=existing[entry['id']];live.update(entry);entries[index]=live
        self.entries[:]=entries
        for entry in self.entries:
            if entry['id'] in self.timers:self.timers[entry['id']].entry=entry
            else:self.timers[entry['id']]=BossTimer(entry)
        restored={e['id'] for e in entries}
        self.config['deleted_boss_ids']=[key for key in self.config.get('deleted_boss_ids',[]) if key not in restored]
        self.changed()
        if ui and ui.window.winfo_exists():ui.refresh()

    def open_presets(self):
        if self.preset_menu and not self.preset_menu.closed:self.preset_menu.close();return
        from preset_ui import PresetDropdown
        self.preset_menu=PresetDropdown(self,self.preset_button)

    def open_index(self):
        if self.index_window and self.index_window.winfo_exists():self.index_window.deiconify();self.index_window.lift();return
        from index_ui import IndexPanel
        self.index_ui=IndexPanel(self);self.index_window=self.index_ui.window

    def persist(self):
        if self.demo: return
        now,wall=time.monotonic(),time.time()
        self.config['timers']={key:timer.snapshot(now,wall) for key,timer in self.timers.items()}
        self.config['qi']=self.qi.snapshot(now,wall)
        self.config['events']=self.gate.snapshot(now,wall)
        try:
            self.store.save(); self._save_error=''
        except (OSError,ValueError):
            self._save_error='Changes could not be saved. See tracker.log.'
            logging.exception('Could not save tracker data')

    def scan(self):
        from scan_pipeline import LatestFrame,ScanFrame,capture_delay,SCAN_INTERVAL
        self.frames=LatestFrame()
        for lane in ('banner','notifications','labels'):
            threading.Thread(target=self.scan_lane,args=(lane,),daemon=True).start()
        try:
            import mss
            from PIL import Image,ImageDraw
            with mss.mss() as screen:
                while not self.stop.is_set():
                    started=time.monotonic()
                    try:
                        region=game_window()
                        if not region:
                            self.frames.publish(None)
                            self.events.put(('status',False,'Return to the game to resume scanning.'))
                            self.stop.wait(SCAN_INTERVAL);continue
                        with self.data_lock:masks=self.masks[:];revision=self.revision
                        captured=time.monotonic();shot=screen.grab(region)
                        image=Image.frombytes('RGB',shot.size,shot.rgb)
                        draw=ImageDraw.Draw(image)
                        for x,y,width,height in masks:
                            draw.rectangle((x-region['left'],y-region['top'],x-region['left']+width,y-region['top']+height),fill='black')
                        self.frames.publish(ScanFrame(revision,captured,image))
                    except Exception:
                        logging.exception('Screen capture interrupted')
                        self.events.put(('status',False,'Scan interrupted; retrying. Timers continue.'))
                    self.stop.wait(capture_delay(started,time.monotonic()))
        except Exception:
            logging.exception('Could not start screen capture')
            self.events.put(('status',False,'Reader stopped. See tracker.log; manual timers still work.'))

    def scan_lane(self,lane):
        try:
            from screen_reader import ScreenReader
            with self.data_lock:entries=copy.deepcopy(self.scan_entries);revision=self.revision
            reader=ScreenReader(entries,priority=lane!='labels');sequence=0
            while not self.stop.is_set():
                sequence,frame=self.frames.next(sequence,self.stop)
                if frame is None or self.stop.is_set():continue
                if frame.revision!=revision:
                    with self.data_lock:entries=copy.deepcopy(self.scan_entries);revision=self.revision
                    if revision!=frame.revision:continue
                    reader.configure(entries)
                try:
                    started=time.monotonic();posted=set()
                    def publish(readings):
                        fresh=[r for r in readings if r not in posted];posted.update(fresh)
                        if fresh and not self.stop.is_set():self.events.put(('readings',revision,frame.captured,fresh))
                    readings=reader.read_background(frame.image,emit=publish) if lane=='labels' else reader.read_events(frame.image,lane,emit=publish)
                    publish(readings)
                    if lane!='labels':
                        self.events.put(('scanned',time.monotonic(),time.monotonic()-started,reader.mode))
                        self.events.put(('status',True,'Watching for boss and Qi announcements.'))
                except Exception:
                    logging.exception('OCR lane %s interrupted',lane)
                    self.events.put(('status',False,'Scan interrupted; retrying. Timers continue.'))
        except Exception:
            logging.exception('Could not start OCR lane %s',lane)
            self.events.put(('status',False,'Reader stopped. See tracker.log; manual timers still work.'))

    def handle_readings(self,captured,readings,now):
        event_time=captured  # Model owns the explicit three-second kill correction.
        changed=False
        for reading in readings:
            # A fast countdown must not suppress a slower, earlier-captured kill.
            category='announcement' if reading.kind in ('killed','spawned') else 'timer' if reading.kind in ('countdown','ready') else 'qi'
            key=(reading.boss,category)
            newest=self.reading_times.get(key,float('-inf'))
            if category=='timer':newest=max(newest,self.reading_times.get((reading.boss,'announcement'),float('-inf')))
            if captured<newest:continue
            self.reading_times[key]=captured
            if reading.kind in ('killed','spawned','chaos','void','void_end','chaos_end'):
                if not self.gate.accept(reading.boss+':'+reading.kind,captured):
                    if reading.kind=='spawned' and reading.location and reading.boss in self.timers and self.timers[reading.boss].spawned:
                        self.timers[reading.boss].spawn_location=reading.location;changed=True;self._draw_signatures.pop('body',None)
                    if reading.kind in ('chaos','void') and self.qi.kind==reading.kind and not self.qi.location and reading.location and self.qi.expires and now<self.qi.expires:
                        self.qi.location=reading.location;changed=True
                    continue
            if reading.kind in ('chaos','void'):
                self.qi.activate(reading.kind,event_time,now,reading.location); changed=True
            elif reading.kind in ('void_end','chaos_end'):
                changed=self.qi.exhaust(reading.kind.removesuffix('_end'),now) or changed
            elif reading.boss in self.timers:
                changed=self.timers[reading.boss].observe(reading,event_time if reading.kind=='killed' else captured,now) or changed
        self.last_capture=max(self.last_capture or captured,captured)
        if changed and (now>=self.next_save or any(reading.kind in ('killed','spawned','chaos','void','void_end','chaos_end','ready') for reading in readings)):
            self.persist(); self.next_save=now+5

    def update_scan_focus(self,focused):
        if not focused:
            self.scan_active=False
            if not self.scan_error:self.status='Return to the game to resume scanning.'
        elif self.last_scanned is not None and not self.scan_error:
            self.scan_active=True;self.status='Watching for boss and Qi announcements.'

    def tick(self):
        if self.stop.is_set(): return
        now=time.monotonic()
        if not self.demo and now>=self.next_game_check:
            self.next_game_check=now+1
            if self.lifecycle.should_exit(roblox_window_exists(),now): self.close(); return
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='status':
                    self.scan_active,self.status=event[1:];self.scan_error='interrupted' in self.status.lower() or 'stopped' in self.status.lower()
                elif event[0]=='scanned':self.last_scanned,self.scan_seconds,self.scan_mode=event[1:]
                elif event[1]==self.revision and now-event[2]<20: self.handle_readings(event[2],event[3],now)
        except queue.Empty: pass
        if not self.demo and now>=self.next_focus_check:
            self.next_focus_check=now+.25
            self.update_scan_focus(game_window() is not None)
        for key,timer in self.timers.items():
            state=timer.state(now)
            if state!=self.states.get(key) and state in ('Spawned','Can spawn'): timer.alert_until=now+12
            self.states[key]=state
        self.layout(); self.draw_body(now); self.draw_bottom(now)
        self.children=[win for win in self.children if win.winfo_exists()]
        windows=[self.root]+self.children
        if self.unlock_window and self.unlock_window.winfo_exists() and self.unlock_window.winfo_ismapped(): windows.append(self.unlock_window)
        with self.data_lock: self.masks=[window_rectangle(win) for win in windows if win.winfo_ismapped()]
        if self.hotkey.pressed(): self.toggle_lock()
        if now>=self.next_save: self.persist(); self.next_save=now+5
        self.root.after(100,self.tick)

    def close(self):
        if self.stop.is_set(): return
        for win in self.children:
            if win.winfo_exists() and hasattr(win,'remember_geometry'):win.remember_geometry()
        self.persist(); self.stop.set(); self.hotkey.close(); self.root.destroy()


def main():
    if '--self-test' in sys.argv:
        from diagnostics import run
        raise SystemExit(run(sys.argv[1:]))
    try:ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Yuu.MartialArtsWorldTracker')
    except Exception:pass
    logging.basicConfig(filename=BASE/'tracker.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        app=App(demo='--demo' in sys.argv)
        app.root.mainloop()
    except Exception:
        logging.exception('Tracker startup failed')
        ctypes.windll.user32.MessageBoxW(None,'Tracker could not start. Existing settings were preserved. See tracker.log.','Tracker',0x10)


if __name__=='__main__': main()
