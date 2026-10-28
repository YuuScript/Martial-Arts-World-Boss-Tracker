# Build on Windows

Use **64-bit Python 3.12** with Tkinter. Players do not need Python.

From this repository's root in PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe scripts/test.py
.venv\Scripts\python.exe scripts/build.py
```

The build produces `dist/Martial-Arts-World-Tracker-V1.3.1-Windows.zip` and its SHA-256 checksum. It includes the executable, OCR models, Python runtime, support files, and licenses. The executable has the multi-resolution icon from `assets/tracker.ico`.

The build refuses to overwrite an existing versioned release folder. Remove or archive your own previous build output, or increment `VERSION.txt` and `app/boss_rules.py`, before rebuilding.

## Run from source

```powershell
.venv\Scripts\python.exe app/tracker.py
```

Source runs store settings beside `app/tracker.py`. The player build stores them beside its executable. The public package starts from `data/bosses.json`, not a developer's saved settings.

## Checks

Tests use temporary settings and hidden windows; they do not activate the desktop or capture the game. The build runs the same checks in the packaged executable before creating the ZIP. These checks do not replace a manual in-game test.

## Release

Upload the contents of this source folder to a GitHub repository. Create a release tagged `v1.3.1` and attach the Windows ZIP and its `.sha256` file. Paste [the release notes](RELEASE.md) into the description. Keep executables in release assets rather than committing them to the source repository.
