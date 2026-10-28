"""Parent-owned floating preset panels. place() never changes parent layout."""
import tkinter as tk
from types import SimpleNamespace
from ui_theme import BG,PANEL,TEXT,MUTED,BORDER,ActionButton,RichLabel,RoundedEntry,SlimScrollbar
from PIL import Image,ImageDraw,ImageTk
import painting
from ui_scale import style_tree
from color_editor import InlineColorPicker

class OverlaySurface(tk.Canvas):
    """One painted border and a bounded content window, owned by the overlay."""
    def __init__(self,parent,factor):
        super().__init__(parent,bg=PANEL,highlightthickness=0)
        self._ui_factor=factor;self._surface_key=None
        self.surface=self.create_image(0,0,anchor='nw')
        self.content=tk.Frame(self,bg=PANEL)
        self.item=self.create_window(0,0,anchor='nw',window=self.content)
        self.bind('<Configure>',self.redraw)
    def redraw(self,event=None):
        width=max(1,self.winfo_width());height=max(1,self.winfo_height())
        pad=max(6,round(10*self._ui_factor))
        self.coords(self.item,pad,pad)
        self.itemconfigure(self.item,width=max(1,width-2*pad),height=max(1,height-2*pad))
        key=(width,height,0)
        if key!=self._surface_key:
            self._surface_key=key
            # Square outline matches the rectangular native backing exactly.
            # Use the same fill behind edge pixels so no dark corners show.
            self._image=ImageTk.PhotoImage(painting.surface(width,height,PANEL,PANEL,BORDER,key[2]),master=self)
            self.itemconfigure(self.surface,image=self._image)

