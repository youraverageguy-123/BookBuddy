import { openUrl } from "@tauri-apps/plugin-opener";

export const geminiProvider = {
  id: "gemini",
  name: "Google Gemini",
  links: {
    studio: "https://aistudio.google.com/app/apikey",
    keyGuide: "https://ai.google.dev/gemini-api/docs/api-key",
    documentation: "https://ai.google.dev/gemini-api/docs",
  },
  capabilities: [
    ["AI dictionary", "Ask for a plain-language explanation of selected wording."],
    ["Context explanations", "Explain passages using spoiler-safe reached-book context."],
    ["Translation", "Translate text you explicitly select."],
    ["Background analysis", "Analyze completed chapters only after you opt in."],
    ["Image understanding", "Use a separately authorized vision key after local tools are insufficient."],
  ] as const,
  setupSteps: [
    "Open Google AI Studio and sign in with your Google account.",
    "Choose Create API key, then copy the generated key.",
    "Return to BookBuddy, paste the key in AI Settings, and save it.",
    "Run the connection test. BookBuddy sends no book text during verification.",
  ],
} as const;

const allowed = new Set(Object.values(geminiProvider.links));
export async function openOfficialAILink(url: string): Promise<void> {
  if (!allowed.has(url as typeof geminiProvider.links[keyof typeof geminiProvider.links])) throw new Error("This link is not approved by BookBuddy.");
  if ("__TAURI_INTERNALS__" in window) await openUrl(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}
