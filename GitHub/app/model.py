"""Countdown and event state, independent of OCR and window rendering."""
import math
from dataclasses import dataclass

GREEN = '#9cf4bf'
RED = '#ff848c'
GOLD = '#f5ce72'


@dataclass(frozen=True)
class Reading:
    boss: str
    kind: str
    seconds: int | None = None
    location: str = ""


class BossTimer:
    def __init__(self, entry):
        self.entry = entry
        self.deadline = None
        self.spawned = False
        self.last_seen = None
        self.source = ''
        self.last_kill = None
        self.kill_until = 0
        self.alert_until = 0
        self.last_announcement = None
        self.spawn_location = ''
        self.spawned_at = None
        self.reset_until = None

    def observe(self, reading, captured, shown_at, source='screen'):
        self.advance(shown_at)
        duration = self.entry.get('duration')
        if reading.kind == 'killed':
            if self.last_kill is not None and captured-self.last_kill < 15:return False
            self.spawned_at = self.reset_until = None
            self.last_kill = captured
            self.kill_until = shown_at + 5
            self.alert_until = 0
            self.spawned = False
            self.deadline = captured + max(0,duration-3) if duration and self.entry.get('mechanic')!='wukong' else None
        elif reading.kind == 'spawned':
            if reading.location:self.spawn_location=reading.location
            if self.spawned_at is None:
                self.spawned_at = captured
                self.reset_until = None
                self.alert_until = shown_at + 12
            self.spawned = True
            self.last_announcement = captured
        elif reading.kind == 'ready':
            if not self.spawned:
                self.deadline = captured
        elif reading.kind == 'countdown':
            if self.entry.get('mechanic')=='wukong':return False
            seconds = reading.seconds
            if seconds is None or seconds < 0 or seconds > (duration + 30 if duration else 86400):
                return False
            candidate = captured + seconds
            new_cycle = self.deadline is not None and candidate > self.deadline + 45
            if source == 'manual' or (new_cycle and (self.last_announcement is None or captured-self.last_announcement > 30)):
                self.spawned = False
            # Ignore a stale label for a short period immediately after a kill.
            if self.last_kill is not None and captured-self.last_kill < 2 and duration and seconds < duration-10:
                return False
            if seconds>0 and not self.spawned:
                self.spawned=False;self.spawned_at=None;self.reset_until=None
            if self.deadline is None or abs(candidate-self.deadline) > 2:
                self.deadline = candidate
        self.last_seen, self.source = captured, source
        return True

    def remaining(self, now):
        return None if self.deadline is None else max(0, math.ceil(self.deadline-now))

    def advance(self,now):
        if self.entry.get('mechanic')=='wukong':
            if self.spawned_at is not None and now>=self.spawned_at+900:
                self.spawned=False;self.spawned_at=None;self.last_announcement=None;self.alert_until=0
            return
        if self.spawned_at is None and (self.spawned or (self.deadline is not None and now>=self.deadline and self.entry.get('mechanic')!='kraken')):
            self.spawned_at=self.last_announcement if self.spawned and self.last_announcement is not None else self.deadline
        if self.spawned_at is not None and now>=self.spawned_at+180:
            if self.reset_until is None:self.reset_until=self.spawned_at+183
            self.spawned=False;self.deadline=None
            if now>=self.reset_until:
                self.spawned_at=None;self.reset_until=None;self.last_seen=None;self.source='';self.alert_until=0

    def state(self, now):
        self.advance(now)
        if self.reset_until is not None:return 'Reset'
        if now < self.kill_until:
            return 'KILLED'
        if self.spawned:
            return 'Spawned'
        left = self.remaining(now)
        if left is None:
            return 'Waiting for notification' if self.entry.get('mechanic')=='wukong' else 'Need entry'
        if left == 0:
            return 'Can spawn' if self.entry.get('mechanic') == 'kraken' else 'Spawned'
        return 'countdown'

    def sort_key(self, now):
        state=self.state(now)
        if state in ('Spawned','Reset'):return (0,-(self.spawned_at or 0),self.entry['name'])
        left=self.remaining(now)
        return (2 if left is None else 1,left if left is not None else float('inf'),self.entry['name'])

    def progress(self, now):
        if self.state(now) in ('Spawned', 'Can spawn'):
            return 1.0
        left, duration = self.remaining(now), self.entry.get('duration')
        # A partial screenshot does not establish a full respawn duration.
        return 0 if left is None or not duration else max(0, min(1, 1-left/duration))

    def color(self, now):
        state = self.state(now)
        if state == 'Reset': return GOLD
        if state == 'KILLED': return RED
        if state == 'Spawned': return GREEN
        if state == 'Can spawn': return '#a8d6ff'
        left, duration = self.remaining(now), self.entry.get('duration')
        if left is None: return '#d6e4f5'
        if left <= 60: return GREEN
        if not duration: return '#d4dbe5'
        midpoint = duration/2
        if left >= midpoint:
            a,b=(255,132,140),(255,226,146)
            factor=(duration-left)/max(1,duration-midpoint)
        else:
            a,b=(255,226,146),(156,244,191)
            factor=(midpoint-left)/max(1,midpoint-60)
        factor=max(0,min(1,factor))
        return '#'+''.join(f'{round(x+(y-x)*factor):02x}' for x,y in zip(a,b))

    def snapshot(self, now, wall):
        def stamp(value): return None if value is None else wall+(value-now)
        return dict(deadline=stamp(self.deadline), spawned=self.spawned, last_seen=stamp(self.last_seen), source=self.source,
                    last_kill=stamp(self.last_kill), last_announcement=stamp(self.last_announcement))

    def restore(self, data, now, wall):
        def stamp(value): return None if value is None else now+(float(value)-wall)
        self.deadline=stamp(data.get('deadline'))
        self.spawned=bool(data.get('spawned',False))
        self.last_seen=stamp(data.get('last_seen'))
        self.last_kill=stamp(data.get('last_kill'))
        self.last_announcement=stamp(data.get('last_announcement'))
        self.source=data.get('source','saved')


