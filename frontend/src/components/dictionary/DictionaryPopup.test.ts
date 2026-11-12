import { describe, expect, it } from "vitest";
import popupSource from "./DictionaryPopup.tsx?raw";
import readerSource from "../../pages/ReaderPage.tsx?raw";
import storeSource from "../../store/readerStore.ts?raw";
import { dictionarySchema } from "../../types/contracts";

describe("dictionary integration", () => {
  it("accepts independent glossary, context, dictionary, and pronunciation sections", () => {
    const result = dictionarySchema.parse({
      schema_version: "dictionary_v1",
      query: { selected_text: "world", normalized_text: "world", lemma: "world", language: "en", chapter_index: 0, knowledge_as_of_chapter: -1 },
      routing: { primary: "general_dictionary", story_object_match: false, object_kind: null, object_id: null, confidence: null, ambiguous: false },
      story_glossary: { status: "unavailable", reason: "graph_not_committed", provider: "book_graph", provider_version: "knowledge_object_v1", diagnostics: [] },
      context: { status: "ok", meaning: "the people and places around someone", provider: "wordnet_wsd", provider_version: "wsd_v1", diagnostics: [] },
      general_dictionary: { status: "ok", senses: [{ definition: "everything that exists", synonyms: ["universe"] }], provider: "open_english_wordnet", provider_version: "oewn-via-wn", diagnostics: [] },
      pronunciation: { status: "ok", variants: [{ ipa: "/wɝld/", audio: { status: "unavailable" } }], provider: "offline_pronunciation", provider_version: "pronunciation_v1", diagnostics: [] },
      diagnostics: [],
    });
    expect(result.context.status).toBe("ok");
    expect(result.general_dictionary.status).toBe("ok");
    expect(result.pronunciation.status).toBe("ok");
    expect(result.story_glossary.status).toBe("unavailable");
  });

  it("dismisses from the app background, EPUB document, and Escape", () => {
    expect(popupSource).toContain("onPointerDownOutside={onDismiss}");
    expect(popupSource).toContain("onInteractOutside={onDismiss}");
    expect(popupSource).toContain("onEscapeKeyDown={onDismiss}");
    expect(readerSource).toContain('contents.document.addEventListener("pointerdown", (event)');
    expect(readerSource).toContain("dismissReaderPanels()");
    expect(readerSource).toContain("setDictionarySelection(null)");
  });

  it("reserves reader chrome when resolving popup collisions", () => {
    expect(popupSource).toContain("collisionPadding={{ top: 74, right: 16, bottom: 54, left: 16 }}");
    expect(popupSource).toContain('sticky="always"');
  });

  it("retries completed chapters and clears their authorization after commit", () => {
    expect(readerSource).toContain("progress?.naturallyCompleted");
    expect(readerSource).toContain("complete.mutate(chapter.index)");
    expect(readerSource).toContain("committed: true, retryRequired: false");
  });

  it("supports CSRE context capture, suppression defaults, and context-first rendering", () => {
    expect(readerSource).toContain("buildSelectionContext(paragraphText, text");
    expect(readerSource).toContain("sentenceSelectionStart");
    expect(popupSource).toContain('popupAction === "suppress_popup"');
    expect(storeSource).toContain('functionWordMode: "suppress"');
    expect(storeSource).toContain("version: 5");
    // One meaning leads the card: the book's own, then this sentence's, then the dictionary's.
    expect(popupSource).toContain("const definition = bookMeaning ?? contextMeaning ?? generalDefinition;");
    expect(popupSource.indexOf('{ id: "meaning", label: "Meaning" }')).toBeLessThan(popupSource.indexOf('{ id: "book", label: "In this book" }'));
    // Provider names and confidence figures stay out of the visible card.
    expect(popupSource).not.toContain("<small>Confidence");
  });

  it("resets the optional AI explanation for every new word", () => {
    expect(popupSource).toContain("const selectionKey");
    expect(popupSource).toContain("resetExplanation()");
    expect(popupSource).toContain("[resetExplanation, selectionKey]");
  });

  it("offers one clear lookup action instead of duplicate dictionary and character buttons", async () => {
    const { readerPluginManager } = await import("../../plugins");
    const actions = readerPluginManager.selectionActions({ dictionary: true, chapter_analysis: true });
    expect(actions.filter((action) => ["dictionary", "story", "character"].includes(action.id)).map((action) => action.label)).toEqual(["Look up"]);
    expect(popupSource).toContain("Ask AI about this wording");
    expect(popupSource).toContain("AI explanations need a Gemini API key");
    expect(popupSource).toContain("Set up optional AI");
  });

  it("handles arrow navigation from inside the EPUB document", () => {
    expect(readerSource).toContain('contents.document.addEventListener("keydown", listener)');
    expect(readerSource).toContain('event.key === "ArrowRight"');
    expect(readerSource).toContain('event.key === "ArrowLeft"');
  });
});
