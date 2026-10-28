"""Stable, compact Index: retain row widgets, filter in place, never auto-resize."""
import tkinter as tk
from tkinter import ttk
import uuid
from ui_theme import BG,PANEL,TEXT,MUTED,BORDER,CardFrame,RichLabel,RoundedEntry,SlimScrollbar
from color_editor import InlineColorPicker
from registry import filtered_entries,check_name_conflicts,alias_warnings
from model import BossTimer
from boss_rules import REGIONS,region_for


class IndexPanel:
    def __init__(self,app):
        self.app=app;self.rows={};self.editor=None;self.editing=None;self.preview_key=None;self.pending=None;self.scroll_pending=None;self.scroll_target=None;self.build_pending=None
        self.window=app.panel('Index',540,610,key='index',resizable=True)
        self.window.bind('<Destroy>',self.destroy,add='+')
        tk.Label(self.window,text='Boss Library',bg=BG,fg=TEXT,font=('Segoe UI',12,'bold'),anchor='w').pack(fill='x',padx=14)
        self.instructions=tk.Label(self.window,text='Instructions\nEnter the full name. Respawn time is optional.\nWukong and Kraken cannot be reliably added manually.',bg=BG,fg=MUTED,font=('Segoe UI',9,'bold'),justify='left',anchor='w',wraplength=570)
        self.instructions.pack(fill='x',padx=14,pady=(5,2))
        self.warning=tk.Label(self.window,text='Boss names must match the in-game announcements as closely as possible for accurate detection.',bg=BG,fg='#ff9999',font=('Segoe UI',9,'bold'),justify='left',anchor='w',wraplength=570)
        self.warning.pack(fill='x',padx=14,pady=(0,6))
        search=tk.Frame(self.window,bg=BG);search.pack(fill='x',padx=14,pady=(0,8))
        tk.Label(search,text='Search',bg=BG,fg=MUTED,font=('Segoe UI',9,'bold')).pack(side='left',padx=(0,8))
        self.query=tk.StringVar();self.search=RoundedEntry(search,textvariable=self.query,bg=PANEL,fg=TEXT,insertbackground=TEXT,relief='flat',highlightthickness=1,highlightbackground=BORDER)
        self.search.pack(side='left',fill='x',expand=True)
        app.button(search,'×',lambda:self.query.set('')).pack(side='right',padx=3)
        tk.Label(search,text='A–Z',bg=BG,fg=MUTED).pack(side='right',padx=5)
        area=tk.Frame(self.window,bg=BG);area.pack(fill='both',expand=True,padx=10)
        self.canvas=tk.Canvas(area,bg=BG,highlightthickness=0,width=570)
        scroll=SlimScrollbar(area,command=self.canvas.yview);self.scroll=scroll
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scroll.set,yscrollincrement=14)
        self.inner=tk.Frame(self.canvas,bg=BG);self.inner_id=self.canvas.create_window(0,0,anchor='nw',window=self.inner,width=570)
        self.inner.bind('<Configure>',self.queue_scroll)
        self.canvas.bind('<Configure>',self.resize)
        self.headers=[]
        for title in ('Pinned','Unpinned'):
            header=tk.Frame(self.inner,bg=BG);header.pack(fill='x',pady=(7,3))
            tk.Label(header,text=title,bg=BG,fg='#a7f5cb' if title=='Pinned' else TEXT,font=('Segoe UI',11,'bold'),anchor='w').pack(side='left',padx=5)
            tk.Frame(header,bg=BORDER,height=1).pack(side='left',fill='x',expand=True,padx=8)
            self.headers.append(header)
        self.region_headers={}
        for region in REGIONS:
            header=tk.Frame(self.inner,bg=BG)
            tk.Label(header,text=region,bg=BG,fg='#f5ce72',font=('Segoe UI',10,'bold'),anchor='w').pack(side='left',padx=5)
            tk.Frame(header,bg=BORDER,height=1).pack(side='left',fill='x',expand=True,padx=8)
            self.region_headers[region]=header
        footer=tk.Frame(self.window,bg=BG);footer.pack(fill='x',padx=12,pady=9)
        app.button(footer,'+ Add boss',lambda:self.edit(None)).pack(side='left')
        self.save_preset_button=app.button(footer,'Save Preset',self.open_save_preset);self.save_preset_button.icon_name='Save';self.save_preset_button.draw();self.save_preset_button.pack(side='left',padx=6)
        self.preset_overlay=None
        scale_area=tk.Frame(footer,bg=BG);scale_area.pack(side='right')
        app.button(scale_area,'−',lambda:self.window.set_scale(round(self.scale*96/app.dpi*20-1)/20)).pack(side='left')
        self.scale_label=tk.Label(scale_area,text=f'UI scale {round(self.scale*96/app.dpi*100)}%',bg=BG,fg=TEXT,font=('Segoe UI',10,'bold'));self.scale_label.pack(side='left',padx=7)
        app.button(scale_area,'+',lambda:self.window.set_scale(round(self.scale*96/app.dpi*20+1)/20)).pack(side='left')
        self.query.trace_add('write',self.queue_filter)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.window.bind('<MouseWheel>',self.wheel,add='+')
        self.refresh(initial=True)
        self.window.retain_on_close=True;self.window.on_close=self.cancel
        self.window.on_scale=self.scale_changed
        app.finish_panel(self.window)
    @property
    def scale(self):return self.window._window_scale

    def destroy(self,event):
        if event.widget!=self.window:return
        if self.pending:self.window.after_cancel(self.pending);self.pending=None
        if self.scroll_pending:self.window.after_cancel(self.scroll_pending);self.scroll_pending=None
        if self.build_pending:self.window.after_cancel(self.build_pending);self.build_pending=None
        self.clear_preview()
    def clear_preview(self):
        if self.preview_key:self.app.color_overrides.pop(self.preview_key,None)
        self.preview_key=None
    def scale_changed(self):
        self.scale_label.configure(text=f'UI scale {round(self.scale*96/self.app.dpi*100)}%');self.queue_scroll()
    def resize(self,event):
        if getattr(self,'_last_width',None)==event.width:return
        self._last_width=event.width
        self.canvas.itemconfigure(self.inner_id,width=max(round(280*self.scale*1.5),event.width))
        self.instructions.configure(wraplength=max(round(240*self.scale*1.5),event.width-round(5*self.scale*1.5)));self.warning.configure(wraplength=max(round(240*self.scale*1.5),event.width-round(5*self.scale*1.5)))
    def queue_scroll(self,event=None):
        if self.scroll_pending:self.window.after_cancel(self.scroll_pending)
        self.scroll_pending=self.window.after_idle(self.sync_scroll)
    def sync_scroll(self):
        self.scroll_pending=None
        self.canvas.configure(scrollregion=(0,0,max(1,self.canvas.winfo_width()),max(1,self.inner.winfo_reqheight())))
        if self.scroll_target is not None:self.canvas.yview_moveto(self.scroll_target);self.scroll_target=None
    def wheel(self,event):
        self.canvas.yview_scroll(-3 if event.delta>0 else 3,'units');return 'break'
    def bind_wheel(self,widget):
        widget.bind('<MouseWheel>',self.wheel)
        for child in widget.winfo_children():self.bind_wheel(child)
    def queue_filter(self,*args):
        if self.pending:self.window.after_cancel(self.pending)
        self.pending=self.window.after(60,self.filter_now)
    def filter_now(self):
        if self.pending:self.window.after_cancel(self.pending)
        self.pending=None;self.refresh();self.scroll_target=0;self.queue_scroll()
    def placeholder(self,entry):
        surface=CardFrame(self.inner,entry['color']);surface.configure(height=round(58*self.scale*1.5));surface._ui_factor=self.scale*1.5
        placeholder=tk.Label(surface.content,text=entry['name'],bg=PANEL,fg=entry['color'],font=('Segoe UI',-round(22*self.scale),'bold'),anchor='w');placeholder.pack(fill='x',pady=8)
        row=dict(surface=surface,placeholder=placeholder);self.rows[entry['id']]=row;self.bind_wheel(surface)
        return row
    def build_batch(self):
        self.build_pending=None
        ordered=filtered_entries(self.app.entries,self.query.get())+self.app.entries
        pending=[];seen=set()
        for entry in ordered:
            if entry['id'] not in seen and 'label' not in self.rows.get(entry['id'],{}):pending.append(entry);seen.add(entry['id'])
        for entry in pending[:1]:self.update_row(entry)
        if len(pending)>1:self.build_pending=self.window.after(8,self.build_batch)
    def make_row(self,entry):
        row=self.rows.get(entry['id']) or self.placeholder(entry)
        surface=row['surface']
        if 'placeholder' in row:row.pop('placeholder').destroy()
        line=tk.Frame(surface.content,bg=PANEL);line.pack(fill='x',padx=4,pady=3)
        label=RichLabel(line,text=entry['name'],fg=entry['color'],bg=PANEL,font=('Segoe UI',11,'bold'),anchor='w',justify='left',wraplength=330)
        pin=self.app.button(line,'Pinned' if entry['pinned'] else 'Pin',lambda:self.pin(entry));pin.configure(min_width=70);pin.pack(side='right',padx=2)
        self.app.button(line,'Edit',lambda:self.edit(entry)).pack(side='right',padx=2)
        duration=tk.Label(line,bg=PANEL,fg=MUTED,font=('Segoe UI',9));duration.pack(side='right',padx=6)
        label.pack(side='left',fill='x',expand=True)
        def fit_label(event):
            width=max(50,event.width)
            if int(label.cget('wraplength'))!=width:label.configure(wraplength=width)
        label.bind('<Configure>',fit_label)
        row=dict(surface=surface,label=label,pin=pin,duration=duration);self.rows[entry['id']]=row
        self.bind_wheel(surface);return row
    def update_row(self,entry):
        from tracker import duration_text
        row=self.rows.get(entry['id'])
        if not row or 'label' not in row:row=self.make_row(entry)
        fingerprint=(entry['name'],entry['color'],entry.get('duration'),entry['pinned'])
        if row.get('fingerprint')==fingerprint:return row
        row['fingerprint']=fingerprint
        row['label'].configure(text=entry['name'],fg=entry['color'])
        row['duration'].configure(text='Notification only' if entry.get('mechanic')=='wukong' else duration_text(entry.get('duration')) or 'Error! - Set a timer',fg=MUTED if entry.get('duration') or entry.get('mechanic')=='wukong' else '#ff9999',wraplength=110)
        row['pin'].configure(text='Pinned' if entry['pinned'] else 'Pin',bg='#1d5a41' if entry['pinned'] else '#25394e',fg='#baffda' if entry['pinned'] else TEXT)
        row['surface'].accent=entry['color'];self.app.style_panel(row['surface']);row['surface'].redraw()
        return row
    def refresh(self,initial=False):
        position=self.canvas.yview()[0]
        visible=filtered_entries(self.app.entries,self.query.get());self.visible_ids=[entry['id'] for entry in visible]
        needed=set() if initial else {entry['id'] for entry in visible[:4] if entry['id'] not in self.rows}
        for entry in self.app.entries:
            if entry['id'] in needed or 'label' in self.rows.get(entry['id'],{}):self.update_row(entry)
            elif entry['id'] not in self.rows:self.placeholder(entry)
        if not self.build_pending:self.build_pending=self.window.after(8,self.build_batch)
        wanted={entry['id'] for entry in visible}
        for key,row in self.rows.items():
            if key not in wanted and row['surface'].winfo_manager():row['surface'].pack_forget()
        ordered=[self.headers[0]]+[self.rows[e['id']]['surface'] for e in visible if e['pinned']]+[self.headers[1]]
        for region,header in self.region_headers.items():
            entries=[e for e in visible if not e['pinned'] and e.get('region',region_for(e['name']))==region]
            if entries:ordered.extend([header]+[self.rows[e['id']]['surface'] for e in entries])
            elif header.winfo_manager():header.pack_forget()
        # Retain every row and the window geometry; only change sibling order.
        if list(self.inner.pack_slaves())!=ordered:
            previous=None
            for widget in ordered:
                widget.pack(fill='x',pady=(7,3) if widget in self.headers or widget in self.region_headers.values() else 2,**({'after':previous} if previous is not None else {}))
                previous=widget
        if self.editor and self.editing is None:self.editor.pack(fill='x',padx=8,pady=8)
        self.scroll_target=position;self.queue_scroll()
    def pin(self,entry):
        entry['pinned']=not entry['pinned']
        self.refresh();self.app.changed()
    def cancel(self):
        overlay=getattr(self,'preset_overlay',None)
        if overlay and not overlay.closed:overlay.close()
        self.clear_preview()
        if self.editor:self.editor.destroy();self.editor=None
        if self.editing:
            row=self.rows[self.editing['id']];row['surface'].selected=False;row['surface'].accent=self.editing['color'];row['label'].configure(fg=self.editing['color']);row['surface'].redraw()
        self.editing=None
    def edit(self,entry):
        from tracker import duration_text,input_duration
        self.cancel();self.editing=entry
        if entry:self.update_row(entry)
        parent=self.rows[entry['id']]['surface'].content if entry else self.inner
        if entry:self.rows[entry['id']]['surface'].selected=True
        editor=tk.Frame(parent,bg=PANEL);editor.pack(fill='x',padx=6,pady=6);self.editor=editor
        self.form={};error=tk.StringVar();warning=tk.StringVar()
        fields=tk.Frame(editor,bg=PANEL);fields.pack(fill='x')
        fields.grid_columnconfigure(0,weight=4);fields.grid_columnconfigure(1,weight=1)
        rows=(('Full name','name',entry['name'] if entry else '',0,0,1),('Respawn (optional)','duration',duration_text(entry.get('duration')) if entry else '',0,1,1),('Secondary Name / Alias (optional)','alias',entry.get('alias','') if entry else '',2,0,2))
        for label,key,value,row,col,span in rows:
            tk.Label(fields,text=label,bg=PANEL,fg=MUTED,font=('Segoe UI',9,'bold'),anchor='w').grid(row=row,column=col,columnspan=span,sticky='w',padx=3)
            var=tk.StringVar(value=value);self.form[key]=var
            RoundedEntry(fields,textvariable=var,width=10 if key=='duration' else 22,bg=BG,fg=TEXT,insertbackground=TEXT,font=('Segoe UI',10)).grid(row=row+1,column=col,columnspan=span,sticky='ew',padx=3,pady=(2,5))
        tk.Label(editor,text='Region',bg=PANEL,fg=MUTED,font=('Segoe UI',9,'bold'),anchor='w').pack(fill='x')
        self.region_var=tk.StringVar(value=entry.get('region',region_for(entry['name'])) if entry else REGIONS[-1])
        ttk.Combobox(editor,textvariable=self.region_var,values=REGIONS,state='readonly').pack(fill='x',pady=3)
        override=tk.BooleanVar(value=entry.get('alias_override',False) if entry else False);self.alias_override=override
        tk.Checkbutton(editor,text='Prefer this alias when names overlap',variable=override,bg=PANEL,fg=MUTED,activebackground=PANEL,activeforeground=TEXT,selectcolor=BG,font=('Segoe UI',9),anchor='w').pack(fill='x')
        warning_label=tk.Label(editor,textvariable=warning,bg=PANEL,fg='#f4ce80',wraplength=430,justify='left',font=('Segoe UI',9))
        warning_label.pack(fill='x')
        def warn(*args):
            candidate=dict(id=entry['id'] if entry else '',name=self.form['name'].get(),alias=self.form['alias'].get())
            warnings=alias_warnings(candidate,self.app.entries)
            warning.set('Shared alias. Saving is allowed; priority is optional.' if warnings else '')
            if warnings:warning_label.pack(fill='x',after=fields)
            else:warning_label.pack_forget()
        self.form['alias'].trace_add('write',warn);self.form['name'].trace_add('write',warn);warn()
        selected=[entry['color'] if entry else '#d4dbe5'];picker=[None]
        def preview(color):
            selected[0]=color
            if entry:
                self.preview_key=entry['id'];self.app.color_overrides[entry['id']]=color
                surface=self.rows[entry['id']]['surface'];surface.accent=color;surface.redraw();self.rows[entry['id']]['label'].configure(fg=color)
        def colors():
            if picker[0]:
                if picker[0].winfo_manager():picker[0].pack_forget()
                else:picker[0].pack(fill='x',before=actions,pady=5)
            else:
                picker[0]=InlineColorPicker(editor,self.app,selected[0],preview);picker[0].pack(fill='x',before=actions,pady=5)
                self.picker=picker[0];self.bind_wheel(picker[0]);self.app.style_panel(picker[0])
        self.app.button(editor,'Set a Color',colors).pack(anchor='w',pady=4)
        actions=tk.Frame(editor,bg=PANEL);actions.pack(fill='x',pady=5)
        def save():
            try:
                if picker[0] and picker[0].dirty and not picker[0].apply():raise ValueError(picker[0].error.get())
                name=self.form['name'].get().strip()
                if not name:raise ValueError('Enter the full name.')
                candidate=dict(id=entry['id'] if entry else uuid.uuid4().hex,name=name,alias=self.form['alias'].get().strip(),duration=input_duration(self.form['duration'].get()),color=selected[0],alias_override=override.get(),pinned=entry['pinned'] if entry else True,mechanic=entry.get('mechanic','standard') if entry else 'standard')
                candidate['region']=self.region_var.get()
                check_name_conflicts(candidate,self.app.entries)
                if entry:entry.update(candidate)
                else:self.app.entries.append(candidate);self.app.timers[candidate['id']]=BossTimer(candidate)
                self.cancel();self.app.changed();self.refresh()
            except ValueError as exc:error.set(str(exc))
        save_button=self.app.button(actions,'Save changes' if entry else 'Add boss',save);save_button.configure(bg='#1662b5');save_button.pack(side='right')
        self.app.button(actions,'Cancel',self.cancel).pack(side='right',padx=6)
        if entry and entry.get('mechanic')!='wukong':self.app.button(actions,'Set Timer',lambda:self.app.manual(entry['id'])).pack(side='left')
        if entry:
            armed=[False]
            def delete_tracker():
                if armed[0]:self.app.delete_boss(entry['id'])
                else:armed[0]=True;delete.configure(text='Confirm?')
            delete=self.app.button(actions,'Delete tracker',delete_tracker);delete.configure(bg='#602e3a',fg='#ffb2b8',min_width=125);delete.pack(side='left',padx=5)
        error_label=tk.Label(editor,textvariable=error,bg=PANEL,fg='#ff9999',wraplength=400,justify='left')
        error.trace_add('write',lambda *args:error_label.pack(fill='x') if error.get() else error_label.pack_forget())
        self.form_error=error;self.bind_wheel(editor);self.app.style_panel(editor)
        if entry:self.rows[entry['id']]['surface'].redraw()
        else:self.scroll_target=1
        self.queue_scroll()

    def open_save_preset(self):
        if self.preset_overlay and not self.preset_overlay.closed:self.preset_overlay.close();return
        from preset_ui import SavePresetPanel
        self.preset_overlay=SavePresetPanel(self.app,self.window,self.save_preset_button)
