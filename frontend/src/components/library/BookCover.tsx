import { useEffect, useState } from "react";
import { booksApi } from "../../api/books";

export function BookCover({ book, session, title, featured = false }: { book: string; session: string; title: string; featured?: boolean }) {
  const [source, setSource] = useState<string | null>(null); const [loading, setLoading] = useState(true);
  useEffect(() => {
    let disposed = false; let url: string | null = null;
    setLoading(true); void booksApi.cover(book, session, featured ? 640 : 320).then((buffer) => {
      if (disposed) return;
      url = URL.createObjectURL(new Blob([buffer])); setSource(url);
    }).catch(() => setSource(null)).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; if (url) URL.revokeObjectURL(url); };
  }, [book, featured, session]);
  return <div className={`book-cover ${featured ? "featured" : ""} ${loading ? "is-loading" : ""}`} aria-label={source ? `Cover of ${title}` : undefined}>
    {loading ? <span className="cover-skeleton" aria-label="Loading cover"/> : source ? <img loading="lazy" src={source} alt={`Cover of ${title}`}/> : <span aria-hidden="true">{title.trim().slice(0, 1).toUpperCase() || "B"}</span>}
  </div>;
}
