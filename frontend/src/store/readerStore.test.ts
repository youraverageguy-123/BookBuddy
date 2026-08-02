import { describe, expect, it } from "vitest";
import { defaultPresentation, effectiveReaderSettings, migrateReaderState, positionFromBackend, seedBackendReaderPositions } from "./readerStore";

describe("ReaderSettingsV5 authority and migration", () => {
  it("hydrates exact resume CFIs from backend-owned book state", () => {
    expect(positionFromBackend({
      session_key: "Book::Reading",
      last_cfi: "epubcfi(/6/18!/4/4/2/1:0)",
      current_chapter: 7,
      chapter_progress: 1 / 6,
      book_progress: 0.072,
      updated_at: 123,
    })).toEqual({
      cfi: "epubcfi(/6/18!/4/4/2/1:0)",
      chapterIndex: 7,
      chapterProgress: 1 / 6,
      bookProgress: 0.072,
      updatedAt: 123000,
    });
  });

  it("migrates legacy exact CFIs without letting derived progress replace them", () => {
    const migrated = migrateReaderState({
      theme: "dark",
      progress: {
        "Book::Reading::2": {
          lastCfi: "epubcfi(/6/8!/4/2:17)",
          currentProgress: 0.42,
        },
      },
    });
    expect(migrated.schemaVersion).toBe(5);
    expect(migrated.global?.readerTheme).toBe("night");
    expect(migrated.books?.["Book::Reading"]?.position?.cfi).toBe("epubcfi(/6/8!/4/2:17)");
  });

  it("applies book settings only while its override is enabled", () => {
    const inherited = effectiveReaderSettings({
      global: defaultPresentation,
      books: { "Book::Reading": { override: false, settings: { fontSize: 31 } } },
    }, "Book::Reading");
    const overridden = effectiveReaderSettings({
      global: defaultPresentation,
      books: { "Book::Reading": { override: true, settings: { fontSize: 31 } } },
    }, "Book::Reading");
    expect(inherited.fontSize).toBe(defaultPresentation.fontSize);
    expect(overridden.fontSize).toBe(31);
  });

  it("never replaces an exact local CFI with derived backend progress", () => {
    const books = { "Book::Reading": { override: false, position: { cfi: "epubcfi(/local)", chapterIndex: 4, chapterProgress: .2, bookProgress: .1, updatedAt: 500 } } };

    const seeded = seedBackendReaderPositions(books, [{ session_key: "Book::Reading", last_cfi: "epubcfi(/backend)", current_chapter: 7, chapter_progress: .8, book_progress: .5, updated_at: 999 }]);

    expect(seeded).toBe(books);
    expect(seeded["Book::Reading"]?.position?.cfi).toBe("epubcfi(/local)");
  });
});