class EventGate:
    """Deduplicate continuous messages and short OCR misses; persisted across restart."""
    def __init__(self):
        self.events={}

    def accept(self, key, captured):
        previous=self.events.get(key)
        self.events[key]={'first': previous['first'] if previous else captured, 'last': captured}
        if previous and (captured-previous['last'] < 5 or captured-previous['first'] < (15 if key.endswith(':killed') else 30)):
            return False
        self.events[key]={'first':captured,'last':captured}
        return True

    def snapshot(self, now, wall):
        return {key:{field:wall+(value-now) for field,value in stamps.items()} for key,stamps in self.events.items()}

    def restore(self, data, now, wall):
        self.events={key:{field:now+(float(value)-wall) for field,value in stamps.items()} for key,stamps in data.items() if set(stamps)=={'first','last'}}


class QiState:
    """One exclusive Qi event slot with an optional detected Void location."""
    def __init__(self):
        self.kind=None
        self.expires=None
        self.flash_until=0
        self.location=''
        self.exhausted_kind=None
        self.exhausted_until=0

    def activate(self, kind, captured, shown_at, location=''):
        if kind not in ('chaos','void'):
            raise ValueError('Unknown Qi state')
        self.kind, self.expires, self.location = kind, captured+900, location
        self.flash_until=shown_at+12
        self.exhausted_until=0

    def exhaust(self,kind,shown_at):
        if self.kind and self.kind!=kind and self.expires and self.expires>shown_at: return False
        self.exhausted_kind=kind
        self.kind=None;self.location='';self.expires=None
        self.exhausted_until=shown_at+5;self.flash_until=self.exhausted_until
        return True

    def state(self, now):
        if now<self.exhausted_until: return ('Chaos' if self.exhausted_kind=='chaos' else 'Void')+' Qi Exhausted'
        if self.expires is None or now >= self.expires:
            return 'None Detected'
        if self.kind=='chaos': return 'Chaos Qi Detected!'
        return 'Void Qi Detected!'

    def snapshot(self, now, wall):
        return dict(exhausted_kind=self.exhausted_kind, kind=self.kind, expires=None if self.expires is None else wall+(self.expires-now), location=self.location, exhausted_until=wall+self.exhausted_until-now if self.exhausted_until>now else None)

    def restore(self, data, now, wall):
        self.exhausted_until=now+float(data['exhausted_until'])-wall if data.get('exhausted_until') else 0
        self.flash_until=self.exhausted_until
        self.exhausted_kind=data.get('exhausted_kind')
        self.kind=data.get('kind')
        self.location=data.get('location','')
        self.expires=None if data.get('expires') is None else now+(float(data['expires'])-wall)


class GameLifecycle:
    def __init__(self):
        self.seen_game=False
        self.missing_since=None

    def should_exit(self,present,now):
        if present:
            self.seen_game=True
            self.missing_since=None
            return False
        if not self.seen_game: return False
        if self.missing_since is None: self.missing_since=now
        return now-self.missing_since>=3
