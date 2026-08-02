# BookBuddy Pre-v1 Stabilization Audit

## Goal

Bring the application from

> "A prototype that demonstrates the architecture"

to

> "A polished desktop reader that users can comfortably live in."

No analyzer work until this reaches a quality bar where the UI disappears and reading feels effortless.

---

# Priority 0 (Critical Bugs)

These actively break expected behaviour.

---

## Reader preferences are not persistent

### Current

Theme sometimes resets.

Font sometimes resets.

Chapter position sometimes resets.

Sometimes another book opens in default theme.

---

### Expected

Reader preferences must be deterministic.

Global defaults

↓

Book override (optional)

↓

Current session

↓

Last chapter

↓

Last page

Exactly one source of truth.

---

### Required architecture

```
reader_settings.json

{
    global: {
        theme,
        font,
        fontSize,
        lineHeight,
        paragraphSpacing,
        columnWidth,
        useBookFonts
    },

    books: {
        <bookId>: {
            override: false,

            readerPosition,

            chapter,

            page,

            zoom,

            customTheme
        }
    }
}
```

Book settings should override global only when override=true.

Otherwise inherit global.

---

## Theme switching blank page

Current:

Palette clicked

↓

Entire page disappears

↓

Next page

↓

Content magically comes back

Meaning renderer is losing layout after CSS injection.

Likely epub.js reflow timing.

Needs investigation.

---

## Reader position not restored

Should reopen exactly where reader exited.

Not:

Chapter only.

Not:

Beginning of page.

Exactly.

---

## Horizontal scrolling

Current

Reader occasionally allows horizontal scroll.

Desktop reading should never have horizontal scrolling.

```
overflow-x: hidden
```

should be enforced throughout.

Audit every container.

---

## Browser context menu

Current

Right click

↓

Chrome menu

Ridiculous.

Desktop app should never expose browser UI.

Replace with

```
Open

Continue Reading

Favorite

Want To Read

Collections

Remove

Properties
```

---

## Image scaling broken

Images massively zoomed.

Should respect

```
max-width

max-height

object-fit

intrinsic dimensions
```

Images should fit viewport.

Not fill viewport.

Zoom feature should be independent.

---

## Theme not propagated

Dictionary

Reader

Settings

Selection popup

Dialogs

Library

need same theme.

Currently dictionary looks like different application.

---

## Theme not applied instantly

Changing theme should update

Reader

Dialogs

Sidebar

Menus

Popup

without reopening anything.

---

# Priority 1 (Reader Polish)

---

## Duplicate exit fullscreen icons

Current

Two icons nearly identical.

Users shouldn't have to decipher hieroglyphics.

Replace with

```
Exit fullscreen
Minimize
```

using clearly distinct icons.

---

## Reader whitespace

Largest visual issue.

Columns are floating in empty void.

Need responsive width.

Suggested

```
Wide monitor

1100-1350px

Reader

Centered

Margins adaptive

Never fixed.
```

---

## Typography

Need proper rhythm.

Audit

Heading spacing

Paragraph spacing

Drop caps

Line height

Letter spacing

Widows

Orphans

---

## EPUB CSS support

Respect

```
drop caps

small caps

first-letter

embedded fonts

image alignment

poetry

tables

lists
```

Current

Drop caps lost.

Book typography flattened.

---

## Use Book Fonts

Add option

```
Use Publisher Fonts

ON

OFF
```

Exactly like Aquile.

Fallback chain

Publisher font

↓

Selected font

↓

System font

---

## Font catalogue

Keep intentionally small.

Serif

Literata

Source Serif

EB Garamond

Crimson

Sans

Inter

Atkinson

Source Sans

System

Nothing else.

No 300 Google Fonts.

---

## Reader spacing settings

Need

Column width

Margins

Paragraph spacing

Line height

Font size

Image scaling

Justification

Hyphenation

---

## Image zoom

Double click

↓

Zoom

Mouse wheel

↓

Scale

Drag

↓

Pan

ESC

↓

Exit

---

## Reader animations

Minimal.

Only

Theme fade

Page fade

Popup

Selection

Never animated scrolling.

