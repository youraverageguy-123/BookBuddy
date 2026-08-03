# BookBuddy README Publication Plan

## Purpose

This document is the source-of-truth checklist for publishing and maintaining
BookBuddy's repository README. The README must describe the application that a
reader can use today, while keeping unfinished interfaces in a clearly labelled
roadmap.

BookBuddy is currently a pre-release, Windows-focused EPUB reader. Its verified
application stack is React 19, TypeScript, Vite, epub.js, Tauri 2/Rust, FastAPI,
EbookLib, Beautiful Soup, SQLite, and optional Google GenAI integration.

## Publication principles

- Describe current, source-verified behavior rather than architectural intent.
- Separate offline reader capabilities from optional AI capabilities.
- Do not convert backend data models into claims about visible user interfaces.
- Do not use completion percentages unless they are generated from a maintained,
  objective release tracker.
- Mark the product as pre-release and disclose unsigned Windows bundles.
- Never include API keys, local filesystem paths, private library titles, or
  unsanitized logs.
- Update the README whenever a feature moves between planned, in development,
  and available.

## README structure

### 1. Hero

- [x] BookBuddy name and existing owl artwork
- [x] One-line local-first, spoiler-aware EPUB-reader description
- [x] Version 0.1.11 badge
- [x] Windows x64 badge
- [x] Pre-release badge
- [x] Tauri 2, React 19, and Python 3.13-tested badges
- [x] Release-ready links for Releases, documentation, and Roadmap
- [ ] MIT badge and `LICENSE` link are publishable only after `LICENSE` exists

The configured repository URL is:

`https://github.com/youraverageguy-123/BookBuddy`

The repository and Releases endpoints were not publicly visible at the time of
this audit. Recheck every link before publication.

### 2. Product description

Keep the introductory description below 150 words. It should explain:

- what BookBuddy is;
- who benefits from it;
- how it preserves the original EPUB presentation;
- how local reader data and chapter-bounded knowledge reduce unnecessary data
  exposure and spoilers; and
- that AI is optional, while core reading remains available without an API key.

Do not explain internal schemas or implementation details in the introduction.

### 3. Available features

The following features are implemented and may be presented as available.

#### EPUB reader

- [x] Manual EPUB import through drag-and-drop, Ctrl+O, or the Library command
- [x] Covers, hierarchical contents, chapter navigation, and reading restoration
- [x] Book search with chapter, reached-text, and whole-book scopes
- [x] Reading progress and personalized remaining-time estimates
- [x] Paged and continuous layouts
- [x] Fullscreen reading and keyboard navigation
- [x] Embedded-image zoom and pan
- [x] Publisher fonts, headings, drop caps, images, indents, and structural layout
- [x] Optional replacement fonts without discarding publisher structure
- [x] Paper, night, sepia, OLED, and forest reader themes
- [x] Adjustable type size, spacing, width, margins, alignment, and hyphenation

#### Library and reading state

- [x] Home, Library, and Collections views
- [x] Continue-reading, recent, favorite, pinned, want-to-read, and finished states
- [x] Custom collections and automatic reading-state shelves
- [x] Bookmarks
- [x] Highlights, underlines, notes, annotation colors, and annotation search
- [x] Local reading statistics and ETA learning
- [x] Notes and statistics export

#### Dictionary and optional AI

- [x] Context-sensitive selection lookup
- [x] Local dictionary and pronunciation when optional datasets are installed
- [x] Grammar explanations for function words
- [x] Optional Gemini selection explanations and translations
- [x] Optional Gemini-supported chapter analysis
- [x] Optional, isolated Gemini Vision keys
- [x] Encrypted API-key storage for the current Windows account

#### Desktop operation

- [x] Tauri-managed local FastAPI sidecar
- [x] Authenticated random-port loopback communication in packaged builds
- [x] Recoverable native startup splash
- [x] Database integrity, backup, and optimization controls
- [x] Bounded cache inspection and cleanup
- [x] Background-task status
- [x] Local reading-data export and reset controls

### 4. Privacy and AI explanation

The README must state all of the following:

- EPUB reading, navigation, progress, notes, bookmarks, collections, appearance,
  and settings do not require a Gemini API key.
- When optional AI is configured, selected text or current-chapter analysis
  inputs may be sent to Gemini for the corresponding AI capability.
- BookBuddy constrains story-aware results to the reader's completed knowledge
  boundary, but this is a mitigation and must not be described as a guarantee.
- Stored keys are encrypted for the current Windows account and are not returned
  by the settings API or included in normal logs and exports.
- Image processing is local-first. Gemini Vision is optional and considered only
  for explicitly enabled, low-confidence cases.

Avoid the inaccurate claim that no reading-triggered background analysis can
ever contact Gemini. With AI configured, chapter analysis may run as part of the
reader's staged analysis lifecycle.

### 5. Architecture

Use one compact diagram showing:

