import { describe, expect, it } from "vitest";
import { constellation, describeRun, formatElapsed } from "./analysisModel";

const task = (values: Record<string, unknown>) => ({ status: "processing", progress: 0, log: "", ...values });

describe("analysis progress model", () => {
  it("describes a run while chapters are being read", () => {
    const run = describeRun({ analysed_through: 10, task: task({ current_chapter: 11, target_chapter: 29, log: "Processing Chapter 11..." }) });
    expect(run.phase).toBe("reading");
    expect(run.headline).toBe("Reading chapter 12 of 30");
    expect(run.finished).toBe(11);
    expect(run.total).toBe(30);
    expect(run.percent).toBe(37);
  });

  it("switches to connecting once every chapter is read, and to done on completion", () => {
    const connecting = describeRun({ analysed_through: 29, task: task({ target_chapter: 29, log: "Replaying immutable chapter evidence..." }) });
    expect(connecting.phase).toBe("connecting");
    expect(connecting.percent).toBeLessThan(100);
    const done = describeRun({ analysed_through: 29, task: task({ status: "completed", target_chapter: 29 }) });
    expect(done.phase).toBe("done");
    expect(done.percent).toBe(100);
    expect(done.finished).toBe(30);
  });

  it("keeps finished chapters visible after a failure or cancel", () => {
    const failed = describeRun({ analysed_through: 3, task: task({ status: "error", target_chapter: 9 }) });
    expect(failed.phase).toBe("failed");
    expect(failed.finished).toBe(4);
    expect(failed.percent).toBe(40);
    expect(describeRun({ analysed_through: 3, task: task({ status: "cancelled", target_chapter: 9 }) }).phase).toBe("cancelled");
    expect(describeRun({ analysed_through: -1, task: task({ status: "idle" }) }).phase).toBe("idle");
  });

  it("places one star per chapter inside the canvas, the same way every time", () => {
    const stars = constellation(40, 640, 260);
    expect(stars).toHaveLength(40);
    for (const star of stars) {
      expect(star.x).toBeGreaterThan(0); expect(star.x).toBeLessThan(640);
      expect(star.y).toBeGreaterThan(0); expect(star.y).toBeLessThan(260);
    }
    expect(constellation(40, 640, 260)).toEqual(stars);
    expect(constellation(0, 640, 260)).toEqual([]);
  });

  it("formats elapsed time", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(75.9)).toBe("1:15");
  });
});
