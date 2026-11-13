import { SendHorizontal, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { chatSessionKey, useChatStore } from "./chatStore";
import { finishedChaptersLabel } from "./knowledgeModel";

const suggestions = ["Who are the main characters so far?", "Summarize what has happened so far.", "Remind me how these characters know each other."];
const EMPTY: never[] = [];

export function ChatPanel({ book, session, asOfChapter, aiAvailable, variant = "page", onClose }: {
  book: string; session: string; asOfChapter: number; aiAvailable: boolean; variant?: "page" | "drawer"; onClose?: () => void;
}) {
  const sessionKey = chatSessionKey(book, session);
  const messages = useChatStore((state) => state.conversations[sessionKey] ?? EMPTY);
  const pending = useChatStore((state) => Boolean(state.pending[sessionKey]));
  const failed = useChatStore((state) => Boolean(state.failed[sessionKey]));
  const ask = useChatStore((state) => state.ask);
  const retry = useChatStore((state) => state.retry);
  const clear = useChatStore((state) => state.clear);
  const [draft, setDraft] = useState("");
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [messages, pending, failed]);

  const ready = aiAvailable && asOfChapter >= 0;
  // A question left unanswered by a restart or a dropped request can be sent again.
  const unanswered = !pending && messages.at(-1)?.role === "user";
  const send = (text: string) => {
    if (!text.trim() || !ready || pending) return;
    setDraft("");
    void ask({ book, session, asOfChapter, question: text });
  };

  return <section className={`chat-panel chat-${variant}`} aria-label="Ask about this book">
    <header>
      <div><strong>Ask about this book</strong><small>{asOfChapter >= 0 ? `Answers use only ${finishedChaptersLabel(asOfChapter)}, which you have read.` : "Finish a chapter to start asking."}</small></div>
      <div className="chat-header-actions">
        {messages.length > 0 && <button type="button" aria-label="Clear conversation" title="Clear conversation" onClick={() => clear(sessionKey)}><Trash2/></button>}
        {onClose && <button type="button" aria-label="Close chat" onClick={onClose}><X/></button>}
      </div>
    </header>
    <div className="chat-log" ref={log} aria-live="polite">
      {!aiAvailable && <p className="chat-notice">Chat needs a Gemini API key. <Link to="/settings">Open AI settings</Link></p>}
      {aiAvailable && asOfChapter < 0 && <p className="chat-notice">BookBuddy only answers from chapters you have read, so nothing can be spoiled. Finish the first chapter and come back.</p>}
      {ready && messages.length === 0 && <div className="chat-suggestions">{suggestions.map((text) => <button key={text} type="button" onClick={() => send(text)}>{text}</button>)}</div>}
      {messages.map((message, index) => <article key={index} className={`chat-message from-${message.role}`}>
        <p>{message.text}</p>
        {message.sources && message.sources.length > 0 && <small>From {message.sources.map((source) => `chapter ${source.chapter_index + 1}`).join(", ")}</small>}
      </article>)}
      {pending && <p className="chat-notice" role="status">Thinking…</p>}
      {unanswered && ready && <p className="chat-notice" role={failed ? "alert" : "status"}>{failed ? "BookBuddy could not get an answer. Gemini may be busy or unreachable." : "This question was not answered."} <button type="button" className="text-button" onClick={() => void retry({ book, session, asOfChapter })}>Try again</button></p>}
    </div>
    <form onSubmit={(event) => { event.preventDefault(); send(draft); }}>
      <input aria-label="Your question" value={draft} maxLength={1000} disabled={!ready} onChange={(event) => setDraft(event.target.value)} placeholder={ready ? "Ask about what you have read" : "Chat is not available yet"}/>
      <button type="submit" aria-label="Send question" disabled={!ready || pending || !draft.trim()}><SendHorizontal/></button>
    </form>
  </section>;
}