1. Tauri desktop and React reader;
2. authenticated loopback FastAPI service;
3. EPUB parsing, reader state, dictionary/search, and optional AI analysis;
4. local EPUB files, caches, and SQLite databases.

Do not show PySide6. Do not describe NetworkX as a current dependency. Do not
present internal graph tables as a finished relationship or character UI.

### 6. Installation and developer setup

#### Reader installation

- [x] Link to GitHub Releases rather than a repository-root executable
- [x] Provide NSIS installer and portable ZIP paths conceptually
- [x] Disclose that the Windows artifacts are currently unsigned
- [x] Give a short first-run workflow
- [ ] Confirm a public release and its assets exist before publication
- [ ] Confirm checksums and signatures for each published build

#### Development

- [x] PowerShell-oriented setup instructions
- [x] Python 3.13 identified as the tested environment, not the minimum version
- [x] Core Python requirements separated from optional AI, dictionary, and image
  requirements
- [x] Backend and Vite development commands
- [x] Python, frontend build, lint, and test commands
- [x] Rust/Visual Studio prerequisites and NSIS packaging command

### 7. Status and roadmap

Use status words instead of estimated percentages.

#### Available

- EPUB reading and publisher-style preservation
- Search, progress, bookmarks, annotations, collections, and statistics
- Contextual dictionary and optional AI-assisted selection tools
- Chapter-bounded background analysis and local knowledge persistence

#### Planned

- Relationship visualization
- Character explorer
- Reader-facing knowledge and timeline views
- Reader chat
- PDF support

Do not list reading statistics as unfinished. Do not advertise the compile-time
reader adapter registry as an installable third-party plugin system.

### 8. Known pre-release limitations

- Windows x64 is the documented end-user distribution target.
- The current installer and portable bundle are unsigned.
- EPUB is the supported import format; PDF is planned.
- Full local dictionary and pronunciation support requires optional datasets.
- Explanation, translation, deeper chapter analysis, and Vision features require
  configured Gemini credentials.
- Public GitHub Releases were not available during this audit.

### 9. Screenshots

No current, publication-ready screenshots are stored in the repository. Omit a
screenshots section until real captures are available.

Before adding screenshots:

- [ ] Capture the current 0.1.11 packaged Windows application
- [ ] Use redistributable or synthetic EPUB content
- [ ] Remove API keys, usernames, filesystem paths, and personal library data
- [ ] Include only completed interfaces
- [ ] Optimize image size and add meaningful alt text
- [ ] Prefer Home, Reader, Contents, contextual lookup, Notes, image zoom, and
  Settings views

### 10. Contributing, support, and license

- [x] Concise fork, branch, test, commit, and pull-request workflow
- [x] GitHub Issues template guidance in prose
- [x] Ask for BookBuddy version, Windows version, reproduction steps, and
  sanitized startup logs in bug reports
- [ ] Add a standard MIT `LICENSE` file before claiming that the repository is
  MIT-licensed
- [ ] Confirm the intended copyright holder and year

## Release validation checklist

Run this checklist before every README update or public release:

- [ ] Version agrees across `config/version.json`, `frontend/package.json`,
  `frontend/src-tauri/Cargo.toml`, and `frontend/src-tauri/tauri.conf.json`
- [ ] Every current-feature statement has a visible UI or documented user path
- [ ] Roadmap items are not described as available
- [ ] GitHub repository, Issues, documentation, and Releases links resolve
- [ ] Release assets exist and match the documented architecture
- [ ] Unsigned or pre-release status is accurately disclosed
- [ ] `LICENSE` exists before the MIT badge and license statement are published
- [ ] Markdown headings and internal anchors render correctly on GitHub
- [ ] Mermaid architecture renders on GitHub
- [ ] Logo and future screenshot paths use repository-relative URLs
- [ ] No secrets, absolute local paths, private titles, or personal data appear
- [ ] Setup commands work from a clean Windows checkout
- [ ] Automated checks are reported separately from packaged Windows acceptance

## README maintenance triggers

Review the README whenever any of these changes ship:

- relationship or character interfaces;
- knowledge or timeline interfaces;
- reader chat;
- PDF import;
- third-party plugin loading;
- supported operating systems or architectures;
- installer signing;
- authentication, AI-provider, or privacy behavior;
- developer prerequisites or build commands; or
- the canonical BookBuddy version.

## Claims to avoid

Do not write any of the following unless the relevant behavior is verifiably
available:

- "BookBuddy supports PDF."
- "BookBuddy has a relationship web or character explorer."
- "BookBuddy never sends text to an external service."
- "BookBuddy guarantees that AI can never reveal a spoiler."
- "BookBuddy supports third-party plugins."
- "BookBuddy is MIT-licensed" before the actual license file exists.
- "Download the latest release" before a public release with the documented
  assets exists.

Prefer precise labels such as **Available**, **Optional**, **In development**,
**Planned**, and **Pre-release**.
