import { z } from "zod";

export const capabilitySchema = z.object({
  chapter_analysis: z.boolean(), dictionary: z.boolean(), contextual_dictionary: z.boolean(),
  pronunciation: z.boolean(), recorded_audio: z.boolean(), vision: z.boolean(), translation: z.boolean().default(false),
});
export const healthSchema = z.object({ schema_version: z.literal("bookbuddy_health_v1"), status: z.literal("ready"), version: z.string(), storage: z.object({ library: z.string() }), capabilities: capabilitySchema });
export const aiSettingsSchema = z.object({
  schema_version: z.literal("bookbuddy_ai_settings_v1"), configured: z.boolean(), vision_configured: z.boolean(),
  key_count: z.number().int().nonnegative(), vision_key_count: z.number().int().nonnegative(),
  source: z.enum(["none", "environment", "encrypted"]), storage_protection: z.string(),
  provider: z.object({ id: z.string(), name: z.string() }).default({ id: "gemini", name: "Google Gemini" }),
  models: z.object({ text: z.string(), dictionary: z.string(), vision: z.string() }).default({ text: "", dictionary: "", vision: "" }),
  connection_status: z.enum(["not_configured", "saved_unverified", "connected", "invalid_key", "network_unavailable", "quota_exceeded", "region_unsupported", "permission_denied", "provider_unavailable", "unexpected_error"]).default("not_configured"),
  verification: z.record(z.string(), z.object({ outcome: z.string(), model: z.string(), message: z.string(), verified_at: z.number() })).default({}),
  background_analysis: z.object({ enabled: z.boolean(), paused: z.boolean(), active_count: z.number(), queued_count: z.number() }).default({ enabled: false, paused: false, active_count: 0, queued_count: 0 }),
  last_error: z.object({ code: z.string(), model: z.string(), attempt: z.number(), at: z.number() }).nullable().optional(),
  documentation: z.array(z.string()).default([]),
  capabilities: z.object({ text: z.boolean(), vision: z.boolean(), text_reason: z.string().default("not_configured"), vision_reason: z.string().default("not_configured") }),
});
export const aiVerificationSchema = z.object({
  schema_version: z.literal("bookbuddy_ai_verification_v1"), capability: z.enum(["text", "vision"]),
  outcome: z.string(), provider: z.string(), model: z.string(), message: z.string(), verified_at: z.number(),
});

export const analysisJobSchema = z.object({
  chapter_index: z.number().int().nonnegative(),
  state: z.enum(["idle", "queued", "analyzing", "staged", "eligible", "committing", "paused", "committed", "cancelled", "error"]),
  progress: z.number(), log: z.string(), eligible: z.boolean(), retryable: z.boolean(),
  error_code: z.string().nullable(), created_at: z.number(), updated_at: z.number(),
});
export const analysisStatusSchema = z.object({ schema_version: z.literal("reader_analysis_v1"), session_key: z.string(), state: z.enum(["active", "idle"]), progress: z.number(), jobs: z.array(analysisJobSchema) });
export const analysisJobEnvelopeSchema = z.object({ schema_version: z.literal("reader_analysis_job_v1"), job: analysisJobSchema });

const integritySchema = z.object({ status: z.string(), issues: z.array(z.string()).default([]) }).passthrough();
export const sessionSchema = z.object({
  session_key: z.string(), book_name: z.string(), session_name: z.string(), book_title: z.string(),
  label: z.string().optional(), total_chapters: z.number().int().nullable().optional(), integrity: integritySchema.optional(),
  updated_at: z.number().optional(), analysis: z.object({ status: z.string(), progress: z.number().optional() }).passthrough(),
  reader_analysis: analysisStatusSchema,
  author: z.string().nullable().optional(), imported_at: z.number().nullable().optional(), cover_available: z.boolean().optional(), total_words: z.number().int().nonnegative().nullable().optional(),
  description: z.string().nullable().optional(), series: z.string().nullable().optional(), publisher: z.string().nullable().optional(), language: z.string().nullable().optional(), publication_year: z.string().nullable().optional(), genres: z.array(z.string()).nullable().optional(), source_size_bytes: z.number().int().nonnegative().nullable().optional(),
}).passthrough();
export const sessionsSchema = z.object({ schema_version: z.literal("bookbuddy_sessions_v1"), sessions: z.array(sessionSchema) });

