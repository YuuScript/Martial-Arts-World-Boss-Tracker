"""Shared glass-style drawing and rounded controls."""
import tkinter as tk
from PIL import ImageTk
from collections import OrderedDict
import painting
from tkinter import font as tkfont

BG=painting.BG
PANEL=painting.PANEL
TEXT=painting.TEXT
MUTED=painting.MUTED
BORDER=painting.BORDER
ACCENT='#9fcfff'


def blend(a,b,amount):
    x=[int(a[i:i+2],16) for i in (1,3,5)]
    y=[int(b[i:i+2],16) for i in (1,3,5)]
    return '#'+''.join(f'{round(u+(v-u)*amount):02x}' for u,v in zip(x,y))


def rounded(canvas,x1,y1,x2,y2,r=8,**options):
    r=max(0,min(r,(x2-x1)/2,(y2-y1)/2))
    points=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
    return canvas.create_polygon(points,smooth=True,splinesteps=20,**options)


def cached_image(canvas,image,key):
    if type(canvas).__name__=='CardFrame':
        # Rows with equal geometry share the same Tk image. Keep each row's
        # current image alive separately, so cache eviction never blanks it.
        root=canvas._root()
        if not hasattr(root,'_card_surface_cache'):root._card_surface_cache=OrderedDict();root._card_surface_pixels=0
        cache=root._card_surface_cache
        if key not in cache:
            pixels=image.width*image.height
            cache[key]=(ImageTk.PhotoImage(image,master=root),pixels);root._card_surface_pixels+=pixels
            while len(cache)>64 or (root._card_surface_pixels>8000000 and len(cache)>1):
                _,(_,old_pixels)=cache.popitem(last=False);root._card_surface_pixels-=old_pixels
        else:cache.move_to_end(key)
        return cache[key][0]
    if not hasattr(canvas,'_paint_cache'):canvas._paint_cache=OrderedDict()
    cache=canvas._paint_cache
    if key not in cache:
        cache[key]=ImageTk.PhotoImage(image,master=canvas)
        while len(cache)>(4 if type(canvas).__name__=='CardFrame' else 128):cache.popitem(last=False)
    else:cache.move_to_end(key)
    return cache[key]


def card(canvas,x1,y1,x2,y2,accent=None,flash=False):
    factor=getattr(canvas,'_ui_factor',1);border=painting.vibrant(accent) if flash and accent else '#435c6d'
    key=('card',round(x2-x1),round(y2-y1),border,round(12*factor))
    if getattr(canvas,'_fast_resize',False):
        rounded(canvas,x1,y1,x2,y2,key[4],fill=PANEL,outline=border);return
    bitmap=painting.surface(key[1],key[2],PANEL,BG,border,key[4])
    canvas.create_image(round(x1),round(y1),anchor='nw',image=cached_image(canvas,bitmap,key))


def rich_text(canvas,x,y,text,color,font,anchor='w',width=None,tag=''):
    # Native Tk/GDI font rasterization at integer physical-pixel sizes.
    options=dict(text=text,font=font,anchor=anchor,tags=tag,fill=color)
    if width:options['width']=round(width)
    item=canvas.create_text(round(x),round(y),**options)
    if not hasattr(canvas,'_text_items'):canvas._text_items={}
    canvas._text_items[item]=text
    return item


class RichLabel(tk.Label):
    """Compatibility name for a native, DPI-aware text label; never a bitmap."""
    def __init__(self,parent,**options):
        if 'fg' in options:options['fg']=painting.vibrant(options['fg'])
        super().__init__(parent,**options)
    def configure(self,cnf=None,**kwargs):
        if 'fg' in kwargs:kwargs['fg']=painting.vibrant(kwargs['fg'])
        return super().configure(cnf,**kwargs)
    config=configure
    def redraw(self):pass


class RoundedEntry(tk.Frame):
    def __init__(self,parent,**options):
        self.fill=options.pop('bg',BG)
        options.pop('highlightthickness',None);options.pop('highlightbackground',None);options.pop('relief',None)
        super().__init__(parent,bg=parent.cget('bg'))
        self.edge=tk.Canvas(self,bg=self.cget('bg'),highlightthickness=0);self.edge.place(x=0,y=0,relwidth=1,relheight=1)
        self.entry=tk.Entry(self,bg=self.fill,relief='flat',borderwidth=0,highlightthickness=0,**options)
        self.entry.pack(fill='x',expand=True,padx=9,pady=5)
        self._edge_key=None;self._edge_item=self.edge.create_image(0,0,anchor='nw')
        self.edge.bind('<Configure>',self.redraw)
    def redraw(self,event=None):
        width=event.width if event else self.edge.winfo_width();height=event.height if event else self.edge.winfo_height()
        if min(width,height)<2:return
        key=(width,height,max(3,round(7*getattr(self,'_ui_factor',1))),self.fill)
        if key==self._edge_key:return
        self._edge_key=key
        im=painting.surface(width,height,self.fill,self.fill,'#506c7d',key[2]).copy()
        # The border backing is fully painted; transparent pixels cannot expose
        # undefined child-window backing storage while the entry moves.
        from PIL import Image
        filled=Image.new('RGBA',im.size,self.cget('bg'));filled.alpha_composite(im)
        self._image=ImageTk.PhotoImage(filled,master=self);self.edge.itemconfigure(self._edge_item,image=self._image)
    def bind(self,sequence=None,func=None,add=None):
        if hasattr(self,'entry') and sequence in ('<Return>','<Escape>'):return self.entry.bind(sequence,func,add)
        return super().bind(sequence,func,add)
    def get(self):return self.entry.get()
    def focus_set(self):return self.entry.focus_set()


