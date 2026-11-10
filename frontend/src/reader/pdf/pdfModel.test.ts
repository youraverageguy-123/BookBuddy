import { describe, expect, it } from "vitest";
import { chapterFinishedByStep, chapterProgressAt, clampPage, pageFromHref, parsePdfLocation, pdfLocation, rangeForPage } from "./pdfModel";

const ranges = [
  { index: 0, start_page: 1, end_page: 1 },
  { index: 1, start_page: 2, end_page: 5 },
  { index: 2, start_page: 6, end_page: 9 },
];

describe("PDF reading model", () => {
  it("round-trips a stored location and survives bad input", () => {
    expect(parsePdfLocation(pdfLocation(7), 9)).toBe(7);
    expect(parsePdfLocation("pdf-page:400", 9)).toBe(9);
    expect(parsePdfLocation("epubcfi(/6/4!/4)", 9)).toBe(1);
    expect(parsePdfLocation("pdf-page:abc", 9)).toBe(1);
    expect(parsePdfLocation(undefined, 9)).toBe(1);
    expect(clampPage(0, 9)).toBe(1);
  });

  it("maps contents targets and pages to chapters", () => {
    expect(pageFromHref("page-6", 9)).toBe(6);
    expect(pageFromHref("chapter.xhtml", 9)).toBeNull();
    expect(rangeForPage(ranges, 4)?.index).toBe(1);
    expect(rangeForPage(ranges, 40)).toBeUndefined();
    expect(chapterProgressAt(ranges[1], 3)).toBe(0.5);
    expect(chapterProgressAt(ranges[1], 5)).toBe(1);
  });

  it("marks a chapter finished only when stepping forward off its last page", () => {
    expect(chapterFinishedByStep(ranges, 5, 6)).toBe(1);
    expect(chapterFinishedByStep(ranges, 1, 2)).toBe(0);
    expect(chapterFinishedByStep(ranges, 4, 5)).toBeNull();
    expect(chapterFinishedByStep(ranges, 6, 5)).toBeNull();
    expect(chapterFinishedByStep(ranges, 5, 9)).toBeNull();
  });
});
