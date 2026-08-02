import { z } from "zod";
import { apiRequest, encoded } from "./client";

const translationSchema = z.object({
  schema_version: z.literal("bookbuddy_selection_translation_v1"),
  translation: z.string(), target_language: z.string(), provider: z.string(),
});

export const translationApi = {
  translate: (book: string, session: string, selectedText: string, targetLanguage: string) => apiRequest(
    `/reader/${encoded(book)}/${encoded(session)}/translate-selection`, translationSchema,
    { method: "POST", body: JSON.stringify({ selected_text: selectedText, target_language: targetLanguage }) },
  ),
};
