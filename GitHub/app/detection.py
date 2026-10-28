from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from model import Reading
from boss_rules import normalized, special_events

@dataclass
class Line:
    text: str
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def height(self):
        return max(1, self.y2 - self.y1)

    @property
    def cx(self):
        return (self.x1 + self.x2) / 2


def join_lines(results):
    """Join spatially adjacent OCR fragments, never arbitrary screen-wide text."""
    rows = []
    for box, text, confidence in results or []:
        if confidence < .45:
            continue
        rows.append(Line(text, min(p[0] for p in box), min(p[1] for p in box), max(p[0] for p in box), max(p[1] for p in box)))
    rows.sort(key=lambda r: (r.y1, r.x1))
    merged = []
    for row in rows:
        found = None
        for other in reversed(merged):
            overlap = min(row.y2, other.y2) - max(row.y1, other.y1)
            gap = max(row.x1 - other.x2, other.x1 - row.x2, 0)
            if overlap >= .5 * min(row.height, other.height) and gap <= 3 * max(row.height, other.height):
                found = other
                break
        if found:
            found.text = (found.text + ' ' + row.text) if row.x1 >= found.x1 else (row.text + ' ' + found.text)
            found.x1, found.y1 = min(found.x1, row.x1), min(found.y1, row.y1)
            found.x2, found.y2 = max(found.x2, row.x2), max(found.y2, row.y2)
        else:
            merged.append(row)
    return sorted(merged, key=lambda r: (r.y1, r.x1))


def parse_clock(text):
    match = re.search(r'(?<!\d)([0-9OoIl]{1,2})\s*[:：]\s*([0-9OoIl]{2})(?!\d)', text)
    if not match:
        return None
    translate = str.maketrans({'O': '0', 'o': '0', 'I': '1', 'l': '1'})
    minutes, seconds = [int(group.translate(translate)) for group in match.groups()]
    return minutes * 60 + seconds if seconds < 60 else None


def nearby(a, b):
    gap = max(a.y1 - b.y2, b.y1 - a.y2, 0)
    return gap <= max(a.height, b.height) * 4 and abs(a.cx - b.cx) < max(a.x2 - a.x1, b.x2 - b.x1) / 2 + 60



def compact(text):
    return re.sub(r'[^a-z0-9]', '', normalized(text))


def name_key(text):
    # Keep capitalization supplied in the Index; punctuation/spacing are OCR-tolerant.
    return re.sub(r'[^A-Za-z0-9]', '', text)


def void_location(text):
    # Strip the notification's CJK badge, not words from the actual location.
    text=re.sub(r'[\u3400-\u9fff]+',' ',text)
    text=' '.join(text.split())
    match=re.search(r'\b(?:the\s+)?void\s+has\s+opened\s+in\s+(?:the\s+)?(.{2,120}?)[：:;]',text,re.I)
    if not match: return None
    location=match[1].strip(' "“”\'.,')
    return location if re.fullmatch(r"[A-Za-z][A-Za-z0-9 '\-’]{1,100}",location) else None


def clean_location(text):
    # Correct only the observed OCR confusion, not arbitrary unknown places.
    return re.sub(r'\bcastern(?=\s+fog\b)',lambda m:'Eastern' if m[0][0].isupper() else 'eastern',text,flags=re.I)


def chaos_location(text):
    text=' '.join(re.sub(r'[\u3400-\u9fff]+',' ',text).split())
    match=re.search(r'heaven\s+and\s+earth\s+come\s+unstitched\s+(?:deep\s+)?(?:on|in|at|near|beneath|beyond)\s+(?:the\s+)?(.{2,100}?)\s*[:：;]\s*primordial\s+chaos',text,re.I)
    if not match: return ''
    return clean_location(match[1].strip(' "“”\'.,'))


