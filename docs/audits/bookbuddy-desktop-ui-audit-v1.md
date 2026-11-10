# BookBuddy Desktop UI Audit v1

## Goal

Transform BookBuddy from a functional EPUB reader into a premium native desktop reading application where the **book remains the primary focus** and every interaction feels deliberate, smooth, and unobtrusive.

---

# Core Design Philosophy

BookBuddy is **not** an AI application with a reader.

BookBuddy is a **reading application with an AI companion.**

The reader always has priority.

The AI exists only when explicitly requested.

The interface should disappear while reading.

---

# Design Principles

## Reading First

Every UI decision must answer:

> Does this improve reading?

If not, remove it.

---

## Progressive Disclosure

Only reveal functionality when needed.

Examples

* AI appears only after selection.
* Toolbar appears only on interaction.
* Reader controls disappear during reading.
* Advanced settings remain categorized.

---

## Calm Interface

Avoid visual noise.

No permanent floating buttons.

No excessive animations.

No decorative panels.

Whitespace is a feature.

---

## Native Desktop Feel

Every interaction should feel like a polished desktop application rather than a wrapped website.

Target characteristics

* Immediate response
* Smooth transitions
* Hover feedback
* Predictable navigation
* Keyboard-first support

---

# Visual Identity

## Color Palette

Primary

* Charcoal backgrounds
* Warm gold accent
* Cream typography

Secondary

* Neutral grays
* Soft shadows
* Rounded corners

Avoid introducing unrelated accent colors.

The entire application should feel visually cohesive.

---

## Typography

Prioritize readability.

Hierarchy

* Large section headings
* Medium metadata
* Comfortable body text
* Consistent spacing

Use typography to create structure instead of decorative elements.

---

# Navigation

## Primary Navigation

Sidebar

```
Home

Library

Collections

Settings
```

No unnecessary destinations.

Reader is entered by opening a book.

Reader is not a permanent sidebar item.

---

## Home

Purpose

Help users decide what to read next.

Sections

* Continue Reading
* Recent Reads
* Recently Added
* Favorites
* Collections
* Reading Statistics (future)

Large featured covers.

Minimal text.

Fast access.

---

## Library

Purpose

Complete collection view.

Support

* Grid
* Search
* Sort
* Filters
* Drag & Drop import

No permanent upload button.

---

# Empty Library Experience

Instead of

```
Add EPUB
```

Display

```
📚

Your library is empty

Upload your first book

[ Large + ]

or drag an EPUB here
```

The entire empty state acts as the upload target.

Supports

* Click
* Drag & Drop

---

# Book Cards

Hover interaction

* Lift slightly
* Increase shadow
* Small scale
* Smooth transition
* Brighten title

Duration

120–180 ms

Never bounce.

Never overshoot.

Interaction should feel subtle.

---

# Collections (Future)

Examples

* Currently Reading
* Favorites
* Finished
* Want To Read
* Sci-Fi
* Fantasy
* Programming
* Custom collections

Collections are first-class objects.

---

# Reader Philosophy

The reader is sacred.

Once a book opens,

everything else disappears.

---

# Reader Layout

Normal Mode

Book occupies nearly entire window.

Toolbar hidden.

No sidebars.

No floating widgets.

---

Fullscreen

Only the book remains visible.

Mouse movement

↓

Toolbar fades in.

Mouse leaves

↓

Toolbar fades out.

No arrows.

No persistent navigation controls.

---

# Reader Controls

Visible only when needed.

Examples

* Search
* Bookmark
* Typography
* Theme
* Fullscreen
* Overflow menu

Toolbar auto-hides.

---

# AI Integration

Selection

↓

Dictionary Popup

↓

Optional AI Expansion

No permanent AI sidebar.

No width reduction.

AI exists only inside contextual popups.

---

# Selection Popup

Contains

* Definition
* Pronunciation
* Story Character
* Story Location
* Story Event
* Explain
* Translate (future)

Popup expands instead of opening separate panels.

---

# Reading Themes

Ship curated themes.

Examples

Night

```
Black
White
```

Paper

```
Warm White
Dark Gray
```

Sepia

```
Cream
Brown
```

OLED

```
Pure Black
White
```

Forest

