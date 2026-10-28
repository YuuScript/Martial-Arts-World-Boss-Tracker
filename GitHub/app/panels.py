"""Remembered, bounded placement and edge resizing for editor panels."""
import tkinter as tk
import ctypes as c
from ctypes import wintypes as w
from ui_theme import BG,BORDER,TEXT,RichLabel
from window_style import decorate_window,edge_at,edge_cursor
from win_capture import custom_header,move_window,window_rectangle
from ui_scale import bounded_scale,resize_scale


def bounded_geometry(rect,area):
    x,y,width,height=map(int,rect);left,top,right,bottom=area
    width=min(width,right-left);height=min(height,bottom-top)
    return max(left,min(x,right-width)),max(top,min(y,bottom-height)),width,height


def work_area(x,y):
    class Info(c.Structure):_fields_=[('size',w.DWORD),('monitor',w.RECT),('work',w.RECT),('flags',w.DWORD)]
    u=c.windll.user32
    u.MonitorFromPoint.argtypes=[w.POINT,w.DWORD];u.MonitorFromPoint.restype=w.HANDLE
    u.GetMonitorInfoW.argtypes=[w.HANDLE,c.POINTER(Info)]
    info=Info();info.size=c.sizeof(info)
    if u.GetMonitorInfoW(u.MonitorFromPoint(w.POINT(int(x),int(y)),2),c.byref(info)):
        r=info.work;return r.left,r.top,r.right,r.bottom
    return 0,0,u.GetSystemMetrics(0),u.GetSystemMetrics(1)


