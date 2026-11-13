import { beforeEach, describe, expect, it, vi } from "vitest";

const chat = vi.fn();
vi.mock("../../api/knowledge", () => ({ knowledgeApi: { chat: (...args: unknown[]) => chat(...args) } }));

import { chatSessionKey, useChatStore } from "./chatStore";

const request = { book: "Book", session: "Reading", asOfChapter: 3 };
const key = chatSessionKey("Book", "Reading");
const state = () => useChatStore.getState();

describe("chat store", () => {
  beforeEach(() => { chat.mockReset(); state().clear(key); });

  it("keeps the question and the pending state outside any component", async () => {
    let answer!: (value: unknown) => void;
    chat.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    const asking = state().ask({ ...request, question: "  Who is Nick?  " });
    expect(state().conversations[key]).toEqual([{ role: "user", text: "Who is Nick?" }]);
    expect(state().pending[key]).toBe(true);
    answer({ answer: "The narrator.", sources: [] });
    await asking;
    expect(state().pending[key]).toBe(false);
    expect(state().conversations[key]?.at(-1)).toMatchObject({ role: "assistant", text: "The narrator." });
    expect(chat).toHaveBeenCalledWith("Book", "Reading", "Who is Nick?", 3, []);
  });

  it("marks a failed question and retries it without repeating it", async () => {
    chat.mockRejectedValueOnce(new Error("busy")).mockResolvedValueOnce({ answer: "Done.", sources: [] });
    await state().ask({ ...request, question: "Summarize" });
    expect(state().failed[key]).toBe(true);
    expect(state().conversations[key]).toHaveLength(1);
    await state().retry(request);
    expect(state().failed[key]).toBe(false);
    expect(state().conversations[key]?.map((message) => message.role)).toEqual(["user", "assistant"]);
  });

  it("ignores a second question while one is pending and drops answers to a cleared chat", async () => {
    let answer!: (value: unknown) => void;
    chat.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    const asking = state().ask({ ...request, question: "First" });
    await state().ask({ ...request, question: "Second" });
    expect(chat).toHaveBeenCalledTimes(1);
    state().clear(key);
    answer({ answer: "Late.", sources: [] });
    await asking;
    expect(state().conversations[key]).toBeUndefined();
    expect(state().pending[key]).toBe(false);
  });
});