export const chapterSchema = z.object({ index: z.number().int(), title: z.string(), item_id: z.string(), spine_href: z.string(), section_type: z.string(), word_count: z.number().int().nonnegative().optional(), book_name: z.string().optional() });
export const navigationEntrySchema = z.object({
  entry_id: z.string(), title: z.string(), spine_href: z.string(), depth: z.number().int().nonnegative(),
  kind: z.enum(["chapter", "story", "part", "front_matter", "back_matter", "other"]),
  display_number: z.string().nullable(), chapter_index: z.number().int().nonnegative().nullable(),
});
export const navigationBookSchema = z.object({
  book_id: z.string(), title: z.string(), source_title: z.string(), ordinal: z.number().int().positive(),
  start_chapter_index: z.number().int().nonnegative().nullable(), end_chapter_index: z.number().int().nonnegative().nullable(),
  entries: z.array(navigationEntrySchema),
});
export const bookNavigationSchema = z.object({ schema_version: z.literal("bookbuddy_navigation_v1"), mode: z.enum(["single", "omnibus"]), books: z.array(navigationBookSchema) });
export const bookSchema = z.object({ schema_version: z.literal("bookbuddy_book_v1"), format: z.enum(["epub", "pdf"]).default("epub"), page_count: z.number().int().nonnegative().default(0), page_ranges: z.array(z.object({ index: z.number().int(), start_page: z.number().int(), end_page: z.number().int() })).default([]), title: z.string(), author: z.string(), total_chapters: z.number().int(), word_count: z.number().int().nonnegative().optional(), chapters: z.array(chapterSchema), table_of_contents: z.array(z.object({ index: z.number().int(), title: z.string(), book_name: z.string().optional() })), navigation: bookNavigationSchema.optional() });
export const uploadSchema = z.object({ book_name: z.string(), session_name: z.string(), total_chapters: z.number().int(), inherited_graph: z.boolean(), series_matches: z.array(z.unknown()) });
export const loadSchema = z.object({ message: z.string(), total_chapters: z.number().int(), session_type: z.string() });

export const readerBookStateSchema = z.object({
  session_key: z.string(), favorite: z.boolean(), want_to_read: z.boolean(),
  last_opened_at: z.number().nullable(), last_cfi: z.string(), current_chapter: z.number().int().nullable(),
  chapter_progress: z.number(), book_progress: z.number(), added_at: z.number().nullable(),
  finished_at: z.number().nullable(), updated_at: z.number(),
  knowledge_through_chapter: z.number().int().nullable().optional(), analysis_mode: z.enum(["off", "auto", "custom"]).nullable().optional(),
  title_override: z.string().nullable().optional(), author_override: z.string().nullable().optional(), description_override: z.string().nullable().optional(), series_override: z.string().nullable().optional(), rating: z.number().nullable().optional(), tags: z.array(z.string()).default([]),
});
export const readerChapterProgressSchema = z.object({
  session_key: z.string(), chapter_index: z.number().int().nonnegative(), last_cfi: z.string(),
  current_progress: z.number(), contiguous_progress: z.number(), threshold_started: z.boolean(),
  naturally_completed: z.boolean(), committed: z.boolean(), retry_required: z.boolean(), updated_at: z.number(),
});
export const readerCollectionSchema = z.object({ collection_id: z.string(), name: z.string(), sort_order: z.number().int(), session_keys: z.array(z.string()), description: z.string().default(""), pinned: z.boolean().default(false), book_sort: z.string().default("recent"), custom_cover: z.string().nullable().optional(), created_at: z.number().optional(), updated_at: z.number().optional() });
export const readerBookmarkSchema = z.object({ bookmark_id: z.string(), session_key: z.string(), chapter_index: z.number().int(), cfi: z.string(), excerpt: z.string(), name: z.string().default(""), created_at: z.number() });
export const readerAnnotationSchema = z.object({
  annotation_id: z.string(), session_key: z.string(), chapter_index: z.number().int(), cfi_range: z.string(),
  quote: z.string(), annotation_type: z.enum(["highlight", "underline", "note"]), color: z.string(),
  note_text: z.string(), created_at: z.number(), updated_at: z.number(),
});
export const readerLibraryStateSchema = z.object({
  schema_version: z.literal("bookbuddy_reader_library_v1"), user_id: z.string(),
  books: z.array(readerBookStateSchema), chapters: z.array(readerChapterProgressSchema),
  collections: z.array(readerCollectionSchema), bookmarks: z.array(readerBookmarkSchema), annotation_counts: z.record(z.string(), z.number().int().nonnegative()).default({}),
  smart_collections: z.object({ currently_reading: z.array(z.string()), favorites: z.array(z.string()), finished: z.array(z.string()), want_to_read: z.array(z.string()) }),
});

