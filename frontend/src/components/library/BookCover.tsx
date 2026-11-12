import { useEffect, useRef, useState } from "react";
import { booksApi } from "../../api/books";

/** True once the element has come near the viewport. Covers off-screen in a long library are never fetched. */
function useNearViewport<T extends Element>(): [React.RefObject<T | null>, boolean] {
  const target = useRef<T>(null);
  const [near, setNear] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const element = target.current;
    if (near || !element) return;
    // Start loading a screen and a half early so covers are ready before they scroll in.
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { setNear(true); observer.disconnect(); }
    }, { rootMargin: "150% 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [near]);
  return [target, near];
}

export function BookCover({ book, session, title, featured = false }: { book: string; session: string; title: string; featured?: boolean }) {
  const [frame, near] = useNearViewport<HTMLDivElement>();
  const [source, setSource] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!near) return;
    let disposed = false;
    let url: string | null = null;
    setLoading(true);
    void booksApi.cover(book, session, featured ? 640 : 320).then((buffer) => {
      if (disposed) return;
      url = URL.createObjectURL(new Blob([buffer]));
      setSource(url);
    }).catch(() => setSource(null)).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; if (url) URL.revokeObjectURL(url); };
  }, [book, featured, near, session]);

  return <div ref={frame} className={`book-cover ${featured ? "featured" : ""} ${loading ? "is-loading" : ""}`} aria-label={source ? `Cover of ${title}` : undefined}>
    {loading ? <span className="cover-skeleton" aria-label="Loading cover"/>
      : source ? <img loading="lazy" decoding="async" src={source} alt={`Cover of ${title}`}/>
      : <span aria-hidden="true">{title.trim().slice(0, 1).toUpperCase() || "B"}</span>}
  </div>;
}
