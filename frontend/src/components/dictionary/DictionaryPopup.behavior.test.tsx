import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DictionaryPopup, type SelectionInfo } from "./DictionaryPopup";

const highlight = vi.fn(async (selectedText: string) => ({
  schema_version: "dictionary_v1",
  query: { selected_text: selectedText },
  routing: { primary: "general_dictionary", popup_action: "show_popup" },
  resolution: { classification: { primary_class: "common_word" } },
  story_glossary: { status: "not_found" },
  context: { status: "ok", meaning: `Context for ${selectedText}` },
  general_dictionary: { status: "ok", senses: [{ definition: `Definition for ${selectedText}` }] },
  pronunciation: { status: "unavailable", variants: [] },
  diagnostics: [],
}));
const explain = vi.fn(async (selectedText: string) => ({ explanation: `AI explanation for ${selectedText}` }));

vi.mock("../../api/dictionary", () => ({
  dictionaryApi: {
    highlight: (_book: string, _session: string, request: { selectedText: string }) => highlight(request.selectedText),
    explain: (_book: string, _session: string, request: { selectedText: string }) => explain(request.selectedText),
    audio: vi.fn(),
  },
}));

vi.mock("../../api/health", () => ({
  healthApi: { get: vi.fn(async () => ({ capabilities: { chapter_analysis: true } })) },
}));

vi.mock("../../services/performance/recorder", () => ({ recordPerformanceSample: vi.fn() }));

const selected = (text: string): SelectionInfo => ({
  text,
  context: `The sentence contains ${text}.`,
  chapter: 2,
  knowledgeAsOfChapter: 2,
  anchorX: 300,
  anchorY: 300,
});

describe("DictionaryPopup behavior", () => {
  afterEach(() => { cleanup(); highlight.mockClear(); explain.mockClear(); vi.unstubAllGlobals(); });

  it("never shows the previous word's AI explanation after the selection changes", async () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <DictionaryPopup book="Book" session="Session" selection={selected("first")} onDismiss={vi.fn()}/>
      </QueryClientProvider>,
    );

    await user.click(await screen.findByRole("tab", { name: "Ask AI" }));
    await user.click(await screen.findByRole("button", { name: "Ask AI about this wording" }));
    expect(await screen.findByText("AI explanation for first")).toBeInTheDocument();

    view.rerender(
      <QueryClientProvider client={client}>
        <DictionaryPopup book="Book" session="Session" selection={selected("second")} onDismiss={vi.fn()}/>
      </QueryClientProvider>,
    );

    expect(screen.queryByText("AI explanation for first")).not.toBeInTheDocument();
    // A new word starts on its meaning again, not on the previous word's tab.
    expect(await screen.findByRole("tab", { name: "Meaning" })).toHaveAttribute("aria-selected", "true");
    await user.click(await screen.findByRole("tab", { name: "Ask AI" }));
    await user.click(await screen.findByRole("button", { name: "Ask AI about this wording" }));
    expect(await screen.findByText("AI explanation for second")).toBeInTheDocument();
    expect(explain.mock.calls.map(([word]) => word)).toEqual(["first", "second"]);
  });
});