const serviceResultSchema = z.object({ status: z.string(), provider: z.string(), provider_version: z.string(), diagnostics: z.array(z.unknown()) }).passthrough();
export const dictionarySchema = z.object({
  schema_version: z.string(),
  query: z.object({ selected_text: z.string(), normalized_text: z.string(), lemma: z.string(), forms: z.object({ original: z.string(), lower: z.string(), lemma: z.string(), normalized: z.string() }).passthrough().optional(), language: z.string(), chapter_index: z.number().int(), knowledge_as_of_chapter: z.number().int().nullable().optional() }),
  routing: z.object({ primary: z.string(), story_object_match: z.boolean(), object_kind: z.string().nullable(), object_id: z.number().nullable(), confidence: z.number().nullable(), ambiguous: z.boolean(), popup_action: z.enum(["show_popup", "suppress_popup"]).optional(), suppression_reason: z.string().nullable().optional() }),
  resolution: z.object({ schema_version: z.literal("csre_v1"), classification: z.object({ primary_class: z.string(), confidence: z.number(), evidence: z.array(z.string()), ambiguous: z.boolean() }).passthrough(), morphology: z.record(z.string(), z.unknown()), named_entity: z.record(z.string(), z.unknown()), route: z.record(z.string(), z.unknown()), ranked_candidates: z.array(z.record(z.string(), z.unknown())), display_order: z.array(z.string()) }).optional(),
  context: serviceResultSchema, general_dictionary: serviceResultSchema, story_glossary: serviceResultSchema,
  pronunciation: serviceResultSchema, diagnostics: z.array(z.unknown()),
});

export type Health = z.infer<typeof healthSchema>;
export const aiModelsSchema = z.object({ schema_version: z.literal("bookbuddy_ai_models_v1"), selected: z.string(), status: z.string(), models: z.array(z.object({ id: z.string(), name: z.string(), description: z.string().default("") })) });
export const analysisTaskSchema = z.object({ status: z.string().nullable().default("idle"), progress: z.number().nullable().default(0), log: z.string().nullable().default(""), current_chapter: z.number().int().nullable().optional(), target_chapter: z.number().int().nullable().optional(), last_analyzed_chapter: z.number().int().nullable().optional() });
export const analysisOverviewSchema = z.object({ schema_version: z.literal("bookbuddy_analysis_overview_v1"), total_chapters: z.number().int(), chapters: z.array(z.object({ index: z.number().int(), title: z.string() })), analysed_through: z.number().int(), ai_available: z.boolean(), task: analysisTaskSchema });
export const customAnalysisSchema = z.object({ schema_version: z.literal("bookbuddy_custom_analysis_v1"), through_chapter: z.number().int(), chapters_to_analyse: z.number().int(), started: z.boolean() });
export type AnalysisOverview = z.infer<typeof analysisOverviewSchema>;
export type AISettings = z.infer<typeof aiSettingsSchema>;
export type Session = z.infer<typeof sessionSchema>;
export type Book = z.infer<typeof bookSchema>;
export type Chapter = z.infer<typeof chapterSchema>;
export type BookNavigation = z.infer<typeof bookNavigationSchema>;
export type NavigationBook = z.infer<typeof navigationBookSchema>;
export type NavigationEntry = z.infer<typeof navigationEntrySchema>;
export type AnalysisStatus = z.infer<typeof analysisStatusSchema>;
export type AnalysisJob = z.infer<typeof analysisJobSchema>;
export type DictionaryResult = z.infer<typeof dictionarySchema>;
export type ReaderLibraryState = z.infer<typeof readerLibraryStateSchema>;
export type ReaderBookState = z.infer<typeof readerBookStateSchema>;
export type ReaderCollection = z.infer<typeof readerCollectionSchema>;
export type ReaderBookmark = z.infer<typeof readerBookmarkSchema>;
export type ReaderAnnotation = z.infer<typeof readerAnnotationSchema>;
