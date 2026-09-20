import { describe, expect, it } from "vitest";
import { findDocumentSearchMatches, selectDocumentSearchMatch, selectSearchResultMatch } from "./searchResultMatch";

describe("reader search result matching", () => {
  it("uses nearby excerpt words to select the clicked occurrence", () => {
    const matches = [
      { cfi: "first", excerpt: "I ask Dominus Portobello for reassurance." },
      { cfi: "second", excerpt: "She salutes. I nod to Dominus Portobello. Make sure you put that where it counts." },
    ];
    expect(selectSearchResultMatch(matches, "…She salutes. I nod to <mark>Dominus Portobello</mark>. Make sure you put that where it counts…")?.cfi).toBe("second");
  });

  it("falls back to the first epub.js match when no context is available", () => {
    expect(selectSearchResultMatch([{ cfi: "first" }, { cfi: "second" }], "")?.cfi).toBe("first");
  });

  it("finds and selects the clicked occurrence in the live EPUB document", () => {
    document.body.innerHTML = "<p>Dominus Portobello appears briefly.</p><p>She salutes. I nod to <em>Dominus Portobello</em>. Make sure you put that where it counts.</p>";
    const matches = findDocumentSearchMatches(document, "Dominus Portobello");
    expect(matches).toHaveLength(2);
    expect(selectDocumentSearchMatch(matches, "She salutes. I nod to <mark>Dominus Portobello</mark>. Make sure you put that where it counts.")?.range.toString()).toBe("Dominus Portobello");
  });
});
