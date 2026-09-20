import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";
import ePub, { type Book as EpubBook, type Contents, type Rendition } from "epubjs";
import { ArrowLeft, Bookmark, Info, Library, ListTree, LoaderCircle, Maximize, MoreHorizontal, NotebookPen, Palette, Pencil, Search, Settings, Type, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { analysisApi } from "../api/analysis";
import { booksApi, sessionRouteSchema } from "../api/books";
import { healthApi } from "../api/health";
import { readerLibraryQuery, readerStateApi } from "../api/readerState";
import { searchApi, type ReaderSearchResult } from "../api/search";
import { translationApi } from "../api/translation";
import { DictionaryPopup, type SelectionInfo } from "../components/dictionary/DictionaryPopup";
import { ContentsPanel } from "../components/reader/ContentsPanel";
import { AnnotationColorPicker } from "../components/reader/AnnotationColorPicker";
import { FullscreenControls } from "../components/reader/FullscreenControls";
import { SelectionToolbar } from "../components/reader/SelectionToolbar";
import type { SelectionActionId } from "../plugins";
import { effectiveReaderSettings, flushReaderSettings, progressKey, useReaderStore, type ReaderTheme } from "../store/readerStore";
import type { Chapter } from "../types/contracts";
import { calculateBookProgress, emptyProgress, formatBookProgressPercent, updateContiguousProgress, type NavigationKind } from "../utils/progress";
import { buildSelectionContext } from "../utils/selectionContext";
import { sanitizeEpubDocument } from "../reader/rendition/sanitizeEpubDocument";
import { applyReaderDocumentStyles, buildReaderDocumentStyles, preparePublisherImages, reinforcePublisherInitials } from "../reader/rendition/readerDocumentStyles";
import { annotationColorPresets, normalizeAnnotationColor, syncRenditionAnnotations, type RenderedAnnotation, type RenditionAnnotationApi, type VisualAnnotationType } from "../reader/rendition/annotationRendering";
import { findDocumentSearchMatches, selectDocumentSearchMatch, selectSearchResultMatch } from "../reader/searchResultMatch";
import { offlineReaderFonts, readerFontFamily, readerFontOptions } from "../reader/fonts";
import { afterStablePaint, recordPerformanceSample } from "../services/performance/recorder";
import { AIRequiredDialog } from "../features/ai/AIRequiredDialog";

interface RelocatedLocation {
  start: { href: string; cfi: string; percentage?: number; displayed?: { page: number; total: number } };
  end: { atEnd?: boolean };
}

const normalizeHref = (href: string): string => decodeURIComponent(href.split("#")[0] ?? "").replace(/^\.\//, "").toLowerCase();
const chapterForHref = (chapters: Chapter[], href: string): Chapter | undefined => {
  const normalized = normalizeHref(href);
  return chapters.find((chapter) => normalized.endsWith(normalizeHref(chapter.spine_href)) || normalizeHref(chapter.spine_href).endsWith(normalized));
};
const readerThemeColors = (theme: ReaderTheme) => ({
  paper: { paper: "#fbf8ef", ink: "#302c24" }, night: { paper: "#171816", ink: "#eee9df" },
  sepia: { paper: "#eee0bd", ink: "#4a3825" }, oled: { paper: "#000000", ink: "#ffffff" },
  forest: { paper: "#11251e", ink: "#f1e8ce" },
}[theme]);

function ReaderRange({ label, value, min, max, step = 1, suffix = "", help, formatValue = (current) => current, onChange }: { label: string; value: number; min: number; max: number; step?: number; suffix?: string; help?: string; formatValue?: (value: number) => number; onChange: (value: number) => void }) {
  const updateValue = (event: React.FormEvent<HTMLInputElement>) => onChange(Number(event.currentTarget.value));
  return <label><span>{label}{help && <ReaderHelp text={help}/>} <output>{formatValue(value)}{suffix}</output></span><input type="range" min={min} max={max} step={step} value={value} onInput={updateValue} onChange={updateValue}/></label>;
}

function ReaderHelp({ text }: { text: string }) {
  return <span className="setting-help" tabIndex={0} aria-label={text} data-tooltip={text}><Info/></span>;
}

function NoteColorSelector({ color, onChange }: { color: string; onChange: (color: string) => void }) {
  return <fieldset className="note-color-selector"><legend>Note color</legend><div className="annotation-preset-grid" aria-label="Note colors">{annotationColorPresets.map((preset) => <button key={preset.value} type="button" className={color.toLowerCase() === preset.value ? "active" : ""} aria-label={preset.name} title={preset.name} style={{ "--annotation-color":preset.value } as React.CSSProperties} onClick={() => onChange(preset.value)}><span/></button>)}<label className="note-custom-color" title="Custom color"><input type="color" aria-label="Choose a custom note color" value={color} onChange={(event) => onChange(event.target.value)}/></label></div></fieldset>;
}

export default function ReaderPage() {
  const params = sessionRouteSchema.safeParse(useParams());
  if (!params.success) return <main className="centered-state" role="alert">This reader link is invalid.</main>;
  return <Reader bookName={params.data.book} sessionName={params.data.session} />;
}

function Reader({ bookName, sessionName }: { bookName: string; sessionName: string }) {
  const navigate = useNavigate(); const queryClient = useQueryClient(); const container = useRef<HTMLDivElement>(null);
  const overflowMenu = useRef<HTMLDetailsElement>(null);
  const epubBook = useRef<EpubBook | null>(null); const rendition = useRef<Rendition | null>(null); const currentChapter = useRef<number | null>(null);
  const searchHighlightCfi = useRef<string | null>(null);
  const navigation = useRef<NavigationKind>("restore"); const currentProgress = useRef(0); const [selection, setSelection] = useState<SelectionInfo | null>(null); const [dictionarySelection, setDictionarySelection] = useState<SelectionInfo | null>(null); const [selectionCfi, setSelectionCfi] = useState("");
  const currentCfi = useRef("");
  const readerOpenStarted = useRef(performance.now()); const firstRelocationRecorded = useRef(false); const annotationStarted = useRef(0);
  const renderedAnnotations = useRef<Map<string, RenderedAnnotation>>(new Map()); const [renditionRevision, setRenditionRevision] = useState(0);
  const retriedCompletions = useRef<Set<number>>(new Set());
  const [readerError, setReaderError] = useState<string | null>(null); const [windowError, setWindowError] = useState<string | null>(null); const [searchOpen, setSearchOpen] = useState(false); const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ReaderSearchResult[]>([]); const [searching, setSearching] = useState(false); const [searchMessage, setSearchMessage] = useState("");
  const [searchScope, setSearchScope] = useState<"chapter" | "reached" | "whole">("reached"); const [spoilerGate, setSpoilerGate] = useState(false);
  const [noteDraft, setNoteDraft] = useState<string | null>(null); const [noteColor, setNoteColor] = useState(normalizeAnnotationColor(undefined,"highlight"));
  const [translationSelection, setTranslationSelection] = useState<SelectionInfo | null>(null); const [translationTarget, setTranslationTarget] = useState("Spanish");
  const [annotationsOpen, setAnnotationsOpen] = useState(false); const [annotationQuery, setAnnotationQuery] = useState("");
  const [annotationPicker, setAnnotationPicker] = useState<{type:VisualAnnotationType;color:string;x:number;y:number}|null>(null);
  const [editingAnnotation, setEditingAnnotation] = useState<{ id: string; text: string; color: string } | null>(null);
  const [zoomImage,setZoomImage]=useState<{src:string;alt:string}|null>(null); const [zoomScale,setZoomScale]=useState(1); const [zoomOffset,setZoomOffset]=useState({x:0,y:0}); const panStart=useRef<{x:number;y:number;ox:number;oy:number}|null>(null);
  const [closeOpen, setCloseOpen] = useState(false); const [finishingInBackground, setFinishingInBackground] = useState(false);
  const [aiRequiredFeature, setAIRequiredFeature] = useState<string | null>(null);
  const [chapterTitle, setChapterTitle] = useState(""); const [chapterPercent, setChapterPercent] = useState(0); const [bookProgress, setBookProgress] = useState(0); const [page, setPage] = useState({ current: 0, total: 0 });
  const [fullscreen, setFullscreen] = useState(false); const [fullscreenControls, setFullscreenControls] = useState(false); const [typographyOpen, setTypographyOpen] = useState(false); const [tocOpen, setTocOpen] = useState(false);
  const pageTurnPending = useRef(false);
  const persistenceTimer = useRef<number | null>(null); const pendingPersistence = useRef<(() => void) | null>(null);
  const store = useReaderStore();
  const sessionKey = `${bookName}::${sessionName}`;
  const settings = effectiveReaderSettings(store, sessionKey);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const documentFlow = settings.readingMode === "paged" ? "paginated" : "scrolled";
  const readerDocumentCss = useMemo(() => buildReaderDocumentStyles({ ...settings, fontFamily: readerFontFamily(settings.font) }, readerThemeColors(settings.readerTheme), documentFlow), [documentFlow, settings]);
  const userId = store.readerProfileId;
  const readerLibrary = useQuery({ ...readerLibraryQuery(userId ?? "missing"), enabled: Boolean(userId) });
  const health = useQuery({ queryKey:["health"], queryFn:healthApi.get, retry:false });
  const aiSettings = useQuery({ queryKey:["ai-settings"], queryFn:healthApi.aiSettings, retry:false });
  const backgroundAnalysisEnabled = Boolean(aiSettings.data?.background_analysis.enabled && !aiSettings.data?.background_analysis.paused && aiSettings.data?.capabilities.text);
  const annotations = useQuery({ queryKey:["reader-annotations",userId,sessionKey], queryFn:() => readerStateApi.annotations(userId!,sessionKey), enabled:Boolean(userId) });
  const visibleAnnotations = useMemo(() => { const needle=annotationQuery.trim().toLowerCase(); return (annotations.data?.annotations ?? []).filter((item) => !needle || `${item.quote} ${item.note_text} ${item.annotation_type}`.toLowerCase().includes(needle)); }, [annotationQuery, annotations.data?.annotations]);
  const metadata = useQuery({ queryKey: ["book", bookName, sessionName], queryFn: async () => {
    try { return await booksApi.metadata(bookName, sessionName); }
    catch { await booksApi.load(bookName, sessionName); return booksApi.metadata(bookName, sessionName); }
  } });
  const analysis = useQuery({ queryKey: ["reader-analysis", bookName, sessionName], queryFn: () => analysisApi.status(bookName, sessionName), refetchInterval: (queryState) => queryState.state.data?.state === "active" ? 1_000 : 5_000, enabled: Boolean(metadata.data) });
  const stage = useMutation({ mutationFn: (chapter: number) => analysisApi.stage(bookName, sessionName, chapter), onSettled: () => queryClient.invalidateQueries({ queryKey: ["reader-analysis", bookName, sessionName] }) });
  const complete = useMutation({ mutationFn: (chapter: number) => analysisApi.complete(bookName, sessionName, chapter), onSettled: () => queryClient.invalidateQueries({ queryKey: ["reader-analysis", bookName, sessionName] }) });
  const discard = useMutation({ mutationFn: (chapter: number) => analysisApi.discard(bookName, sessionName, chapter), onSettled: () => queryClient.invalidateQueries({ queryKey: ["reader-analysis", bookName, sessionName] }) });
  const bookmark = useMutation({ mutationFn: async () => {
    if (!userId || currentChapter.current === null || !currentCfi.current) throw new Error("This page is not ready to bookmark.");
    const existing = readerLibrary.data?.bookmarks.find((item) => item.session_key === `${bookName}::${sessionName}` && item.cfi === currentCfi.current);
    if (existing) return readerStateApi.deleteBookmark(userId, existing.bookmark_id);
    return readerStateApi.createBookmark(userId, bookName, sessionName, currentChapter.current, currentCfi.current, chapterTitle);
  }, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reader-library", userId] }) });
  const annotation = useMutation({ mutationFn: (values: { annotation_type:"highlight"|"underline"|"note"; color?:string; note_text?:string }) => {
    const recovered=useReaderStore.getState().books[sessionKey]?.draftNote;
    const source=selection&&selectionCfi?{chapter:selection.chapter,cfi:selectionCfi,quote:selection.text}:recovered?.cfi&&recovered.chapterIndex!==undefined?{chapter:recovered.chapterIndex,cfi:recovered.cfi,quote:recovered.quote??""}:null;
    if (!userId || !source) throw new Error("The selection is no longer available.");
    return readerStateApi.createAnnotation(userId,bookName,sessionName,{chapter_index:source.chapter,cfi_range:source.cfi,quote:source.quote,annotation_type:values.annotation_type,color:values.color,note_text:values.note_text});
  }, onSuccess: (_data,values) => { if (annotationStarted.current) recordPerformanceSample("annotation_save",performance.now()-annotationStarted.current); annotationStarted.current=0; setSelection(null); setAnnotationPicker(null); setNoteDraft(null); if(values.annotation_type==="note")setAnnotationsOpen(true); useReaderStore.getState().setDraftNote(sessionKey,undefined); void queryClient.invalidateQueries({queryKey:["reader-annotations",userId,sessionKey]}); void queryClient.invalidateQueries({queryKey:["reader-library",userId]}); } });
  const deleteAnnotation = useMutation({ mutationFn:(id:string) => readerStateApi.deleteAnnotation(userId!,id), onSuccess:() => { void queryClient.invalidateQueries({queryKey:["reader-annotations",userId]}); void queryClient.invalidateQueries({queryKey:["reader-library",userId]}); } });
  const updateAnnotation = useMutation({ mutationFn:({id,text,color}:{id:string;text:string;color:string}) => readerStateApi.updateAnnotation(userId!,id,{note_text:text,color}), onSuccess:() => { setEditingAnnotation(null); void queryClient.invalidateQueries({queryKey:["reader-annotations",userId]}); } });
  const translation = useMutation({ mutationFn:() => translationApi.translate(bookName,sessionName,translationSelection!.text,translationTarget) });

  useEffect(() => {
    const recovered=useReaderStore.getState().books[sessionKey]?.draftNote;
    if (recovered?.cfi) { setNoteDraft(recovered.text); setNoteColor(normalizeAnnotationColor(recovered.color,"highlight")); }
  },[sessionKey]);

  useEffect(() => {
    const keyPrefix = `${bookName}::${sessionName}`;
    for (const item of readerLibrary.data?.chapters ?? []) {
      if (item.session_key !== keyPrefix) continue;
      const key = progressKey(bookName, sessionName, item.chapter_index);
      if (useReaderStore.getState().progress[key]) continue;
      useReaderStore.getState().setProgress(key, { lastCfi: item.last_cfi, currentProgress: item.current_progress, contiguousProgress: item.contiguous_progress, thresholdStarted: item.threshold_started, naturallyCompleted: item.naturally_completed, committed: item.committed, retryRequired: item.retry_required });
    }
  }, [bookName, readerLibrary.data?.chapters, sessionName]);

  useEffect(() => {
    const book = metadata.data;
    if (!book) return;
    for (const chapter of book.chapters) {
      const progress = useReaderStore.getState().progress[progressKey(bookName, sessionName, chapter.index)];
      if (!backgroundAnalysisEnabled || !progress?.naturallyCompleted || !progress.retryRequired || retriedCompletions.current.has(chapter.index)) continue;
      retriedCompletions.current.add(chapter.index);
      complete.mutate(chapter.index);
    }
  }, [backgroundAnalysisEnabled, bookName, complete, metadata.data, sessionName]);

  useEffect(() => {
    if (!analysis.data) return;
    for (const job of analysis.data.jobs) {
      if (job.state !== "committed") continue;
      const key = progressKey(bookName, sessionName, job.chapter_index);
      const progress = useReaderStore.getState().progress[key];
      if (!progress || (progress.committed && !progress.retryRequired)) continue;
      useReaderStore.getState().setProgress(key, { ...progress, committed: true, retryRequired: false });
      if (userId) void readerStateApi.updateChapter(userId, bookName, sessionName, job.chapter_index, { ...progress, committed: true, retryRequired: false });
    }
  }, [analysis.data, bookName, sessionName, userId]);

  const latestCompletedChapter = useMemo(() => {
    if (!metadata.data) return -1;
    return metadata.data.chapters.reduce((latest, chapter) => store.progress[progressKey(bookName, sessionName, chapter.index)]?.naturallyCompleted ? Math.max(latest, chapter.index) : latest, -1);
  }, [bookName, metadata.data, sessionName, store.progress]);

  const leaveChapter = useCallback((chapter: number) => {
    const progress = useReaderStore.getState().progress[progressKey(bookName, sessionName, chapter)];
    if (progress?.thresholdStarted && !progress.naturallyCompleted) discard.mutate(chapter);
  }, [bookName, discard, sessionName]);

  const clearSearchHighlight = useCallback(() => {
    const cfi = searchHighlightCfi.current;
    if (!cfi) return;
    try { rendition.current?.annotations.remove(cfi, "highlight"); } catch { /* rendition may already be destroyed */ }
    // Re-apply any saved highlight that happens to share this exact range.
    // Search markers are ephemeral and must never remove user-owned annotations.
    if (rendition.current) {
      renderedAnnotations.current = syncRenditionAnnotations(rendition.current.annotations as unknown as RenditionAnnotationApi, new Map(), annotations.data?.annotations ?? []);
    }
    searchHighlightCfi.current = null;
  }, [annotations.data?.annotations]);
  const closeSearch = useCallback(() => { clearSearchHighlight(); setSearchOpen(false); }, [clearSearchHighlight]);
  const dismissReaderPanels = useCallback(() => { if (overflowMenu.current) overflowMenu.current.open=false; setTypographyOpen(false); setTocOpen(false); closeSearch(); setSelection(null); setAnnotationPicker(null); setDictionarySelection(null); }, [closeSearch]);
  const previousPage = async () => { if (pageTurnPending.current) return; pageTurnPending.current=true; const started=performance.now(); navigation.current = "backward"; try { await rendition.current?.prev(); } finally { pageTurnPending.current=false; afterStablePaint(started,"page_turn"); } };
  const nextPage = async () => {
    if (pageTurnPending.current) return;
    pageTurnPending.current = true;
    const chapter = currentChapter.current;
    if (chapter !== null && currentProgress.current >= 0.95) {
      const key = progressKey(bookName, sessionName, chapter); const previous = useReaderStore.getState().progress[key] ?? emptyProgress();
      const update = updateContiguousProgress(previous, 1, previous.lastCfi, "forward", 0.08, true);
      useReaderStore.getState().setProgress(key, update.progress); if (userId) void readerStateApi.updateChapter(userId, bookName, sessionName, chapter, update.progress); if (update.completedNaturally && backgroundAnalysisEnabled) complete.mutate(chapter);
    }
    const started=performance.now(); navigation.current = "forward"; try { await rendition.current?.next(); } finally { pageTurnPending.current=false; afterStablePaint(started,"page_turn"); }
  };
  const setNativeFullscreen = async (target: boolean) => {
    try {
      if ("__TAURI_INTERNALS__" in window) await getCurrentWindow().setFullscreen(target);
      else if (target && !document.fullscreenElement) await document.documentElement.requestFullscreen();
      else if (!target && document.fullscreenElement) await document.exitFullscreen();
      setFullscreen(target); setFullscreenControls(false);
    } catch { setWindowError("Window controls are temporarily unavailable. Reading is unaffected."); }
  };
  const handleReaderKey = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    const tagName = target?.tagName?.toLowerCase();
    if (target?.isContentEditable || tagName === "input" || tagName === "textarea" || tagName === "select") return;
    if (event.key === "F11") { event.preventDefault(); void setNativeFullscreen(!fullscreen); return; }
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "f") { event.preventDefault(); setFullscreenControls(true); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "f") { event.preventDefault(); setSearchOpen(true); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "d") { event.preventDefault(); bookmark.mutate(); return; }
    if (event.ctrlKey && event.key.toLowerCase() === "b") { event.preventDefault(); setAnnotationsOpen((open) => !open); return; }
    if (event.ctrlKey && (event.key === "+" || event.key === "=")) { event.preventDefault(); store.setAppearance({fontSize:Math.min(38,settings.fontSize+1)}); return; }
    if (event.ctrlKey && event.key === "-") { event.preventDefault(); store.setAppearance({fontSize:Math.max(14,settings.fontSize-1)}); return; }
    if (event.key === "ArrowRight" || event.key === "PageDown" || (event.key === " " && !event.shiftKey)) { event.preventDefault(); event.stopPropagation(); void nextPage(); }
    if (event.key === "ArrowLeft" || event.key === "PageUp" || (event.key === " " && event.shiftKey)) { event.preventDefault(); event.stopPropagation(); void previousPage(); }
    if (event.key === "Escape") {
      if (zoomImage) setZoomImage(null); else if (noteDraft !== null) setNoteDraft(null); else if (annotationPicker) setAnnotationPicker(null); else if (selection) setSelection(null); else if (dictionarySelection) setDictionarySelection(null); else if (annotationsOpen) setAnnotationsOpen(false); else if (fullscreenControls) setFullscreenControls(false); else if (typographyOpen) setTypographyOpen(false); else if (tocOpen) setTocOpen(false); else if (searchOpen) closeSearch(); else if (fullscreen) void setNativeFullscreen(false);
    }
  };

  useEffect(() => {
    const book = metadata.data; if (!book || !container.current) return;
    let disposed = false;
    let resizeObserver: ResizeObserver | undefined;
    const iframeKeyListeners: Array<{ document: Document; listener: (event: KeyboardEvent) => void }> = [];
    void booksApi.epub(bookName, sessionName).then((buffer) => {
      if (disposed || !container.current) return;
      const instance = ePub(buffer, { replacements: "blobUrl" }); epubBook.current = instance;
      const view = instance.renderTo(container.current, { width: "100%", height: "100%", manager: "default", spread: settings.readingMode === "paged" ? "auto" : "none", flow: settings.readingMode === "paged" ? "paginated" : "scrolled-doc", minSpreadWidth: 1000, allowScriptedContent: false });
      renderedAnnotations.current = new Map(); rendition.current = view; setRenditionRevision((revision) => revision + 1);
      const resizeRendition = () => {
        const host = container.current;
        const managerReady = Boolean((view as unknown as { manager?: unknown }).manager);
        if (!managerReady || !host || host.clientWidth <= 0 || host.clientHeight <= 0) return;
        view.resize(Math.floor(host.clientWidth), Math.floor(host.clientHeight));
      };
      resizeObserver = new ResizeObserver(resizeRendition);
      resizeObserver.observe(container.current);
      view.hooks.content.register((contents: Contents) => {
        sanitizeEpubDocument(contents.document);
        const activeSettings = settingsRef.current;
        const activePalette = readerThemeColors(activeSettings.readerTheme);
        const activeFlow = activeSettings.readingMode === "paged" ? "paginated" : "scrolled";
        const activeDocumentSettings = { ...activeSettings, fontFamily: readerFontFamily(activeSettings.font) };
        const activeCss = buildReaderDocumentStyles(activeDocumentSettings, activePalette, activeFlow);
        applyReaderDocumentStyles(contents.document, activeCss, activePalette, activeFlow, activeDocumentSettings);
        preparePublisherImages(contents.document);
        const fontStyles=contents.document.createElement("style"); fontStyles.dataset.bookbuddyFonts="offline"; fontStyles.textContent=offlineReaderFonts; contents.document.head?.appendChild(fontStyles);
        // Never block a page turn on font or stylesheet recovery. Publisher
        // resources render natively; a failed stylesheet is recovered later.
        void reinforcePublisherInitials(contents.document, true).then(() => applyReaderDocumentStyles(contents.document, activeCss, activePalette, activeFlow, activeDocumentSettings));
        contents.document.addEventListener("pointerdown", (event) => {
          if (!(event.target as Element | null)?.closest("img,svg")) dismissReaderPanels();
          setSelection(null);
        });
        contents.document.addEventListener("contextmenu", (event) => event.preventDefault());
        contents.document.addEventListener("click", (event) => { const image=(event.target as Element | null)?.closest("img") as HTMLImageElement | null; if (!image) return; const source=image.currentSrc||image.src; if (source) { event.preventDefault(); setZoomScale(1); setZoomOffset({x:0,y:0}); setZoomImage({src:source,alt:image.getAttribute("alt")||"Book illustration"}); } });
        const listener = (event: KeyboardEvent) => handleReaderKey(event);
        contents.document.addEventListener("keydown", listener);
        iframeKeyListeners.push({ document: contents.document, listener });
      });
      view.on("selected", (cfiRange: string, contents: Contents) => {
        const selectionStarted = performance.now();
        const selected = contents.window.getSelection(); const text = selected?.toString() ?? ""; if (!text.trim() || text.length > 160 || !selected?.rangeCount) return;
        const range = selected.getRangeAt(0); const anchor = range.commonAncestorContainer.parentElement ?? selected.anchorNode?.parentElement;
        const rect = range.getBoundingClientRect(); const frameRect = contents.document.defaultView?.frameElement?.getBoundingClientRect();
        const paragraphElement = anchor?.closest("p,li,blockquote,div") ?? anchor;
        const paragraphText = paragraphElement?.textContent ?? text;
        let paragraphOffset = paragraphText.indexOf(text);
        if (paragraphElement) {
          try { const prefix = range.cloneRange(); prefix.selectNodeContents(paragraphElement); prefix.setEnd(range.startContainer, range.startOffset); paragraphOffset = prefix.toString().length; } catch { /* use nearest textual match */ }
        }
        const context = buildSelectionContext(paragraphText, text, Math.max(0, paragraphOffset));
        const chapter = currentChapter.current; if (chapter === null) return;
        const selectionInfo = { text, context: context.sentence, paragraph: context.paragraph, sentence: context.sentence, previousSentence: context.previousSentence, nextSentence: context.nextSentence, sentenceSelectionStart: context.sentenceSelectionStart, sentenceSelectionEnd: context.sentenceSelectionEnd, chapter, knowledgeAsOfChapter: Math.min(chapter - 1, latestCompletedChapter), explainFunctionWords: effectiveReaderSettings(useReaderStore.getState(), sessionKey).functionWordMode === "grammar", anchorX: Math.max(24, Math.min(window.innerWidth - 24, (frameRect?.left ?? 0) + rect.left + rect.width / 2)), anchorY: Math.max(24, (frameRect?.top ?? 0) + rect.bottom) };
        setSelectionCfi(cfiRange); setSelection(selectionInfo); setDictionarySelection(null);
        afterStablePaint(selectionStarted,"selection_toolbar");
      });
      view.on("relocated", (raw: RelocatedLocation) => {
        const chapter = chapterForHref(book.chapters, raw.start.href); if (!chapter) return;
        if (!firstRelocationRecorded.current) { firstRelocationRecorded.current=true; recordPerformanceSample(saved?"resume":"reader_open",performance.now()-readerOpenStarted.current); }
        if (currentChapter.current !== null && currentChapter.current !== chapter.index) leaveChapter(currentChapter.current);
        currentChapter.current = chapter.index; setChapterTitle(chapter.title); setSelection(null);
        const displayed = raw.start.displayed; const observed = displayed && displayed.total > 0 ? displayed.page / displayed.total : Math.max(0, Math.min(1, raw.start.percentage ?? 0));
        const overall = calculateBookProgress(book.chapters, chapter.index, observed);
        currentProgress.current = observed; setChapterPercent(Math.round(observed * 100)); setBookProgress(overall);
        const layoutDivisor = Math.max(1, Number((view as unknown as { _layout?: { props?: { divisor?: number } } })._layout?.props?.divisor ?? 1));
        currentCfi.current = raw.start.cfi; setPage({ current: displayed ? Math.ceil(displayed.page / layoutDivisor) : 0, total: displayed ? Math.ceil(displayed.total / layoutDivisor) : 0 });
        useReaderStore.getState().setBookPosition(sessionKey, { cfi: raw.start.cfi, chapterIndex: chapter.index, displayedPage: displayed?.page, chapterProgress: observed, bookProgress: overall, updatedAt: Date.now() });
        const key = progressKey(bookName, sessionName, chapter.index); const previous = useReaderStore.getState().progress[key] ?? emptyProgress();
        const relocationKind: NavigationKind = navigation.current === "restore" && !previous.lastCfi ? "forward" : navigation.current;
        const pageTolerance = Math.max(0.08, displayed && displayed.total > 0 ? (1 / displayed.total) + 0.02 : 0.08);
        const update = updateContiguousProgress(previous, observed, raw.start.cfi, relocationKind, pageTolerance);
        useReaderStore.getState().setProgress(key, update.progress);
        if (userId) {
          pendingPersistence.current = () => {
            void readerStateApi.updateChapter(userId, bookName, sessionName, chapter.index, update.progress);
            void readerStateApi.updateBook(userId, bookName, sessionName, { last_opened_at: Date.now() / 1000, last_cfi: raw.start.cfi, current_chapter: chapter.index, chapter_progress: observed, book_progress: overall, finished_at: update.completedNaturally && chapter.index === book.chapters.at(-1)?.index ? Date.now() / 1000 : undefined });
          };
          if (persistenceTimer.current !== null) window.clearTimeout(persistenceTimer.current);
          persistenceTimer.current = window.setTimeout(() => { persistenceTimer.current=null; pendingPersistence.current?.(); pendingPersistence.current=null; }, 450);
        }
        if (backgroundAnalysisEnabled && (chapter.word_count ?? 0) >= 20 && (update.crossedThreshold || (navigation.current === "restore" && previous.contiguousProgress >= 0.5 && !previous.naturallyCompleted))) stage.mutate(chapter.index);
        navigation.current = "reflow";
      });
      const savedPosition = useReaderStore.getState().books[sessionKey]?.position;
      const saved = savedPosition?.cfi;
      return instance.ready.then(async () => {
        await (view as unknown as { started: Promise<void> }).started;
        if (settings.readingMode === "paged") {
          const pagedManager = (view as unknown as { manager: { viewSettings?: { forceEvenPages?: boolean } } }).manager;
          if (pagedManager.viewSettings) pagedManager.viewSettings.forceEvenPages = false;
        }
        await view.display(saved || undefined);
        const restoredLocation = view.currentLocation() as unknown as RelocatedLocation;
        const restoredChapter = chapterForHref(book.chapters, restoredLocation?.start?.href ?? "");
        if (savedPosition && restoredChapter?.index !== savedPosition.chapterIndex) {
          const fallbackChapter = book.chapters.find((chapter) => chapter.index === savedPosition.chapterIndex);
          if (fallbackChapter) await view.display(fallbackChapter.spine_href);
        }
        resizeRendition();
      });
    }).catch((error: unknown) => setReaderError(error instanceof Error ? error.message : "The EPUB could not be rendered."));
    return () => { disposed = true; resizeObserver?.disconnect(); iframeKeyListeners.forEach(({ document, listener }) => document.removeEventListener("keydown", listener)); if (currentChapter.current !== null) leaveChapter(currentChapter.current); clearSearchHighlight(); renderedAnnotations.current.clear(); rendition.current?.destroy(); rendition.current=null; epubBook.current?.destroy(); };
  // Rendition is deliberately recreated only when the book identity changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metadata.data?.title, bookName, sessionName, settings.readingMode]);

  useEffect(() => { document.documentElement.dataset.readerTheme = settings.readerTheme; return () => { delete document.documentElement.dataset.readerTheme; }; }, [settings.readerTheme]);
  useEffect(() => {
    const view = rendition.current; if (!view) return;
    const reflowStarted = performance.now();
    const openContents = view.getContents() as unknown as Contents[];
    const palette = readerThemeColors(settings.readerTheme);
    const currentSettings = settingsRef.current;
    const activeDocumentSettings = { ...currentSettings, fontFamily: readerFontFamily(currentSettings.font) };
    openContents.forEach((contents) => {
      applyReaderDocumentStyles(contents.document, readerDocumentCss, palette, documentFlow, activeDocumentSettings);
      preparePublisherImages(contents.document);
    });
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const host = container.current;
      if (host) view.resize(Math.floor(host.clientWidth), Math.floor(host.clientHeight));
      afterStablePaint(reflowStarted,"theme_reflow");
    }));
  }, [documentFlow, readerDocumentCss, settings.columnWidth, settings.font, settings.fontSize, settings.hyphenation, settings.imageScale, settings.justification, settings.lineSpacing, settings.marginPercent, settings.paragraphSpacing, settings.readerTheme, settings.usePublisherFonts]);
  useEffect(() => {
    const view=rendition.current; if (!view) return;
    renderedAnnotations.current=syncRenditionAnnotations(view.annotations as unknown as RenditionAnnotationApi,renderedAnnotations.current,annotations.data?.annotations ?? []);
  }, [annotations.data?.annotations, renditionRevision]);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => handleReaderKey(event);
    window.addEventListener("keydown", listener); return () => window.removeEventListener("keydown", listener);
  });
  useEffect(() => {
    const listener = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (overflowMenu.current?.open && !target?.closest(".reader-overflow")) overflowMenu.current.open = false;
      if (target?.closest(".typography-panel,.toc-panel,.search-panel,.dictionary-popup,.selection-toolbar,.annotation-color-picker,.reader-toolbar,.note-editor,.annotation-drawer,.translation-panel,.image-zoom")) return;
      dismissReaderPanels();
    };
    window.addEventListener("pointerdown", listener, true);
    return () => window.removeEventListener("pointerdown", listener, true);
  }, [dismissReaderPanels]);
  useEffect(() => () => {
    if (persistenceTimer.current !== null) window.clearTimeout(persistenceTimer.current);
    pendingPersistence.current?.();
    pendingPersistence.current=null;
  }, []);
  useEffect(() => {
    if (!userId) return;
    const startedAt = Date.now()/1000; const startProgress = bookProgress; let activeSeconds=0; let lastActivity=Date.now();
    const activity=() => { lastActivity=Date.now(); };
    const timer=window.setInterval(() => { if (document.visibilityState === "visible" && document.hasFocus() && Date.now()-lastActivity < 60_000) activeSeconds += 1; },1000);
    for (const event of ["pointerdown","keydown","wheel"] as const) window.addEventListener(event,activity,{passive:true});
    return () => { window.clearInterval(timer); for (const event of ["pointerdown","keydown","wheel"] as const) window.removeEventListener(event,activity); const endedAt=Date.now()/1000; if (activeSeconds>0) void readerStateApi.recordReadingSession(userId,bookName,sessionName,{started_at:startedAt,ended_at:endedAt,active_seconds:activeSeconds,start_progress:startProgress,end_progress:currentProgress.current}); };
  // A reading session is bounded by the mounted book identity.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[userId,bookName,sessionName]);
  const runReachedSearch = async () => {
    const needle = query.trim();
    if (!needle) { setSearchResults([]); setSearchMessage(""); return; }
    if (searchScope === "whole" && !store.books[sessionKey]?.wholeBookSearchConfirmed) { setSpoilerGate(true); return; }
    setSearching(true); setSearchMessage("Searching indexed text…");
    try {
      let status = await searchApi.status(bookName, sessionName);
      if (!status.ready) {
        setSearchMessage("Preparing offline search for this book…");
        await searchApi.rebuild(bookName, sessionName);
        for (let attempt=0; attempt<120 && !status.ready; attempt+=1) {
          await new Promise((resolve) => window.setTimeout(resolve, 250));
          status = await searchApi.status(bookName, sessionName);
        }
        if (!status.ready) throw new Error("Search is still being prepared. Please try again in a moment.");
      }
      const options = searchScope === "chapter" ? { chapter: currentChapter.current ?? 0 } : searchScope === "reached" ? { maxChapter: currentChapter.current ?? 0 } : {};
      const result=await searchApi.query(bookName, sessionName, needle, options); setSearchResults(result.results); setSearchMessage(result.results.length ? "" : "No matches in this search scope."); recordPerformanceSample("indexed_search",result.elapsed_ms);
    } catch (error) { setSearchResults([]); setSearchMessage(error instanceof Error ? error.message : "Search could not be completed."); }
    finally { setSearching(false); }
  };
  const openSearchResult = async (result: ReaderSearchResult) => {
    const instance = epubBook.current; const view = rendition.current; if (!instance || !view) return;
    clearSearchHighlight();
    navigation.current = "jump";
    await view.display(result.spine_href);
    const liveContents = view.getContents() as unknown as Contents[];
    for (const contents of liveContents) {
      const liveMatch = selectDocumentSearchMatch(findDocumentSearchMatches(contents.document, query), result.excerpt);
      if (!liveMatch) continue;
      const target = contents.cfiFromRange(liveMatch.range);
      await view.display(target);
      view.annotations.highlight(target, { search: true }, undefined, "bookbuddy-search-highlight", { fill: "#ffd54a", "fill-opacity": "0.82", "mix-blend-mode": "normal" });
      searchHighlightCfi.current = target;
      return;
    }
    // Fallback for unusual EPUB documents whose text is not available through the live iframe.
    const section = instance.spine.get(result.spine_href);
    if (section) {
      await section.load(instance.load.bind(instance));
      const matches = section.find(query.trim()) as unknown as Array<{ cfi: string; excerpt?: string }>;
      const target = selectSearchResultMatch(matches, result.excerpt)?.cfi || result.spine_href;
      section.unload();
      await view.display(target);
      if (target !== result.spine_href) {
        view.annotations.highlight(target, { search: true }, undefined, "bookbuddy-search-highlight", { fill: "#ffd54a", "fill-opacity": "0.82", "mix-blend-mode": "normal" });
        searchHighlightCfi.current = target;
      }
      return;
    }
  };
  const activeJobs = analysis.data?.jobs.filter((job) => ["queued", "analyzing", "eligible", "committing"].includes(job.state)) ?? [];
  const pendingEligible = analysis.data?.jobs.filter((job) => job.eligible && job.state !== "committed") ?? [];
  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    void getCurrentWindow().isFullscreen().then(setFullscreen);
  }, []);

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    let unlisten: (() => void) | undefined;
    void getCurrentWindow().onCloseRequested(async (event) => {
      event.preventDefault();
      if (pendingEligible.length > 0) { setCloseOpen(true); return; }
      const chapter = currentChapter.current;
      if (chapter !== null) {
        const progress = useReaderStore.getState().progress[progressKey(bookName, sessionName, chapter)];
        if (progress?.thresholdStarted && !progress.naturallyCompleted) await analysisApi.discard(bookName, sessionName, chapter).catch(() => undefined);
      }
      await flushReaderSettings(); await invoke("exit_app");
    }).then((dispose) => { unlisten = dispose; });
    return () => unlisten?.();
  }, [bookName, pendingEligible.length, sessionName]);
  useEffect(() => { const flush=()=>{void flushReaderSettings();}; window.addEventListener("pagehide",flush); document.addEventListener("visibilitychange",flush); return()=>{window.removeEventListener("pagehide",flush);document.removeEventListener("visibilitychange",flush);}; },[]);

  useEffect(() => {
    if (!finishingInBackground || !analysis.data) return;
    const unfinished = analysis.data.jobs.some((job) => job.eligible && !["committed", "error", "cancelled"].includes(job.state));
    if (unfinished) return;
    void (async () => {
      let allowed = await isPermissionGranted(); if (!allowed) allowed = (await requestPermission()) === "granted";
      if (allowed) sendNotification({ title: "BookBuddy analysis finished", body: "Your completed chapters are safely stored." });
      await invoke("exit_app");
    })();
  }, [analysis.data, finishingInBackground]);

  const requestClose = async () => {
    if (pendingEligible.length > 0) { setCloseOpen(true); return; }
    const chapter = currentChapter.current;
    if (chapter !== null) {
      const progress = useReaderStore.getState().progress[progressKey(bookName, sessionName, chapter)];
      if (progress?.thresholdStarted && !progress.naturallyCompleted) await analysisApi.discard(bookName, sessionName, chapter).catch(() => undefined);
    }
    if ("__TAURI_INTERNALS__" in window) await invoke("exit_app"); else window.close();
  };
  const goHome = async () => { if (fullscreen) await setNativeFullscreen(false); if (currentChapter.current !== null) leaveChapter(currentChapter.current); navigate("/"); };
  const minimizeWindow = async () => { if ("__TAURI_INTERNALS__" in window) await getCurrentWindow().minimize(); };
  const currentBookmark = readerLibrary.data?.bookmarks.some((item) => item.session_key === `${bookName}::${sessionName}` && item.cfi === currentCfi.current);
  const handleSelectionAction = (action:SelectionActionId) => {
    if (!selection) return;
    if (action === "copy") { void navigator.clipboard.writeText(selection.text); setSelection(null); return; }
    if (action === "highlight" || action === "underline") { const type=action; setAnnotationPicker({type,color:normalizeAnnotationColor(undefined,type),x:selection.anchorX??24,y:selection.anchorY??24}); return; }
    if (action === "note") { const color=normalizeAnnotationColor(store.books[sessionKey]?.draftNote?.color,"highlight"); const draft={text:store.books[sessionKey]?.draftNote?.text??"",color,updatedAt:Date.now(),cfi:selectionCfi,quote:selection.text,chapterIndex:selection.chapter}; store.setDraftNote(sessionKey,draft); setNoteColor(color); setNoteDraft(draft.text); return; }
    if (action === "search") { setQuery(selection.text); setSearchOpen(true); setSelection(null); return; }
    if (action === "translate") { if (!health.data?.capabilities.translation) { setAIRequiredFeature("Translation"); return; } setTranslationSelection(selection); translation.reset(); setSelection(null); return; }
    setDictionarySelection(selection); setSelection(null);
  };

  if (metadata.isLoading) return <main className="reader-loading"><LoaderCircle className="spin"/><p>Opening the book…</p></main>;
  if (metadata.error || readerError) return <main className="centered-state" role="alert"><p className="eyebrow">Reader unavailable</p><h1>This book could not be opened.</h1><p>{readerError ?? metadata.error?.message}</p><button className="primary" onClick={() => navigate("/")}>Return to library</button></main>;
  return <main className={`reader-page ${fullscreen ? "is-fullscreen" : ""} ${annotationsOpen && !fullscreen ? "has-annotations" : ""} mode-${settings.readingMode}`} style={{ "--reader-column": `${settings.columnWidth}px`, "--reader-spread": `${(settings.columnWidth * 2) + 168}px` } as React.CSSProperties}>
    <FullscreenControls fullscreen={fullscreen} revealed={fullscreenControls} onRevealedChange={setFullscreenControls} onHome={() => void goHome()} onExit={() => void setNativeFullscreen(false)} onMinimize={() => void minimizeWindow()} onClose={() => void requestClose()}/>
    {windowError && <div className="reader-window-error" role="status">{windowError}<button aria-label="Dismiss window-control message" onClick={() => setWindowError(null)}><X/></button></div>}
    {!fullscreen && <header className="reader-toolbar">
      <button aria-label="Back to Library" title="Back to Library" onClick={() => navigate("/library")}><ArrowLeft/></button><Link to="/library" aria-label="Library" title="Library"><Library/></Link>
      <button aria-label="Table of contents" title="Table of contents" onClick={() => { setTypographyOpen(false); closeSearch(); setTocOpen((open) => !open); }}><ListTree/></button>
      <div className="reader-book-title"><strong>{metadata.data?.title}</strong><span>{chapterTitle}</span></div>
      <button aria-label="Search reached text" title="Search reached text" onClick={() => { setTocOpen(false); setTypographyOpen(false); if (searchOpen) closeSearch(); else setSearchOpen(true); }}><Search/></button>
      <button aria-label="Book notes" title="Book notes (Ctrl B)" className={annotationsOpen ? "active" : ""} onClick={() => setAnnotationsOpen((open) => !open)}><NotebookPen/></button>
      <button aria-label={currentBookmark ? "Remove bookmark" : "Bookmark this page"} title={currentBookmark ? "Remove bookmark" : "Bookmark this page"} className={currentBookmark ? "active" : ""} onClick={() => bookmark.mutate()}><Bookmark/></button>
      <button aria-label="Reader typography" title="Reader typography" onClick={() => { setTocOpen(false); closeSearch(); setTypographyOpen((open) => !open); }}><Type/></button>
      <button aria-label="Change reader theme" title={`Theme: ${settings.readerTheme}`} onClick={() => { const themes = ["paper","night","sepia","oled","forest"] as const; store.setAppearance({ readerTheme: themes[(themes.indexOf(settings.readerTheme) + 1) % themes.length] }); }}><Palette/></button>
      <button aria-label="Enter fullscreen" title="Enter fullscreen (F11)" onClick={() => void setNativeFullscreen(true)}><Maximize/></button>
      <details ref={overflowMenu} className="reader-overflow"><summary aria-label="More reader controls" title="More"><MoreHorizontal/></summary><div><Link to="/settings"><Settings/>Reader settings</Link><p className={activeJobs.length ? "active" : ""}>{activeJobs.length ? `Analyzing ${Math.round(analysis.data?.progress ?? 0)}%` : "Reader ready"}</p><small>Fullscreen controls: Ctrl Shift F</small></div></details>
    </header>}
    {tocOpen && !fullscreen && <ContentsPanel navigation={metadata.data?.navigation} chapters={metadata.data?.chapters ?? []} bookTitle={metadata.data?.title ?? "Contents"} currentChapterIndex={currentChapter.current} onClose={() => setTocOpen(false)} onNavigate={(href) => { navigation.current="jump"; setTocOpen(false); void rendition.current?.display(href); }}/>} 
    {typographyOpen && !fullscreen && <aside className="typography-panel" aria-label="Typography controls">
      <label><span>Override this book <ReaderHelp text="Off uses your reader defaults. On stores a separate set of controls for only this EPUB."/></span><input type="checkbox" checked={Boolean(store.books[sessionKey]?.override)} onChange={(event) => store.setBookOverride(sessionKey, event.target.checked)}/></label>
      <label><span>Book font <ReaderHelp text="Original EPUB font uses the typefaces embedded or named by the publisher. Other choices replace only the font face; publisher headings, drop caps, indents, emphasis, and layout remain."/></span><select value={settings.usePublisherFonts ? "publisher" : settings.font} onChange={(event) => { const values = event.target.value === "publisher" ? { usePublisherFonts: true } : { usePublisherFonts: false, font: event.target.value as typeof settings.font }; if (store.books[sessionKey]?.override) store.setBookAppearance(sessionKey, values); else store.setAppearance(values); }}><option value="publisher">Original EPUB font & styling</option>{readerFontOptions.map((font) => <option key={font.id} value={font.id}>{font.label}</option>)}</select></label>
      <ReaderRange label="Font size" help="Changes the base reading-text size while keeping the EPUB's relative heading and drop-cap sizes." value={settings.fontSize} min={14} max={38} suffix="px" onChange={(fontSize) => store.books[sessionKey]?.override ? store.setBookAppearance(sessionKey, { fontSize }) : store.setAppearance({ fontSize })}/>
      <ReaderRange label="Line height" help="Controls vertical space between lines of reading text." value={settings.lineSpacing} min={1.2} max={2.2} step={0.05} onChange={(lineSpacing) => store.books[sessionKey]?.override ? store.setBookAppearance(sessionKey, { lineSpacing }) : store.setAppearance({ lineSpacing })}/>
      <ReaderRange label="Paragraph spacing" help="Adds space after paragraphs without removing the publisher's indents, alignment classes, or chapter layout." value={settings.paragraphSpacing} min={0} max={2} step={0.1} suffix="em" onChange={(paragraphSpacing) => store.books[sessionKey]?.override ? store.setBookAppearance(sessionKey, { paragraphSpacing }) : store.setAppearance({ paragraphSpacing })}/>
      <ReaderRange label="Column width" help="Sets the maximum width of one reading page or column." value={settings.columnWidth} min={540} max={1100} step={20} suffix="px" onChange={(columnWidth) => store.books[sessionKey]?.override ? store.setBookAppearance(sessionKey, { columnWidth }) : store.setAppearance({ columnWidth })}/>
      <ReaderRange label="Image scale" help="Limits large EPUB images while preserving their aspect ratio." value={settings.imageScale} min={0.5} max={1} step={0.05} suffix="%" formatValue={(value) => Math.round(value*100)} onChange={(imageScale) => store.books[sessionKey]?.override ? store.setBookAppearance(sessionKey, { imageScale }) : store.setAppearance({ imageScale })}/>
      <label><span>Reading mode <ReaderHelp text="Paged lays the EPUB out like pages and supports spreads on wide screens. Continuous makes each chapter vertically scrollable."/></span><select value={settings.readingMode} onChange={(event) => store.books[sessionKey]?.override ? store.setBookAppearance(sessionKey, { readingMode: event.target.value as "paged" | "continuous" }) : store.setAppearance({ readingMode: event.target.value as "paged" | "continuous" })}><option value="paged">Paged</option><option value="continuous">Continuous scroll</option></select></label>
    </aside>}
    {searchOpen && !fullscreen && <aside className="search-panel" aria-label="Search this book">
      <form onSubmit={(event) => { event.preventDefault(); void runReachedSearch(); }}><Search/><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this book"/><button aria-label="Run search"><Search/></button><button type="button" aria-label="Close search" onClick={closeSearch}><X/></button></form>
      <select aria-label="Search scope" value={searchScope} onChange={(event) => setSearchScope(event.target.value as typeof searchScope)}><option value="chapter">Current chapter</option><option value="reached">Reached text</option><option value="whole">Whole book</option></select>
      {searchMessage && <p role={searching ? "status" : "alert"}>{searchMessage}</p>}
      {spoilerGate && <div className="spoiler-gate" role="alert"><strong>Whole-book results may reveal unread text.</strong><div><button onClick={() => { store.confirmWholeBookSearch(sessionKey); setSpoilerGate(false); void runReachedSearch(); }}>Search whole book</button><button onClick={() => { setSearchScope("reached"); setSpoilerGate(false); }}>Keep it spoiler-safe</button></div></div>}
      {searching ? <p>Searching indexed text…</p> : searchResults.map((result) => <button key={`${result.chapter_index}-${result.paragraph_index}`} onClick={() => void openSearchResult(result)}><strong>{result.chapter_title}{currentChapter.current !== null && result.chapter_index > currentChapter.current ? " · unread" : ""}</strong><span>{result.excerpt.replace(/<\/?mark>/g, "")}</span></button>)}
    </aside>}
    {annotationsOpen && !fullscreen && <aside className="annotation-drawer" aria-label="Notes for this book"><header><div><strong>Book notes</strong><small>{visibleAnnotations.length} saved</small></div><button aria-label="Close notes" onClick={() => setAnnotationsOpen(false)}><X/></button></header><input aria-label="Search annotations" value={annotationQuery} onChange={(event) => setAnnotationQuery(event.target.value)} placeholder="Search notes and saved lines"/>{annotations.isLoading ? <p>Loading annotations…</p> : visibleAnnotations.length ? visibleAnnotations.map((item) => { const color=normalizeAnnotationColor(item.color,item.annotation_type === "underline" ? "underline" : "highlight"); return <article key={item.annotation_id} style={{"--annotation-color":color} as React.CSSProperties}><button className="annotation-jump" onClick={() => { navigation.current="jump"; void rendition.current?.display(item.cfi_range); }}><small><i className="annotation-color-dot" style={{background:color}}/>{item.annotation_type === "note" ? "Note" : item.annotation_type} · Chapter {item.chapter_index+1}</small>{item.quote && <q>{item.quote}</q>}{item.note_text && <span className="annotation-note-text">{item.note_text}</span>}</button><div className="annotation-actions"><button aria-label="Edit annotation" onClick={() => setEditingAnnotation({id:item.annotation_id,text:item.note_text,color})}><Pencil/>Edit</button><button aria-label="Delete annotation" onClick={() => deleteAnnotation.mutate(item.annotation_id)}>Delete</button></div></article>; }) : <p className="annotation-empty">No saved notes or highlights yet. Select a line in the book to add one.</p>}</aside>}
    {editingAnnotation && <aside className="note-editor" aria-label="Edit annotation"><label>Note<textarea autoFocus value={editingAnnotation.text} onChange={(event) => setEditingAnnotation({...editingAnnotation,text:event.target.value})}/></label><NoteColorSelector color={editingAnnotation.color} onChange={(color) => setEditingAnnotation({...editingAnnotation,color})}/><div><button className="primary" disabled={updateAnnotation.isPending} onClick={() => updateAnnotation.mutate({id:editingAnnotation.id,text:editingAnnotation.text,color:editingAnnotation.color})}>Save changes</button><button className="secondary" onClick={() => setEditingAnnotation(null)}>Cancel</button></div></aside>}
    {zoomImage&&<div className="image-zoom" role="dialog" aria-modal="true" aria-label={zoomImage.alt} onWheel={(event) => { event.preventDefault(); setZoomScale((scale) => Math.max(.5,Math.min(6,scale+(event.deltaY<0?.25:-.25)))); }} onPointerMove={(event) => { if (!panStart.current) return; setZoomOffset({x:panStart.current.ox+event.clientX-panStart.current.x,y:panStart.current.oy+event.clientY-panStart.current.y}); }} onPointerUp={() => {panStart.current=null;}} onClick={(event) => { if (event.target === event.currentTarget) setZoomImage(null); }}><button className="zoom-close" aria-label="Close image zoom" onClick={() => setZoomImage(null)}><X/></button><button className="zoom-reset" onClick={() => {setZoomScale(1);setZoomOffset({x:0,y:0});}}>Reset</button><button className="zoom-out" aria-label="Zoom out" onClick={() => setZoomScale((scale)=>Math.max(.5,scale-.25))}>−</button><button className="zoom-in" aria-label="Zoom in" onClick={() => setZoomScale((scale)=>Math.min(6,scale+.25))}>+</button><output className="zoom-level">{Math.round(zoomScale*100)}%</output><img src={zoomImage.src} alt={zoomImage.alt} draggable={false} style={{transform:`translate(${zoomOffset.x}px,${zoomOffset.y}px) scale(${zoomScale})`}} onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); panStart.current={x:event.clientX,y:event.clientY,ox:zoomOffset.x,oy:zoomOffset.y}; }}/></div>}
    <section className="reading-surface" aria-label="EPUB reading area"><button className="page-edge previous" aria-label="Previous page" onClick={() => void previousPage()}/><div ref={container} className="epub-container"/><button className="page-edge next" aria-label="Next page" onClick={() => void nextPage()}/></section>
    <footer className="reader-status"><span>{page.total > 0 ? `Page ${page.current} of ${page.total}` : `${chapterPercent}% of chapter`}</span><span className="reader-progress-control"><input aria-label="Book progress" title="Book progress" type="range" min="0" max="100" step="1" value={formatBookProgressPercent(bookProgress)} onChange={(event) => { const percent=Number(event.target.value)/100; const target=metadata.data?.chapters[Math.min((metadata.data?.chapters.length??1)-1,Math.floor(percent*(metadata.data?.chapters.length??1)))]; if(target){navigation.current="jump";void rendition.current?.display(target.spine_href);} }}/><span className="status-chapter">{chapterTitle || "Beginning"}</span></span><span>{formatBookProgressPercent(bookProgress)}% of book</span></footer>
    {selection && !annotationPicker && <SelectionToolbar x={selection.anchorX ?? 24} y={selection.anchorY ?? 24} capabilities={{dictionary:Boolean(health.data?.capabilities.dictionary),chapter_analysis:Boolean(health.data?.capabilities.chapter_analysis),translation:Boolean(health.data?.capabilities.translation)}} onAction={handleSelectionAction}/>} 
    {selection && annotationPicker && <AnnotationColorPicker {...annotationPicker} saving={annotation.isPending} onColorChange={(color) => setAnnotationPicker({...annotationPicker,color})} onSave={() => { annotationStarted.current=performance.now(); annotation.mutate({annotation_type:annotationPicker.type,color:annotationPicker.color}); }} onCancel={() => setAnnotationPicker(null)}/>} 
    {noteDraft !== null && <aside className="note-editor" aria-label="New note"><label>Note<textarea autoFocus value={noteDraft} onChange={(event) => { const previous=useReaderStore.getState().books[sessionKey]?.draftNote; setNoteDraft(event.target.value); store.setDraftNote(sessionKey,{...previous,text:event.target.value,color:noteColor,updatedAt:Date.now()}); }}/></label><NoteColorSelector color={noteColor} onChange={(color) => { const previous=useReaderStore.getState().books[sessionKey]?.draftNote; setNoteColor(color); store.setDraftNote(sessionKey,{...previous,text:noteDraft,color,updatedAt:Date.now()}); }}/><div><button className="primary" disabled={annotation.isPending} onClick={() => {annotationStarted.current=performance.now();annotation.mutate({annotation_type:"note",color:noteColor,note_text:noteDraft});}}>Save note</button><button className="secondary" onClick={() => setNoteDraft(null)}>Keep draft</button><button className="text-button" onClick={() => {setNoteDraft(null);store.setDraftNote(sessionKey,undefined);}}>Discard draft</button></div></aside>}
    {translationSelection && <aside className="translation-panel" role="dialog" aria-modal="true" aria-label="Translate selection"><header><strong>Translate selection</strong><button aria-label="Close translation" onClick={() => setTranslationSelection(null)}><X/></button></header><blockquote>{translationSelection.text}</blockquote><label>Translate to<select value={translationTarget} onChange={(event) => { setTranslationTarget(event.target.value); translation.reset(); }}><option>Spanish</option><option>French</option><option>German</option><option>Hindi</option><option>Japanese</option><option>Portuguese</option></select></label>{translation.data && <p className="translation-result" aria-live="polite">{translation.data.translation}</p>}{translation.error && <p role="alert">{translation.error.message}</p>}<button className="primary" disabled={translation.isPending} onClick={() => translation.mutate()}>{translation.isPending ? "Translating…" : "Translate"}</button></aside>}
    <DictionaryPopup book={bookName} session={sessionName} selection={dictionarySelection} onDismiss={() => setDictionarySelection(null)}/>
    <AIRequiredDialog open={Boolean(aiRequiredFeature)} feature={aiRequiredFeature ?? "This feature"} onOpenChange={(open) => { if (!open) setAIRequiredFeature(null); }}/>
    <Dialog.Root open={closeOpen} onOpenChange={setCloseOpen}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="close-dialog"><Dialog.Title>Chapter analysis is not finished</Dialog.Title><Dialog.Description>BookBuddy can finish every chapter you completed in the background. Earlier chapters are already safe.</Dialog.Description><div className="dialog-actions"><button className="primary" onClick={() => { setCloseOpen(false); setFinishingInBackground(true); void invoke("hide_to_tray"); }}>Finish in background</button><button className="secondary" onClick={() => { void Promise.all(pendingEligible.map((job) => analysisApi.discard(bookName, sessionName, job.chapter_index))).finally(() => invoke("exit_app")); }}>Cancel analysis and exit</button><Dialog.Close className="text-button">Keep reading</Dialog.Close></div></Dialog.Content></Dialog.Portal></Dialog.Root>
  </main>;
}
