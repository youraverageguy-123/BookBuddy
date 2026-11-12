import type { AnalysisOverview } from "../../types/contracts";

export type RunPhase = "reading" | "connecting" | "done" | "failed" | "cancelled" | "idle";

export interface RunProgress {
  phase: RunPhase;
  /** Chapters finished so far in the range being analysed (0-based index + 1). */
  finished: number;
  /** Chapters in the range, counted from the start of the book. */
  total: number;
  /** 0-based index of the chapter being read right now, when known. */
  current: number | null;
  percent: number;
  headline: string;
}

/** Turns the backend task record into what the progress screen shows. */
export function describeRun(overview: Pick<AnalysisOverview, "task" | "analysed_through">): RunProgress {
  const { task } = overview;
  const target = task.target_chapter ?? overview.analysed_through;
  const total = Math.max(target + 1, 0);
  const finished = Math.min(Math.max(overview.analysed_through + 1, 0), total);
  const status = task.status ?? "idle";
  const base = { finished, total, current: null as number | null };
  if (status === "completed") return { ...base, phase: "done", finished: total, percent: 100, headline: "Story knowledge is ready." };
  if (status === "error") return { ...base, phase: "failed", percent: percentOf(finished, total), headline: "Analysis stopped before it finished." };
  if (status === "cancelled") return { ...base, phase: "cancelled", percent: percentOf(finished, total), headline: "Analysis was cancelled." };
  if (status !== "processing") return { ...base, phase: "idle", percent: percentOf(finished, total), headline: "" };
  // Once every chapter has been read, the engine links the evidence into the graph.
  if (finished >= total || /replay/i.test(task.log ?? "")) {
    return { ...base, phase: "connecting", finished: total, percent: 96, headline: "Connecting the story…" };
  }
  const current = task.current_chapter ?? finished;
  return { ...base, phase: "reading", current, percent: Math.min(94, percentOf(finished, total)), headline: `Reading chapter ${current + 1} of ${total}` };
}

const percentOf = (finished: number, total: number): number => total > 0 ? Math.round((finished / total) * 100) : 0;

export interface Star { x: number; y: number; index: number }

/**
 * Deterministic positions for one "star" per chapter, spiralling out from the
 * middle so the picture grows evenly as chapters finish.
 */
export function constellation(count: number, width: number, height: number): Star[] {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const limit = Math.min(width, height) / 2 - 18;
  return Array.from({ length: count }, (_, index) => {
    const radius = limit * Math.sqrt((index + 0.6) / Math.max(count, 1));
    const angle = index * golden;
    // The canvas is wider than tall, so the spiral is stretched sideways.
    return { index, x: width / 2 + Math.cos(angle) * radius * (width / height) * 0.82, y: height / 2 + Math.sin(angle) * radius };
  });
}

export function formatElapsed(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
