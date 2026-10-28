"""Shared, cached raster styling for live widgets and offline visual verification."""
import colorsys, functools, math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

BG='#101e2a';PANEL='#172a38';TEXT='#f5f9ff';MUTED='#bdd1e5';BORDER='#526f83'

def rgb(color):return tuple(int(color[i:i+2],16) for i in (1,3,5))
def mix(a,b,t):return '#'+''.join(f'{round(x+(y-x)*t):02x}' for x,y in zip(rgb(a),rgb(b)))
def vibrant(color):
    h,l,s=colorsys.rgb_to_hls(*(v/255 for v in rgb(color)))
    return '#'+''.join(f'{round(v*255):02x}' for v in colorsys.hls_to_rgb(h,max(.64,l),s))

@functools.lru_cache(maxsize=96)
def face(points=10,bold=False,dpi=96):
    return ImageFont.truetype(str(Path('C:/Windows/Fonts')/('segoeuib.ttf' if bold else 'segoeui.ttf')),max(7,round(abs(points) if points<0 else points*dpi/72)))

def lines_for(text,font,width):
    if not width:return text.split('\n')
    output=[]
    for paragraph in text.split('\n'):
        current=''
        for word in paragraph.split():
            trial=(current+' '+word).strip()
            if current and font.getlength(trial)>width:output.append(current);current=word
            else:current=trial
            while font.getlength(current)>width and len(current)>1:
                cut=len(current)-1
                while cut>1 and font.getlength(current[:cut])>width:cut-=1
                output.append(current[:cut]);current=current[cut:]
        output.append(current)
    return output

@functools.lru_cache(maxsize=256)
def text_height(text,points,bold,width,dpi=96):
    font=face(points,bold,dpi);lines=lines_for(text,font,width)
    return sum(font.getmetrics())*(len(lines)-1)+max((font.getbbox(line or 'Ag',anchor='lt')[3] for line in lines),default=0)+4

@functools.lru_cache(maxsize=256)
def text_image(text,color,points=10,bold=False,width=0,dpi=96,gradient=True):
    font=face(points,bold,dpi);lines=lines_for(text,font,width)
    line_height=sum(font.getmetrics());wide=max(1,math.ceil(max((font.getlength(line) for line in lines),default=0))+2)
    glyph_height=max((font.getbbox(line or 'Ag',anchor='lt')[3] for line in lines),default=line_height)
    high=max(1,line_height*(len(lines)-1)+glyph_height+2);ss=3
    big_font=face(-font.size*ss,bold,dpi)
    mask=Image.new('L',(wide*ss,high*ss));draw=ImageDraw.Draw(mask)
    for i,line in enumerate(lines):draw.text((0,i*line_height*ss),line,font=big_font,fill=255,anchor='lt')
    ink=Image.new('RGBA',mask.size,color)
    if gradient:
        ramp=Image.linear_gradient('L').resize(mask.size)
        ink=Image.composite(Image.new('RGBA',mask.size,color),Image.new('RGBA',mask.size,mix(color,'#ffffff',.10)),ramp)
    ink.putalpha(mask)
    result=Image.new('RGBA',((wide+2)*ss,(high+2)*ss))
    result.paste((0,0,0,105),(ss,ss,wide*ss+ss,high*ss+ss),mask)
    result.alpha_composite(ink,(0,0))
    return result.resize((wide+2,high+2),Image.Resampling.LANCZOS)

@functools.lru_cache(maxsize=32)
def surface(width,height,top=PANEL,bottom=BG,border=BORDER,radius=10):
    width=max(2,int(width));height=max(2,int(height));scale=2
    size=(width*scale,height*scale)
    ramp=Image.linear_gradient('L').resize(size)
    im=Image.composite(Image.new('RGBA',size,bottom),Image.new('RGBA',size,top),ramp)
    mask=Image.new('L',im.size);ImageDraw.Draw(mask).rounded_rectangle((1,1,width*scale-2,height*scale-2),radius=radius*scale,fill=255)
    im.putalpha(mask)
    if border:ImageDraw.Draw(im).rounded_rectangle((1,1,width*scale-2,height*scale-2),radius=radius*scale,outline=border,width=scale)
    return im.resize((width,height),Image.Resampling.LANCZOS)


