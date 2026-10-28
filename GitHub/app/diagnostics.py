"""Explicit off-screen release checks. Never start the capture worker or show UI."""
import argparse
import io
import json
import os
from pathlib import Path
import tempfile
import time
import traceback
import unittest


def run(arguments):
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--report',required=True)
    parser.add_argument('--fixtures')
    args=parser.parse_args(arguments)
    report=Path(args.report).resolve()
    fixtures=Path(args.fixtures).resolve() if args.fixtures else None
    data={'passed':False}
    previous=Path.cwd()
    try:
        import test_tracker
        import test_integration
        import test_session
        import test_v1
        import test_presets
        import test_scan_pipeline
        import test_public_release
        with tempfile.TemporaryDirectory(dir=report.parent) as folder:
            os.chdir(folder); Path('work').mkdir()
            suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in (test_tracker,test_integration,test_session,test_v1,test_presets,test_scan_pipeline,test_public_release))
            output=io.StringIO()
            result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
            data.update(tests=result.testsRun,tests_passed=result.wasSuccessful(),details=output.getvalue())
            if fixtures:
                from screen_reader import ScreenReader
                from storage import DEFAULT_BOSSES
                from PIL import Image
                reader=ScreenReader(DEFAULT_BOSSES+[dict(id='grey_fang',name='Grey Fang',mechanic='standard'),dict(id='jiao',name='Jiao, The Flood Dragon',alias='Jiao',mechanic='standard')])
                data['screenshots']=[]
                for fixture in json.loads(fixtures.read_text(encoding='utf-8')):
                    label,path,boss,kind,seconds,*location=fixture
                    started=time.monotonic()
                    with Image.open(path) as source: readings=reader.read(source.convert('RGB'),force_full=True)
                    passed=any((r.boss,r.kind,r.seconds)==(boss,kind,seconds) and (not location or r.location==location[0]) for r in readings)
                    data['screenshots'].append(dict(name=label,passed=passed,seconds=round(time.monotonic()-started,3),locations=[r.location for r in readings if r.location]))
                # A full screenshot, followed by a focused pass through its cached regions.
                full=next(item for item in json.loads(fixtures.read_text(encoding='utf-8')) if item[0]=='jade_full')
                with Image.open(full[1]) as source:
                    screenshot=source.convert('RGB'); reader.read(screenshot,force_full=True)
                    started=time.monotonic(); readings=reader.read(screenshot,allow_cache=False)
                    data['focused_scan']=dict(mode=reader.mode,seconds=round(time.monotonic()-started,3),passed=any(r.boss=='jade' and r.seconds==841 for r in readings))
            data['passed']=data['tests_passed'] and all(item['passed'] for item in data.get('screenshots',[])) and data.get('focused_scan',{'passed':True})['passed']
            os.chdir(previous)
    except Exception:
        data['error']=traceback.format_exc()
    finally:
        os.chdir(previous)
        report.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return 0 if data['passed'] else 1

