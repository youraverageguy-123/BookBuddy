import { ArrowLeft, BookOpen, Check, Pencil, Star } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { readerStateApi } from "../api/readerState";
import { BookCover } from "../components/library/BookCover";
import { useLibraryModel } from "../hooks/useLibraryModel";
import { effectiveBookMetadata, formatBytes, formatDate } from "../utils/bookMetadata";
import { useState } from "react";

export default function BookDetailsPage() {
  const params = useParams<{ book: string; session: string }>(); const book = decodeURIComponent(params.book ?? ""); const session = decodeURIComponent(params.session ?? "");
  const model = useLibraryModel(); const navigate = useNavigate(); const queryClient = useQueryClient(); const userId = model.userId;
  const item = model.sessions.data?.sessions.find((candidate) => candidate.book_name === book && candidate.session_name === session);
  const state = item ? model.stateBySession.get(item.session_key) : undefined; const metadata = item ? effectiveBookMetadata(item, state) : null;
  const [editing, setEditing] = useState(false); const [description, setDescription] = useState(state?.description_override ?? ""); const [rating, setRating] = useState(state?.rating ?? 0);
  const save = useMutation({ mutationFn: () => readerStateApi.updateBook(userId!, book, session, { description_override: description.trim(), rating }), onSuccess: () => { setEditing(false); void queryClient.invalidateQueries({ queryKey: ["reader-library", userId] }); } });
  if (!item || !metadata || !userId) return <main className="centered-state" role="alert"><h1>Book unavailable</h1><Link to="/library">Return to Library</Link></main>;
  const sessionKey = item.session_key; const bookmarks = model.bookmarksBySession.get(sessionKey) ?? 0; const annotations = model.annotationCounts.get(sessionKey) ?? 0;
  const open = () => { void readerStateApi.updateBook(userId, book, session, { last_opened_at: Date.now() / 1000, added_at: item.imported_at ?? Date.now() / 1000 }); navigate(`/reader/${encodeURIComponent(book)}/${encodeURIComponent(session)}`); };
  return <main className="book-details-page page-frame">
    <header className="page-intro"><Link className="back-link" to="/library"><ArrowLeft/>Library</Link><p className="eyebrow">Book details</p><h1>{metadata.title}</h1><p>{metadata.author}</p></header>
    <section className="book-details-hero"><BookCover book={book} session={session} title={metadata.title} featured/><div className="book-details-copy"><div className="book-details-actions"><button className="primary" onClick={open}><BookOpen/>Continue Reading</button><button className="secondary" onClick={() => setEditing(!editing)}><Pencil/>Edit local metadata</button></div><div className="detail-progress"><strong>{Math.round((state?.book_progress ?? 0) * 100)}%</strong><span>Reading progress</span><div className="card-progress"><span style={{ width: `${Math.round((state?.book_progress ?? 0) * 100)}%` }}/></div></div><dl className="metadata-grid"><Meta label="Author" value={metadata.author}/><Meta label="Series" value={metadata.series}/><Meta label="Publisher" value={metadata.publisher}/><Meta label="Language" value={metadata.language}/><Meta label="Publication year" value={metadata.publicationYear}/><Meta label="Genres" value={metadata.genres.join(", ")}/><Meta label="File size" value={formatBytes(metadata.fileSizeBytes)}/><Meta label="Word count" value={metadata.wordCount ? metadata.wordCount.toLocaleString() : "Unavailable"}/><Meta label="Added" value={formatDate(state?.added_at ?? item.imported_at)}/><Meta label="Last opened" value={formatDate(state?.last_opened_at)}/><Meta label="Reading status" value={state?.finished_at ? "Finished" : (state?.book_progress ?? 0) > 0 ? "Currently reading" : "Unread"}/><Meta label="Saved items" value={`${bookmarks} bookmarks · ${annotations} notes/highlights`}/></dl></div></section>
    <section className="description-panel"><div className="section-heading"><h2>Description</h2>{metadata.rating !== undefined && metadata.rating !== null && <span className="rating-display"><Star fill="currentColor"/> {metadata.rating}/5</span>}</div>{metadata.description ? <p className="book-description">{metadata.description}</p> : <p className="quiet-empty">Description unavailable in this EPUB.</p>}</section>
    {editing && <div className="dialog-overlay"><form className="book-dialog" role="dialog" aria-modal="true" aria-label="Edit local metadata" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}><h2>Edit local metadata</h2><label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={20000}/></label><label>Rating<select value={rating} onChange={(event) => setRating(Number(event.target.value))}>{[0,1,2,3,4,5].map((value) => <option key={value} value={value}>{value ? `${value}/5` : "Not rated"}</option>)}</select></label><button className="primary" disabled={save.isPending}><Check/>Save</button><button type="button" className="secondary" onClick={() => setEditing(false)}>Cancel</button></form></div>}
  </main>;
}

function Meta({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value || "Unavailable"}</dd></div>; }
