import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Bookmark, ClipboardCopy, Download, Ellipsis, FolderOpen, Heart, Info, Library, Pin, Star, Trash2, X } from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { writeText } from "@tauri-apps/plugin-clipboard-manager";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { useEffect, useId, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { booksApi } from "../../api/books";
import { readerStateApi } from "../../api/readerState";
import { useReaderStore } from "../../store/readerStore";
import type { ReaderBookState, ReaderCollection, Session } from "../../types/contracts";
import type { ReaderLibraryState } from "../../types/contracts";
import { BookCover } from "./BookCover";
import { effectiveBookMetadata } from "../../utils/bookMetadata";

type DialogKind = "remove" | "properties" | null;
type BookActionProps = {
  session: Session;
  state?: ReaderBookState;
  userId: string;
  collections: ReaderCollection[];
};
type BookActionControls = {
  open: () => void;
  showContextMenu: (event: MouseEvent<HTMLElement>) => void;
  showMenuFromButton: (event: MouseEvent<HTMLButtonElement>) => void;
  toggleFavorite: () => void;
  favoritePending: boolean;
  pinned: boolean;
};
type BookActionControllerProps = BookActionProps & {
  children: (controls: BookActionControls) => ReactNode;
};

const emptyPinnedSessionKeys: string[] = [];

/** Owns the actions shared by full cards and the specialized book covers on Home. */
export function BookActionController({ session, state, userId, collections, children }: BookActionControllerProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [removed, setRemoved] = useState(false);
  const [actionNotice, setActionNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const removalTimer = useRef<number | null>(null);
  const titleId = useId();
  const library = useReaderStore((reader) => reader.library);
  const pinnedSessionKeys = library.pinnedSessionKeys ?? emptyPinnedSessionKeys;
  const setPreferences = useReaderStore((reader) => reader.setLibraryPreferences);
  const pinned = pinnedSessionKeys.includes(session.session_key);
  const refreshReader = () => queryClient.invalidateQueries({ queryKey: ["reader-library", userId] });
  const refreshSessions = () => queryClient.invalidateQueries({ queryKey: ["sessions"] });
  const update = useMutation({
    mutationFn: (values: Parameters<typeof readerStateApi.updateBook>[3]) => readerStateApi.updateBook(userId, session.book_name, session.session_name, values),
    onMutate: async (values) => {
      const queryKey = ["reader-library", userId] as const;
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<ReaderLibraryState>(queryKey);
      if (previous) {
        queryClient.setQueryData<ReaderLibraryState>(queryKey, {
          ...previous,
          books: previous.books.map((book) => book.session_key === session.session_key ? { ...book, ...values } : book),
        });
      }
      return { previous };
    },
    onSuccess: (_data, values) => {
      if (typeof values.favorite === "boolean") {
        setActionNotice({ kind: "success", text: values.favorite ? "Added to Favourites" : "Removed from Favourites" });
      }
    },
    onError: (_error, _values, context) => {
      if (context?.previous) queryClient.setQueryData(["reader-library", userId], context.previous);
      setActionNotice({ kind: "error", text: "Book preference could not be saved" });
    },
    onSettled: refreshReader,
  });
  const remove = useMutation({
    mutationFn: () => booksApi.softDelete(session.book_name, session.session_name),
    onSuccess: () => {
      setRemoved(true);
      setDialog(null);
      if (removalTimer.current !== null) window.clearTimeout(removalTimer.current);
      removalTimer.current = window.setTimeout(() => { void refreshSessions(); }, 8000);
    },
    onError: () => setActionNotice({ kind: "error", text: "Book could not be removed" }),
  });
  const restore = useMutation({
    mutationFn: () => booksApi.restore(session.book_name, session.session_name),
    onSuccess: () => {
      if (removalTimer.current !== null) window.clearTimeout(removalTimer.current);
      setRemoved(false);
      void refreshSessions();
    },
    onError: () => setActionNotice({ kind: "error", text: "Book could not be restored" }),
  });
  const membership = useMutation({
    mutationFn: ({ collectionId, present }: { collectionId: string; present: boolean }) => readerStateApi.setCollectionMember(userId, collectionId, session.session_key, present),
    onSuccess: (_data, variables) => {
      setActionNotice({ kind: "success", text: variables.present ? "Added to collection" : "Removed from collection" });
      void refreshReader();
    },
    onError: () => setActionNotice({ kind: "error", text: "Collection could not be updated" }),
  });
  const open = () => {
    setMenu(null);
    void readerStateApi.updateBook(userId, session.book_name, session.session_name, {
      last_opened_at: Date.now() / 1000,
      added_at: session.imported_at ?? Date.now() / 1000,
    });
    navigate(`/reader/${encodeURIComponent(session.book_name)}/${encodeURIComponent(session.session_name)}`);
  };
  const details = () => { setMenu(null); navigate(`/book/${encodeURIComponent(session.book_name)}/${encodeURIComponent(session.session_name)}`); };
  const copy = async (text: string, label: string) => { try { if ("__TAURI_INTERNALS__" in window) await writeText(text); else await navigator.clipboard.writeText(text); setActionNotice({kind:"success",text:`${label} copied`}); } catch { setActionNotice({kind:"error",text:`${label} could not be copied`}); } setMenu(null); };
  const sourcePath = async () => invoke<string>("session_source_path", { book: session.book_name, session: session.session_name });
  const revealFile = async () => {
    try {
      if (!("__TAURI_INTERNALS__" in window)) throw new Error("desktop_only");
      await revealItemInDir(await sourcePath());
      setActionNotice({ kind: "success", text: "Book file revealed" });
    } catch {
      setActionNotice({ kind: "error", text: "Reveal File is available in the desktop app" });
    }
    setMenu(null);
  };
  const copyFilePath = async () => {
    try {
      if (!("__TAURI_INTERNALS__" in window)) throw new Error("desktop_only");
      await copy(await sourcePath(), "File path");
    } catch {
      setActionNotice({ kind: "error", text: "File path is available in the desktop app" });
      setMenu(null);
    }
  };
  const exportNotes = async () => {
    try {
      const payload = await booksApi.exportNotes(userId, session.book_name, session.session_name);
      const filename = `${(state?.title_override || session.book_title).replace(/[\\/:*?"<>|]/g, "_")}-notes.md`;
      if ("__TAURI_INTERNALS__" in window) {
        await invoke("save_text_export", { filename, contents: new TextDecoder().decode(payload) });
      } else {
        const url = URL.createObjectURL(new Blob([payload], { type: "text/markdown" }));
        const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      }
      setActionNotice({ kind: "success", text: "Notes exported" });
    } catch {
      setActionNotice({ kind: "error", text: "Notes could not be exported" });
    }
    setMenu(null);
  };
  const showMenu = (x: number, y: number) => {
    setMenu({
      x: Math.max(8, Math.min(window.innerWidth - 252, x)),
      y: Math.max(8, Math.min(window.innerHeight - 278, y)),
    });
  };
  const showContextMenu = (event: MouseEvent<HTMLElement>) => {
    event.preventDefault();
    showMenu(event.clientX, event.clientY);
  };
  const showMenuFromButton = (event: MouseEvent<HTMLButtonElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    showMenu(rect.right - 220, rect.bottom + 4);
  };
  const toggleFavorite = () => {
    if (update.isPending) return;
    update.mutate({ favorite: !state?.favorite });
    setMenu(null);
  };
  const togglePinned = () => {
    setPreferences({
      pinnedSessionKeys: pinned
        ? pinnedSessionKeys.filter((key) => key !== session.session_key)
        : [session.session_key, ...pinnedSessionKeys],
    });
    setActionNotice({ kind: "success", text: pinned ? "Unpinned from Start" : "Pinned to Start" });
    setMenu(null);
  };

  useEffect(() => {
    if (!actionNotice) return;
    const timer = window.setTimeout(() => setActionNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [actionNotice]);

  useEffect(() => () => {
    if (removalTimer.current !== null) window.clearTimeout(removalTimer.current);
  }, []);

  useEffect(() => {
    if (!menu && !dialog) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenu(null);
        setDialog(null);
      }
    };
    const closeOnResize = () => setMenu(null);
    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("resize", closeOnResize);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("resize", closeOnResize);
    };
  }, [dialog, menu]);

  useEffect(() => {
    if (dialog) closeButton.current?.focus();
  }, [dialog]);

  return <>
    {!removed && children({ open, showContextMenu, showMenuFromButton, toggleFavorite, favoritePending: update.isPending, pinned })}
    {menu && createPortal(<div className="context-menu-layer">
      <button className="context-dismiss" aria-label="Close book menu" onClick={() => setMenu(null)} />
      <div className="card-menu context-menu" style={{ left: menu.x, top: menu.y }} role="menu" aria-label={`Actions for ${session.book_title}`}>
        <button role="menuitem" onClick={open}><BookOpen /><span>Open Book</span></button>
        <button role="menuitem" onClick={toggleFavorite}><Star /><span>{state?.favorite ? "Remove Favourite" : "Add Favourite"}</span></button>
        <button role="menuitem" onClick={() => { setDialog("properties"); setMenu(null); }}><Info /><span>Book Info</span></button>
        <button role="menuitem" onClick={details}><FolderOpen /><span>Book Details</span></button>
        <button role="menuitem" onClick={() => void copy(state?.title_override || session.book_title,"Title")}><ClipboardCopy/><span>Copy Title</span></button>
        <button role="menuitem" onClick={() => void copy(state?.author_override || session.author || "Unknown author","Author")}><ClipboardCopy/><span>Copy Author</span></button>
        <button role="menuitem" onClick={() => void revealFile()}><FolderOpen/><span>Reveal File</span></button>
        <button role="menuitem" onClick={() => void copyFilePath()}><ClipboardCopy/><span>Copy File Path</span></button>
        <button role="menuitem" onClick={() => void exportNotes()}><Download/><span>Export Notes</span></button>
        {collections.length > 0 && <div className="context-menu-group" role="group" aria-label="Collections"><span><Library/>Collections</span>{collections.map((collection) => { const present=collection.session_keys.includes(session.session_key); return <button key={collection.collection_id} role="menuitemcheckbox" aria-checked={present} disabled={membership.isPending} onClick={()=>membership.mutate({collectionId:collection.collection_id,present:!present})}><span aria-hidden="true">{present?"✓":""}</span><span>{collection.name}</span></button>; })}</div>}
        <button role="menuitem" onClick={() => { setDialog("remove"); setMenu(null); }}><Trash2 /><span>Remove</span></button>
        <button role="menuitem" onClick={togglePinned}><Pin /><span>{pinned ? "Unpin from Start" : "Pin to Start"}</span></button>
      </div>
    </div>, document.body)}
    {removed && createPortal(<div className="undo-toast" role="status">Removed from Library <button onClick={() => restore.mutate()}>Undo</button></div>, document.body)}
    {actionNotice && createPortal(<div className={`undo-toast action-notice ${actionNotice.kind}`} role={actionNotice.kind === "error" ? "alert" : "status"}>{actionNotice.text}</div>, document.body)}
    {dialog && createPortal(<div className="dialog-overlay" onClick={() => setDialog(null)}>
      <section className="book-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(event) => event.stopPropagation()}>
        <button ref={closeButton} className="dialog-x" aria-label="Close book information" onClick={() => setDialog(null)}><X /></button>
        {dialog === "remove" && <>
          <h2 id={titleId}>Remove this book?</h2>
          <p>You can undo this action or restore it before a permanent purge.</p>
          <button className="primary danger" disabled={remove.isPending} onClick={() => remove.mutate()}>Remove from Library</button>
          <button className="secondary" onClick={() => setDialog(null)}>Keep book</button>
        </>}
        {dialog === "properties" && <>
          <h2 id={titleId}>{session.book_title}</h2>
          <dl>
            <dt>Author</dt><dd>{session.author || "Unknown"}</dd>
            <dt>Session</dt><dd>{session.session_name}</dd>
            <dt>Chapters</dt><dd>{session.total_chapters ?? "Unknown"}</dd>
            <dt>Collections</dt><dd>{collections.filter((collection) => collection.session_keys.includes(session.session_key)).map((collection) => collection.name).join(", ") || "None"}</dd>
            <dt>Integrity</dt><dd>{session.integrity?.status ?? "Available"}</dd>
          </dl>
        </>}
      </section>
    </div>, document.body)}
  </>;
}

export function BookCard({ session, state, userId, collections, bookmarkCount = 0, compact = false, view = compact ? "compact" : "grid", matchReason = "" }: BookActionProps & { bookmarkCount?: number; compact?: boolean; view?: "grid"|"large"|"compact"|"detailed"; matchReason?: string }) {
  const metadata = effectiveBookMetadata(session,state);
  return <BookActionController session={session} state={state} userId={userId} collections={collections}>{({ open, showContextMenu, showMenuFromButton, toggleFavorite, favoritePending, pinned }) =>
    <article className={`premium-book-card ${view}`} onContextMenu={showContextMenu} onAuxClick={(event) => { if(event.button===1){ event.preventDefault(); window.location.hash=`#/book/${encodeURIComponent(session.book_name)}/${encodeURIComponent(session.session_name)}`; } }}>
      <button className="book-open-area" onClick={open} onDoubleClick={open} aria-label={`${state?.book_progress ? "Continue" : "Open"} ${metadata.title}`}>
        <BookCover book={session.book_name} session={session.session_name} title={metadata.title} />
        <span className="book-copy">
          <small>{state?.finished_at ? "Finished" : (state?.book_progress ?? 0) > 0 ? `${Math.round((state?.book_progress ?? 0) * 100)}% read` : "Ready to read"}</small>
          {pinned && <span className="book-pinned-badge"><Pin />Pinned to Start</span>}
          <strong>{metadata.title}</strong>
          <span>{metadata.author}</span>
          {matchReason && <mark className="match-reason">{matchReason}</mark>}
          {view === "detailed" && <><p>{metadata.description || "Description unavailable."}</p><small>{[metadata.series,metadata.publisher,metadata.publicationYear].filter(Boolean).join(" · ") || "Metadata unavailable"}</small></>}
        </span>
      </button>
      <div className="book-card-actions">
        <button disabled={favoritePending} aria-label={state?.favorite ? "Remove from favorites" : "Add to favorites"} className={state?.favorite ? "active" : ""} onClick={toggleFavorite}><Heart fill={state?.favorite ? "currentColor" : "none"} /></button>
        {bookmarkCount > 0 && <span title={`${bookmarkCount} saved items`}><Bookmark />{bookmarkCount}</span>}
        <button aria-label={`More actions for ${session.book_title}`} onClick={showMenuFromButton}><Ellipsis /></button>
      </div>
      <div className="card-progress" aria-label={`${Math.round((state?.book_progress ?? 0) * 100)}% read`}><span style={{ width: `${Math.round((state?.book_progress ?? 0) * 100)}%` }} /></div>
    </article>
  }</BookActionController>;
}
