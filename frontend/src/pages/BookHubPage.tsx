import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, CalendarClock, Check, Lock, MessageCircle, Network, NotebookPen, Pencil, Star, Users } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { readerStateApi } from "../api/readerState";
import { PageSkeleton } from "../components/common/Skeleton";
import { BookCover } from "../components/library/BookCover";
import { AnalysisCard } from "../features/analysis/AnalysisCard";
import { finishedChaptersLabel, knowledgeBoundary } from "../features/knowledge/knowledgeModel";
import { useLibraryModel } from "../hooks/useLibraryModel";
import { effectiveBookMetadata, formatBytes, formatDate } from "../utils/bookMetadata";

/** One place per book: continue reading, choose how it is analysed, and reach everything BookBuddy knows about it. */
export default function BookHubPage() {
  const params = useParams<{ book: string; session: string }>();
  const book = decodeURIComponent(params.book ?? ""); const session = decodeURIComponent(params.session ?? "");
  const model = useLibraryModel(); const navigate = useNavigate(); const queryClient = useQueryClient();
  const userId = model.userId;
  const item = model.sessions.data?.sessions.find((candidate) => candidate.book_name === book && candidate.session_name === session);
  const state = item ? model.stateBySession.get(item.session_key) : undefined;
  const metadata = item ? effectiveBookMetadata(item, state) : null;
  const sessionKey = `${book}::${session}`;
  const boundary = useMemo(() => knowledgeBoundary(model.reader.data?.chapters ?? [], model.reader.data?.books ?? [], sessionKey), [model.reader.data?.books, model.reader.data?.chapters, sessionKey]);
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState(""); const [rating, setRating] = useState(0);
  const save = useMutation({
    mutationFn: () => readerStateApi.updateBook(userId!, book, session, { description_override: description.trim(), rating }),
    onSuccess: () => { setEditing(false); void queryClient.invalidateQueries({ queryKey: ["reader-library", userId] }); },
  });

  if (model.sessions.isLoading || (userId && model.reader.isLoading)) return <PageSkeleton label="Loading book"/>;
  if (!item || !metadata || !userId) return <main className="centered-state" role="alert"><h1>Book unavailable</h1><Link to="/library">Return to Library</Link></main>;

  const progress = Math.round((state?.book_progress ?? 0) * 100);
  const bookmarks = model.bookmarksBySession.get(sessionKey) ?? 0; const notes = model.annotationCounts.get(sessionKey) ?? 0;
  const readerLink = `/reader/${encodeURIComponent(book)}/${encodeURIComponent(session)}`;
  const knowledge = (tab: string) => `/book/${encodeURIComponent(book)}/${encodeURIComponent(session)}/knowledge?tab=${tab}`;
  const open = () => {
    void readerStateApi.updateBook(userId, book, session, { last_opened_at: Date.now() / 1000, added_at: item.imported_at ?? Date.now() / 1000 });
    navigate(readerLink);
  };
  const startEditing = () => { setDescription(state?.description_override ?? ""); setRating(state?.rating ?? 0); setEditing(true); };
  const unlocked = boundary >= 0;
  const lockedReason = "Finish a chapter, or use Custom analysis above.";

  return <main className="book-hub page-frame">
    <Link className="back-link" to="/library"><ArrowLeft/>Library</Link>
    <section className="hub-hero">
      <BookCover book={book} session={session} title={metadata.title} featured/>
      <div className="hub-hero-copy">
        <p className="eyebrow">{state?.finished_at ? "Finished" : progress > 0 ? "Currently reading" : "Ready to read"}</p>
        <h1>{metadata.title}</h1>
        <p className="hub-author">{metadata.author}</p>
        <div className="detail-progress"><strong>{progress}%</strong><span>Reading progress</span><div className="card-progress"><span style={{ width: `${progress}%` }}/></div></div>
        <div className="book-details-actions">
          <button className="primary hub-continue" onClick={open}><BookOpen/>{progress > 0 ? "Continue reading" : "Start reading"}</button>
          <button className="secondary" onClick={startEditing}><Pencil/>Edit details</button>
        </div>
        <p className="hub-boundary">{unlocked ? `Story knowledge is unlocked for ${finishedChaptersLabel(boundary)}.` : "Story knowledge unlocks as you read, or when you tell BookBuddy how far you have already read."}</p>
      </div>
    </section>

    <AnalysisCard book={book} session={session} userId={userId} mode={state?.analysis_mode ?? null}
      declaredThrough={state?.knowledge_through_chapter ?? null} currentChapter={state?.current_chapter ?? null}/>

    <section aria-labelledby="hub-explore">
      <div className="section-heading"><h2 id="hub-explore">Explore this book</h2></div>
      <div className="hub-tiles">
        <HubTile to={knowledge("characters")} icon={<Users/>} title="Characters" text="Who is who, with aliases and events." locked={!unlocked} lockedReason={lockedReason}/>
        <HubTile to={knowledge("relationships")} icon={<Network/>} title="Relationship map" text="How everyone is connected so far." locked={!unlocked} lockedReason={lockedReason}/>
        <HubTile to={knowledge("timeline")} icon={<CalendarClock/>} title="Timeline" text="What happened, chapter by chapter." locked={!unlocked} lockedReason={lockedReason}/>
        <HubTile to={knowledge("chat")} icon={<MessageCircle/>} title="Ask about this book" text="Chat that only uses what you have read." locked={!unlocked} lockedReason={lockedReason}/>
        <HubTile to={readerLink} icon={<NotebookPen/>} title="Notes and bookmarks" text={`${notes} note${notes === 1 ? "" : "s"} and highlight${notes === 1 ? "" : "s"} · ${bookmarks} bookmark${bookmarks === 1 ? "" : "s"}. Opens in the reader.`}/>
      </div>
    </section>

    <section className="description-panel">
      <div className="section-heading"><h2>About this book</h2>{metadata.rating !== undefined && metadata.rating !== null && metadata.rating > 0 && <span className="rating-display"><Star fill="currentColor"/> {metadata.rating}/5</span>}</div>
      {metadata.description ? <p className="book-description">{metadata.description}</p> : <p className="quiet-empty">No description is included in this book.</p>}
      <dl className="metadata-grid">
        <Meta label="Series" value={metadata.series}/><Meta label="Publisher" value={metadata.publisher}/>
        <Meta label="Language" value={metadata.language}/><Meta label="Publication year" value={metadata.publicationYear}/>
        <Meta label="Genres" value={metadata.genres.join(", ")}/><Meta label="File size" value={formatBytes(metadata.fileSizeBytes)}/>
        <Meta label="Word count" value={metadata.wordCount ? metadata.wordCount.toLocaleString() : ""}/><Meta label="Added" value={formatDate(state?.added_at ?? item.imported_at)}/>
        <Meta label="Last opened" value={formatDate(state?.last_opened_at)}/>
      </dl>
    </section>

    {editing && <div className="dialog-overlay">
      <form className="book-dialog" role="dialog" aria-modal="true" aria-label="Edit details" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <h2>Edit details</h2>
        <label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={20000}/></label>
        <label>Rating<select value={rating} onChange={(event) => setRating(Number(event.target.value))}>{[0, 1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value ? `${value}/5` : "Not rated"}</option>)}</select></label>
        <button className="primary" disabled={save.isPending}><Check/>Save</button>
        <button type="button" className="secondary" onClick={() => setEditing(false)}>Cancel</button>
      </form>
    </div>}
  </main>;
}

function HubTile({ to, icon, title, text, locked = false, lockedReason = "" }: { to: string; icon: ReactNode; title: string; text: string; locked?: boolean; lockedReason?: string }) {
  return <Link className={`hub-tile ${locked ? "locked" : ""}`} to={to}>
    <span className="hub-tile-icon" aria-hidden="true">{locked ? <Lock/> : icon}</span>
    <strong>{title}</strong>
    <small>{locked ? lockedReason : text}</small>
  </Link>;
}

function Meta({ label, value }: { label: string; value: string | null | undefined }) {
  return <div><dt>{label}</dt><dd>{value || "Unavailable"}</dd></div>;
}
