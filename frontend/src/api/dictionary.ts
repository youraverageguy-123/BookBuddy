import { apiArrayBuffer, apiRequest, encoded } from "./client";
import { dictionarySchema } from "../types/contracts";
import { z } from "zod";

export interface HighlightInput {
  chapterIndex: number; selectedText: string; contextText: string; knowledgeAsOfChapter: number;
  sentenceText?: string; previousSentence?: string; nextSentence?: string; paragraphText?: string;
  sentenceSelectionStart?: number; sentenceSelectionEnd?: number; explainFunctionWords?: boolean;
}
export const dictionaryApi = {
  highlight: (book: string, session: string, input: HighlightInput) => apiRequest(
    `/reader/${encoded(book)}/${encoded(session)}/highlight`, dictionarySchema,
    { method: "POST", body: JSON.stringify({ chapter_index: input.chapterIndex, selected_text: input.selectedText, context_text: input.contextText, sentence_text: input.sentenceText, previous_sentence: input.previousSentence, next_sentence: input.nextSentence, paragraph_text: input.paragraphText, sentence_selection_start: input.sentenceSelectionStart, sentence_selection_end: input.sentenceSelectionEnd, knowledge_as_of_chapter: input.knowledgeAsOfChapter, explain_function_words: input.explainFunctionWords ?? false, language: "en", allow_ai_fallback: false }) },
  ),
  audio: (audioId: string) => apiArrayBuffer(`/dictionary/pronunciation/audio/${encoded(audioId)}`),
  explain: (book: string, session: string, input: Pick<HighlightInput, "chapterIndex" | "selectedText" | "contextText" | "knowledgeAsOfChapter">) => apiRequest(
    `/reader/${encoded(book)}/${encoded(session)}/explain-selection`, z.object({ schema_version: z.literal("bookbuddy_selection_explanation_v1"), explanation: z.string(), provider: z.string() }),
    { method: "POST", body: JSON.stringify({ chapter_index: input.chapterIndex, selected_text: input.selectedText, context_text: input.contextText, knowledge_as_of_chapter: input.knowledgeAsOfChapter }) },
  ),
};
