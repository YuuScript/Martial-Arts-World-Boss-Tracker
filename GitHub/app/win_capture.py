"""Windows capture helpers. No game memory or injected scripts."""
import ctypes as c
from ctypes import wintypes as w

u = c.windll.user32
k = c.windll.kernel32
u.GetAsyncKeyState.argtypes = [c.c_int]
u.GetAsyncKeyState.restype = c.c_short
u.GetForegroundWindow.restype = w.HWND
u.GetAncestor.argtypes = [w.HWND, w.UINT]
u.GetAncestor.restype = w.HWND
u.GetWindowLongW.argtypes = [w.HWND, c.c_int]
u.SetWindowLongW.argtypes = [w.HWND, c.c_int, c.c_long]
u.SetWindowDisplayAffinity.argtypes = [w.HWND, w.DWORD]
u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
u.IsWindowVisible.argtypes = [w.HWND]
u.IsIconic.argtypes = [w.HWND]
u.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
u.ClientToScreen.argtypes = [w.HWND, c.POINTER(w.POINT)]
u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
u.EnumWindows.argtypes = [c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM), w.LPARAM]


def game_window():
    found = []
    @c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(hwnd, unused):
        title = c.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, title, 256)
        if title.value.strip().lower() == 'roblox' and u.IsWindowVisible(hwnd) and not u.IsIconic(hwnd):
            rect, point = w.RECT(), w.POINT(0, 0)
            if u.GetClientRect(hwnd, c.byref(rect)) and u.ClientToScreen(hwnd, c.byref(point)) and rect.right > 100 and rect.bottom > 100:
                found.append((hwnd, dict(left=point.x, top=point.y, width=rect.right, height=rect.bottom)))
        return True
    u.EnumWindows(visit, 0)
    if not found:
        return None
    foreground = u.GetForegroundWindow()
    # Monitoring is active only when the game itself has foreground focus.
    return next((region for hwnd,region in found if hwnd==foreground),None)


def roblox_window_exists():
    """Presence is independent of foreground focus and minimization."""
    found = []
    @c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(hwnd, unused):
        title = c.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, title, 256)
        if title.value.strip().lower() == 'roblox':
            found.append(hwnd)
        return True
    u.EnumWindows(visit, 0)
    return bool(found)


def hwnd_for(root):
    return u.GetAncestor(root.winfo_id(), 2)


def allow_capture(root):
    # Normal screenshots must include the HUD; the scanner masks its own pixels.
    return bool(u.SetWindowDisplayAffinity(hwnd_for(root), 0))


def click_through(root, enabled):
    hwnd = hwnd_for(root)
    flags = u.GetWindowLongW(hwnd, -20)
    flags = flags | 0x20 | 0x80000 if enabled else flags & ~0x20
    u.SetWindowLongW(hwnd, -20, flags)
    return bool(u.GetWindowLongW(hwnd, -20) & 0x20) == bool(enabled)


class Hotkey:
    """Poll just this shortcut; Tk cannot consume it from a Windows message queue."""
    def __init__(self, key_state=None):
        self.key_state = key_state or u.GetAsyncKeyState
        self.was_down = False

    def pressed(self):
        down = all(self.key_state(key) & 0x8000 for key in (0x11, 0x12, ord('T')))
        fired = down and not self.was_down
        self.was_down = down
        return fired

    def close(self):
        self.was_down = False


def dark_titlebar(root):
    try:
        value = c.c_int(1)
        dwm = c.windll.dwmapi.DwmSetWindowAttribute
        dwm.argtypes = [w.HWND, w.DWORD, c.c_void_p, w.DWORD]
        dwm(hwnd_for(root), 20, c.byref(value), c.sizeof(value))
    except (AttributeError, OSError):
        pass


def repaint(root):
    """Schedule one paint after layout; do not synchronously repaint children."""
    if hasattr(root,'native_frame'):root.native_frame.queue_paint();return
    u.RedrawWindow.argtypes=[w.HWND,c.c_void_p,w.HANDLE,w.UINT]
    u.RedrawWindow(hwnd_for(root),None,None,0x0001|0x0080)


def custom_header(root):
    """Keep native DWM border/corners while the app owns its title content."""
    if hasattr(root,'native_frame'):root.native_frame.install()
    else:
        hwnd=hwnd_for(root);ex=u.GetWindowLongW(hwnd,-20)
        u.SetWindowLongW(hwnd,-20,(ex|0x00040000)&~0x00000080&~0x08000000)
    allow_capture(root)


def move_window(root,x,y):
    """Move without discarding the compositor's valid client pixels."""
    u.SetWindowPos.argtypes=[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT]
    u.SetWindowPos(hwnd_for(root),None,int(x),int(y),0,0,0x0001|0x0004|0x0010)


def window_rectangle(root):
    rect=w.RECT()
    u.GetWindowRect.argtypes=[w.HWND,c.POINTER(w.RECT)]
    u.GetWindowRect(hwnd_for(root),c.byref(rect))
    return (rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)