def make_panel(app,title,width,height,key=None,resizable=False):
    key=key or title
    saved_scale=app.config.get('reference_windows',{}).get(key,{}).get('scale',app.scale)*96/app.dpi
    chosen=app.config.setdefault('panel_scales',{}).setdefault(key,saved_scale)
    ratio=float(chosen)*app.dpi/96
    win=tk.Toplevel(app.root);win.withdraw();win.overrideredirect(True)
    win.title(title);win.configure(bg=BG);win._window_scale=ratio
    decorate_window(win);win.attributes('-topmost',True);win.attributes('-alpha',app.config.get('ui_opacity',.95))
    base=window_rectangle(app.root);saved=app.config.setdefault('reference_windows',{}).get(key)
    if saved:
        desired=saved['rect'][:];old=saved.get('scale',ratio);desired[2]=round(desired[2]*ratio/old);desired[3]=round(desired[3]*ratio/old)
    else:desired=[base[0]+35,base[1]+35,round(width*1.5*ratio),round(height*1.5*ratio)]
    rect=bounded_geometry(desired,work_area(desired[0],desired[1]));win._reference_size=[rect[2]/ratio,rect[3]/ratio]
    win.geometry(f'{rect[2]}x{rect[3]}{rect[0]:+d}{rect[1]:+d}')
    def remember():
        if win.winfo_exists():
            actual=window_rectangle(win)
            if actual[2]>100 and actual[3]>100:
                app.config['reference_windows'][key]={'rect':list(actual),'scale':win._window_scale}
                win._reference_size=[actual[2]/win._window_scale,actual[3]/win._window_scale]
    def close():
        remember();app.persist()
        if hasattr(win,'on_close'):win.on_close()
        if getattr(win,'retain_on_close',False):win.withdraw()
        else:win.destroy()
    def apply_scale(value=None,persist=True):
        actual=window_rectangle(win);old=win._window_scale
        if value is not None:win._window_scale=bounded_scale(value)*app.dpi/96
        ratio=win._window_scale/old
        target=bounded_geometry((actual[0],actual[1],round(actual[2]*ratio),round(actual[3]*ratio)),work_area(actual[0],actual[1]))
        app.style_panel(win);win.geometry(f'{target[2]}x{target[3]}{target[0]:+d}{target[1]:+d}')
        win.native_frame.update_corner()
        if hasattr(win,'on_scale'):win.on_scale()
        if persist:
            app.config.setdefault('panel_scales',{})[key]=win._window_scale*96/app.dpi
            remember();app.persist()
    win.close_panel=close;win.remember_geometry=remember;win.apply_ui_scale=apply_scale
    win.set_scale=apply_scale
    win.protocol('WM_DELETE_WINDOW',close);win.bind('<Alt-F4>',lambda e:close())
    top=tk.Frame(win,bg=BG);top.pack(fill='x',padx=8,pady=7)
    label=RichLabel(top,text=title,bg=BG,fg=TEXT,font=('Segoe UI',13,'bold'),anchor='w');label.pack(side='left',padx=6)
    app.button(top,'×',close).pack(side='right',padx=3)
    drag={}
    def begin(e):
        if edge_at(win,e):return
        drag.update(x=e.x_root-window_rectangle(win)[0],y=e.y_root-window_rectangle(win)[1])
    def move(e):
        if drag:
            old=window_rectangle(win);x,y,_,_=bounded_geometry((e.x_root-drag['x'],e.y_root-drag['y'],old[2],old[3]),work_area(e.x_root,e.y_root));move_window(win,x,y)
    def end(e):remember();app.persist();drag.clear()
    for widget in (top,label):widget.bind('<Button-1>',begin);widget.bind('<B1-Motion>',move);widget.bind('<ButtonRelease-1>',end)
    if resizable:
        resize={};pending=[None];latest=[None]
        def begin_size(e,side):
            drag.clear();latest[0]=None
            resize.update(side=side,start=(e.x_root,e.y_root),rect=window_rectangle(win),scale=win._window_scale)
            win._resizing=True
        def apply_size():
            if pending[0] is not None:win.after_cancel(pending[0])
            pending[0]=None
            if not resize or not latest[0]:return
            ex,ey=latest[0];side=resize['side'];x,y,wide,high=resize['rect'];dx=ex-resize['start'][0];dy=ey-resize['start'][1]
            scale=resize['scale']
            if len(side)==2:
                new=round(resize_scale(scale*96/app.dpi,wide,high,dx,dy,side),2)*app.dpi/96
                nw=round(wide*new/scale);nh=round(high*new/scale)
                if new!=win._window_scale:
                    win._window_scale=new;app.style_panel(win)
                    if hasattr(win,'on_scale'):win.on_scale()
            else:
                nw=max(round(430*scale*1.5),wide+(-dx if 'w' in side else dx)) if any(t in side for t in 'ew') else wide
                nh=max(round(360*scale*1.5),high+(-dy if 'n' in side else dy)) if any(t in side for t in 'ns') else high
            nx=x+wide-nw if 'w' in side else x;ny=y+high-nh if 'n' in side else y
            nx,ny,nw,nh=bounded_geometry((nx,ny,nw,nh),work_area(nx,ny))
            if window_rectangle(win)!=(nx,ny,nw,nh):win.geometry(f'{nw}x{nh}{nx:+d}{ny:+d}')
        def size(e):
            latest[0]=(e.x_root,e.y_root)
            if pending[0] is None:pending[0]=win.after(16,apply_size)
        def end_size(e):
            if pending[0] is not None:win.after_cancel(pending[0]);pending[0]=None
            apply_size();resize.clear();win._resizing=False
            app.style_panel(win)
            for child in walk(win):
                if hasattr(child,'redraw'):child.redraw()
            app.config.setdefault('panel_scales',{})[key]=win._window_scale*96/app.dpi
            remember();app.persist()
        win._begin_resize=begin_size;win._resize_move=size;win._flush_resize=apply_size;win._end_resize=end_size
        win.bind('<Motion>',lambda e:win.configure(cursor=edge_cursor(edge_at(win,e))),add='+')
        win.bind('<ButtonPress-1>',lambda e:begin_size(e,edge_at(win,e)) if edge_at(win,e) else None,add='+')
        win.bind('<B1-Motion>',lambda e:size(e) if resize else None,add='+')
        win.bind('<ButtonRelease-1>',lambda e:end_size(e) if resize else None,add='+')
    app.children.append(win)
    return win


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)
