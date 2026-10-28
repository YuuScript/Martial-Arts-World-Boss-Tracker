"""OCR engine with bounded work: full discovery and small tracked-region passes."""
import time
import hashlib
import math
from dataclasses import replace
from collections import OrderedDict
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from rapidocr_onnxruntime import RapidOCR
from detection import Detector, join_lines, compact, nearby


class ScreenReader:
    def __init__(self, entries,priority=False):
        self.engine=RapidOCR(use_cls=False,intra_op_num_threads=2 if priority else 1,inter_op_num_threads=1,det_limit_type='max')
        self.detection_limit=960 if priority else 1280
        self.rec_cache=OrderedDict()
        self.detector=Detector(entries)
        self.regions=[]
        self.last_full=0
        self.size=None
        self.mode='full'
        self.frame_key=None
        self.frame_time=0
        self.frame_result=[]
        self.tile_index=0
        self.background_pass=0
        self.priority_pass=0

    def configure(self, entries):
        self.frame_key=None
        self.rec_cache.clear()
        self.detector=Detector(entries)
        self.regions=[]
        self.last_full=0
        self.size=None;self.tile_index=0;self.background_pass=0

    @staticmethod
    def factor(image): return 2 if image.width<700 else 1

    def raw(self,image,factor=None,limit=None,min_height=0,on_partial=None,focus_y=None):
        # Bound ONLY text detection. Recognition still sees original-resolution
        # glyphs (including enlarged small/foggy crops), not a shrunken screen.
        factor=factor or self.factor(image)
        if factor>1:image=image.resize((image.width*factor,image.height*factor),Image.Resampling.LANCZOS)
        limit=limit or self.detection_limit
        ratio=min(1,limit/max(image.size))
        probe=image.resize((max(1,round(image.width*ratio)),max(1,round(image.height*ratio))),Image.Resampling.LANCZOS) if ratio<1 else image
        boxes,_=self.engine(np.asarray(probe.convert('RGB')),use_rec=False)
        if not boxes:return []
        sx,sy=image.width/probe.width,image.height/probe.height
        polygons=[]
        for box in boxes:
            box=np.asarray(box,dtype=np.float32)*np.array([sx,sy],dtype=np.float32)
            if np.ptp(box[:,1])<min_height*factor:continue
            polygons.append(box)
        if not polygons:return []
        if focus_y is not None:polygons.sort(key=lambda box:abs(float(np.mean(box[:,1]))-image.height*focus_y))
        source=self.engine.load_img(np.asarray(image.convert('RGB')))
        crops=self.engine.get_crop_img_list(source,polygons)
        output=[]
        # Stream small batches: a matched banner never waits for all other text.
        for start in range(0,len(crops),4):
            batch=crops[start:start+4];keys=[(crop.shape,hashlib.blake2b(crop.tobytes(),digest_size=12).digest()) for crop in batch]
            missing=[i for i,key in enumerate(keys) if key not in self.rec_cache]
            if missing:
                recognized,_=self.engine.text_rec([batch[i] for i in missing])
                for i,value in zip(missing,recognized):self.rec_cache[keys[i]]=value
            for offset,key in enumerate(keys):
                text,confidence=self.rec_cache[key][:2]
                self.rec_cache.move_to_end(key)
                if confidence>=.5:output.append((polygons[start+offset].tolist(),text,float(confidence)))
            while len(self.rec_cache)>128:self.rec_cache.popitem(last=False)
            if on_partial:on_partial(output)
        return output

    @staticmethod
    def enhanced(image):
        # Stretch low-contrast fog text locally; do not brighten the whole scene.
        return ImageEnhance.Contrast(ImageOps.autocontrast(image.convert('RGB'),cutoff=1)).enhance(1.4)

    def read_events(self,image,lane='banner',emit=None):
        width,height=image.size
        if height<500 or width<700:
            crop=image
        elif lane=='banner':
            crop=image.crop((0,round(height*.02),width,round(height*.65)))
        else:
            left=.5 if width>height*1.25 else .2
            crop=image.crop((round(width*left),round(height*.12),width,round(height*.96)))
        self.mode='center announcements' if lane=='banner' else 'side notifications'
        result=[];seen=set()
        def partial(raw):
            fresh=[r for r in self.detector.parse(raw) if r not in seen]
            seen.update(fresh);result.extend(fresh)
            if fresh and emit:emit(fresh)
        # Alternate local contrast on successive fresh frames, without delaying
        # an already recognized event behind an extra full OCR retry.
        self.priority_pass+=1
        if self.priority_pass%2==0:crop=self.enhanced(crop)
        threshold=max(10,height*.012) if lane=='banner' and height>=500 else 0
        factor=1 if lane=='banner' else self.factor(crop)
        raw=self.raw(crop,factor=factor,min_height=threshold,on_partial=partial,focus_y=.55 if lane!='banner' else None)
        if any(r.kind in ('void','chaos') and not r.location for r in result):
            lines=join_lines(raw)
            for line in lines:
                if not any(token in compact(line.text) for token in ('voidhasopened','heavenandearth','primordialchaos')):continue
                neighbors=[other for other in lines if nearby(line,other)]
                pad=max(8,line.height/factor)
                rect=(max(0,int(min(v.x1 for v in neighbors)/factor-pad)),max(0,int(min(v.y1 for v in neighbors)/factor-pad)),min(crop.width,int(max(v.x2 for v in neighbors)/factor+pad)),min(crop.height,int(max(v.y2 for v in neighbors)/factor+pad)))
                # Refine just the incomplete location, after publishing detection.
                partial(self.raw(self.enhanced(crop.crop(rect)),factor=2))
                break
        return result

    def read_priority(self,image):
        return list(set(self.read_events(image,'banner')+self.read_events(image,'notifications')))

    def read_background(self,image,emit=None):
        # Native-resolution overlapping tiles avoid shrinking distant glyphs to
        # fit a whole monitor into the OCR detector. One tile per pass bounds work.
        if self.size!=image.size:
            self.regions=[];self.size=image.size;self.tile_index=0
        self.background_pass+=1
        if self.regions and self.background_pass%2==0:
            self.mode='tracked labels'
            rect=self.regions[self.tile_index%len(self.regions)]
            crop=image.crop(rect)
            readings=self.detector.parse(self.raw(crop))
            if readings and emit:emit(readings)
            if not readings:readings=self.detector.parse(self.raw(self.enhanced(crop),factor=2))
            return readings
        w,h=image.size
        if w<700 or h<500:return self.read(image,force_full=True)
        tile=self.tile_index%4;self.tile_index+=1
        left=0 if tile%2==0 else round(w*.4);top=0 if tile<2 else round(h*.4)
        rect=(left,top,min(w,left+round(w*.6)),min(h,top+round(h*.6)))
        crop=image.crop(rect)
        # Alternate contrast-enhanced views, so a foggy label receives a retry
        # even when the first pass could not locate any text at all.
        if (self.tile_index//4)%2:crop=self.enhanced(crop)
        previous=self.regions[:];readings=self.discovery(crop,emit=emit)
        found=[(a+left,b+top,c+left,d+top) for a,b,c,d in self.regions]
        self.regions=(found+previous)[:6];self.mode='label discovery'
        return readings

    def discovery(self,image,emit=None):
        scale=self.factor(image)
        raw=self.raw(image,limit=2000 if image.width>2000 else None,on_partial=(lambda rows:emit(self.detector.parse(rows))) if emit else None)
        readings=self.detector.parse(raw)
        if readings and emit:emit(readings)
        if scale==2 and image.width<400 and (not readings or any(r.kind in ('void','chaos') and not r.location for r in readings)):
            alternate=self.raw(self.enhanced(image),factor=4)
            improved=self.detector.parse(alternate)
            if improved:
                raw=alternate;readings=improved;scale=4
        regions=[]
        resolved={r.boss for r in readings if r.kind not in ('void','chaos') or r.location}
        lines=join_lines(raw)
        for line in lines:
            text=compact(line.text)
            boss=self.detector.identify(line.text)
            if not (boss or text.startswith(('returnsin','returnin')) or any(phrase in text for phrase in ('callagain','callingaltar','hasfallen','broughtdown','oldthunder','primordialchaos','heavenandearth','voidhasopened','voidhasclosed','chaoshasclosed','stillfor','canbewokenagain','sleepingcolossus'))):
                continue
            if any(token in text for token in ('callagain','callingaltar','oldthunder')): boss=self.detector.kraken
            elif 'primordialchaos' in text or 'heavenandearth' in text or 'voidhasopened' in text or 'voidhasclosed' in text: boss='qi'
            elif boss is None: boss=next((self.detector.identify(other.text) for other in lines if nearby(line,other) and self.detector.identify(other.text)),None)
            h=max(12,line.height)/scale
            rect=(max(0,int(line.x1/scale-h*3)),max(0,int(line.y1/scale-h*4)),min(image.width,int(line.x2/scale+h*3)),min(image.height,int(line.y2/scale+h*5)))
            if any(abs(rect[0]-r[0])<h*3 and abs(rect[1]-r[1])<h*3 for r in regions):
                continue
            regions.append(rect)
            if boss not in resolved and len(regions)<=3:
                refined=self.detector.parse(self.raw(image.crop(rect)))
                if not refined or any(r.kind in ('void','chaos') and not r.location for r in refined):
                    refined=self.detector.parse(self.raw(self.enhanced(image.crop(rect)),factor=4 if rect[2]-rect[0]<400 else 2))
                readings.extend(refined)
                if refined and emit:emit(refined)
                resolved.update(r.boss for r in refined if r.kind not in ('void','chaos') or r.location)
        self.regions=regions[:6]
        return readings

    def read(self,image,force_full=False,allow_cache=True):
        now=time.monotonic()
        frame_key=(image.size,hashlib.blake2b(image.tobytes(),digest_size=16).digest())
        if allow_cache and not force_full and frame_key==self.frame_key:
            self.mode='cached frame'
            elapsed=max(0,math.floor(now-self.frame_time))
            return [replace(r,seconds=max(0,r.seconds-elapsed)) if r.kind=='countdown' else r for r in self.frame_result]
        if force_full or self.size!=image.size or not self.regions or now-self.last_full>=2:
            self.mode='full'
            self.size=image.size
            result=self.discovery(image)
            self.last_full=time.monotonic()
        else:
            self.mode='focused'
            result=[]
            for rect in self.regions:
                cropped=image.crop(rect)
                raw_crop=self.raw(cropped);detected=self.detector.parse(raw_crop)
                if raw_crop and (not detected or any(r.kind in ('void','chaos') and not r.location for r in detected)):
                    detected.extend(self.detector.parse(self.raw(self.enhanced(cropped),factor=4 if cropped.width<400 else 2)))
                result.extend(detected)
        # Notifications appear around the middle-right; keep this region active
        # between full sweeps even when cached regions contain only boss labels.
        if self.mode=='focused' and image.width>=700:
            rect=(int(image.width*.25),int(image.height*.35),int(image.width*.98),int(image.height*.75))
            result.extend(r for r in self.detector.parse(self.raw(image.crop(rect))) if r.kind in ('chaos','void','spawned','void_end','chaos_end'))
        priority={'countdown':0,'ready':1,'killed':2,'spawned':3,'chaos':4,'void':5,'chaos_end':6,'void_end':7}
        complete={r.kind for r in result if r.kind in ('void','chaos') and r.location}
        result=[r for r in result if r.kind not in complete or r.location]
        result=sorted(set(result),key=lambda r:(priority[r.kind],r.boss))
        self.frame_key=frame_key;self.frame_time=now;self.frame_result=result
        return result
