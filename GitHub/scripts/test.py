"""Run source checks without opening the HUD or capturing the desktop."""
from pathlib import Path
import os, sys, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tests')]
(ROOT/'build').mkdir(exist_ok=True)
previous=Path.cwd()
with tempfile.TemporaryDirectory(dir=ROOT/'build') as temporary:
    try:
        os.chdir(temporary);Path('work').mkdir()
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    finally:os.chdir(previous)
raise SystemExit(0 if result.wasSuccessful() else 1)
