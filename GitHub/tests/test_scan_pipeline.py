"""Latest-frame cadence and early OCR delivery, without screen capture."""
import threading, unittest
from collections import OrderedDict
from types import SimpleNamespace
from PIL import Image
import numpy as np
from scan_pipeline import LatestFrame,ScanFrame,capture_delay
from screen_reader import ScreenReader

class ScanPipelineTests(unittest.TestCase):
    def test_slow_consumer_gets_latest_frame_without_backlog(self):
        frames=LatestFrame();stop=threading.Event()
        frames.publish(ScanFrame(1,1.,'first'));sequence,frame=frames.next(0,stop)
        self.assertEqual(frame.image,'first')
        for n in range(2,20):frames.publish(ScanFrame(1,n*.5,n))
        sequence,frame=frames.next(sequence,stop)
        self.assertEqual(frame.image,19)
        frames.publish(None);self.assertIsNone(frames.next(sequence,stop)[1])
        stop.set();self.assertEqual(frames.next(frames.sequence,stop)[0],frames.sequence)
        self.assertAlmostEqual(capture_delay(100,100.1),.4)
        self.assertEqual(capture_delay(100,101),.01)

    def test_recognized_batches_publish_before_remaining_text(self):
        trace=[]
        class Engine:
            def __call__(self,image,**kwargs):
                return [[[0,y],[20,y],[20,y+7],[0,y+7]] for y in range(0,50,10)],None
            def load_img(self,image):return image
            def get_crop_img_list(self,source,boxes):return [np.full((8,20,3),n,dtype=np.uint8) for n in range(len(boxes))]
            def text_rec(self,crops):trace.append(('ocr',len(crops)));return [('sample',.99) for _ in crops],0
        reader=ScreenReader.__new__(ScreenReader);reader.engine=Engine();reader.detection_limit=960;reader.rec_cache=OrderedDict()
        reader.raw(Image.new('RGB',(64,64)),factor=1,on_partial=lambda lines:trace.append(('published',len(lines))))
        self.assertEqual(trace,[('ocr',4),('published',4),('ocr',1),('published',5)])

    def test_small_tile_retries_unresolved_timer_at_higher_resolution(self):
        from unittest.mock import Mock
        from detection import Detector
        from model import Reading
        from test_tracker import line
        reader=ScreenReader.__new__(ScreenReader);reader.regions=[]
        reader.detector=Detector([dict(id='grey',name='Grey Fang')])
        reader.raw=Mock(side_effect=[
            [line('Grey Rang',y=100),line('Returns in 4:05',y=125)],
            [line('Grey Fang',y=100),line('Returns in 4:05',y=125)]])
        result=reader.discovery(Image.new('RGB',(620,580)))
        self.assertIn(Reading('grey','countdown',245),result)
        self.assertEqual(reader.raw.call_count,2)
