import { useMutation, useQueryClient } from "@tanstack/react-query";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import { AlertCircle, BookOpen, ChevronDown, Grid2X2, List, LoaderCircle, Plus, Search, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { booksApi } from "../api/books";
import { readerStateApi } from "../api/readerState";
import { BookCard } from "../components/library/BookCard";
import { useLibraryModel } from "../hooks/useLibraryModel";
import { useReaderStore } from "../store/readerStore";
import { afterStablePaint, recordPerformanceSample } from "../services/performance/recorder";
import { effectiveBookMetadata, metadataSearch } from "../utils/bookMetadata";

const isTauri = (): boolean => "__TAURI_INTERNALS__" in window;
type Filter = "all" | "reading" | "unread" | "finished" | "favorites" | "attention";

export default function LibraryPage({ onReady }: { onReady?: () => void }) {
  const model = useLibraryModel(); const navigate = useNavigate(); const queryClient = useQueryClient(); const input = useRef<HTMLInputElement>(null); const uploadStarted=useRef(0);
  const [query, setQuery] = useState(""); const [filter, setFilter] = useState<Filter>("all"); const [dragging, setDragging] = useState(false);
  const sort = useReaderStore((state) => state.library.sort); const density = useReaderStore((state) => state.library.density); const setPreferences = useReaderStore((state) => state.setLibraryPreferences);
  const upload = useMutation({ mutationFn: async (source?: File | string) => typeof source === "string" ? booksApi.uploadDesktopPath(source) : isTauri() ? booksApi.uploadDesktop() : source ? booksApi.uploadWeb(source) : null, onSuccess: async (result) => { if (!result || !model.userId) return; if(uploadStarted.current)recordPerformanceSample("import_5mb",performance.now()-uploadStarted.current); await Promise.all([readerStateApi.updateBook(model.userId, result.book_name, result.session_name, { added_at: Date.now() / 1000, last_opened_at: Date.now() / 1000 }), queryClient.invalidateQueries({ queryKey: ["sessions"] }), queryClient.invalidateQueries({ queryKey: ["reader-library", model.userId] })]); navigate(`/reader/${encodeURIComponent(result.book_name)}/${encodeURIComponent(result.session_name)}`); } });
  const openPicker = () => { uploadStarted.current=performance.now(); return isTauri() ? upload.mutate(undefined) : input.current?.click(); };
  const measureInteraction=(action:()=>void) => {const started=performance.now();action();afterStablePaint(started,"home_interaction");};

  useEffect(() => { if (model.sessions.isSuccess && model.reader.isSuccess) onReady?.(); }, [model.reader.isSuccess, model.sessions.isSuccess, onReady]);
  useEffect(() => { const key = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") { event.preventDefault(); openPicker(); } }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); });
  useEffect(() => {
    if (!isTauri()) return;
    let unlisten: (() => void) | undefined;
    void getCurrentWebviewWindow().onDragDropEvent((event) => {
      if (event.payload.type === "over") setDragging(true);
      if (event.payload.type === "leave") setDragging(false);
      if (event.payload.type === "drop") { setDragging(false); const paths = event.payload.paths.filter((path) => path.toLowerCase().endsWith(".epub")); if (paths.length === 1) {uploadStarted.current=performance.now();upload.mutate(paths[0]);} }
    }).then((dispose) => { unlisten = dispose; });
    return () => unlisten?.();
  });

  const items = useMemo(() => {
    const needle = query.trim().toLowerCase(); const collectionsBySession = new Map<string, string[]>();
    for (const collection of model.collections) for (const key of collection.session_keys) collectionsBySession.set(key, [...(collectionsBySession.get(key) ?? []), collection.name]);
    const list = (model.sessions.data?.sessions ?? []).filter((item) => {
      const state = model.stateBySession.get(item.session_key); const searched = metadataSearch(effectiveBookMetadata(item,state), collectionsBySession.get(item.session_key) ?? [], needle);
      if (needle && !searched.matches) return false;
      if (filter === "reading") return Boolean(state && state.book_progress > 0 && !state.finished_at);
      if (filter === "unread") return Boolean(state?.want_to_read || !state || state.book_progress === 0);
      if (filter === "finished") return Boolean(state?.finished_at);
      if (filter === "favorites") return Boolean(state?.favorite);
      if (filter === "attention") return item.integrity?.status === "broken";
      return true;
    });
    return list.sort((a, b) => {
      const left = model.stateBySession.get(a.session_key); const right = model.stateBySession.get(b.session_key);
      if (sort === "title") return a.book_title.localeCompare(b.book_title);
      if (sort === "author") return (a.author ?? "").localeCompare(b.author ?? "");
      if (sort === "added") return (b.imported_at ?? 0) - (a.imported_at ?? 0);
      if (sort === "progress") return (right?.book_progress ?? 0) - (left?.book_progress ?? 0);
      if (sort === "rating") return (right?.rating ?? 0) - (left?.rating ?? 0);
      if (sort === "series") return (effectiveBookMetadata(a,left).series).localeCompare(effectiveBookMetadata(b,right).series);
      if (sort === "year") return effectiveBookMetadata(b,right).publicationYear.localeCompare(effectiveBookMetadata(a,left).publicationYear);
      return (right?.last_opened_at ?? b.updated_at ?? 0) - (left?.last_opened_at ?? a.updated_at ?? 0);
    });
  }, [filter, model.collections, model.sessions.data?.sessions, model.stateBySession, query, sort]);

  if (!model.userId) return <main className="centered-state">Reader profile unavailable.</main>;
  const all = model.sessions.data?.sessions ?? [];
  return <main className="library-page page-frame" onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }} onDrop={(event) => { event.preventDefault(); setDragging(false); const files = [...event.dataTransfer.files].filter((file) => file.name.toLowerCase().endsWith(".epub")); if (files.length === 1) {uploadStarted.current=performance.now();upload.mutate(files[0]);} }}>
    <header className="page-intro library-intro"><div><p className="eyebrow">Every story, within reach</p><h1>Library</h1><p>Search, sort, or simply follow the cover that calls to you.</p></div>{all.length > 0 && <button className="quiet-import" onClick={openPicker}><Upload/>Import <kbd>Ctrl O</kbd></button>}</header>
    <input ref={input} hidden type="file" accept=".epub,application/epub+zip" onChange={(event) => { const file = event.target.files?.[0]; if (file) {uploadStarted.current=performance.now();upload.mutate(file);} event.target.value = ""; }}/>
    {(upload.error || model.sessions.error) && <div className="notice error" role="alert"><AlertCircle/><span>{(upload.error ?? model.sessions.error)?.message}</span></div>}
    {model.sessions.isLoading ? <div className="centered-state"><LoaderCircle className="spin"/>Loading library…</div> : all.length === 0 ? <button className="library-empty-drop" onClick={openPicker}><BookOpen/><h2>Your library is empty</h2><p>Upload your first book</p><span><Plus/></span><small>or drag an EPUB here</small></button> : <>
      <section className="library-tools" aria-label="Library controls"><label className="search-field"><Search/><span className="sr-only">Search library metadata</span><input value={query} onChange={(event) => measureInteraction(()=>setQuery(event.target.value))} placeholder="Search title, author, series, description, or tags"/></label><select aria-label="Filter library" value={filter} onChange={(event) => measureInteraction(()=>setFilter(event.target.value as Filter))}><option value="all">All books</option><option value="reading">Currently Reading</option><option value="unread">Unread / Want to Read</option><option value="finished">Finished</option><option value="favorites">Favorites</option><option value="attention">Needs Attention</option></select><select aria-label="Sort library" value={sort} onChange={(event) => measureInteraction(()=>setPreferences({ sort: event.target.value as typeof sort }))}><option value="recent">Recently opened</option><option value="added">Recently added</option><option value="title">Title</option><option value="author">Author</option><option value="progress">Progress</option><option value="rating">Rating</option><option value="series">Series</option><option value="year">Publication year</option></select><div className="view-switcher" aria-label="Library view"><button className={density === "grid" ? "active" : ""} aria-label="Grid view" onClick={() => setPreferences({density:"grid"})}><Grid2X2/></button><button className={density === "large" ? "active" : ""} aria-label="Large covers" onClick={() => setPreferences({density:"large"})}><BookOpen/></button><button className={density === "compact" ? "active" : ""} aria-label="Compact list" onClick={() => setPreferences({density:"compact"})}><List/></button><button className={density === "detailed" ? "active" : ""} aria-label="Detailed list" onClick={() => setPreferences({density:"detailed"})}><ChevronDown/></button></div></section>
      <p className="result-count" role="status">{items.length} {items.length === 1 ? "book" : "books"}{query && ` · Search scope: metadata`}</p>
      {items.length ? <div className={`book-grid ${density}`}>{items.map((item) => { const state=model.stateBySession.get(item.session_key); const collections=model.collections.filter((collection)=>collection.session_keys.includes(item.session_key)).map((collection)=>collection.name); const reason=metadataSearch(effectiveBookMetadata(item,state),collections,query).reason; return <BookCard compact={density === "compact"} view={density} matchReason={reason} key={item.session_key} session={item} state={state} userId={model.userId!} collections={model.collections} bookmarkCount={model.bookmarksBySession.get(item.session_key)}/>; })}</div> : <div className="quiet-empty large"><Search/><strong>No books match this view.</strong><span>Try a broader search or clear a filter.</span><button className="secondary" onClick={() => {setQuery("");setFilter("all")}}>Clear search and filters</button></div>}
    </>}
    {dragging && <div className="drop-overlay" role="status"><Upload/><strong>Drop EPUB to Import</strong></div>}
    {upload.isPending && <div className="import-progress" role="status"><LoaderCircle className="spin"/>Importing your book…</div>}
  </main>;
}
