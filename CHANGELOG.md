# Changelog

## 0.2.0

### New

- **Story knowledge page** for every book, limited to the chapters you have finished:
  - Character explorer with aliases, relationships, and events.
  - Interactive relationship map.
  - Timeline of events by chapter.
- **Ask about this book**: a spoiler-bounded chat, on the story knowledge page and as a drawer in the reader. Needs a Gemini key.
- **PDF reading (early)**: import text PDFs, read page by page with zoom, a contents panel, and resume. Selection tools, annotations, bookmarks, and search are not available for PDFs yet.
- **Model picker**: after saving a Gemini key, choose the model in Settings → AI from the models your key can use. The choice applies immediately and is remembered.

### Fixed and hardened

- **Installer:** the app was written to the previous install location (or `%LOCALAPPDATA%\BookBuddy` on a new machine) while the shortcuts, uninstaller, and registry entry pointed at the folder beside the installer. Everything now goes to the same folder.
- Pressing F5 or Ctrl+R no longer leaves the window blank.
- The book title in the reader toolbar is readable again when the app theme is dark and the page theme is light.
- The window now talks to the desktop host over the fast IPC channel instead of falling back after a blocked request.
- Importing a large book no longer freezes the rest of the app while it is processed.
- Import and load errors no longer show raw internal error text.
- The EPUB sanitizer now also blocks protocol-relative URLs, non-image `data:` documents, and schemes disguised with tabs or control characters.

### Project

- Continuous integration runs backend and frontend checks on every push.
- Build caches are no longer tracked in git; audit documents have clean file names.

### Upgrade notes

- Run the installer from the folder that contains your existing `BookBuddy` folder (for most people, Downloads) to upgrade in place. Your library, notes, and settings are kept.
- The installer and portable build are still unsigned, so Windows may show a warning.

## 0.1.11

- Initial public pre-release.
