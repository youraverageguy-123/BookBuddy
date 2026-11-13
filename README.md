<div align="center">
  <img src="frontend/public/bookbuddy-logo.png" alt="BookBuddy owl logo" width="180">

# BookBuddy

### A private, local-first EPUB and PDF reader that remembers the story for you, without spoilers.

[![CI](https://github.com/youraverageguy-123/BookBuddy/actions/workflows/ci.yml/badge.svg)](https://github.com/youraverageguy-123/BookBuddy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.3.0-c89b5b)](https://github.com/youraverageguy-123/BookBuddy/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078d4)](https://github.com/youraverageguy-123/BookBuddy/releases)
[![Status](https://img.shields.io/badge/status-pre--release-orange)](#current-status)
[![Tauri](https://img.shields.io/badge/Tauri-2-24c8db)](https://tauri.app/)
[![React](https://img.shields.io/badge/React-19-61dafb)](https://react.dev/)
[![Python](https://img.shields.io/badge/Python-3.13%20tested-3776ab)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[Download](https://github.com/youraverageguy-123/BookBuddy/releases/latest)
·
[What's new](#whats-new-in-030)
·
[Architecture](docs/architecture.md)
·
[Roadmap](#roadmap)
·
[Report an issue](https://github.com/youraverageguy-123/BookBuddy/issues)

</div>

> [!IMPORTANT]
> BookBuddy is pre-release software. Its current Windows installer and portable bundle are unsigned, so Windows may display a security warning. Download builds only from this repository's Releases page.

## About BookBuddy

BookBuddy is a reading-first desktop application for people who want a capable EPUB library without giving up the book's original presentation. It preserves publisher typography, headings, drop caps, images, indents, and structural layout while adding search, notes, bookmarks, collections, reading statistics, and configurable reading modes.

Your books and reading state remain on your device. Core reading does not require an AI account or API key. If you configure Gemini, BookBuddy can optionally explain or translate selected text and build chapter-bounded story knowledge intended to reduce exposure to information beyond your current reading progress.

BookBuddy is designed and built by Dhruv ([@youraverageguy-123](https://github.com/youraverageguy-123)).

## What's new in 0.3.0

- **A page for every book.** Clicking a book opens its page: Continue reading, an analysis mode, and tiles for Characters, Relationship map, Timeline, Ask, and notes.
- **Custom analysis.** Already read part of a book? Pick the chapter you reached and BookBuddy analyses everything up to it, without changing your reading position.
- **Redesigned dictionary card.** A compact card beside the selected word, with the meaning in this sentence first and tabs for the rest.
- **Chat that stays put.** A conversation, including an answer still on its way, survives leaving the page and is the same in the reader's chat drawer.
- **Honest status.** When there is no story knowledge yet, the page says why: analysing, waiting on Gemini, stopped, paused, or off.
- **Reliability fixes** for books with a one-entry table of contents, chapter names, slow or failing AI requests, and stale background tasks.

The full list is in the [changelog](CHANGELOG.md).

## Current features

### Publisher-faithful EPUB reading

- Import EPUB files through drag-and-drop, `Ctrl+O`, or the Library command.
- Display covers, publisher styling, embedded fonts, headings, drop caps, images, indents, and structural layouts.
- Navigate hierarchical tables of contents, including grouped omnibus structures. Books that ship without a usable one get a chapter list built from the book itself.
- Resume from the last saved location with chapter and book progress tracking.
- Search the current chapter, previously reached text, or—after confirmation—the whole book.
- Choose between paged and continuous-scrolling layouts.
- Enter distraction-free fullscreen mode and navigate with the keyboard.
- Open embedded illustrations in a zoomable and pannable image viewer.
- Use paper, night, sepia, OLED, or forest reader themes.
- Adjust fonts, type size, line height, paragraph spacing, column width, margins, alignment, hyphenation, and image scale.
- Override appearance for one book without changing global reader defaults.

### Library and reading state

- Home, Library, and Collections views.
- Continue-reading, recent, favorite, pinned, want-to-read, and finished states.
- Custom collections and automatic shelves based on reading state.
- Library search, filtering, sorting, and compact or comfortable layouts.
- Bookmarks tied to precise EPUB locations.
- Highlights, underlines, colored notes, and searchable annotations.
- Local reading-time statistics and personalized remaining-time estimates.
- Exportable notes and reading statistics.
- Local progress and settings migration across supported BookBuddy upgrades.

### Contextual reading tools

- Context-sensitive lookup for selected words and passages.
- Local dictionary definitions when optional WordNet data is installed.
- Local pronunciation when the optional pronunciation corpus is available.
- Grammar-oriented explanations for function words.
- Story-aware lookup constrained by the reader's completed knowledge boundary.
- Optional AI explanations and translations for selected text.

### Optional chapter and image analysis

When Gemini credentials are configured, BookBuddy can:

- Analyze completed chapter content in the background.
- Build evidence-backed story knowledge for contextual lookups.
- Track entities, events, relationships, terminology, and changes over time in its local data pipeline.
- Use separate optional Vision credentials for low-confidence image-analysis cases.
- Choose which Gemini model to use from **Settings → AI**. BookBuddy lists the models your key can access, switches immediately, and remembers the choice; no configuration files need editing.

These backend capabilities support the reader, the contextual dictionary, and the story knowledge views below.

### Story knowledge and chat

Each book has a **Story knowledge** page (from Book details, or the reader's More menu) built from analyzed chapters:

- **Characters** — a searchable explorer of people, places, and things, with aliases, relationships, and events for each.
- **Relationships** — an interactive map of who is connected to whom, colored by warm, hostile, or neutral feeling.
- **Timeline** — events grouped by chapter, with the characters involved.
- **Ask** — a chat about the book, also available as a drawer inside the reader.

All four are limited to the chapters you have read. The knowledge views need chapter analysis; chat needs a Gemini key and also works from the text of those chapters alone.

### Book page and analysis modes

Clicking a book opens its own page: Continue reading, the story knowledge tiles, notes, and details in one place. Each book has an analysis mode:

- **Off** — no AI analysis for this book.
- **Auto** — each chapter is analysed in the background as you finish it.
- **Custom** — for books you have already read. Pick the chapter you reached and BookBuddy analyses everything up to it, showing progress as it goes. Story knowledge unlocks through that chapter; your reading position and statistics are not changed.

Custom analysis sends each chapter that has not been analysed yet to Gemini, so it uses API quota in proportion to the number of chapters. It can be stopped at any time and resumes from where it stopped.

### PDF reading (early)

- Import text PDFs alongside EPUBs.
- Page-by-page reading with zoom, a contents panel built from the PDF outline, and resume.
- Chapters come from the PDF outline, or from fixed page groups when there is none, so analysis, story knowledge, and chat work for PDFs too.
- Not yet available for PDFs: text selection, dictionary lookup, highlights, notes, bookmarks, in-book search, covers, and reader themes. Scanned PDFs without a text layer can be read but not analyzed.

### Desktop operation

- Tauri-managed local FastAPI backend.
- Authenticated random-port loopback communication in packaged builds.
- Native startup splash with managed backend readiness checks.
- Background-task status and recovery controls.
- Local database integrity, backup, and optimization tools.
- Bounded cache inspection and cleanup.
- API keys protected for the current Windows account.
- Local reading-data export and reset controls.

## Privacy and Gemini

BookBuddy is designed as a local-first application.

| Capability | API key required? | Behavior |
|---|---:|---|
| EPUB import and reading | No | EPUB content and reader state remain in BookBuddy's local data folders. |
| Progress, collections, notes, and bookmarks | No | Stored locally in reader-state storage. |
| EPUB search | No | Uses a local search index. |
| Dictionary and pronunciation | No | Available locally when their optional datasets are installed. |
| AI explanation and translation | Yes | The selected text and relevant bounded context may be sent to Gemini. |
| Chapter analysis | Yes | Current-chapter analysis inputs may be sent to Gemini when analysis is enabled and credentials are configured. |
| AI image fallback | Yes | Uses separately configured Vision credentials only for eligible low-confidence cases. |

BookBuddy limits story-aware results to the latest completed chapter knowledge available to the reader. This is a spoiler-reduction boundary, not a guarantee that generated text can never contain an unwanted inference.

Saved credentials are protected for the current Windows account. Their values are not returned by the settings API and are excluded from normal logs and data exports.

The image pipeline is local-first. Local metadata, hashing, preprocessing, and OCR are preferred; Gemini Vision is optional and isolated from the text-AI key pool.

## Installation

### Windows installer

1. Open [GitHub Releases](https://github.com/youraverageguy-123/BookBuddy/releases/latest).
2. Download `BookBuddy_<version>_x64-setup.exe`.
3. Run the installer.
4. Launch BookBuddy from the installed application.

The installer is currently unsigned. Confirm that the file came from this repository before continuing through any Windows warning.

### Portable edition

1. Download `BookBuddy_<version>_portable.zip` from the same release.
2. Extract the complete `BookBuddy` folder.
3. Launch `BookBuddy.exe` from inside that folder.
4. Keep the application and its generated data folders together when moving the portable installation.

Do not run the executable directly from inside the ZIP archive.

## First use

1. Open the Library and import an EPUB with the import button, drag-and-drop, or `Ctrl+O`.
2. Select the book to open its page, then choose **Continue reading**.
3. Open the typography controls to choose a layout, theme, font, and spacing.
4. Select text to use the dictionary, create a highlight or note, search, or copy it.
5. Optionally open **Settings → AI** to save one or more Gemini API keys, then pick a model from the list that appears.
6. On the book page, choose **Auto** to analyse chapters as you finish them, or **Custom** to analyse a book you have already started up to the chapter you reached.
7. Leave the AI fields empty if you want to use BookBuddy as an offline reader.

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| "Analysis is waiting on Gemini" | Gemini is overloaded, unreachable, or your quota is used up. BookBuddy keeps retrying in the background. | Wait, or pick a different model in **Settings → AI**. The latest provider error is shown there. |
| "Nothing worth showing yet" | The analysed chapters contained no named characters or events. Front matter often does not. | Keep reading, or raise the chapter under **Custom** on the book page. |
| "Analysis is off" | This book's analysis mode is Off. | Choose **Auto** or **Custom** on the book page. |
| Chat says it could not get an answer | Gemini did not answer within two short attempts. | Choose **Try again**. Your question is kept. |
| "Nothing is running at that address" in Settings → Advanced | That check is only for developers running a separate backend. | Nothing. BookBuddy's own backend status is shown just above it. |

## Architecture

```mermaid
flowchart LR
    A["Tauri 2 desktop host"] --> B["React 19 interface<br/>library · book page · reader · story knowledge"]
    B -->|"Authenticated loopback API"| C["Managed FastAPI sidecar"]

    C --> D["EPUB and PDF parsing, search"]
    C --> E["Reader state and contextual dictionary"]
    C --> F["Chapter analysis and spoiler-bounded knowledge"]
    F -->|"optional"| J["Gemini"]

    D --> G["Local book files and bounded caches"]
    E --> H["Local SQLite reader state"]
    F --> I["Per-book knowledge database"]
```

The packaged application owns its backend process and communicates over a random loopback port using a one-time bearer token. Source-development runs may use the fixed local development URL instead.

BookBuddy keeps operational reader state separate from per-book knowledge databases. Notes, bookmarks, and settings do not become story facts. A chapter is analysed in an isolated copy of the book's knowledge and promoted only when it finishes, and every reader-facing query is limited to the chapters you have read.

The full picture, including the analysis flow, AI retry policy, and on-disk layout, is in [docs/architecture.md](docs/architecture.md).

## Technology

| Area | Technology |
|---|---|
| Desktop shell | Tauri 2, Rust |
| User interface | React 19, TypeScript, Vite |
| Book rendering | epub.js, PDF.js |
| Client state | TanStack Query, zustand, zod contracts |
| Backend API | Python, FastAPI, Uvicorn |
| Book parsing | EbookLib, Beautiful Soup |
| Validation | Pydantic |
| Storage | SQLite and local files |
| Optional AI | Google Gemini, with the model chosen in Settings |
| Testing | Python `unittest`, Vitest, Testing Library, GitHub Actions |

## Project structure

```text
backend/       FastAPI application, EPUB processing, reader services, and analysis
frontend/      React reader and Tauri desktop host
config/        Canonical version and runtime configuration
docs/          Architecture, subsystem, and acceptance documentation
packaging/     Frozen-backend packaging specification
requirements/  Core and optional Python dependency sets
scripts/       Version checks and Windows desktop packaging
tests/         Backend, integration, regression, and acceptance tests
```

Generated libraries, caches, logs, databases, build output, and release artifacts are intentionally excluded from source control.

## Development setup

The documented development environment is Windows PowerShell. Python 3.13 is the currently verified interpreter, not a declared minimum version.

### Prerequisites

- Git
- Python 3.13
- Node.js and pnpm
- Rust with the MSVC toolchain for native desktop builds
- Visual Studio Build Tools with the Windows SDK for packaging

### Install the source dependencies

```powershell
git clone https://github.com/youraverageguy-123/BookBuddy.git
cd BookBuddy

py -3.13 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements\requirements.txt

cd frontend
pnpm install --frozen-lockfile
cd ..
```

### Optional Python capabilities

Install only the integrations you intend to use:

```powershell
# Gemini provider
.\venv\Scripts\python.exe backend\dependency_manager.py --ai-gemini --install

# Contextual dictionary and pronunciation packages
.\venv\Scripts\python.exe backend\dependency_manager.py --dictionary --install

# Local image-analysis pipeline
.\venv\Scripts\python.exe backend\dependency_manager.py --image --install

# PDF import
.\venv\Scripts\python.exe backend\dependency_manager.py --pdf --install
```

The dictionary subsystem also requires configured Open English WordNet data and an English spaCy pipeline for its complete local capability set. Missing optional resources degrade the affected section without preventing core reader startup.

### Run in browser-development mode

Start the backend:

```powershell
.\venv\Scripts\python.exe -m uvicorn --app-dir backend app:app --host 127.0.0.1 --port 8000
```

In a second PowerShell window, start Vite:

```powershell
cd frontend
pnpm dev
```

The browser build uses `http://127.0.0.1:8000` unless `VITE_BACKEND_URL` overrides it.

### Run checks

```powershell
# Backend and integration tests
.\venv\Scripts\python.exe -m unittest discover -s tests -t . -v

# Frontend checks
cd frontend
pnpm build
pnpm lint
pnpm test
```

The same checks run in GitHub Actions on every push to `main` and on pull requests: backend tests on Windows with Python 3.13, and lint, tests, and the TypeScript build on Ubuntu with Node 24. The backend job installs the core, PDF, and dictionary requirements plus the English spaCy pipeline and Open English WordNet, because the dictionary tests need them.

### Build the Windows application

Install the Rust MSVC toolchain and Visual Studio Build Tools before packaging:

```powershell
winget install Rustlang.Rustup

winget install Microsoft.VisualStudio.2022.BuildTools `
  --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

Build the frozen backend, Tauri application, NSIS installer, and portable ZIP:

```powershell
.\scripts\build_desktop.ps1
```

The packaging script validates version consistency, freezes the FastAPI sidecar, builds the Tauri application, and prepares release artifacts. Current output is unsigned and must be tested as packaged Windows software before release.

## Additional documentation

- [Architecture](docs/architecture.md)
- [Desktop reader and packaging](docs/desktop_reader.md)
- [Backend startup](docs/backend_startup.md)
- [Dictionary subsystem](docs/dictionary_subsystem.md)
- [Image pipeline](docs/image_pipeline.md)
- [End-to-end audit](docs/end_to_end_audit.md)
- [Pre-v1 architecture decisions](docs/pre_v1_architecture_decisions.md)

## Current status

BookBuddy 0.3.0 is pre-release software.

### Available

- EPUB reading with publisher-style preservation
- Search, progress restoration, bookmarks, and annotations
- Library organization and custom collections
- Reading statistics and ETA estimation
- Contextual dictionary and optional AI selection tools
- Story knowledge: character explorer, relationship map, timeline, and spoiler-bounded chat
- Book page with Off, Auto, and Custom analysis modes
- Early PDF reading
- In-app Gemini model selection
- Chapter-bounded background analysis when Gemini is configured
- Windows installer and portable packaging workflows

### Pre-release limitations

- Windows x64 is the current end-user distribution target.
- Windows artifacts are currently unsigned.
- EPUB is the fully supported format. PDF reading is early and lacks selection tools, annotations, bookmarks, and search.
- Complete local dictionary and pronunciation features require optional datasets.
- AI explanation, translation, chat, deeper analysis, and Vision features require Gemini credentials.
- Story knowledge views are new and have not yet been tested against a wide range of books.

## Roadmap

Planned work includes:

- PDF text selection, dictionary lookup, annotations, bookmarks, and search
- Character portraits and richer relationship history
- Streaming chat answers and saved conversations

Roadmap items describe intended direction, not currently available functionality. Priorities may change as the pre-release reader is tested.

## Contributing

Contributions should remain focused, compatible, and evidence-backed.

1. Fork the repository.
2. Create a focused branch.
3. Make the smallest compatible change.
4. Add or update relevant tests.
5. Run the Python and frontend checks.
6. Commit with a clear description.
7. Open a pull request explaining the behavior, validation, and compatibility impact.

Avoid committing EPUB libraries, databases, credentials, logs, build output, installers, or other generated user data.

## Reporting problems

Use [GitHub Issues](https://github.com/youraverageguy-123/BookBuddy/issues) for reproducible bugs and feature proposals.

For a bug report, include:

- BookBuddy version
- Windows version and architecture
- Installer, portable, or source-development environment
- Exact reproduction steps
- Expected and observed behavior
- Relevant screenshots
- Sanitized startup or application logs

Remove API keys, usernames, filesystem paths, book contents, and private library details before attaching logs. Startup diagnostics can be found in `logs/startup-timings.jsonl` inside the active BookBuddy data folder.

## License

BookBuddy is available under the [MIT License](LICENSE).

EPUB files, cover artwork, publisher fonts, and other book content imported by users remain subject to their original copyrights and licenses.