class Detector:
    def __init__(self, entries):
        self.entries=entries
        self.names=[]
        for entry in entries:
            names=[entry['name']]+[n.strip() for n in entry.get('alias','').split(';') if n.strip()]
            self.names.append((entry['id'],names))
        self.kraken=next((entry['id'] for entry in entries if entry.get('mechanic')=='kraken'),None)

    def identify(self,text):
        tokens=re.findall(r'[a-z0-9]+',normalized(text))
        key=''.join(tokens)
        if not key:return None
        # Whole names beat aliases; an explicit alias override beats inferred names.
        exact=[entry['id'] for entry in self.entries if compact(entry['name'])==key]
        if exact:return exact[0] if len(exact)==1 else None
        aliases=[entry for entry in self.entries if any(compact(alias)==key for alias in entry.get('alias','').split(';') if alias.strip())]
        preferred=[entry for entry in aliases if entry.get('alias_override')]
        if preferred:return preferred[0]['id'] if len(preferred)==1 else None
        if aliases:return aliases[0]['id'] if len(aliases)==1 else None
        shortened=[entry['id'] for entry in self.entries if ',' in entry['name'] and len(key)>=4 and compact(entry['name'].split(',')[0])==key]
        if shortened:return shortened[0] if len(shortened)==1 else None
        embedded=[]
        for entry in self.entries:
            phrase=' '.join(re.findall(r'[a-z0-9]+',normalized(entry['name'])))
            if len(compact(phrase))>=4 and re.search(r'(?<![a-z0-9])'+re.escape(phrase)+r'(?![a-z0-9])',' '.join(tokens)):
                embedded.append((len(compact(phrase)),entry['id']))
        if embedded:
            embedded.sort(reverse=True)
            if len(embedded)==1 or embedded[0][0]>embedded[1][0]:return embedded[0][1]
        if len(tokens)>=2 and len(key)>=8:
            phrase=' '.join(tokens)
            partial=[entry['id'] for entry in self.entries if re.search(r'(?<![a-z0-9])'+re.escape(phrase)+r'(?![a-z0-9])',' '.join(re.findall(r'[a-z0-9]+',normalized(entry['name']))))]
            if partial:return partial[0] if len(partial)==1 else None
        scores={}
        for boss,names in self.names:
            best=0
            for index,name in enumerate(names):
                words=re.findall(r'[a-z0-9]+',normalized(name));name_normalized=''.join(words)
                if key==name_normalized:best=max(best,1.0)
                elif len(name_normalized)>=4 and re.search(r'(?<![a-z0-9])'+re.escape(' '.join(words))+r'(?![a-z0-9])',' '.join(tokens)):
                    best=max(best,.98)
                elif len(key)>=6 and len(name_normalized)>=6:
                    ratio=SequenceMatcher(None,key,name_normalized).ratio()
                    if ratio>=.90:best=max(best,ratio*.95)
                if index==0:
                    short=''.join(re.findall(r'[a-z0-9]+',normalized(name.split(',')[0])))
                    if ',' in name and len(short)>=4 and key==short:best=max(best,.97)
                    if len(tokens)>=2 and len(key)>=8 and ' '.join(tokens) in ' '.join(words) and all(t in words for t in tokens):
                        best=max(best,.91)
            if best:scores[boss]=best
        ranked=sorted(scores.items(),key=lambda pair:pair[1],reverse=True)
        if not ranked or (len(ranked)>1 and ranked[0][1]-ranked[1][1]<.06):return None
        return ranked[0][0]

    def parse(self, results):
        lines=join_lines(results)
        readings=[]
        for line in lines:
            text=compact(line.text)
            neighbors=[other for other in lines if nearby(line,other)]
            group=' '.join(other.text for other in neighbors)
            merged=compact(group)
            for boss,kind in special_events(group,self.entries):
                location=''
                if kind=='spawned' and any(e['id']==boss and e.get('mechanic')=='wukong' for e in self.entries):
                    match=re.search(r'has\s+come\s+down\s+on\s+(.{2,100}?)\.\s*His\s+pressure',group,re.I)
                    location=' '.join(re.sub(r'[\u3400-\u9fff]+',' ',match[1]).split()) if match else ''
                readings.append(Reading(boss,kind,location=location))
            for entry in self.entries:
                mechanic=entry.get('mechanic')
                if mechanic=='colossus' and 'sleeping' in merged:
                    if 'stepintothecratertowakeit' in merged:
                        readings.append(Reading(entry['id'],'spawned'))
                    if 'itcanbewokenagainin' in text:
                        seconds=parse_clock(line.text)
                        if seconds is not None:readings.append(Reading(entry['id'],'countdown',seconds))
                if mechanic=='sword' and 'anamelesssword' in merged and 'stillfor' in text:
                    seconds=parse_clock(line.text)
                    if seconds is not None:readings.append(Reading(entry['id'],'countdown',seconds))
            if re.match(r'^(?:the)?chaoshasclosed',text):
                readings.append(Reading('qi','chaos_end'))
            if 'returnsin' in text or 'returnin' in text:
                seconds=parse_clock(line.text)
                candidates=[(other,self.identify(other.text)) for other in neighbors if other.y1<=line.y1+line.height*.4]
                candidates=[(other,boss) for other,boss in candidates if boss]
                if seconds is not None and candidates:
                    other,boss=min(candidates,key=lambda pair:abs(line.y1-pair[0].y2)+abs(line.cx-pair[0].cx)*.1)
                    readings.append(Reading(boss,'countdown',seconds))
            if 'hasfallen' in text or ('hasfallen' in merged and self.identify(line.text)):
                for candidate in (line.text,group):
                    match=re.search(r'(.+?)\s+has\s+fallen\b',candidate,re.I)
                    if match:
                        boss=self.identify(match[1])
                        if boss: readings.append(Reading(boss,'killed'))
            if 'broughtdown' in merged:
                match=re.search(r'\bbrought\s+down\s+(.+?)(?:!|$)',group,re.I)
                if match:
                    boss=self.identify(match[1].strip())
                    if boss:readings.append(Reading(boss,'killed'))
            if self.kraken:
                altar=any('callingaltar' in compact(other.text) for other in neighbors)
                if 'callagainin' in text and ('straitchurns' in text or altar):
                    seconds=parse_clock(line.text)
                    if seconds is not None: readings.append(Reading(self.kraken,'countdown',seconds))
                if 'stillwater' in text and 'talisman' in text and altar:
                    readings.append(Reading(self.kraken,'ready'))
                if ('oldthunder' in merged or 'stormcliffkraken' in merged) and 'hasrisen' in merged and 'strait' in merged:
                    readings.append(Reading(self.kraken,'spawned'))
            if re.fullmatch(r'(?:the)?voidhasclosed',text):
                readings.append(Reading('qi','void_end'))
            if 'voidhasopened' in merged:
                location=void_location(group)
                readings.append(Reading('qi','void',location=location or ''))
            if 'primordialchaosqi' in merged and 'welledup' in merged and ('highestsummit' in merged or 'heavenandearth' in merged):
                readings.append(Reading('qi','chaos',location=chaos_location(group)))
        priority={'countdown':0,'ready':1,'killed':2,'spawned':3,'chaos':4,'void':5,'chaos_end':6,'void_end':7}
        return sorted(set(readings),key=lambda r:(priority[r.kind],r.boss))
