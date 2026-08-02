import { z } from "zod";
import { apiRequest, encoded } from "./client";

export const readerSearchResultSchema = z.object({ chapter_index:z.number().int(), chapter_title:z.string(), spine_href:z.string(), paragraph_index:z.number().int(), excerpt:z.string(), score:z.number() });
const searchEnvelope = z.object({ schema_version:z.literal("bookbuddy_reader_search_v1"), results:z.array(readerSearchResultSchema), elapsed_ms:z.number() });
const statusEnvelope = z.object({ schema_version:z.literal("bookbuddy_reader_search_status_v1"), index_schema_version:z.number().int().nonnegative(), ready:z.boolean(), word_count:z.number().int().nonnegative().optional(), indexed_at:z.number().optional() });
const rebuildEnvelope = z.object({ schema_version:z.literal("bookbuddy_reader_search_rebuild_v1"), queued:z.boolean(), session_key:z.string() });
export type ReaderSearchResult = z.infer<typeof readerSearchResultSchema>;

export const searchApi = {
  status: (book:string, session:string) => apiRequest(`/reader/${encoded(book)}/${encoded(session)}/search/status`,statusEnvelope),
  rebuild: (book:string, session:string) => apiRequest(`/reader/${encoded(book)}/${encoded(session)}/search/rebuild`,rebuildEnvelope,{method:"POST"}),
  query: (book:string, session:string, query:string, options:{ chapter?:number; maxChapter?:number; limit?:number }={}) => {
    const params = new URLSearchParams({ q:query, limit:String(options.limit ?? 50) });
    if (options.chapter !== undefined) params.set("chapter",String(options.chapter));
    if (options.maxChapter !== undefined) params.set("max_chapter",String(options.maxChapter));
    return apiRequest(`/reader/${encoded(book)}/${encoded(session)}/search?${params}`,searchEnvelope);
  },
};
