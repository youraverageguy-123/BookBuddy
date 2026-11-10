import { useMutation } from "@tanstack/react-query";
import { SendHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { knowledgeApi, type ChatTurn } from "../../api/knowledge";
import { finishedChaptersLabel } from "./knowledgeModel";

interface ChatMessage extends ChatTurn { sources?: { chapter_index: number; chapter_title: string }[] }

const suggestions = ["Who are the main characters so far?", "Summarize what has happened so far.", "Remind me how these characters know each other."];

export function ChatPanel({ book, session, asOfChapter, aiAvailable, variant = "page", onClose }: {
  book: string; session: string; asOfChapter: number; aiAvailable: boolean; variant?: "page" | "drawer"; onClose?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const log = useRef<HTMLDivElement>(null);
  const ask = useMutation({
    mutationFn: ({ question, history }: { question: string; history: ChatTurn[] }) => knowledgeApi.chat(book, session, question, asOfChapter, history),
    onSuccess: (data) => setMessages((current) => [...current, { role: "assistant", text: data.answer, sources: data.sources }]),
  });
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [messages, ask.isPending]);

  const ready = aiAvailable && asOfChapter >= 0;
  const send = (text: string) => {
    const question = text.trim();
    if (!question || !ready || ask.isPending) return;
    const history = messages.map(({ role, text: body }) => ({ role, text: body }));
    setMessages((current) => [...current, { role: "user", text: question }]);
    setDraft("");
    ask.mutate({ question, history });
  };

  return <section className={`chat-panel chat-${variant}`} aria-label="Ask about this book">
    <header>
      <div><strong>Ask about this book</strong><small>{asOfChapter >= 0 ? `Answers use only ${finishedChaptersLabel(asOfChapter)}, which you have finished.` : "Finish a chapter to start asking."}</small></div>
      {onClose && <button type="button" aria-label="Close chat" onClick={onClose}><X/></button>}
    </header>
    <div className="chat-log" ref={log} aria-live="polite">
      {!aiAvailable && <p className="chat-notice">Chat needs a Gemini API key. <Link to="/settings">Open AI settings</Link></p>}
      {aiAvailable && asOfChapter < 0 && <p className="chat-notice">BookBuddy only answers from chapters you have finished, so nothing can be spoiled. Finish the first chapter and come back.</p>}
      {ready && messages.length === 0 && <div className="chat-suggestions">{suggestions.map((text) => <button key={text} type="button" onClick={() => send(text)}>{text}</button>)}</div>}
      {messages.map((message, index) => <article key={index} className={`chat-message from-${message.role}`}>
        <p>{message.text}</p>
        {message.sources && message.sources.length > 0 && <small>From {message.sources.map((source) => `chapter ${source.chapter_index + 1}`).join(", ")}</small>}
      </article>)}
      {ask.isPending && <p className="chat-notice" role="status">Thinking…</p>}
      {ask.error && <p className="chat-notice" role="alert">BookBuddy could not answer that. <button type="button" className="text-button" onClick={() => { const last = [...messages].reverse().find((message) => message.role === "user"); if (last) ask.mutate({ question: last.text, history: messages.slice(0, -1).map(({ role, text }) => ({ role, text })) }); }}>Try again</button></p>}
    </div>
    <form onSubmit={(event) => { event.preventDefault(); send(draft); }}>
      <input aria-label="Your question" value={draft} maxLength={1000} disabled={!ready} onChange={(event) => setDraft(event.target.value)} placeholder={ready ? "Ask about what you have read" : "Chat is not available yet"}/>
      <button type="submit" aria-label="Send question" disabled={!ready || ask.isPending || !draft.trim()}><SendHorizontal/></button>
    </form>
  </section>;
}
