# Changelog

## Unreleased

- **Relationship map redesign:** character badges with initials, curved lines whose thickness shows how strong the feeling is, a "mixed" style when two characters feel differently about each other, hover and selection focus, zoom and pan controls, and a live caption describing what is under the pointer.
- **PDF covers:** the first page of a PDF becomes its library cover the first time the book is opened.
- **Toasts:** brief confirmations for importing a book, adding or removing a bookmark, and changing the AI model.
- **Loading skeletons** replace the "Loading view…" text on page changes and on the story knowledge page.
- Keyboard focus outlines now also cover text areas, tabs, and custom buttons.
- **Fixed: publisher styling in the installed app.** The reader stylesheet and inline styles inside EPUB pages were blocked by the content security policy, which also left links default blue on dark page themes.
- **Fixed: reader settings could roll back.** Overlapping saves (for example while dragging a slider) could fail verification and restore an older state. Saves are now queued.
- Library covers load only as they scroll into view.
- epub.js is loaded on demand, so the reader frame appears before the engine is parsed.
- The reader page's typography panel, notes drawer, image viewer, and translation panel are now separate components.

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