@functools.lru_cache(maxsize=256)
def button_image(text,color,fg,points,bold,width,height,dpi=96,hover=False,factor=1):
    im=surface(width,height,mix(color,'#ffffff',.12 if hover else .05),color,mix(BORDER,fg,.15) if hover else BORDER,max(4,round(8*factor))).copy()
    label=text_image(text,fg,points,bold,0,dpi,True)
    icon_kind={'Lock':'lock','Index':'list','Reset':'reset'}.get(text)
    icon_size=max(10,round(22*factor)) if icon_kind else 0;gap=round(10*factor) if icon_kind else 0
    group_width=label.width+icon_size+gap;x=round((width-group_width)/2)
    if icon_kind:
        ss=3;layer=Image.new('RGBA',(icon_size*ss,icon_size*ss));d=ImageDraw.Draw(layer);u=icon_size*ss/24;stroke=max(2,round(2*u))
        if icon_kind=='lock':
            d.arc((6*u,1*u,18*u,17*u),180,360,fill=fg,width=stroke)
            d.rounded_rectangle((4*u,10*u,20*u,23*u),radius=2*u,fill=fg);d.ellipse((11*u,14*u,13*u,17*u),fill=color)
        elif icon_kind=='list':
            for y in (5,12,19):
                d.ellipse((2*u,(y-1)*u,4*u,(y+1)*u),fill=fg);d.line((8*u,y*u,22*u,y*u),fill=fg,width=stroke)
        else:
            d.arc((3*u,3*u,21*u,21*u),30,310,fill=fg,width=stroke);d.line((20*u,1*u,20*u,8*u,13*u,8*u),fill=fg,width=stroke)
        im.alpha_composite(layer.resize((icon_size,icon_size),Image.Resampling.LANCZOS),(x,round((height-icon_size)/2)))
    im.alpha_composite(label,(x+icon_size+gap,round((height-label.height)/2)))
    return im


@functools.lru_cache(maxsize=24)
def location_pin(size,color):
    from PIL import Image, ImageDraw
    size=max(8,int(size));k=4
    im=Image.new('RGBA',(size*k,size*k));d=ImageDraw.Draw(im)
    d.ellipse((size*k*.15,0,size*k*.85,size*k*.7),fill=color)
    d.polygon([(size*k*.2,size*k*.48),(size*k*.8,size*k*.48),(size*k*.5,size*k*.97)],fill=color)
    d.ellipse((size*k*.38,size*k*.22,size*k*.62,size*k*.46),fill=BG)
    return im.resize((size,size),Image.Resampling.LANCZOS)


@functools.lru_cache(maxsize=64)
def toolbar_icon(label,size,color,bg):
    from PIL import Image,ImageDraw
    size=max(8,round(size));k=4;unit=size*k/24
    im=Image.new('RGBA',(size*k,size*k));d=ImageDraw.Draw(im)
    def box(values):return tuple(round(v*unit) for v in values)
    stroke=max(2,round(2*unit))
    if label=='Lock':
        d.arc(box((6,1,18,17)),180,360,fill=color,width=stroke)
        d.rounded_rectangle(box((4,10,20,23)),radius=round(2*unit),fill=color)
        d.ellipse(box((11,14,13,17)),fill=bg)
    elif label=='Index':
        for row in (5,12,19):
            d.ellipse(box((2,row-1,4,row+1)),fill=color)
            d.line(box((8,row,22,row)),fill=color,width=stroke)
    elif label=='Save':
        d.polygon([box((3,2)),box((17,2)),box((22,7)),box((22,22)),box((3,22))],fill=color)
        d.rectangle(box((7,2,16,9)),fill=bg)
        d.rectangle(box((7,14,18,22)),fill=bg)
        d.line(box((10,17,16,17)),fill=color,width=max(1,round(unit)))
    elif label=='Reset':
        d.arc(box((3,3,21,21)),40,320,fill=color,width=stroke)
        d.line([box((20,1)),box((20,8)),box((13,8))],fill=color,width=stroke)
    return im.resize((size,size),Image.Resampling.LANCZOS)
