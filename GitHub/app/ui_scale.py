"""One reference layout; all dimensions are physical pixels at 96 DPI and 100%."""
import math
HUD_WIDTH=900
HUD_HEIGHT=745
MIN_SCALE=.5
MAX_SCALE=1.


def bounded_scale(value):return max(MIN_SCALE,min(MAX_SCALE,float(value)))

def dimensions(scale,dpi=96):
    ratio=bounded_scale(scale)*dpi/96
    return round(HUD_WIDTH*ratio),round(HUD_HEIGHT*ratio)


def resize_scale(start_scale,start_width,start_height,dx,dy,edge):
    target_width=start_width+(-dx if 'w' in edge else dx)
    target_height=start_height+(-dy if 'n' in edge else dy)
    if len(edge)==2:factor=(target_width*start_width+target_height*start_height)/(start_width**2+start_height**2)
    elif edge in ('e','w'):factor=target_width/start_width
    else:factor=target_height/start_height
    return bounded_scale(start_scale*factor)


def style_tree(widget,factor):
    """Rescale existing widgets in place. Never recreate edits or filter results."""
    import tkinter as tk
    from tkinter import font as tkfont
    if getattr(widget,'_last_style_factor',None)==factor:
        for child in widget.winfo_children():
            if not isinstance(child,tk.Toplevel):style_tree(child,factor)
        return
    widget._last_style_factor=factor
    if not hasattr(widget,'_scale_original'):
        original={}
        try:
            definition=widget.cget('font');font=tkfont.Font(widget,font=definition);size=font.cget('size')
            parts=widget.tk.splitlist(definition)
            if len(parts)>1:
                try:size=int(parts[1])
                except (ValueError,TypeError):pass
            original['font']=(font.actual('family'),abs(size) if size<0 else size*96/72,font.actual('weight'))
        except tk.TclError:pass
        for option in ('wraplength','highlightthickness','borderwidth','padx','pady'):
            try:
                value=float(str(widget.cget(option)))
                if value:original[option]=value
            except (tk.TclError,ValueError,TypeError):pass
        if isinstance(widget,tk.Canvas) and type(widget).__name__ not in ('ActionButton','CardFrame','SlimScrollbar'):
            for option in ('width','height'):
                try:original[option]=float(str(widget.cget(option)))
                except (tk.TclError,ValueError):pass
        if isinstance(widget,tk.Frame):
            for option in ('width','height'):
                try:
                    value=float(str(widget.cget(option)))
                    if value>0:original[option]=value
                except (tk.TclError,ValueError):pass
        if widget.winfo_manager() in ('pack','grid'):
            info=widget.pack_info() if widget.winfo_manager()=='pack' else widget.grid_info()
            original['manager']=(widget.winfo_manager(),{k:tuple(float(str(v)) for v in (info[k] if isinstance(info[k],tuple) else str(info[k]).split())) for k in ('padx','pady','ipadx','ipady') if k in info})
        widget._scale_original=original
    original=widget._scale_original;widget._ui_factor=factor
    options={k:max(1,round(v*factor)) for k,v in original.items() if k not in ('font','manager')}
    if 'font' in original:
        family,size,weight=original['font'];options['font']=(family,-max(7,round(size*factor)),weight)
    if options:widget.configure(**options)
    if 'manager' in original and widget.winfo_manager()==original['manager'][0]:
        values={k:tuple(round(v*factor) for v in pair) for k,pair in original['manager'][1].items()}
        if original['manager'][0]=='pack':widget.pack_configure(**values)
        else:widget.grid_configure(**values)
    for child in widget.winfo_children():
        if not isinstance(child,tk.Toplevel):style_tree(child,factor)
    if type(widget).__name__ in ('ActionButton','CardFrame','SlimScrollbar','RoundedEntry'):widget.draw() if hasattr(widget,'draw') else widget.redraw()
    if type(widget).__name__=='InlineColorPicker':widget.render(False)
