export type NavigationKind = "forward" | "backward" | "jump" | "restore" | "reflow";

export interface ChapterProgress {
  lastCfi: string;
  currentProgress: number;
  contiguousProgress: number;
  thresholdStarted: boolean;
  naturallyCompleted: boolean;
  committed: boolean;
  retryRequired: boolean;
}

export const emptyProgress = (): ChapterProgress => ({
  lastCfi: "", currentProgress: 0, contiguousProgress: 0, thresholdStarted: false,
  naturallyCompleted: false, committed: false, retryRequired: false,
});

export interface ProgressUpdate { progress: ChapterProgress; crossedThreshold: boolean; completedNaturally: boolean }

export interface BookProgressChapter {
  index: number;
  word_count?: number;
}

export function calculateBookProgress(
  chapters: readonly number[] | readonly BookProgressChapter[],
  currentChapterIndex: number,
  chapterProgress: number,
): number {
  if (chapters.length === 0) return 0;
  const normalized = chapters.map((chapter) => typeof chapter === "number" ? { index: chapter } : chapter);
  const position = normalized.findIndex((chapter) => chapter.index === currentChapterIndex);
  if (position < 0) return 0;
  const local = Math.min(1, Math.max(0, chapterProgress));
  const hasCompleteWordCounts = normalized.every((chapter) => typeof chapter.word_count === "number" && chapter.word_count >= 0);
  const totalWords = hasCompleteWordCounts ? normalized.reduce((total, chapter) => total + (chapter.word_count ?? 0), 0) : 0;
  if (totalWords > 0) {
    const wordsBefore = normalized.slice(0, position).reduce((total, chapter) => total + (chapter.word_count ?? 0), 0);
    const currentWords = normalized[position]?.word_count ?? 0;
    return Math.min(1, Math.max(0, (wordsBefore + currentWords * local) / totalWords));
  }
  return Math.min(1, Math.max(0, (position + local) / normalized.length));
}

export function formatBookProgressPercent(progress: number): string {
  const percentage = Math.min(100, Math.max(0, progress * 100));
  return percentage.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: percentage < 10 ? 2 : 1 });
}

export function updateContiguousProgress(
  previous: ChapterProgress,
  observedProgress: number,
  cfi: string,
  navigation: NavigationKind,
  pageTolerance = 0.08,
  advancedThroughEnd = false,
): ProgressUpdate {
  const observed = Math.min(1, Math.max(0, observedProgress));
  let contiguous = previous.contiguousProgress;
  const isContinuous = navigation === "forward" && observed <= contiguous + pageTolerance;
  if (isContinuous) contiguous = Math.max(contiguous, observed);
  if (navigation === "reflow" && Math.abs(observed - contiguous) <= pageTolerance) contiguous = Math.max(contiguous, observed);
  const crossedThreshold = !previous.thresholdStarted && contiguous >= 0.5;
  const completedNaturally = !previous.naturallyCompleted && advancedThroughEnd && navigation === "forward" && contiguous >= 0.95;
  return {
    crossedThreshold,
    completedNaturally,
    progress: {
      ...previous,
      lastCfi: cfi,
      currentProgress: observed,
      contiguousProgress: contiguous,
      thresholdStarted: previous.thresholdStarted || crossedThreshold,
      naturallyCompleted: previous.naturallyCompleted || completedNaturally,
      retryRequired: previous.retryRequired || completedNaturally,
    },
  };
}
