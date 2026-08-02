import { z } from "zod";
import { apiArrayBuffer, apiRequest, encoded } from "./client";
import { readerAnnotationSchema, readerBookmarkSchema, readerCollectionSchema, readerLibraryStateSchema } from "../types/contracts";
import type { ChapterProgress } from "../utils/progress";

const profileSchema = z.object({ user_id: z.string().uuid() });
const bookEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_book_state_v1"), book: z.unknown() });
const chapterEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_chapter_progress_v1"), chapter: z.unknown() });
const collectionEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_collection_v1"), collection: readerCollectionSchema });
const bookmarkEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_bookmark_v1"), bookmark: readerBookmarkSchema });
const annotationEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_annotation_v1"), annotation: readerAnnotationSchema });
const annotationsEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_annotations_v1"), annotations: z.array(readerAnnotationSchema) });
const statisticsEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_statistics_v1"), statistics: z.object({ active_seconds: z.number(), session_count: z.number().int(), books_read: z.number().int(), current_streak_days: z.number().int(), per_book: z.record(z.string(),z.object({active_seconds:z.number(),progress_delta:z.number(),session_count:z.number().int(),seconds_per_book:z.number().nullable(),sufficient_data:z.boolean()})).default({}) }) });
const deletedEnvelope = z.object({ schema_version: z.string(), deleted: z.literal(true) });
const importEnvelope = z.object({ schema_version: z.literal("bookbuddy_reader_import_v1"), imported_books: z.number(), imported_chapters: z.number() });

export interface BookStateUpdate {
  favorite?: boolean; want_to_read?: boolean; last_opened_at?: number; last_cfi?: string;
  current_chapter?: number; chapter_progress?: number; book_progress?: number; added_at?: number; finished_at?: number;
}

export const readerStateApi = {
  createProfile: () => apiRequest("/reader/profile", profileSchema, { method: "POST" }),
  library: (userId: string) => apiRequest(`/reader/${encoded(userId)}/library-state`, readerLibraryStateSchema),
  updateBook: (userId: string, book: string, session: string, values: BookStateUpdate) => apiRequest(
    `/reader/${encoded(userId)}/books/${encoded(book)}/${encoded(session)}`, bookEnvelope, { method: "PUT", body: JSON.stringify(values) },
  ),
  updateChapter: (userId: string, book: string, session: string, chapterIndex: number, progress: ChapterProgress) => apiRequest(
    `/reader/${encoded(userId)}/books/${encoded(book)}/${encoded(session)}/chapters/${chapterIndex}`, chapterEnvelope,
    { method: "PUT", body: JSON.stringify({ last_cfi: progress.lastCfi, current_progress: progress.currentProgress, contiguous_progress: progress.contiguousProgress, threshold_started: progress.thresholdStarted, naturally_completed: progress.naturallyCompleted, committed: progress.committed, retry_required: progress.retryRequired }) },
  ),
  importLegacy: (userId: string, books: unknown[], chapters: unknown[]) => apiRequest(
    `/reader/${encoded(userId)}/state/import`, importEnvelope, { method: "POST", body: JSON.stringify({ books, chapters }) },
  ),
  createCollection: (userId: string, name: string) => apiRequest(`/reader/${encoded(userId)}/collections`, collectionEnvelope, { method: "POST", body: JSON.stringify({ name }) }),
  updateCollection: (userId: string, id: string, values: { name?: string; sort_order?: number }) => apiRequest(`/reader/${encoded(userId)}/collections/${encoded(id)}`, collectionEnvelope, { method: "PUT", body: JSON.stringify(values) }),
  deleteCollection: (userId: string, id: string) => apiRequest(`/reader/${encoded(userId)}/collections/${encoded(id)}`, deletedEnvelope, { method: "DELETE" }),
  setCollectionMember: (userId: string, id: string, sessionKey: string, present: boolean) => apiRequest(`/reader/${encoded(userId)}/collections/${encoded(id)}/member`, collectionEnvelope, { method: "PUT", body: JSON.stringify({ session_key: sessionKey, present }) }),
  createBookmark: (userId: string, book: string, session: string, chapterIndex: number, cfi: string, excerpt = "", name = "") => apiRequest(`/reader/${encoded(userId)}/books/${encoded(book)}/${encoded(session)}/bookmarks`, bookmarkEnvelope, { method: "POST", body: JSON.stringify({ chapter_index: chapterIndex, cfi, excerpt, name }) }),
  updateBookmark: (userId: string, id: string, name: string) => apiRequest(`/reader/${encoded(userId)}/bookmarks/${encoded(id)}`, bookmarkEnvelope, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteBookmark: (userId: string, id: string) => apiRequest(`/reader/${encoded(userId)}/bookmarks/${encoded(id)}`, deletedEnvelope, { method: "DELETE" }),
  annotations: (userId: string, sessionKey?: string, query = "") => apiRequest(`/reader/${encoded(userId)}/annotations?${new URLSearchParams({ ...(sessionKey ? { session_key: sessionKey } : {}), ...(query ? { query } : {}) })}`, annotationsEnvelope),
  createAnnotation: (userId: string, book: string, session: string, values: { chapter_index: number; cfi_range: string; quote: string; annotation_type: "highlight" | "underline" | "note"; color?: string; note_text?: string }) => apiRequest(`/reader/${encoded(userId)}/books/${encoded(book)}/${encoded(session)}/annotations`, annotationEnvelope, { method: "POST", body: JSON.stringify(values) }),
  updateAnnotation: (userId: string, id: string, values: { annotation_type?: "highlight" | "underline" | "note"; color?: string; note_text?: string }) => apiRequest(`/reader/${encoded(userId)}/annotations/${encoded(id)}`, annotationEnvelope, { method: "PATCH", body: JSON.stringify(values) }),
  deleteAnnotation: (userId: string, id: string) => apiRequest(`/reader/${encoded(userId)}/annotations/${encoded(id)}`, deletedEnvelope, { method: "DELETE" }),
  recordReadingSession: (userId: string, book: string, session: string, values: { started_at: number; ended_at: number; active_seconds: number; start_progress: number; end_progress: number }) => apiRequest(`/reader/${encoded(userId)}/books/${encoded(book)}/${encoded(session)}/reading-sessions`, z.object({ schema_version: z.literal("bookbuddy_reading_session_v1"), session: z.unknown() }), { method: "POST", body: JSON.stringify(values) }),
  statistics: (userId: string) => apiRequest(`/reader/${encoded(userId)}/statistics`, statisticsEnvelope),
  exportStatistics: (userId: string) => apiArrayBuffer(`/reader/${encoded(userId)}/statistics/export`),
  resetStatistics: (userId: string) => apiRequest(`/reader/${encoded(userId)}/statistics`, z.object({ schema_version: z.literal("bookbuddy_reader_statistics_reset_v1"), deleted_sessions: z.number().int().nonnegative() }), { method: "DELETE" }),
};

export const readerLibraryQuery = (userId: string) => ({ queryKey: ["reader-library", userId] as const, queryFn: () => readerStateApi.library(userId) });
