import { ArrowLeft, ChevronRight, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { BookNavigation, Chapter, NavigationBook, NavigationEntry } from "../../types/contracts";

interface ContentsPanelProps {
  navigation?: BookNavigation;
  chapters: Chapter[];
  bookTitle: string;
  currentChapterIndex: number | null;
  onNavigate: (href: string) => void;
  onClose: () => void;
}

const legacyNavigation = (chapters: Chapter[], bookTitle: string): BookNavigation => ({
  schema_version: "bookbuddy_navigation_v1",
  mode: "single",
  books: [{
    book_id: "legacy-single-book",
    title: bookTitle,
    source_title: bookTitle,
    ordinal: 1,
    start_chapter_index: chapters.at(0)?.index ?? null,
    end_chapter_index: chapters.at(-1)?.index ?? null,
    entries: chapters.map((chapter, index) => ({
      entry_id: `legacy-entry-${chapter.index}`,
      title: chapter.title,
      spine_href: chapter.spine_href,
      depth: 0,
      kind: "chapter",
      display_number: /\d/.test(chapter.title) ? null : String(index + 1),
      chapter_index: chapter.index,
    })),
  }],
});

const navigationEntryTitle = (entry: NavigationEntry): string => {
  if (!entry.display_number || entry.kind !== "chapter") return entry.title;
  const escaped = entry.display_number.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const stripped = entry.title.replace(new RegExp(`^\\s*(?:chapter\\s+)?${escaped}\\s*(?::|[.\\-\\u2013\\u2014])?\\s*`, "i"), "").trim();
  return stripped || entry.title;
};

const containsChapter = (book: NavigationBook, chapterIndex: number | null): boolean => chapterIndex !== null
  && book.start_chapter_index !== null && book.end_chapter_index !== null
  && chapterIndex >= book.start_chapter_index && chapterIndex <= book.end_chapter_index;

const entryMatches = (entry: NavigationEntry, needle: string): boolean => !needle
  || entry.title.toLocaleLowerCase().includes(needle)
  || Boolean(entry.display_number?.toLocaleLowerCase().includes(needle));

const EMPTY_ENTRIES: NavigationEntry[] = [];

const buildEntryHierarchy = (entries: NavigationEntry[]) => {
  const ancestorsByIndex: NavigationEntry[][] = [];
  const partsWithChildren = new Set<string>();
  const openParts: NavigationEntry[] = [];
  entries.forEach((entry, index) => {
    while (openParts.length && openParts[openParts.length - 1]!.depth >= entry.depth) openParts.pop();
    ancestorsByIndex[index] = [...openParts];
    const hasChildren = entry.kind === "part" && Boolean(entries[index + 1] && entries[index + 1]!.depth > entry.depth);
    if (hasChildren) {
      partsWithChildren.add(entry.entry_id);
      openParts.push(entry);
    }
  });
  return { ancestorsByIndex, partsWithChildren };
};

// Some books ship a table of contents with a single entry ("Start"). List the chapters instead.
const isSparse = (navigation: BookNavigation, chapterCount: number) => chapterCount > 2
  && navigation.books.length === 1
  && navigation.books[0]!.entries.filter((entry) => entry.chapter_index !== null).length < 2;

export function ContentsPanel({ navigation, chapters, bookTitle, currentChapterIndex, onNavigate, onClose }: ContentsPanelProps) {
  const model = useMemo(() => navigation?.books.length && !isSparse(navigation, chapters.length) ? navigation : legacyNavigation(chapters, bookTitle), [bookTitle, chapters, navigation]);
  const isOmnibus = model.mode === "omnibus" && model.books.length > 1;
  const [selectedBookId, setSelectedBookId] = useState<string | null>(isOmnibus ? null : model.books[0]?.book_id ?? null);
  const [query, setQuery] = useState("");
  const [expandedPartIds, setExpandedPartIds] = useState<Set<string>>(new Set());
  const activeRef = useRef<HTMLButtonElement>(null);
  const selectedBook = model.books.find((book) => book.book_id === selectedBookId) ?? null;
  const needle = query.trim().toLocaleLowerCase();
  const visibleBooks = model.books.filter((book) => !needle || book.title.toLocaleLowerCase().includes(needle) || book.source_title.toLocaleLowerCase().includes(needle));
  const selectedEntries = selectedBook?.entries ?? EMPTY_ENTRIES;
  const entryHierarchy = useMemo(() => buildEntryHierarchy(selectedEntries), [selectedEntries]);
  const matchingEntryIndexes = new Set(selectedEntries.flatMap((entry, index) => entryMatches(entry, needle) ? [index] : []));
  const searchContextIds = new Set([...matchingEntryIndexes].flatMap((index) => entryHierarchy.ancestorsByIndex[index]?.map((entry) => entry.entry_id) ?? []));
  const visibleEntries = selectedEntries.filter((entry, index) => {
    if (needle) return matchingEntryIndexes.has(index) || searchContextIds.has(entry.entry_id);
    return entryHierarchy.ancestorsByIndex[index]?.every((part) => expandedPartIds.has(part.entry_id)) ?? true;
  });

  useEffect(() => {
    if (!selectedBook) {
      setExpandedPartIds(new Set());
      return;
    }
    const activeIndex = selectedBook.entries.findIndex((entry) => entry.chapter_index !== null && entry.chapter_index === currentChapterIndex);
    setExpandedPartIds(new Set(activeIndex < 0 ? [] : entryHierarchy.ancestorsByIndex[activeIndex]?.map((entry) => entry.entry_id) ?? []));
  }, [currentChapterIndex, entryHierarchy, selectedBook]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [expandedPartIds, selectedBookId]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      onClose();
    };
    window.addEventListener("keydown", handleEscape, true);
    return () => window.removeEventListener("keydown", handleEscape, true);
  }, [onClose]);

  const chooseBook = (book: NavigationBook) => {
    setSelectedBookId(book.book_id);
    setQuery("");
  };

  const goBack = () => {
    setSelectedBookId(null);
    setQuery("");
  };

  const togglePart = (entryId: string) => {
    setExpandedPartIds((current) => {
      const next = new Set(current);
      if (next.has(entryId)) next.delete(entryId); else next.add(entryId);
      return next;
    });
  };

  return <aside className="toc-panel" aria-label="Table of contents">
    <header>
      <div className="toc-heading">
        {isOmnibus && selectedBook && <button aria-label="Back to books" title="Back to books" onClick={goBack}><ArrowLeft/></button>}
        <strong>{selectedBook?.title ?? "Contents"}</strong>
      </div>
      <button aria-label="Close table of contents" onClick={onClose}><X/></button>
    </header>
    <label className="toc-search"><Search/><input autoFocus aria-label={selectedBook ? "Filter this book's contents" : "Filter books"} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={selectedBook ? "Find a chapter or entry" : "Find a book"}/></label>
    <nav aria-label={selectedBook ? `${selectedBook.title} contents` : "Books in this omnibus"}>
      {!selectedBook && visibleBooks.map((book) => {
        const active = containsChapter(book, currentChapterIndex);
        return <button key={book.book_id} className={`toc-book-row ${active ? "active" : ""}`} aria-current={active ? "location" : undefined} onClick={() => chooseBook(book)}>
          <span className="toc-book-ordinal">{book.ordinal}</span>
          <span className="toc-book-copy"><strong>{book.title}</strong><small>{book.entries.length} entries{active ? " · Current book" : ""}</small></span>
          <ChevronRight/>
        </button>;
      })}
      {selectedBook && visibleEntries.map((entry) => {
        const active = entry.chapter_index !== null && entry.chapter_index === currentChapterIndex;
        const structural = entry.kind === "part";
        const hasChildren = structural && entryHierarchy.partsWithChildren.has(entry.entry_id);
        const expanded = expandedPartIds.has(entry.entry_id) || Boolean(needle);
        const title = navigationEntryTitle(entry);
        const ariaLabel = `${entry.display_number ? `Chapter ${entry.display_number}: ` : ""}${title}`;
        if (hasChildren) return <div
          key={entry.entry_id}
          className={`toc-part-row ${active ? "active" : ""}`}
          style={{ "--toc-indent": `${Math.min(entry.depth, 3) * 14}px` } as CSSProperties}
        >
          <button className={`toc-part-toggle ${expanded ? "expanded" : ""}`} aria-label={`${expanded ? "Collapse" : "Expand"} ${title}`} aria-expanded={expanded} onClick={() => togglePart(entry.entry_id)}><ChevronRight/></button>
          <button ref={active ? activeRef : undefined} className="toc-part-link" aria-current={active ? "location" : undefined} aria-label={ariaLabel} disabled={!entry.spine_href} onClick={() => onNavigate(entry.spine_href)}>
            <span className="toc-entry-copy"><strong>{title}</strong><small>Section</small></span>
          </button>
        </div>;
        return <button
          key={entry.entry_id}
          ref={active ? activeRef : undefined}
          className={`toc-entry-row ${structural ? "structural" : ""} ${active ? "active" : ""}`}
          style={{ "--toc-indent": `${Math.min(entry.depth, 3) * 14}px` } as CSSProperties}
          aria-current={active ? "location" : undefined}
          aria-label={ariaLabel}
          disabled={!entry.spine_href}
          onClick={() => onNavigate(entry.spine_href)}
        >
          <span className="toc-entry-number">{entry.display_number ?? ""}</span>
          <span className="toc-entry-copy"><strong>{title}</strong>{structural && <small>Section</small>}</span>
        </button>;
      })}
      {(selectedBook ? visibleEntries : visibleBooks).length === 0 && <p className="toc-empty">No matching contents.</p>}
    </nav>
  </aside>;
}
