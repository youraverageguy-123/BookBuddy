import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BookNavigation, Chapter } from "../../types/contracts";
import { ContentsPanel } from "./ContentsPanel";

const navigation: BookNavigation = {
  schema_version: "bookbuddy_navigation_v1",
  mode: "omnibus",
  books: [
    { book_id: "book-1", title: "First Tale", source_title: "[Series 01] • First Tale by Author", ordinal: 1, start_chapter_index: 0, end_chapter_index: 67, entries: [
      { entry_id: "one-cover", title: "Cover", spine_href: "one/cover.xhtml", depth: 0, kind: "front_matter", display_number: null, chapter_index: 0 },
      { entry_id: "one-chapter", title: "1: Departure", spine_href: "one/chapter.xhtml", depth: 1, kind: "chapter", display_number: "1", chapter_index: 7 },
    ] },
    { book_id: "book-2", title: "Second Tale", source_title: "[Series 02] • Second Tale by Author", ordinal: 2, start_chapter_index: 68, end_chapter_index: 130, entries: [
      { entry_id: "two-cover", title: "Cover", spine_href: "two/cover.xhtml", depth: 0, kind: "front_matter", display_number: null, chapter_index: 68 },
      { entry_id: "two-part", title: "Part I", spine_href: "two/part.xhtml", depth: 0, kind: "part", display_number: null, chapter_index: 69 },
      { entry_id: "two-chapter", title: "Chapter 1: Arrival", spine_href: "two/chapter.xhtml", depth: 1, kind: "chapter", display_number: "1", chapter_index: 75 },
      { entry_id: "two-note", title: "Publisher Note", spine_href: "two/note.xhtml", depth: 0, kind: "other", display_number: null, chapter_index: null },
    ] },
  ],
};

const chapters: Chapter[] = [{ index: 0, title: "Opening", item_id: "opening", spine_href: "opening.xhtml", section_type: "CHAPTER", word_count: 100 }];

describe("ContentsPanel", () => {
  afterEach(cleanup);
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("drills from omnibus books into publisher-local chapter navigation", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<ContentsPanel navigation={navigation} chapters={chapters} bookTitle="Two Tales" currentChapterIndex={75} onNavigate={onNavigate} onClose={vi.fn()}/>);

    expect(screen.getByRole("button", { name: /First Tale/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Second Tale/ })).toHaveAttribute("aria-current", "location");
    expect(screen.queryByRole("button", { name: /Arrival/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Second Tale/ }));
    expect(screen.getByRole("button", { name: "Chapter 1: Arrival" })).toHaveAttribute("aria-current", "location");
    expect(screen.queryByText("75")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cover" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Part I" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publisher Note" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Chapter 1: Arrival" }));
    expect(onNavigate).toHaveBeenCalledWith("two/chapter.xhtml");
  });

  it("supports scoped search and returns to the books level", async () => {
    const user = userEvent.setup();
    render(<ContentsPanel navigation={navigation} chapters={chapters} bookTitle="Two Tales" currentChapterIndex={0} onNavigate={vi.fn()} onClose={vi.fn()}/>);
    const search = screen.getByRole("textbox", { name: "Filter books" });
    await user.type(search, "Second");
    expect(screen.queryByRole("button", { name: /First Tale/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Second Tale/ }));
    await user.click(screen.getByRole("button", { name: "Back to books" }));
    expect(screen.getByRole("textbox", { name: "Filter books" })).toHaveValue("");
    expect(screen.getByRole("button", { name: /First Tale/ })).toBeInTheDocument();
  });

  it("collapses publisher Parts while keeping their headings navigable", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<ContentsPanel navigation={navigation} chapters={chapters} bookTitle="Two Tales" currentChapterIndex={0} onNavigate={onNavigate} onClose={vi.fn()}/>);

    await user.click(screen.getByRole("button", { name: /Second Tale/ }));
    expect(screen.queryByRole("button", { name: "Chapter 1: Arrival" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Expand Part I" }));
    expect(screen.getByRole("button", { name: "Chapter 1: Arrival" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Part I" }));
    expect(onNavigate).toHaveBeenCalledWith("two/part.xhtml");
  });

  it("closes with Escape while the auto-focused search field is active", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<ContentsPanel navigation={navigation} chapters={chapters} bookTitle="Two Tales" currentChapterIndex={0} onNavigate={vi.fn()} onClose={onClose}/>);

    expect(screen.getByRole("textbox", { name: "Filter books" })).toHaveFocus();
    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("opens an ordinary single book directly to its entries", () => {
    const single: BookNavigation = { ...navigation, mode: "single", books: [navigation.books[0]!] };
    render(<ContentsPanel navigation={single} chapters={chapters} bookTitle="First Tale" currentChapterIndex={7} onNavigate={vi.fn()} onClose={vi.fn()}/>);
    expect(screen.getByRole("button", { name: "Chapter 1: Departure" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /First Tale/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back to books" })).not.toBeInTheDocument();
  });
});
