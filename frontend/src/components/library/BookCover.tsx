import { useEffect, useState } from "react";
import { booksApi } from "../../api/books";

export function BookCover({ book, session, title, featured = false }: { book: string; session: string; title: string; featured?: boolean }) {
  const [source, setSource] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false; let url: string | null = null;
    void booksApi.cover(book, session, featured ? 640 : 320).then((buffer) => {
      if (disposed) return;
      url = URL.createObjectURL(new Blob([buffer])); setSource(url);
    }).catch(() => setSource(null));
    return () => { disposed = true; if (url) URL.revokeObjectURL(url); };
  }, [book, featured, session]);
  return <div className={`book-cover ${featured ? "featured" : ""}`} aria-label={source ? `Cover of ${title}` : undefined}>
    {source ? <img src={source} alt={`Cover of ${title}`}/> : <span aria-hidden="true">{title.trim().slice(0, 1).toUpperCase() || "B"}</span>}
  </div>;
}
