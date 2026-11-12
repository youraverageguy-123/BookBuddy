import { apiRequest, encoded } from "./client";
import { z } from "zod";
import { analysisJobEnvelopeSchema, analysisOverviewSchema, analysisStatusSchema, customAnalysisSchema } from "../types/contracts";

const root = (book: string, session: string) => `/reader/${encoded(book)}/${encoded(session)}/analysis`;
export const analysisApi = {
  /** Chapter list, how far analysis has reached, and the state of any running job. */
  overview: (book: string, session: string) => apiRequest(`${root(book, session)}/overview`, analysisOverviewSchema),
  /** Analyse everything up to a chapter the reader has already read. `dryRun` only counts the work. */
  custom: (book: string, session: string, userId: string, throughChapter: number, dryRun = false) => apiRequest(`${root(book, session)}/custom`, customAnalysisSchema, { method: "POST", body: JSON.stringify({ through_chapter: throughChapter, user_id: userId, dry_run: dryRun }) }),
  cancelRun: (book: string, session: string) => apiRequest(`/cancel/${encoded(book)}/${encoded(session)}`, z.object({ schema_version: z.string() }).passthrough(), { method: "POST" }),
  status: (book: string, session: string) => apiRequest(`${root(book, session)}/status`, analysisStatusSchema),
  stage: (book: string, session: string, chapter: number) => apiRequest(`${root(book, session)}/${chapter}/stage`, analysisJobEnvelopeSchema, { method: "POST" }),
  complete: (book: string, session: string, chapter: number) => apiRequest(`${root(book, session)}/${chapter}/complete`, analysisJobEnvelopeSchema, { method: "POST" }),
  discard: (book: string, session: string, chapter: number) => apiRequest(`${root(book, session)}/${chapter}/stage`, analysisJobEnvelopeSchema, { method: "DELETE" }),
};
