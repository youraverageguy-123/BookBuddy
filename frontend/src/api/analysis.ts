import { apiRequest, encoded } from "./client";
import { analysisJobEnvelopeSchema, analysisStatusSchema } from "../types/contracts";

const root = (book: string, session: string) => `/reader/${encoded(book)}/${encoded(session)}/analysis`;
export const analysisApi = {
  status: (book: string, session: string) => apiRequest(`${root(book, session)}/status`, analysisStatusSchema),
  stage: (book: string, session: string, chapter: number) => apiRequest(`${root(book, session)}/${chapter}/stage`, analysisJobEnvelopeSchema, { method: "POST" }),
  complete: (book: string, session: string, chapter: number) => apiRequest(`${root(book, session)}/${chapter}/complete`, analysisJobEnvelopeSchema, { method: "POST" }),
  discard: (book: string, session: string, chapter: number) => apiRequest(`${root(book, session)}/${chapter}/stage`, analysisJobEnvelopeSchema, { method: "DELETE" }),
};