class FloatingPanel:
    def __init__(self,parent,anchor,title,factor,width=290,above=False,on_close=None):
        self.parent=parent;self.anchor=anchor;self.factor=factor;self.base_width=width;self.above=above;self.on_close=on_close;self.pending=None;self.closed=False
        self.frame=OverlaySurface(parent,factor)
        self.frame.place(x=8,y=8,width=round(width*factor),height=100);self.frame.tk.call('raise',self.frame._w)
        self.header=None;self.title_icon=None
        if title:
            header=tk.Frame(self.frame.content,bg=PANEL);header.pack(fill='x',pady=(0,5));self.header=header
            self.title_icon=tk.Label(header,bg=PANEL);self.title_icon.pack(side='left',padx=(0,5))
            RichLabel(header,text=title,bg=PANEL,fg=TEXT,font=('Segoe UI',11,'bold'),anchor='w').pack(side='left',fill='x',expand=True)
            self.button(header,'×',self.close).pack(side='right')
        area=tk.Frame(self.frame.content,bg=PANEL);area.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(area,bg=PANEL,highlightthickness=0,height=30)
        self.scroll=SlimScrollbar(area,self.canvas.yview);self.scroll.configure(bg=PANEL)
        self.scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.body=tk.Frame(self.canvas,bg=PANEL)
        self.body_id=self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.body.bind('<Configure>',self.queue_position)
        self.canvas.bind('<Configure>',self.canvas_size)
        self.bind_id=parent.bind('<Configure>',self.parent_size,add='+')
        self.escape_id=parent.bind('<Escape>',lambda e:self.close(),add='+')
        self.click_id=parent.bind('<Button-1>',self.outside,add='+')
        self.frame.bind('<Destroy>',self.destroyed,add='+')
    def button(self,parent,text,command):return ActionButton(parent,text,command,('Segoe UI',10))
    def canvas_size(self,event):
        if self.closed:return
        self.canvas.itemconfigure(self.body_id,width=max(1,event.width))
    def parent_size(self,event):
        if event.widget==self.parent:
            factor=getattr(self.parent,'_window_scale',self.factor/1.5)*1.5
            if factor!=self.factor:self.factor=factor;self.finish()
            else:self.queue_position()
    def outside(self,event):
        widget=event.widget
        if widget==self.anchor:return
        while widget is not None:
            if widget==self.frame:return
            widget=getattr(widget,'master',None)
        self.close()
    def wheel(self,event):
        self.canvas.yview_scroll(-3 if event.delta>0 else 3,'units');return 'break'
    def finish(self):
        style_tree(self.frame,self.factor)
        if self.title_icon is not None:
            self._title_image=ImageTk.PhotoImage(painting.toolbar_icon('Save',round(17*self.factor),'#a8d6ff',PANEL),master=self.frame)
            self.title_icon.configure(image=self._title_image)
        def bind(widget):
            widget.bind('<MouseWheel>',self.wheel)
            for child in widget.winfo_children():bind(child)
        bind(self.frame);self.queue_position()
    def queue_position(self,event=None):
        if self.closed:return
        if self.pending:self.parent.after_cancel(self.pending)
        self.pending=self.parent.after_idle(self.position)
    def position(self):
        self.pending=None
        if self.closed or not self.parent.winfo_exists():return
        margin=max(6,round(8*self.factor));pw=max(1,self.parent.winfo_width());ph=max(1,self.parent.winfo_height())
        width=min(round(self.base_width*self.factor),max(1,pw-2*margin))
        pad=max(6,round(10*self.factor));body_height=max(1,self.body.winfo_reqheight())
        header=self.header.winfo_reqheight()+round(5*self.factor) if self.header is not None else 0
        height=min(body_height+header+2*pad,max(1,ph-2*margin))
        self.canvas.configure(height=max(1,height-header-2*pad),scrollregion=(0,0,max(1,self.canvas.winfo_width()),body_height),yscrollincrement=max(8,round(14*self.factor)))
        ax=self.anchor.winfo_rootx()-self.parent.winfo_rootx();ay=self.anchor.winfo_rooty()-self.parent.winfo_rooty()
        x=max(margin,min(ax,pw-width-margin))
        y=ay-height-margin if self.above else ay+self.anchor.winfo_height()+margin
        y=max(margin,min(y,ph-height-margin))
        self.frame.place_configure(x=x,y=y,width=width,height=height);self.frame.tk.call('raise',self.frame._w);self.frame.redraw()
    def destroyed(self,event):
        if event.widget==self.frame:self.cleanup()
    def cleanup(self):
        if self.closed:return
        self.closed=True
        if self.pending:self.parent.after_cancel(self.pending);self.pending=None
        for sequence,binding in (('<Configure>',self.bind_id),('<Escape>',self.escape_id),('<Button-1>',self.click_id)):
            try:self.parent.unbind(sequence,binding)
            except tk.TclError:pass
        if self.on_close:self.on_close()
    def close(self):
        self.cleanup()
        if self.frame.winfo_exists():self.frame.destroy()

class PresetDropdown(FloatingPanel):
    def __init__(self,app,anchor):
        super().__init__(app.root,anchor,None,app.scale*1.5)
        self.app=app;self.populate()
    def populate(self):
        for child in self.body.winfo_children():child.destroy()
        self.color_marks=[]
        presets=self.app.config.get('presets',[])
        if not presets:tk.Label(self.body,text='No presets saved yet.\nUse Save Preset in Index.',bg=PANEL,fg=MUTED,font=('Segoe UI',10),justify='left').pack(fill='x',pady=8)
        for preset in presets:
            row=tk.Frame(self.body,bg=PANEL);row.pack(fill='x',pady=3)
            marker=tk.Label(row,bg=PANEL,borderwidth=0,padx=0,pady=0);marker.pack(side='left',padx=(0,5))
            self.color_marks.append((marker,preset['color']))
            delete=self.button(row,'×',lambda key=preset['id']:self.delete(key));delete.configure(fg='#ff848c',bg='#4b2935');delete.pack(side='right',padx=(5,0))
            self.button(row,preset['name'],lambda key=preset['id']:self.select(key)).pack(side='left',fill='x',expand=True)
        self.error=tk.Label(self.body,text='',bg=PANEL,fg='#ff9999',font=('Segoe UI',9),wraplength=230,justify='left')
        self.finish()
    def finish(self):
        super().finish()
        # A real color swatch, not a tiny font bullet. Render sharply at the
        # active UI scale while retaining the existing row/button heights.
        size=max(10,round(16*self.factor));ss=4
        for marker,color in self.color_marks:
            image=Image.new('RGB',(size*ss,size*ss),PANEL)
            ImageDraw.Draw(image).ellipse((ss,ss,(size-1)*ss,(size-1)*ss),fill=color)
            marker._image=ImageTk.PhotoImage(image.resize((size,size),Image.Resampling.LANCZOS),master=marker)
            marker.configure(image=marker._image)
    def delete(self,key):
        self.app.delete_preset(key);self.populate()
    def select(self,key):
        try:self.app.apply_preset(key);self.close()
        except ValueError as exc:self.error.configure(text=str(exc));self.error.pack(fill='x');self.queue_position()

