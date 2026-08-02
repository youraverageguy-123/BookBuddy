import { describe, expect, it } from "vitest";
import { buildSelectionContext } from "./selectionContext";

describe("selection context", () => {
  it("preserves casing and extracts adjacent sentences and sentence offsets", () => {
    const paragraph = "Before this. He spoke French. After that.";
    const start = paragraph.indexOf("French");
    const result = buildSelectionContext(paragraph, "French", start);
    expect(result).toMatchObject({
      sentence: "He spoke French.", previousSentence: "Before this.", nextSentence: "After that.",
      sentenceSelectionStart: 9, sentenceSelectionEnd: 15,
    });
  });

  it("chooses the occurrence nearest the DOM range offset", () => {
    const paragraph = "Bill arrived. Later, Bill was paid.";
    const start = paragraph.lastIndexOf("Bill");
    expect(buildSelectionContext(paragraph, "Bill", start).sentence).toBe("Later, Bill was paid.");
  });
});
