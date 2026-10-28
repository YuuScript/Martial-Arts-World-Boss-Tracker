"""Half-second capture cadence and a single latest-frame slot for OCR workers."""
from dataclasses import dataclass
from threading import Condition

SCAN_INTERVAL = .5

@dataclass(frozen=True)
class ScanFrame:
    revision: int
    captured: float
    image: object

class LatestFrame:
    def __init__(self):
        self.condition=Condition();self.sequence=0;self.frame=None
    def publish(self,frame):
        with self.condition:
            self.sequence+=1;self.frame=frame;self.condition.notify_all()
    def next(self,after,stop):
        with self.condition:
            while self.sequence<=after and not stop.is_set():self.condition.wait(.1)
            return self.sequence,self.frame

def capture_delay(started,now):
    return max(.01,SCAN_INTERVAL-(now-started))
