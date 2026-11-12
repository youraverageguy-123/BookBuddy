import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight, ListTree, LoaderCircle, MessageCircle, Users, ZoomIn, ZoomOut } from "lucide-react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { analysisApi } from "../../api/analysis";
import { booksApi } from "../../api/books";
import { healthApi } from "../../api/health";
import { readerLibraryQuery, readerStateApi } from "../../api/readerState";
import { ContentsPanel } from "../../components/reader/ContentsPanel";
import { ChatPanel } from "../../features/knowledge/ChatPanel";
import { knowledgeBoundary } from "../../features/knowledge/knowledgeModel";
import { progressKey, useReaderStore } from "../../store/readerStore";
import type { Book } from "../../types/contracts";
import { emptyProgress } from "../../utils/progress";
import { chapterFinishedByStep, chapterProgressAt, clampPage, pageFromHref, parsePdfLocation, pdfLocation, rangeForPage } from "./pdfModel";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const ZOOM_STEPS = [0.6, 0.8, 1, 1.25, 1.5, 2, 2.5];

export default function PdfReader({ bookName, sessionName, metadata }: { bookName: string; sessionName: string; metadata: Book }) {
  const navigate = useNavigate();
  const sessionKey = `${bookName}::${sessionName}`;
  const userId = useReaderStore((state) => state.readerProfileId);
  const readerLibrary = useQuery({ ...readerLibraryQuery(userId ?? "missing"), enabled: Boolean(userId) });
  const aiSettings = useQuery({ queryKey: ["ai-settings"], queryFn: healthApi.aiSettings, retry: false });
  const bookState = readerLibrary.data?.books.find((item) => item.session_key === sessionKey);
  const backgroundAnalysis = Boolean(bookState?.analysis_mode !== "off" && aiSettings.data?.background_analysis.enabled && !aiSettings.data?.background_analysis.paused && aiSettings.data?.capabilities.text);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(0);
  const [tocOpen, setTocOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [completedLocally, setCompletedLocally] = useState(-1);
  const canvas = useRef<HTMLCanvasElement>(null);
  const surface = useRef<HTMLDivElement>(null);
  const ranges = metadata.page_ranges;
  const pageCount = pdf?.numPages ?? metadata.page_count;

  useEffect(() => {
    let cancelled = false;
    let loading: ReturnType<typeof pdfjs.getDocument> | null = null;
    booksApi.epub(bookName, sessionName)
      .then((data) => {
        if (cancelled) return null;
        loading = pdfjs.getDocument({ data: new Uint8Array(data) });
        return loading.promise;
      })
      .then((document) => { if (document && !cancelled) setPdf(document); })
      .catch(() => { if (!cancelled) setError("This PDF could not be opened."); });
    return () => { cancelled = true; void loading?.destroy(); };
  }, [bookName, sessionName]);

  // PDFs carry no cover image, so the first page becomes the library cover the first time the book is opened.
  useEffect(() => {
    if (!pdf) return;
    let cancelled = false;
    void booksApi.cover(bookName, sessionName, 160).catch(async () => {
      const first = await pdf.getPage(1);
      const base = first.getViewport({ scale: 1 });
      const viewport = first.getViewport({ scale: 640 / base.width });
      const surface = document.createElement("canvas");
      surface.width = Math.floor(viewport.width); surface.height = Math.floor(viewport.height);
      await first.render({ canvas: surface, viewport }).promise;
      const image = await new Promise<Blob | null>((resolve) => surface.toBlob(resolve, "image/jpeg", 0.86));
      if (image && !cancelled) await booksApi.uploadCover(bookName, sessionName, image);
    }).catch((error: unknown) => console.warn("PDF cover could not be generated", error));
    return () => { cancelled = true; };
  }, [bookName, pdf, sessionName]);

  // Resume where the reader left off, once the saved state (if any) is known.
  const savedLocation = readerLibrary.data?.books.find((item) => item.session_key === sessionKey)?.last_cfi;
  const savedStateReady = !userId || readerLibrary.isFetched;
  useEffect(() => {
    if (page === null && pdf && savedStateReady) setPage(parsePdfLocation(savedLocation, pdf.numPages));
  }, [page, pdf, savedLocation, savedStateReady]);

  const surfaceMounted = Boolean(pdf) && page !== null && !error;
  useEffect(() => {
    const element = surface.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    setWidth(element.clientWidth);
    return () => observer.disconnect();
    // The reading surface only mounts once the document and start page are known.
  }, [surfaceMounted]);

  useEffect(() => {
    if (!pdf || page === null || !canvas.current || width === 0) return;
    let task: RenderTask | null = null;
    let cancelled = false;
    const target = canvas.current;
    void pdf.getPage(page).then((pdfPage) => {
      if (cancelled) return;
      const base = pdfPage.getViewport({ scale: 1 });
      const fit = Math.min(1100, Math.max(280, width - 48)) / base.width;
      const ratio = window.devicePixelRatio || 1;
      const viewport = pdfPage.getViewport({ scale: fit * zoom * ratio });
      target.width = Math.floor(viewport.width); target.height = Math.floor(viewport.height);
      target.style.width = `${Math.floor(viewport.width / ratio)}px`; target.style.height = `${Math.floor(viewport.height / ratio)}px`;
      task = pdfPage.render({ canvas: target, viewport });
      task.promise.catch(() => undefined);
    }).catch(() => { if (!cancelled) setError("This page could not be shown."); });
    return () => { cancelled = true; task?.cancel(); };
  }, [page, pdf, width, zoom]);

  const completeChapter = useCallback((chapter: number) => {
    const key = progressKey(bookName, sessionName, chapter);
    const previous = useReaderStore.getState().progress[key] ?? emptyProgress();
    if (previous.naturallyCompleted) return;
    const progress = { ...previous, currentProgress: 1, contiguousProgress: 1, thresholdStarted: true, naturallyCompleted: true };
    useReaderStore.getState().setProgress(key, progress);
    setCompletedLocally((latest) => Math.max(latest, chapter));
    if (userId) void readerStateApi.updateChapter(userId, bookName, sessionName, chapter, progress).catch(() => undefined);
    if (backgroundAnalysis) void analysisApi.complete(bookName, sessionName, chapter).catch(() => undefined);
  }, [backgroundAnalysis, bookName, sessionName, userId]);

  const goTo = useCallback((next: number) => {
    if (page === null) return;
    const target = clampPage(next, pageCount);
    if (target === page) {
      // Pressing "next" on the final page finishes the last chapter.
      const last = rangeForPage(ranges, page);
      if (next > pageCount && last && last.end_page === page) completeChapter(last.index);
      return;
    }
    const finished = chapterFinishedByStep(ranges, page, target);
    if (finished !== null) completeChapter(finished);
    setPage(target);
    surface.current?.scrollTo({ top: 0 });
  }, [completeChapter, page, pageCount, ranges]);

  // Save the position shortly after the reader settles on a page.
  useEffect(() => {
    if (!userId || page === null || pageCount === 0) return;
    const range = rangeForPage(ranges, page);
    const timer = window.setTimeout(() => {
      void readerStateApi.updateBook(userId, bookName, sessionName, {
        last_cfi: pdfLocation(page), last_opened_at: Date.now() / 1000, book_progress: page / pageCount,
        current_chapter: range?.index, chapter_progress: chapterProgressAt(range, page),
      }).catch(() => undefined);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [bookName, page, pageCount, ranges, sessionName, userId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const element = event.target as HTMLElement | null;
      if (element && ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName)) return;
      if (page === null) return;
      if (event.key === "ArrowRight" || event.key === "PageDown") { event.preventDefault(); goTo(page + 1); }
      else if (event.key === "ArrowLeft" || event.key === "PageUp") { event.preventDefault(); goTo(page - 1); }
      else if (event.key === "Escape") { setTocOpen(false); setChatOpen(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goTo, page]);

  const boundary = useMemo(() => Math.max(completedLocally, knowledgeBoundary(readerLibrary.data?.chapters ?? [], readerLibrary.data?.books ?? [], sessionKey)), [completedLocally, readerLibrary.data?.books, readerLibrary.data?.chapters, sessionKey]);
  const stepZoom = (direction: 1 | -1) => setZoom((current) => {
    const index = ZOOM_STEPS.findIndex((step) => step >= current - 0.001);
    return ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, Math.max(0, (index === -1 ? ZOOM_STEPS.length - 1 : index) + direction))] ?? current;
  });

  if (error) return <main className="centered-state" role="alert"><p className="eyebrow">Reader unavailable</p><h1>This book could not be opened.</h1><p>{error}</p><button className="primary" onClick={() => navigate("/library")}>Return to library</button></main>;
  if (!pdf || page === null) return <main className="reader-loading"><LoaderCircle className="spin"/><p>Opening the book…</p></main>;
  const currentRange = rangeForPage(ranges, page);
  const chapterTitle = metadata.chapters.find((chapter) => chapter.index === currentRange?.index)?.title ?? "";
  const knowledgeLink = `/book/${encodeURIComponent(bookName)}/${encodeURIComponent(sessionName)}/knowledge`;

  return <main className="reader-page pdf-reader mode-continuous">
    <header className="reader-toolbar">
      <button aria-label="Back to Library" title="Back to Library" onClick={() => navigate("/library")}><ArrowLeft/></button>
      <button aria-label="Table of contents" title="Table of contents" onClick={() => setTocOpen((open) => !open)}><ListTree/></button>
      <div className="reader-book-title"><strong>{metadata.title}</strong><span>{chapterTitle}</span></div>
      <button aria-label="Zoom out" title="Zoom out" disabled={zoom <= (ZOOM_STEPS[0] ?? 0.6)} onClick={() => stepZoom(-1)}><ZoomOut/></button>
      <output className="pdf-zoom-level" aria-label="Zoom level">{Math.round(zoom * 100)}%</output>
      <button aria-label="Zoom in" title="Zoom in" disabled={zoom >= (ZOOM_STEPS[ZOOM_STEPS.length - 1] ?? 2.5)} onClick={() => stepZoom(1)}><ZoomIn/></button>
      <button aria-label="Ask about this book" title="Ask about this book" className={chatOpen ? "active" : ""} onClick={() => setChatOpen((open) => !open)}><MessageCircle/></button>
      <Link to={knowledgeLink} aria-label="Story knowledge" title="Story knowledge"><Users/></Link>
    </header>
    {tocOpen && <ContentsPanel navigation={metadata.navigation} chapters={metadata.chapters} bookTitle={metadata.title} currentChapterIndex={currentRange?.index ?? null} onClose={() => setTocOpen(false)} onNavigate={(href) => { const target = pageFromHref(href, pageCount); setTocOpen(false); if (target !== null) { setPage(target); surface.current?.scrollTo({ top: 0 }); } }}/>}
    <section className="reading-surface pdf-surface" aria-label="PDF reading area">
      <button className="pdf-step previous" aria-label="Previous page" disabled={page <= 1} onClick={() => goTo(page - 1)}><ChevronLeft/></button>
      <div className="pdf-scroll" ref={surface}><canvas ref={canvas} role="img" aria-label={`Page ${page} of ${pageCount}`}/></div>
      <button className="pdf-step next" aria-label="Next page" onClick={() => goTo(page + 1)}><ChevronRight/></button>
    </section>
    <footer className="reader-status">
      <span>Page <input className="pdf-page-input" aria-label="Go to page" type="number" min={1} max={pageCount} value={page} onChange={(event) => { const value = Number(event.target.value); if (Number.isFinite(value) && value >= 1) { setPage(clampPage(value, pageCount)); } }}/> of {pageCount}</span>
      <span className="reader-progress-control"><input aria-label="Book progress" title="Book progress" type="range" min={1} max={pageCount} step={1} value={page} onChange={(event) => setPage(clampPage(Number(event.target.value), pageCount))}/><span className="status-chapter">{chapterTitle}</span></span>
      <span>{Math.round((page / pageCount) * 100)}% of book</span>
    </footer>
    {chatOpen && <ChatPanel variant="drawer" book={bookName} session={sessionName} asOfChapter={boundary} aiAvailable={Boolean(aiSettings.data?.capabilities.text)} onClose={() => setChatOpen(false)}/>}
  </main>;
}