```
Dark Green
Cream
```

Avoid unlimited customization.

Quality over quantity.

---

# Reader Typography

Expose

* Font
* Font Size
* Line Height
* Paragraph Spacing
* Column Width
* Theme

Avoid exposing dozens of low-value typography controls.

---

# Reader Layout

Increase margins slightly beyond Aquile Reader.

Long reading sessions should reduce eye fatigue.

Optimize

* Line length
* Whitespace
* Reading rhythm

---

# Progress Indicators

Bottom Left

Current page

Bottom Center

Book Part

Chapter

Bottom Right

Reading progress

Keep indicators unobtrusive.

---

# Reader Animations

Selection popup

120 ms

Toolbar

150 ms fade

Theme change

150 ms

Page transition

Smooth

Avoid

* Bounce
* Elastic
* Overshoot

---

# Home Animations

Book hover

Lift

Shadow

Scale

Section transitions

Fade

Slide

Very subtle.

---

# Library Animations

Grid updates

Fade

Reflow

Hover

Lift

Shadow

Search

Immediate filtering

---

# Settings

Structure

```
Reader

Library

Appearance

AI

Dictionary

Advanced

About
```

Avoid giant scrolling settings pages.

Use categorized navigation.

---

# Appearance Settings

Support

* Theme
* Accent
* Window Appearance
* Reader Defaults
* Startup Behavior

Keep customization focused.

---

# Reader Defaults

Examples

* Default Theme
* Default Font
* Default Line Height
* Default Column Width

Applied automatically to newly opened books.

---

# Microinteractions

Books respond to hover.

Buttons respond instantly.

Popups animate smoothly.

Transitions remain subtle.

Nothing should distract from reading.

---

# Drag & Drop

Supported throughout the library.

Dragging EPUB

↓

Overlay

```
Drop EPUB to Import
```

No separate upload workflow required.

---

# Startup

Continue using native splash.

Maintain

* Stage-based progress
* Native transitions
* Fade into application

Startup branding should match application branding.

---

# Performance Goals

Every interaction should feel immediate.

Target

Hover

<16 ms

Search

Instant

Theme Switch

<150 ms

Popup

<120 ms

Reader Open

As fast as backend permits

---

# Accessibility

Support

* Keyboard navigation
* High contrast themes
* Reduced motion
* Scalable fonts
* Screen reader friendly labels
* Focus indicators

Accessibility should not be added later.

---

# Features

Collections

Pinned books

Book statistics

Reading streaks

Notes

Annotations

None of these should compromise the clean reading experience.

---

# Implementation Order

## Phase 1

* Sidebar redesign
* Home page
* Library redesign
* Empty library experience
* Book grid
* Hover interactions

---

## Phase 2

* Reader redesign
* Fullscreen reader
* Auto-hide toolbar
* Typography controls
* Theme system

---

## Phase 3

* Settings redesign
* Drag & Drop
* Collections
* Appearance customization

---

## Phase 4

* Microinteractions
* Motion polish
* Accessibility
* Performance tuning

---

# Non-Goals

Do **not** imitate Aquile Reader pixel-for-pixel.

Borrow its strengths while establishing BookBuddy's own identity.

Avoid

* Permanent AI panels
* Persistent reader chrome
* Excessive animations
* Feature overload
* Crowded interfaces
* Generic web-dashboard aesthetics

---

# Success Criteria

BookBuddy should feel like a premium native desktop reader where:

* The application disappears once reading begins.
* The book occupies the user's attention, not the interface.
* AI appears only when requested and never competes with the text.
* Home encourages continuing a reading journey rather than merely listing files.
* Library management is intuitive, with drag-and-drop and a welcoming empty state.
* Hover states and transitions provide subtle feedback without distracting from reading.
* Settings are organized, discoverable, and focused on meaningful customization.
* Startup, navigation, and reader interactions are smooth, consistent, and visually cohesive.
* Every screen shares the same visual language of charcoal backgrounds, warm gold accents, soft shadows, rounded corners, and refined typography.

## Final Principle

> **BookBuddy should feel like the nicest place to spend six uninterrupted hours reading.** Every design decision should reinforce immersion, reduce cognitive load, and let the story remain the true center of the experience.
