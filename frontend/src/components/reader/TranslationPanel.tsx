import { useMutation } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";
import { translationApi } from "../../api/translation";

const languages = ["Spanish", "French", "German", "Hindi", "Japanese", "Portuguese"];

/** Translates one selected passage on request. Mount it with a `key` per selection so each one starts fresh. */
export function TranslationPanel({ book, session, text, onClose }: { book: string; session: string; text: string; onClose: () => void }) {
  const [target, setTarget] = useState(languages[0] ?? "Spanish");
  const translation = useMutation({ mutationFn: () => translationApi.translate(book, session, text, target) });

  return <aside className="translation-panel" role="dialog" aria-modal="true" aria-label="Translate selection">
    <header><strong>Translate selection</strong><button aria-label="Close translation" onClick={onClose}><X/></button></header>
    <blockquote>{text}</blockquote>
    <label>Translate to
      <select value={target} onChange={(event) => { setTarget(event.target.value); translation.reset(); }}>
        {languages.map((language) => <option key={language}>{language}</option>)}
      </select>
    </label>
    {translation.data && <p className="translation-result" aria-live="polite">{translation.data.translation}</p>}
    {translation.error && <p role="alert">{translation.error.message}</p>}
    <button className="primary" disabled={translation.isPending} onClick={() => translation.mutate()}>{translation.isPending ? "Translating…" : "Translate"}</button>
  </aside>;
}