class SlimScrollbar(tk.Canvas):
    def __init__(self,parent,command,**options):
        super().__init__(parent,width=12,bg=BG,highlightthickness=0,cursor='hand2')
        self.command=command;self.first=0.;self.last=1.;self.drag=None
        self.bind('<Configure>',self.draw);self.bind('<Button-1>',self.press);self.bind('<B1-Motion>',self.motion);self.bind('<ButtonRelease-1>',lambda e:setattr(self,'drag',None));self.bind('<MouseWheel>',lambda e:self.command('scroll',-3 if e.delta>0 else 3,'units'))
    def set(self,first,last):
        pair=(float(first),float(last))
        if pair!=(self.first,self.last):self.first,self.last=pair;self.draw()
    def positions(self):
        factor=getattr(self,'_ui_factor',1);height=max(20,self.winfo_height()-6);thumb=min(height,max(24*factor,height*(self.last-self.first)))
        start=3+(height-thumb)*self.first/max(.00001,1-(self.last-self.first)) if self.last-self.first<1 else 3
        return height,thumb,start
    def draw(self,event=None):
        self.delete('all');height,thumb,start=self.positions();wide=max(8,self.winfo_width())
        if self.last-self.first>=.999:return
        rounded(self,2,3,wide-2,height+3,3,fill='#122330',outline='#3e5566')
        rounded(self,2,start,wide-2,start+thumb,3,fill='#7796ad',outline='#829fb2')
    def press(self,event):
        height,thumb,start=self.positions()
        self.drag=event.y-start if start<=event.y<=start+thumb else thumb/2
        self.motion(event)
    def motion(self,event):
        if self.drag is None:return
        height,thumb,start=self.positions()
        fraction=max(0,min(1,(event.y-3-self.drag)/max(1,height-thumb)))*(1-(self.last-self.first))
        self.command('moveto',fraction)


