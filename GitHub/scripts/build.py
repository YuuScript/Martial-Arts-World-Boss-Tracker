"""Build and verify a portable Windows release from clean source."""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, zipfile
ROOT=Path(__file__).resolve().parents[1]
VERSION=(ROOT/'VERSION.txt').read_text().strip()
NAME='Martial Arts World Tracker'
FOLDER=f'Martial-Arts-World-Tracker-{VERSION}-Windows'
DIST=ROOT/'dist'; BUILD=ROOT/'build'; STAGING=BUILD/'package'
release=DIST/FOLDER
if sys.platform!='win32' or sys.version_info[:2]!=(3,12):
    raise SystemExit('Build with 64-bit Python 3.12 on Windows.')
if release.exists():raise SystemExit('This release folder already exists; archive it or update the version before rebuilding.')
BUILD.mkdir(exist_ok=True);DIST.mkdir(exist_ok=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name',NAME,
    '--icon',str(ROOT/'assets/tracker.ico'),'--version-file',str(ROOT/'scripts/windows-version.txt'),
    '--distpath',str(STAGING),'--workpath',str(BUILD/'pyinstaller'),'--specpath',str(BUILD),
    '--paths',str(ROOT/'tests'),'--add-data',f'{ROOT / "assets"}:assets','--add-data',f'{ROOT / "data"}:data',
    '--collect-all','rapidocr_onnxruntime','--collect-all','onnxruntime',str(ROOT/'app/tracker.py')],cwd=ROOT,check=True)
shutil.copytree(STAGING/NAME,release)
shutil.copytree(ROOT/'licenses',release/'_internal/licenses')
shutil.copy2(ROOT/'LICENSE',release/'_internal/licenses/Tracker-MIT.txt')
shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',release/'_internal/licenses/THIRD_PARTY_NOTICES.md')
shutil.copy2(ROOT/'docs/PLAYER-README.txt',release/'README.txt')
report=BUILD/'verification.json'
# The packaged diagnostic mode creates hidden test windows only.
subprocess.run([str(release/(NAME+'.exe')),'--self-test','--report',str(report)],check=True)
verification=json.loads(report.read_text())
if not verification.get('passed'):raise SystemExit('Packaged verification failed; see build/verification.json.')
assert set(p.name for p in release.iterdir())=={NAME+'.exe','_internal','README.txt'}
assert not any(p.name.startswith('settings') or p.suffix=='.log' for p in release.rglob('*'))
archive=DIST/(FOLDER+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in release.rglob('*'):
        if p.is_file():z.write(p,Path(FOLDER)/p.relative_to(release))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n',encoding='ascii')
print(f'Created {archive.name}; {verification["tests"]} packaged checks passed.')
