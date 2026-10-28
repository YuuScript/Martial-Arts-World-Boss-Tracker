"""One native owner for outer borders, clipping and resize invalidation.

Windows 11 DWM draws and clips the rounded frame. No app-owned window regions,
transparent corner pixels, or competing border canvas are installed.
"""
import ctypes as c
from ctypes import wintypes as w
from win_capture import window_rectangle,hwnd_for

u=c.windll.user32
dwm=c.windll.dwmapi
comctl=c.windll.comctl32
SUBCLASSPROC=c.WINFUNCTYPE(c.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM,c.c_size_t,c.c_size_t)
comctl.SetWindowSubclass.argtypes=[w.HWND,SUBCLASSPROC,c.c_size_t,c.c_size_t]
comctl.SetWindowSubclass.restype=w.BOOL
comctl.RemoveWindowSubclass.argtypes=[w.HWND,SUBCLASSPROC,c.c_size_t]
comctl.DefSubclassProc.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
comctl.DefSubclassProc.restype=c.c_ssize_t
dwm.DwmSetWindowAttribute.argtypes=[w.HWND,w.DWORD,c.c_void_p,w.DWORD]
dwm.DwmSetWindowAttribute.restype=c.c_long
u.SetWindowPos.argtypes=[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT]
u.RedrawWindow.argtypes=[w.HWND,c.c_void_p,w.HANDLE,w.UINT]


def edge_at(win,event):
    x,y,width,height=window_rectangle(win);px=event.x_root-x;py=event.y_root-y
    corner=max(7,round(12*getattr(win,'_window_scale',1)))
    if (px<corner or px>=width-corner) and (py<corner or py>=height-corner):return ('n' if py<corner else 's')+('w' if px<corner else 'e')
    return ('n' if py<5 else 's' if py>=height-5 else '')+('w' if px<5 else 'e' if px>=width-5 else '')


def edge_cursor(side):return 'size_nw_se' if side in ('nw','se') else 'size_ne_sw' if side in ('ne','sw') else 'sb_h_double_arrow' if side in ('w','e') else 'sb_v_double_arrow' if side else ''


class NativeFrame:
    def __init__(self,win):
        self.win=win;self.hwnd=None;self.pending=None;self.last_geometry=None;self.corner=None
        self.paint_requests=0;self.paint_flushes=0;self.region_updates=0;self.attributes={};self.callback=SUBCLASSPROC(self.dispatch)
        win.bind('<Configure>',self.configure,add='+');win.bind('<Destroy>',self.destroy,add='+')
    def dispatch(self,hwnd,message,wparam,lparam,subclass_id,reference):
        if message==0x0083 and wparam: # WM_NCCALCSIZE: custom title area, native DWM edge.
            return 0
        if message==0x0082: # WM_NCDESTROY: release subclass before native destruction.
            comctl.RemoveWindowSubclass(hwnd,self.callback,1)
        return comctl.DefSubclassProc(hwnd,message,wparam,lparam)
    def attribute(self,key,value):
        if self.attributes.get(key)==value:return
        data=c.c_int(value)
        result=dwm.DwmSetWindowAttribute(self.hwnd,key,c.byref(data),c.sizeof(data))
        if result==0:self.attributes[key]=value
        return result
    def install(self):
        hwnd=hwnd_for(self.win)
        if not hwnd:return
        if self.hwnd!=hwnd:
            self.hwnd=hwnd;self.attributes.clear()
            if not comctl.SetWindowSubclass(hwnd,self.callback,1,0):raise OSError('Could not attach the tracker window frame.')
        style=u.GetWindowLongW(hwnd,-16);desired=style|0x00C00000|0x00040000|0x02000000
        ex=u.GetWindowLongW(hwnd,-20);desired_ex=(ex|0x00040000)&~0x00000080&~0x08000000
        changed=style!=desired or ex!=desired_ex
        if changed:
            u.SetWindowLongW(hwnd,-16,desired);u.SetWindowLongW(hwnd,-20,desired_ex)
            u.SetWindowPos(hwnd,None,0,0,0,0,0x0020|0x0001|0x0002|0x0004|0x0010)
        self.attribute(2,2) # DWMNCRP_ENABLED.
        self.attribute(20,1) # Dark frame.
        self.attribute(34,0x00836b52) # One system-drawn outline, COLORREF.
        self.attribute(35,0x002a1e10) # Dark custom title area.
        self.update_corner();self.queue_paint()
    def update_corner(self):
        if self.hwnd:self.attribute(33,3 if getattr(self.win,'_window_scale',1)<=.6 else 2)
    def configure(self,event):
        if event.widget!=self.win:return
        geometry=(event.width,event.height,round(getattr(self.win,'_window_scale',1),3))
        if geometry==self.last_geometry:return
        self.last_geometry=geometry;self.update_corner();self.queue_paint()
    def queue_paint(self):
        self.paint_requests+=1
        if self.pending is None:self.pending=self.win.after_idle(self.flush)
    def flush(self):
        self.pending=None
        if not self.hwnd or not self.win.winfo_exists():return
        # Queue painting after Tk's layout pass. No synchronous recursive paint,
        # no erase pass or recursive child invalidation. Tk owns child painting;
        # Windows owns only the outer frame. No native-region replacement.
        u.RedrawWindow(self.hwnd,None,None,0x0001|0x0040|0x0400)
        self.paint_flushes+=1
    def destroy(self,event):
        if event.widget!=self.win:return
        if self.pending:
            self.win.after_cancel(self.pending);self.pending=None
        if self.hwnd:comctl.RemoveWindowSubclass(self.hwnd,self.callback,1)


def decorate_window(win):
    if not hasattr(win,'native_frame'):win.native_frame=NativeFrame(win)
    return win.native_frame
