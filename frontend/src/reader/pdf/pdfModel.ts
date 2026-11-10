export interface PageRange { index: number; start_page: number; end_page: number }

const LOCATION_PREFIX = "pdf-page:";

/** PDF reading positions are stored in the same `last_cfi` field EPUB locations use. */
export const pdfLocation = (page: number): string => `${LOCATION_PREFIX}${page}`;

export function parsePdfLocation(location: string | null | undefined, pageCount: number): number {
  if (!location?.startsWith(LOCATION_PREFIX)) return 1;
  const page = Number.parseInt(location.slice(LOCATION_PREFIX.length), 10);
  return Number.isFinite(page) ? clampPage(page, pageCount) : 1;
}

export const clampPage = (page: number, pageCount: number): number => Math.min(Math.max(1, Math.round(page)), Math.max(1, pageCount));

/** Table-of-contents targets for PDFs look like `page-12`. */
export function pageFromHref(href: string, pageCount: number): number | null {
  const match = /^page-(\d+)$/.exec(href.trim());
  return match ? clampPage(Number(match[1]), pageCount) : null;
}

export function rangeForPage(ranges: readonly PageRange[], page: number): PageRange | undefined {
  return ranges.find((range) => page >= range.start_page && page <= range.end_page);
}

export function chapterProgressAt(range: PageRange | undefined, page: number): number {
  if (!range) return 0;
  const length = range.end_page - range.start_page + 1;
  return Math.min(1, Math.max(0, (page - range.start_page + 1) / length));
}

/**
 * The chapter a reader has just finished by moving from `from` to `to`, if any.
 * Only a single step forward off a chapter's last page counts; jumping around
 * the book must never mark chapters as read.
 */
export function chapterFinishedByStep(ranges: readonly PageRange[], from: number, to: number): number | null {
  if (to !== from + 1) return null;
  const range = rangeForPage(ranges, from);
  return range && range.end_page === from ? range.index : null;
}
