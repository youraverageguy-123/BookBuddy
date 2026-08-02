import { describe, expect, it } from "vitest";
import { calculateBookProgress, emptyProgress, formatBookProgressPercent, updateContiguousProgress } from "./progress";

describe("spoiler-safe contiguous progress", () => {
  it("starts analysis exactly once after continuous reading crosses half", () => {
    let state = emptyProgress();
    for (const value of [0.05, 0.12, 0.2, 0.28, 0.36, 0.44]) state = updateContiguousProgress(state, value, `cfi-${value}`, "forward").progress;
    const crossing = updateContiguousProgress(state, 0.51, "cfi-half", "forward");
    expect(crossing.crossedThreshold).toBe(true);
    expect(updateContiguousProgress(crossing.progress, 0.55, "cfi-later", "forward").crossedThreshold).toBe(false);
  });

  it("does not count a jump over unread content", () => {
    const jumped = updateContiguousProgress(emptyProgress(), 0.8, "cfi-jump", "jump");
    expect(jumped.progress.contiguousProgress).toBe(0);
    expect(jumped.crossedThreshold).toBe(false);
  });

  it("requires a forward end transition to complete", () => {
    const nearEnd = { ...emptyProgress(), contiguousProgress: 0.96, thresholdStarted: true };
    expect(updateContiguousProgress(nearEnd, 1, "end", "jump", 0.08, true).completedNaturally).toBe(false);
    expect(updateContiguousProgress(nearEnd, 1, "end", "forward", 0.08, true).completedNaturally).toBe(true);
  });

  it("accepts the first page of a short reflowed chapter with a page-sized tolerance", () => {
    const firstPage = updateContiguousProgress(emptyProgress(), 0.2, "first-page", "forward", 0.22);
    expect(firstPage.progress.contiguousProgress).toBe(0.2);
  });
});

describe("whole-book display progress", () => {
  it("combines chapter order with chapter-local progress", () => {
    expect(calculateBookProgress([4, 8, 12, 20], 4, 0.5)).toBeCloseTo(0.125);
    expect(calculateBookProgress([4, 8, 12, 20], 12, 0.25)).toBeCloseTo(0.5625);
    expect(calculateBookProgress([4, 8, 12, 20], 20, 1)).toBe(1);
  });

  it("clamps invalid local progress and rejects unknown chapters", () => {
    expect(calculateBookProgress([0, 1], 0, -2)).toBe(0);
    expect(calculateBookProgress([0, 1], 1, 5)).toBe(1);
    expect(calculateBookProgress([0, 1], 9, 0.5)).toBe(0);
  });

  it("weights front matter and chapters by their actual word counts", () => {
    const chapters = [
      { index: 0, word_count: 100 },
      { index: 1, word_count: 100 },
      { index: 2, word_count: 3_000 },
      { index: 3, word_count: 6_800 },
    ];
    expect(calculateBookProgress(chapters, 2, 0.25)).toBeCloseTo(0.095);
  });

  it("keeps an equal-chapter fallback for metadata without word counts", () => {
    expect(calculateBookProgress([{ index: 4 }, { index: 8 }], 8, 0.5)).toBeCloseTo(0.75);
  });

  it("shows useful precision near the beginning of a book", () => {
    expect(formatBookProgressPercent(0.0091)).toBe("0.91");
    expect(formatBookProgressPercent(0.07123)).toBe("7.12");
    expect(formatBookProgressPercent(0.5276)).toBe("52.8");
  });
});
