import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, X } from "lucide-react";
import { useMemo, useState, type CSSProperties } from "react";
import { readerStateApi } from "../../api/readerState";
import { normalizeAnnotationColor } from "../../reader/rendition/annotationRendering";
import type { ReaderAnnotation } from "../../types/contracts";
import { NoteColorSelector } from "./NoteColorSelector";

interface EditingAnnotation { id: string; text: string; color: string }

/** The list of saved notes and highlights for a book, with search, jump, edit, and delete. */
export function AnnotationDrawer({ userId, annotations, loading, onClose, onJump }: {
  userId: string | null; annotations: ReaderAnnotation[]; loading: boolean; onClose: () => void; onJump: (cfiRange: string) => void;
}) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<EditingAnnotation | null>(null);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return annotations.filter((item) => !needle || `${item.quote} ${item.note_text} ${item.annotation_type}`.toLowerCase().includes(needle));
  }, [annotations, query]);
  const remove = useMutation({
    mutationFn: (id: string) => readerStateApi.deleteAnnotation(userId!, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reader-annotations", userId] });
      void queryClient.invalidateQueries({ queryKey: ["reader-library", userId] });
    },
  });
  const update = useMutation({
    mutationFn: ({ id, text, color }: EditingAnnotation) => readerStateApi.updateAnnotation(userId!, id, { note_text: text, color }),
    onSuccess: () => { setEditing(null); void queryClient.invalidateQueries({ queryKey: ["reader-annotations", userId] }); },
  });

  return <>
    <aside className="annotation-drawer" aria-label="Notes for this book">
      <header>
        <div><strong>Book notes</strong><small>{visible.length} saved</small></div>
        <button aria-label="Close notes" onClick={onClose}><X/></button>
      </header>
      <input aria-label="Search annotations" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search notes and saved lines"/>
      {loading ? <p>Loading annotations…</p>
        : visible.length === 0 ? <p className="annotation-empty">No saved notes or highlights yet. Select a line in the book to add one.</p>
        : visible.map((item) => {
          const color = normalizeAnnotationColor(item.color, item.annotation_type === "underline" ? "underline" : "highlight");
          return <article key={item.annotation_id} style={{ "--annotation-color": color } as CSSProperties}>
            <button className="annotation-jump" onClick={() => onJump(item.cfi_range)}>
              <small><i className="annotation-color-dot" style={{ background: color }}/>{item.annotation_type === "note" ? "Note" : item.annotation_type} · Chapter {item.chapter_index + 1}</small>
              {item.quote && <q>{item.quote}</q>}
              {item.note_text && <span className="annotation-note-text">{item.note_text}</span>}
            </button>
            <div className="annotation-actions">
              <button aria-label="Edit annotation" onClick={() => setEditing({ id: item.annotation_id, text: item.note_text, color })}><Pencil/>Edit</button>
              <button aria-label="Delete annotation" disabled={remove.isPending} onClick={() => remove.mutate(item.annotation_id)}>Delete</button>
            </div>
          </article>;
        })}
    </aside>
    {editing && <aside className="note-editor" aria-label="Edit annotation">
      <label>Note<textarea autoFocus value={editing.text} onChange={(event) => setEditing({ ...editing, text: event.target.value })}/></label>
      <NoteColorSelector color={editing.color} onChange={(color) => setEditing({ ...editing, color })}/>
      <div>
        <button className="primary" disabled={update.isPending} onClick={() => update.mutate(editing)}>Save changes</button>
        <button className="secondary" onClick={() => setEditing(null)}>Cancel</button>
      </div>
    </aside>}
  </>;
}