class SavePresetPanel(FloatingPanel):
    def __init__(self,app,parent,anchor):
        super().__init__(parent,anchor,'Save preset',parent._window_scale*1.5,width=350,above=True)
        self.app=app;self.name=tk.StringVar();self.color='#a987f5';self.picker=None
        fields=tk.Frame(self.body,bg=PANEL);fields.pack(fill='x')
        fields.grid_columnconfigure(0,weight=1)
        tk.Label(fields,text='Preset name',bg=PANEL,fg=MUTED,font=('Segoe UI',9,'bold'),anchor='w').grid(row=0,column=0,sticky='w',pady=(0,3))
        tk.Label(fields,text='Preset color',bg=PANEL,fg=MUTED,font=('Segoe UI',9,'bold'),anchor='w').grid(row=0,column=1,sticky='w',padx=(10,0),pady=(0,3))
        self.name_box=RoundedEntry(fields,textvariable=self.name,width=12,bg=BG,fg=TEXT,insertbackground=TEXT,font=('Segoe UI',10))
        self.name_box.grid(row=1,column=0,sticky='ew')
        self.color_row=tk.Frame(fields,bg=PANEL);self.color_row.grid(row=1,column=1,sticky='ew',padx=(10,0))
        self.swatch=self.button(self.color_row,'',self.colors);self.swatch.configure(bg=self.color,min_width=25);self.swatch.pack(side='left',padx=(0,5))
        self.button(self.color_row,'Set a Color',self.colors).pack(side='left')
        self.actions=tk.Frame(self.body,bg=PANEL);self.actions.pack(fill='x',pady=(8,0))
        save=self.button(self.actions,'Save',self.save);save.configure(bg='#1662b5');save.pack(side='left')
        self.button(self.actions,'Cancel',self.close).pack(side='left',padx=6)
        self.error=tk.Label(self.body,bg=PANEL,fg='#ff9999',font=('Segoe UI',9),wraplength=290,justify='left')
        self.finish();self.name_box.bind('<Return>',lambda e:self.save())
    def preview(self,color):self.color=color;self.swatch.configure(bg=color)
    def colors(self):
        if self.picker:
            if self.picker.winfo_manager():self.picker.pack_forget()
            else:self.picker.pack(fill='x',before=self.actions,pady=5)
        else:
            self.picker=InlineColorPicker(self.body,SimpleNamespace(button=self.button),self.color,self.preview)
            self.picker.pack(fill='x',before=self.actions,pady=5)
        self.finish()
    def save(self):
        try:
            if self.picker and self.picker.dirty and not self.picker.apply():raise ValueError(self.picker.error.get())
            self.app.save_preset(self.name.get(),self.color);self.close()
        except ValueError as exc:self.error.configure(text=str(exc));self.error.pack(fill='x');self.finish()
