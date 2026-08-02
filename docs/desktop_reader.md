# BookBuddy desktop reader

The desktop client lives in `frontend/`. It is a Tauri v2 shell around a strict
React application and communicates with BookBuddy only through FastAPI.

## Native startup lifecycle

The packaged desktop starts with a dedicated static `splash` WebView. Rust owns
the managed backend process, validates the authenticated `/health` response,
and only then creates the main WebView hidden. The main window is shown after
reader settings have hydrated and the initial `/sessions` response has rendered.
Neither React nor a failed frontend request can expose an empty application
window. Startup stage timings are written to `logs/startup-timings.jsonl` in
the portable BookBuddy data folder.

The custom backend URL in Settings is diagnostic-only. Packaged application
traffic always uses the random-port, one-time-token managed sidecar.

## Web development

Start the backend and Vite separately:

```powershell
.\venv\Scripts\python.exe -m uvicorn --app-dir backend app:app --host 127.0.0.1 --port 8000
cd frontend
pnpm install
pnpm dev
```

The browser build uses `http://127.0.0.1:8000` unless
`VITE_BACKEND_URL` overrides it. The packaged app receives a random loopback
port and one-time bearer token from its Rust host.

## Verification

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -t . -v
cd frontend
pnpm build
pnpm lint
pnpm test
```

## Windows package

Install the Rust MSVC toolchain and Visual Studio Build Tools with the Windows
10/11 SDK, then install PyInstaller into the project virtual environment:

```powershell
winget install Rustlang.Rustup
winget install Microsoft.VisualStudio.2022.BuildTools --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
.\venv\Scripts\python.exe -m pip install pyinstaller
.\scripts\build_desktop.ps1
```

The build script freezes `backend/main.py`, embeds that backend into the desktop
executable, and creates an unsigned current-user NSIS bundle plus a no-source
portable ZIP.

### Portable release layout

- A standalone `BookBuddy.exe` launched outside a folder named `BookBuddy`
  creates that sibling folder, copies itself and any sibling BookBuddy NSIS
  installer into it, and relaunches from the copy.
- NSIS installs into a `BookBuddy` folder beside the installer and retains a
  copy of the installer there.
- Source/development runs use the project root as their portable data root.
- First launch creates `library`, `database`, `config`, `cache`, `logs`,
  `exports`, and `runtime` inside the portable root. The embedded backend is
  extracted only as a runtime executable; Python, Rust, and TypeScript source
  files are not distributed.
- Existing library and reader-setting files are copied from the former Windows
  AppData locations when the portable destination does not already contain
  them. The legacy copy is preserved.

## Spoiler-safe analysis lifecycle

The frontend records contiguous chapter progress locally. At 50 percent it
queues exact-chapter extraction through the reader analysis API. Extraction is
written to a cache workspace and is not visible to canonical graph, snapshot,
or dictionary routes. Natural chapter completion authorizes evidence promotion
and replay. Leaving an unfinished chapter invalidates and deletes staging.

Dictionary requests send both the current rendered chapter and the latest
completed knowledge boundary. This keeps pre-existing, fully analyzed library
sessions from exposing current or future chapter graph facts.
