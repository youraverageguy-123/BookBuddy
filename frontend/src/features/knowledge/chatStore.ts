import { create } from "zustand";
import { knowledgeApi, type ChatTurn } from "../../api/knowledge";

export interface ChatMessage extends ChatTurn { sources?: { chapter_index: number; chapter_title: string }[] }

export interface ChatRequest { book: string; session: string; asOfChapter: number; question: string }

interface ChatState {
  conversations: Record<string, ChatMessage[]>;
  /** Books with a question on its way to the AI. Kept here so it survives leaving the page. */
  pending: Record<string, boolean>;
  /** Books whose last question failed and can be retried. */
  failed: Record<string, boolean>;
  ask: (request: ChatRequest) => Promise<void>;
  retry: (request: Omit<ChatRequest, "question">) => Promise<void>;
  clear: (sessionKey: string) => void;
}

const STORAGE_KEY = "bookbuddy-chats-v1";
const MAX_MESSAGES = 40;

export const chatSessionKey = (book: string, session: string) => `${book}::${session}`;

function load(): Record<string, ChatMessage[]> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as Record<string, ChatMessage[]> : {};
  } catch { return {}; }
}

function save(conversations: Record<string, ChatMessage[]>): void {
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(conversations)); } catch { /* storage may be unavailable; the in-memory copy still works */ }
}

// Bumped when a conversation is cleared, so a late answer to a cleared chat is dropped.
const generations: Record<string, number> = {};

/**
 * Chat history per book. It lives outside the panel so leaving the page, switching
 * tabs, or opening the reader drawer shows the same conversation, including a
 * question that is still being answered. Kept for the app session, not forever.
 */
export const useChatStore = create<ChatState>((set, get) => {
  const append = (key: string, message: ChatMessage) => set((state) => {
    const conversations = { ...state.conversations, [key]: [...(state.conversations[key] ?? []), message].slice(-MAX_MESSAGES) };
    save(conversations);
    return { conversations };
  });
  const flag = (name: "pending" | "failed", key: string, value: boolean) => set((state) => ({ [name]: { ...state[name], [key]: value } }) as Pick<ChatState, "pending" | "failed">);

  const send = async ({ book, session, asOfChapter, question }: ChatRequest, history: ChatTurn[]) => {
    const key = chatSessionKey(book, session);
    const generation = generations[key] ?? 0;
    flag("pending", key, true); flag("failed", key, false);
    try {
      const data = await knowledgeApi.chat(book, session, question, asOfChapter, history);
      if ((generations[key] ?? 0) === generation) append(key, { role: "assistant", text: data.answer, sources: data.sources });
    } catch {
      if ((generations[key] ?? 0) === generation) flag("failed", key, true);
    } finally {
      if ((generations[key] ?? 0) === generation) flag("pending", key, false);
    }
  };
  const turns = (messages: ChatMessage[]): ChatTurn[] => messages.map(({ role, text }) => ({ role, text }));

  return {
    conversations: load(),
    pending: {},
    failed: {},
    ask: async (request) => {
      const key = chatSessionKey(request.book, request.session);
      const question = request.question.trim();
      if (!question || get().pending[key]) return;
      const history = turns(get().conversations[key] ?? []);
      append(key, { role: "user", text: question });
      await send({ ...request, question }, history);
    },
    retry: async (request) => {
      const key = chatSessionKey(request.book, request.session);
      const messages = get().conversations[key] ?? [];
      const last = messages.at(-1);
      if (!last || last.role !== "user" || get().pending[key]) return;
      await send({ ...request, question: last.text }, turns(messages.slice(0, -1)));
    },
    clear: (key) => {
      generations[key] = (generations[key] ?? 0) + 1;
      set((state) => {
        const conversations = { ...state.conversations };
        delete conversations[key];
        save(conversations);
        return { conversations, pending: { ...state.pending, [key]: false }, failed: { ...state.failed, [key]: false } };
      });
    },
  };
});
