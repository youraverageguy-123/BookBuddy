import { describe, expect, it } from "vitest";
import { effectiveBookMetadata, formatPublicationYear, metadataSearch } from "./bookMetadata";
import { sessionsSchema, type ReaderBookState, type Session } from "../types/contracts";

const session = { session_key:"Book::Reading", book_name:"Book", session_name:"Reading", book_title:"Source title", author:"Source author", description:"Publisher synopsis", publisher:"Publisher", language:"en", publication_year:"2024", genres:["Fantasy"], analysis:{status:"idle"}, reader_analysis:{schema_version:"reader_analysis_v1",session_key:"Book::Reading",state:"idle",progress:0,jobs:[]} } as Session;
const state = { session_key:"Book::Reading", favorite:false, want_to_read:false, last_opened_at:null, last_cfi:"", current_chapter:null, chapter_progress:0, book_progress:0, added_at:null, finished_at:null, updated_at:0, title_override:"Local title", tags:["owned"] } as ReaderBookState;

describe("effective book metadata", () => {
  it("prefers local overrides without fabricating unavailable metadata", () => {
    const metadata = effectiveBookMetadata(session,state);
    expect(metadata.title).toBe("Local title");
    expect(metadata.description).toBe("Publisher synopsis");
    expect(metadata.series).toBe("");
  });

  it("reports the field that matched library search", () => {
    const metadata = effectiveBookMetadata(session,state);
    expect(metadataSearch(metadata,[],"Source author").reason).toBe("Matched Author");
    expect(metadataSearch(metadata,[],"owned").reason).toBe("Matched Tag");
  });

  it("uses imported series and presents full EPUB dates as a year", () => {
    const metadata = effectiveBookMetadata({ ...session, series:"Dungeon Crawler Carl", publication_year:"2020-10-02T04:00:00+00:00" });
    expect(metadata.series).toBe("Dungeon Crawler Carl");
    expect(metadata.publicationYear).toBe("2020");
    expect(formatPublicationYear("2020-10-02T04:00:00+00:00")).toBe("2020");
  });

  it("accepts absent EPUB metadata represented as null by the backend", () => {
    const parsed = sessionsSchema.parse({
      schema_version: "bookbuddy_sessions_v1",
      sessions: [{
        ...session,
        description: null,
        series: null,
        publisher: null,
        language: null,
        publication_year: null,
        genres: null,
        source_size_bytes: null,
        total_words: null,
      }],
    });

    expect(effectiveBookMetadata(parsed.sessions[0]!).genres).toEqual([]);
    expect(effectiveBookMetadata(parsed.sessions[0]!).publicationYear).toBe("Unavailable");
  });
});
