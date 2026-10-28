"""Compact inline color editor. Draft changes never overwrite a saved entry."""
import colorsys,re
import numpy as np
import tkinter as tk
from PIL import Image,ImageDraw,ImageTk
from ui_theme import BG,PANEL,TEXT,MUTED,BORDER,RoundedEntry


class InlineColorPicker(tk.Frame):
    def __init__(self,parent,app,initial,preview):
        super().__init__(parent,bg=PANEL)
        self.preview=preview;self.app=app;self.h,self.s,self.v=colorsys.rgb_to_hsv(*[int(initial[i:i+2],16)/255 for i in (1,3,5)])
        self.hex=tk.StringVar();self.rgb=tk.StringVar();self.error=tk.StringVar();self.updating=False;self.dirty=None
        self.square=tk.Canvas(self,width=220,height=64,bg=PANEL,highlightthickness=0);self.square.grid(row=0,column=0,sticky='w',padx=3,pady=3)
        self.swatch=tk.Label(self,bg=PANEL);self.swatch.grid(row=0,column=1,padx=8)
        self.hue=tk.Canvas(self,width=220,height=20,bg=PANEL,highlightthickness=0);self.hue.grid(row=1,column=0,padx=3)
        fields=tk.Frame(self,bg=PANEL);fields.grid(row=2,column=0,columnspan=2,sticky='ew',pady=5)
        for i,(title,var) in enumerate((('HEX',self.hex),('RGB',self.rgb))):
            tk.Label(fields,text=title,bg=PANEL,fg=MUTED,font=('Segoe UI',9,'bold')).grid(row=0,column=i,sticky='w')
            box=RoundedEntry(fields,textvariable=var,width=14,bg=BG,fg=TEXT,insertbackground=TEXT,relief='flat',highlightthickness=1,highlightbackground=BORDER)
            box.grid(row=1,column=i,sticky='ew',padx=(0,7));box.bind('<Return>',lambda e:self.apply())
            fields.grid_columnconfigure(i,weight=1)
        self.app.button(fields,'Apply color',self.apply).grid(row=1,column=2)
        self.error_label=tk.Label(self,textvariable=self.error,bg=PANEL,fg='#ffaaa9',font=('Segoe UI',9),wraplength=330)
        self.error.trace_add('write',lambda *args:self.error_label.grid(row=3,column=0,columnspan=2,sticky='w') if self.error.get() else self.error_label.grid_remove())
        self.square.bind('<Button-1>',self.pick_sv);self.square.bind('<B1-Motion>',self.pick_sv)
        self.hue.bind('<Button-1>',self.pick_hue);self.hue.bind('<B1-Motion>',self.pick_hue)
        self.hex.trace_add('write',lambda *a:self.mark('hex'));self.rgb.trace_add('write',lambda *a:self.mark('rgb'))
        self.render(False)
    def mark(self,field):
        if not self.updating:self.dirty=field
    def color(self):return '#'+''.join(f'{round(c*255):02X}' for c in colorsys.hsv_to_rgb(self.h,self.s,self.v))
    def render(self,notify=True):
        # Render handles and swatch at 3x resolution then downsample for smooth edges.
        size=3;factor=getattr(self,'_ui_factor',1);w,h=max(20,round(220*factor)),max(16,round(64*factor));strip_height=max(10,round(20*factor));swatch_size=max(20,round(48*factor))
        base=np.array(colorsys.hsv_to_rgb(self.h,1,1),dtype=np.float32)
        saturation=np.linspace(0,1,w)[None,:,None];value=np.linspace(1,0,h)[:,None,None]
        pixels=np.uint8(np.clip(((1-saturation)+saturation*base)*value*255,0,255))
        im=Image.fromarray(pixels).resize((w*size,h*size),Image.Resampling.BICUBIC);draw=ImageDraw.Draw(im)
        x=self.s*(w-1)*size;y=(1-self.v)*(h-1)*size;r=max(3,round(5*factor))*size
        draw.ellipse((x-r,y-r,x+r,y+r),outline='black',width=3*size);draw.ellipse((x-r+size,y-r+size,x+r-size,y+r-size),outline='white',width=size)
        self.square_image=ImageTk.PhotoImage(im.resize((w,h),Image.Resampling.LANCZOS),master=self)
        self.square.delete('all');self.square.create_image(0,0,anchor='nw',image=self.square_image)
        strip=Image.new('RGB',(w*size,strip_height*size),PANEL);draw=ImageDraw.Draw(strip)
        for x in range(w*size):
            color=tuple(round(c*255) for c in colorsys.hsv_to_rgb(x/(w*size-1),1,1));draw.line((x,round(6*factor)*size,x,round(14*factor)*size),fill=color)
        x=self.h*(w-1)*size;draw.ellipse((x-round(5*factor)*size,round(4*factor)*size,x+round(5*factor)*size,round(16*factor)*size),outline='white',width=size)
        self.hue_image=ImageTk.PhotoImage(strip.resize((w,strip_height),Image.Resampling.LANCZOS),master=self)
        self.hue.delete('all');self.hue.create_image(0,0,anchor='nw',image=self.hue_image)
        sw=Image.new('RGB',(swatch_size*3,swatch_size*3),PANEL);ImageDraw.Draw(sw).ellipse((8,8,swatch_size*3-8,swatch_size*3-8),fill=self.color(),outline=BORDER,width=3)
        self.swatch_image=ImageTk.PhotoImage(sw.resize((swatch_size,swatch_size),Image.Resampling.LANCZOS),master=self);self.swatch.configure(image=self.swatch_image)
        self.updating=True;self.hex.set(self.color());self.rgb.set(', '.join(str(int(self.color()[i:i+2],16)) for i in (1,3,5)));self.updating=False;self.dirty=None;self.error.set('')
        if notify:self.preview(self.color())
    def pick_sv(self,e):self.s=max(0,min(1,e.x/max(1,round(220*getattr(self,'_ui_factor',1))-1)));self.v=1-max(0,min(1,e.y/max(1,round(64*getattr(self,'_ui_factor',1))-1)));self.render()
    def pick_hue(self,e):self.h=max(0,min(1,e.x/max(1,round(220*getattr(self,'_ui_factor',1))-1)));self.render()
    def apply(self):
        try:
            if self.dirty=='hex':
                text=self.hex.get().strip()
                if not re.fullmatch(r'#[0-9a-fA-F]{6}',text):raise ValueError('Use HEX like #69A7FF.')
                values=[int(text[i:i+2],16) for i in (1,3,5)]
            elif self.dirty=='rgb':
                values=[int(v.strip()) for v in self.rgb.get().split(',')]
                if len(values)!=3 or any(v<0 or v>255 for v in values):raise ValueError('Use three RGB values from 0 to 255.')
            else:self.preview(self.color());return True
            self.h,self.s,self.v=colorsys.rgb_to_hsv(*(v/255 for v in values));self.render();return True
        except ValueError as exc:self.error.set(str(exc));return False