---

# Priority 2 (Library)

---

## Layout

Current

Everything stacked vertically.

Feels like website.

Should resemble desktop application.

More information visible immediately.

---

## Recent reads

Reduce card size.

Show more books.

Currently hero occupies half screen, remove it, keep only welcome when reader is open for first time, and then welcome back whenever it is open, in small letters.

---

## Scroll reduction

Current

Need scroll immediately.

Target

Most useful content visible without scrolling.

---

## Responsive grid

Cards

```
auto-fill

minmax()
```

instead of fixed count.

---

## Sidebar

Needs

collapse

tooltips

width animation

pin state

---

## Continue reading card

Improve

Chapter

Progress

Time remaining

Last opened

Continue button

---

## Book card

Need

Favorite state

Collections

Context menu

Hover

Progress

Author

Reading status

---

## Context menu

```
Continue

Favorite

Want To Read

Collections

Rename

Delete

Export Notes

Properties
```

---

## Empty states

Need beautiful empty pages.

Not blank rectangles.

---

# Priority 3 (Reader UX)

---

## Scroll lock

Desktop readers generally use

Wheel

↓

Page progression

Not infinite webpage scrolling.

Investigate

Paged

Continuous

Hybrid

Support both.

---

## Keyboard shortcuts

```
Left

Right

Space

PgUp

PgDn

F11

Ctrl+F

Ctrl+D

Ctrl+B

Ctrl++

Ctrl+-
```

---

## Search

In-book

Current chapter

Whole book

Spoiler-safe glossary

---

## Bookmarks

Multiple

Named

Searchable

---

## Notes

Highlight

Underline

Sticky note

---

## Selection toolbar

Needs

Dictionary

Story

Character

Copy

Highlight

Search

Translate

---

# Priority 4 (Desktop Feel)

---

## Browser remnants

Audit entire application.

No

Browser context menu

Browser selection flash

Browser scrollbar styling

Browser focus outlines

Browser dialogs

Everything should feel native.

---

## Scrollbars

Custom themed.

Thin.

Consistent.

---

## Window restore

Remember

Window size

Position

Fullscreen

---

## Startup

Need proper launch sequence.

Splash

↓

Backend

↓

Library

↓

Ready

Never white flash.

---

## Loading

Skeletons.

Not blank pages.

---

## Error handling

Friendly.

No stack traces.

---

## Drag & Drop

EPUB

↓

Window

↓

Import.

---

# Priority 5 (Packaging & Installation)

This is where you'll avoid headaches later.

---

## Installation layout

Current

Installer only installs executables.

Target

```
BookBuddy/

BookBuddy.exe

backend.exe

config/

library/

database/

logs/

cache/

themes/

exports/

plugins/ (future)
```

---

## User data location

Do **not** store mutable data beside the executable in `Program Files`.

Production layout should use the operating system's user data directory.

For Windows, a good target is:

```text
%LOCALAPPDATA%/BookBuddy/

library/
database/
logs/
cache/
config/
exports/
```

The installation directory should contain only application binaries and static resources. This avoids permission issues and allows seamless updates.

---

## First launch

Automatically create

```
library/

database/

logs/

cache/

exports/

config/
```

if missing.

---

## Logging

Rotate

Compress

Delete old logs.

---

## Cache

Need

image cache

cover cache

web cache

dictionary cache

analysis cache

with cleanup policy.

---

## Updates

Preserve

Library

Database

Config

Themes

Reader positions

during upgrades.

---

# Priority 6 (EPUB Engine Audit)


A sensible roadmap is:

**Stage 1**

* Keep epub.js as the parser and package/navigation engine.
* Override and improve its rendering with your own CSS, pagination logic, image handling, font management, and event pipeline.

**Stage 2**

* Build your own rendering layer that consumes EPUB resources directly while still using epub.js only for EPUB parsing and manifest extraction.

**Stage 3**

* If you eventually hit hard architectural limits, replace the rendering engine entirely with one built around your own pagination and layout model.

That lets you deliver features while gradually taking ownership of the reading experience instead of disappearing into a year-long "rewrite the renderer" project.

---


