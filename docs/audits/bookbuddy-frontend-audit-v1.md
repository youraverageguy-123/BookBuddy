# BookBuddy Frontend Audit v1

### Scope: Desktop Reader + Backend Integration

---

# 1. Objectives

This phase exists to prove that the backend is usable.

By the end of this phase, the application should allow a user to:

* Open a local EPUB.
* Read the book in a pleasant interface.
* Trigger background analysis.
* Continue reading while analysis runs.
* Click or highlight a word.
* See BookBuddy's dictionary popup.
* Display contextual meaning from the backend.
* Hear pronunciation.
* Never accidentally reveal spoilers.
* Resume reading later.

Nothing more.

No graphs.

No timelines.

No mascot.

No fancy animations.

---

# 2. Overall Architecture

```
┌────────────────────────────┐
│        Tauri Desktop       │
└─────────────┬──────────────┘
              │
┌─────────────▼──────────────┐
│        React Client        │
│                            │
│ Reader                     │
│ Dictionary                 │
│ Library                    │
│ Settings                   │
└─────────────┬──────────────┘
              │ HTTP
┌─────────────▼──────────────┐
│       FastAPI Backend      │
│                            │
│ Upload                     │
│ Reader State               │
│ Dictionary                 │
│ Analysis                   │
│ Sessions                   │
└─────────────┬──────────────┘
              │
      SQLite + Evidence
```

**Rule:** The frontend **never** reads the database directly. Every interaction goes through your FastAPI API. That keeps one source of truth and lets you swap storage later if needed.

---

# 3. Technology Stack

Use current, boring, well-supported tools.

* **Tauri v2**: desktop shell.
* **React 19**: UI.
* **TypeScript (strict)**: no `any`.
* **Vite**: bundler.
* **Tailwind CSS**: styling.
* **shadcn/ui**: accessible building blocks.
* **TanStack Query**: server state (analysis progress, dictionary calls, uploads).
* **Zustand**: local UI state (sidebar open, font size, current selection).
* **React Router**: navigation.
* **epub.js**: EPUB rendering and CFI support.
* **Framer Motion**: subtle UI transitions only.
* **Zod**: validate API responses.
* **React Hook Form**: settings/forms.

Avoid Redux unless the app genuinely grows into needing it.

---

# 4. Project Structure

```
src/
│
├── api/
│   ├── books.ts
│   ├── dictionary.ts
│   ├── analysis.ts
│   └── client.ts
│
├── components/
│   ├── reader/
│   ├── dictionary/
│   ├── layout/
│   ├── dialogs/
│   └── common/
│
├── hooks/
│
├── pages/
│
├── store/
│
├── types/
│
├── utils/
│
├── assets/
│
└── styles/
```

No `components/misc/final2/new/`.

Humans love creating junk drawers. Resist the instinct.

---

# 5. Screens

Only three.

## Library

Purpose:

Choose a book.

Contains:

* Recently opened books.
* Upload button.
* Analysis status.
* Continue reading.

---

## Reader

Main application.

Contains:

* Book.
* Dictionary popup.
* Progress bar.
* Reading controls.

---

## Settings

Contains:

* Theme.
* Font.
* Font size.
* Line spacing.
* Backend URL.
* API diagnostics.

Nothing else yet.

---

# 6. Reader Layout

```
--------------------------------------------------------

Toolbar

--------------------------------------------------------

Reading Area

--------------------------------------------------------

Status Bar

--------------------------------------------------------
```

Toolbar:

* Back
* Library
* Search
* Font
* Theme
* Analysis status

Reading Area:

90% of the screen.

No distractions.

---

# 7. EPUB Rendering

Do **not** build your own EPUB renderer.

Use **epub.js**.

It already handles:

* XHTML parsing
* images
* internal links
* tables
* CFI navigation
* highlights
* reflow

Building an EPUB renderer is a multi-month project. Spend that time on BookBuddy's unique features instead.

---

# 8. Upload Flow

```
User clicks Upload

↓

Tauri file picker

↓

Select EPUB

↓

POST /books/upload

↓

Backend creates session

↓

Returns session_id

↓

React stores session_id

↓

Navigate to reader
```

The frontend never parses the EPUB itself. It asks the backend to own the import and then receives the session information.

---

# 9. Analysis Flow

The reader should feel alive but never block.

```
Open Book

↓

Reader appears instantly

↓

Backend starts analysis

↓

Progress updates

↓

Reader stays usable
```

Analysis is asynchronous.

No modal.

No loading screen preventing reading.

---

# 10. Progress Polling

React should periodically ask:

```
GET /analysis/{session_id}/status
```

Return:

```
Running

Current chapter

Total chapters

Percentage

ETA
```

TanStack Query can poll this endpoint and update only the components that care about progress.

---

# 11. Dictionary Interaction

This is the heart of BookBuddy.

User selects:

```
ephemeral
```

React sends:

```
POST /dictionary/context
```

Body:

```
session_id

chapter

paragraph

selected_text

surrounding_context
```

Backend responds:

```
Official definition

Contextual meaning

Pronunciation

Part of speech

Synonyms

Difficulty

Examples
```

Popup appears next to the selection.

The popup should be lightweight and disappear when dismissed.

---

# 12. Reader State

Persist locally:

* Current CFI/location.
* Theme.
* Font size.
* Line spacing.
* Last opened book.
* Recent books.

Restore them automatically on launch.

---

# 13. Backend Communication

Never scatter `fetch()` throughout the codebase.

Create an API layer:

```
api/
├── books.ts
├── analysis.ts
├── dictionary.ts
└── client.ts
```

Every request goes through this layer. That gives you one place to handle authentication (if added later), retries, logging, and error formatting.

---

# 14. Error Handling

Every failure should have a clear path.

Examples:

* Corrupt EPUB → "This file could not be imported."
* Backend offline → Offer reconnect.
* Dictionary unavailable → Keep reading; disable popup.
* Analysis failed → Show status, don't crash the reader.

The reader should always degrade gracefully.

---

# 15. Performance

Keep it responsive.

* Lazy-load non-visible routes.
* Virtualize long lists (library).
* Memoize expensive reader components.
* Avoid unnecessary re-renders.
* Load images on demand if possible.

Measure before optimizing.

---

# 16. Accessibility

Even if it's not your top priority now, build the foundations correctly.

* Keyboard navigation.
* Resizable text.
* High-contrast themes.
* Screen-reader-friendly controls.
* Respect reduced-motion settings.

Good accessibility often improves usability for everyone.

---

# 17. Testing

Cover the critical paths.

* Upload flow.
* Reader opens.
* Progress updates.
* Dictionary popup.
* API failures.
* State restoration.

Use component tests for UI and integration tests for the upload-to-reader flow.

---

# 18. Milestones

Build in this order:

1. Tauri shell with React.
2. Library screen.
3. EPUB rendering.
4. Backend upload integration.
5. Session management.
6. Reader progress persistence.
7. Dictionary popup.
8. Analysis status indicator.
9. Settings.
10. Performance and polish.

---