class ActionButton(tk.Canvas):
    """Rounded, keyboard-accessible button with the same invoke API as Tk buttons."""
    def __init__(self,parent,text,command,font):
        self.options=dict(text=text,font=font,fg=TEXT,bg='#25394e',min_width=0)
        self.command=command;self.hover=False
        super().__init__(parent,bg=parent.cget('bg'),highlightthickness=0,takefocus=True,cursor='hand2')
        self.bind('<Enter>',lambda event:self.set_hover(True))
        self.bind('<Leave>',lambda event:self.set_hover(False))
        self.bind('<ButtonRelease-1>',lambda event:self.invoke() if 0<=event.x<self.winfo_width() and 0<=event.y<self.winfo_height() else None)
        self.bind('<Return>',lambda event:self.invoke())
        self.bind('<space>',lambda event:self.invoke())
        self.bind('<FocusIn>',lambda event:self.set_hover(True))
        self.bind('<FocusOut>',lambda event:self.set_hover(False))
        self.draw()
    def set_hover(self,value):
        if value!=self.hover:self.hover=value;self.draw()
    def invoke(self):return self.command()
    def cget(self,key):
        if key in self.options:return self.options[key]
        return super().cget(key)
    def configure(self,cnf=None,**kwargs):
        if cnf:kwargs.update(cnf)
        changed=False
        for key in tuple(kwargs):
            if key in self.options:
                value=kwargs.pop(key);changed=changed or self.options[key]!=value;self.options[key]=value
        result=super().configure(**kwargs) if kwargs else None
        if hasattr(self,'options') and changed:self.draw()
        return result
    config=configure
    def draw(self):
        font_definition=self.options['font']
        if getattr(self,'_font_definition',None)!=font_definition:
            self._font_definition=font_definition;self._measure=tkfont.Font(self,font=font_definition)
        font=self._measure;factor=getattr(self,'_ui_factor',1);label=self.options['text']
        icon_name=getattr(self,'icon_name',None) or (label if label in ('Lock','Index','Reset') else None)
        icon=round(22*factor) if icon_name else 0;gap=round(10*factor) if icon else 0
        text_width=font.measure(label);width=max(round(self.options['min_width']*factor),text_width+round(22*factor)+icon+gap);height=font.metrics('linespace')+round(12*factor)
        square=getattr(self,'square',False)
        if square:width=height
        super().configure(width=width,height=height)
        key=(label,self.options['bg'],self.options['fg'],str(font_definition),factor,self.hover,width,height,getattr(self,'smooth_icon',False),icon_name,square)
        if getattr(self,'_draw_key',None)==key:return
        self._draw_key=key
        bg=self.options['bg'];fg=self.options['fg']
        bitmap=painting.surface(width,height,painting.mix(bg,'#ffffff',.12 if self.hover else .05),bg,BORDER,max(1,round(2*factor)) if square else max(4,round(8*factor)))
        self._image=ImageTk.PhotoImage(bitmap,master=self)
        self.delete('all');self.create_image(0,0,anchor='nw',image=self._image)
        group=text_width+icon+gap;left=round((width-group)/2)
        if icon and (getattr(self,'smooth_icon',False) or icon_name=='Save'):
            bitmap=painting.toolbar_icon(icon_name,icon,fg,bg)
            self._icon_image=ImageTk.PhotoImage(bitmap,master=self)
            self.create_image(left,round((height-icon)/2),anchor='nw',image=self._icon_image)
        else:
            if icon:
                x=left;y=round((height-icon)/2);unit=icon/24;stroke=max(1,round(2*factor))
                if label=='Lock':
                    self.create_arc(x+6*unit,y+unit,x+18*unit,y+17*unit,start=0,extent=180,style='arc',outline=fg,width=stroke)
                    rounded(self,x+4*unit,y+10*unit,x+20*unit,y+23*unit,2*factor,fill=fg,outline='')
                    self.create_oval(x+11*unit,y+14*unit,x+13*unit,y+17*unit,fill=bg,outline='')
                elif label=='Index':
                    for row in (5,12,19):
                        self.create_oval(x+2*unit,y+(row-1)*unit,x+4*unit,y+(row+1)*unit,fill=fg,outline='')
                        self.create_line(x+8*unit,y+row*unit,x+22*unit,y+row*unit,fill=fg,width=stroke)
                else:
                    self.create_arc(x+3*unit,y+3*unit,x+21*unit,y+21*unit,start=40,extent=280,style='arc',outline=fg,width=stroke)
                    self.create_line(x+20*unit,y+unit,x+20*unit,y+8*unit,x+13*unit,y+8*unit,fill=fg,width=stroke)
        self.create_text(left+icon+gap+text_width/2,height/2,text=label,font=font_definition,fill=fg,anchor='center')


class CardFrame(tk.Canvas):
    def __init__(self,parent,accent=None,selected=False):
        super().__init__(parent,bg=BG,highlightthickness=0,height=64)
        self.accent=accent; self.selected=selected
        self.content=tk.Frame(self,bg=PANEL)
        self.item=self.create_window(9,6,anchor='nw',window=self.content)
        self._surface_key=None
        self._surface_item=self.create_image(0,0,anchor='nw',tags='surface')
        self.tag_lower('surface')
        self.bind('<Configure>',self.redraw)
        self.content.bind('<Configure>',self.fit)
    def fit(self,event=None):
        height=self.content.winfo_reqheight()+round(12*getattr(self,'_ui_factor',1))
        if int(self.cget('height'))!=height: self.configure(height=height)
    def redraw(self,event=None):
        w=max(40,self.winfo_width());h=max(30,self.winfo_height())
        factor=getattr(self,'_ui_factor',1);pad=round(9*factor)
        fast=getattr(self.winfo_toplevel(),'_resizing',False)
        layout_key=(w,h,factor,self.accent,self.selected,fast)
        if getattr(self,'_redraw_key',None)==layout_key:return
        self._redraw_key=layout_key
        inset=max(1,round(3*factor));border=painting.vibrant(self.accent) if self.selected and self.accent else '#435c6d'
        key=(w-2*inset,h-2*inset,border,max(3,round(12*factor)))
        self.delete('drag-surface')
        if fast:
            self.itemconfigure(self._surface_item,state='hidden')
            item=rounded(self,inset,inset,w-inset,h-inset,key[3],fill=PANEL,outline=border,tags='drag-surface')
            self.tag_lower(item)
        else:self.itemconfigure(self._surface_item,state='normal')
        if not fast and key!=self._surface_key:
            self._surface_key=key
            bitmap=painting.surface(key[0],key[1],PANEL,BG,key[2],key[3])
            self._surface_image=cached_image(self,bitmap,key)
            self.coords(self._surface_item,inset,inset)
            self.itemconfigure(self._surface_item,image=self._surface_image)
        self.coords(self.item,pad,round(6*factor));self.itemconfigure(self.item,width=max(20,w-2*pad))
