import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Bookmark, Ellipsis, Heart, Info, Pin, Star, Trash2, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { booksApi } from "../../api/books";
import { readerStateApi } from "../../api/readerState";
import { useReaderStore } from "../../store/readerStore";
import type { ReaderBookState, ReaderCollection, Session } from "../../types/contracts";
import { BookCover } from "./BookCover";

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
  const closeButton = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const library = useReaderStore((reader) => reader.library);
  const pinnedSessionKeys = library.pinnedSessionKeys ?? emptyPinnedSessionKeys;
  const setPreferences = useReaderStore((reader) => reader.setLibraryPreferences);
  const pinned = pinnedSessionKeys.includes(session.session_key);
  const refreshReader = () => queryClient.invalidateQueries({ queryKey: ["reader-library", userId] });
  const refreshSessions = () => queryClient.invalidateQueries({ queryKey: ["sessions"] });
  const update = useMutation({
    mutationFn: (values: Parameters<typeof readerStateApi.updateBook>[3]) => readerStateApi.updateBook(userId, session.book_name, session.session_name, values),
    onSuccess: refreshReader,
  });
  const remove = useMutation({
    mutationFn: () => booksApi.softDelete(session.book_name, session.session_name),
    onSuccess: () => {
      setRemoved(true);
      setDialog(null);
      window.setTimeout(() => { void refreshSessions(); }, 8000);
    },
  });
  const restore = useMutation({
    mutationFn: () => booksApi.restore(session.book_name, session.session_name),
    onSuccess: () => {
      setRemoved(false);
      void refreshSessions();
    },
  });
  const open = () => {
    setMenu(null);
    void readerStateApi.updateBook(userId, session.book_name, session.session_name, {
      last_opened_at: Date.now() / 1000,
      added_at: session.imported_at ?? Date.now() / 1000,
    });
    navigate(`/reader/${encodeURIComponent(session.book_name)}/${encodeURIComponent(session.session_name)}`);
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
    update.mutate({ favorite: !state?.favorite });
    setMenu(null);
  };
  const togglePinned = () => {
    setPreferences({
      pinnedSessionKeys: pinned
        ? pinnedSessionKeys.filter((key) => key !== session.session_key)
        : [session.session_key, ...pinnedSessionKeys],
    });
    setMenu(null);
  };

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
    {children({ open, showContextMenu, showMenuFromButton, toggleFavorite })}
    {menu && createPortal(<div className="context-menu-layer">
      <button className="context-dismiss" aria-label="Close book menu" onClick={() => setMenu(null)} />
      <div className="card-menu context-menu" style={{ left: menu.x, top: menu.y }} role="menu" aria-label={`Actions for ${session.book_title}`}>
        <button role="menuitem" onClick={open}><BookOpen /><span>Open Book</span></button>
        <button role="menuitem" onClick={toggleFavorite}><Star /><span>{state?.favorite ? "Remove Favourite" : "Add Favourite"}</span></button>
        <button role="menuitem" onClick={() => { setDialog("properties"); setMenu(null); }}><Info /><span>Book Info</span></button>
        <button role="menuitem" onClick={() => { setDialog("remove"); setMenu(null); }}><Trash2 /><span>Remove</span></button>
        <button role="menuitem" onClick={togglePinned}><Pin /><span>{pinned ? "Unpin from Start" : "Pin to Start"}</span></button>
      </div>
    </div>, document.body)}
    {removed && createPortal(<div className="undo-toast" role="status">Removed from Library <button onClick={() => restore.mutate()}>Undo</button></div>, document.body)}
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

export function BookCard({ session, state, userId, collections, bookmarkCount = 0, compact = false }: BookActionProps & { bookmarkCount?: number; compact?: boolean }) {
  return <BookActionController session={session} state={state} userId={userId} collections={collections}>{({ open, showContextMenu, showMenuFromButton, toggleFavorite }) =>
    <article className={`premium-book-card ${compact ? "compact" : ""}`} onContextMenu={showContextMenu}>
      <button className="book-open-area" onClick={open} aria-label={`${state?.book_progress ? "Continue" : "Open"} ${session.book_title}`}>
        <BookCover book={session.book_name} session={session.session_name} title={session.book_title} />
        <span className="book-copy">
          <small>{state?.finished_at ? "Finished" : (state?.book_progress ?? 0) > 0 ? `${Math.round((state?.book_progress ?? 0) * 100)}% read` : "Ready to read"}</small>
          <strong>{session.book_title}</strong>
          <span>{session.author || "Unknown author"}</span>
        </span>
      </button>
      <div className="book-card-actions">
        <button aria-label={state?.favorite ? "Remove from favorites" : "Add to favorites"} className={state?.favorite ? "active" : ""} onClick={toggleFavorite}><Heart /></button>
        {bookmarkCount > 0 && <span title={`${bookmarkCount} saved items`}><Bookmark />{bookmarkCount}</span>}
        <button aria-label={`More actions for ${session.book_title}`} onClick={showMenuFromButton}><Ellipsis /></button>
      </div>
      <div className="card-progress" aria-label={`${Math.round((state?.book_progress ?? 0) * 100)}% read`}><span style={{ width: `${Math.round((state?.book_progress ?? 0) * 100)}%` }} /></div>
    </article>
  }</BookActionController>;
}
