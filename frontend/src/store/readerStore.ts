import { load } from "@tauri-apps/plugin-store";
import { invoke } from "@tauri-apps/api/core";
import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";
import type { ChapterProgress } from "../utils/progress";

export type AppTheme = "system" | "light" | "dark" | "contrast";
export type ReaderFont = "segoe-ui" | "segoe-print" | "segoe-script" | "georgia" | "cambria" | "calibri" | "candara" | "constantia" | "corbel" | "times-new-roman" | "arial" | "bahnschrift" | "consolas" | "courier-new" | "franklin-gothic" | "palatino" | "sitka" | "tahoma" | "verdana" | "trebuchet" | "literata" | "source-serif" | "eb-garamond" | "crimson" | "inter" | "atkinson" | "source-sans" | "system";
export type ReaderTheme = "paper" | "night" | "sepia" | "oled" | "forest";
export type Accent = "gold" | "brass" | "amber" | "sapphire" | "sage" | "rose";
export type ReadingMode = "paged" | "continuous";
export type LibrarySort = "recent" | "added" | "title" | "author" | "progress" | "rating" | "series" | "year";
export type LibraryDensity = "grid" | "large" | "compact" | "detailed";

export interface ReaderPresentationSettings {
  appTheme: AppTheme;
  readerTheme: ReaderTheme;
  accent: Accent;
  font: ReaderFont;
  fontSize: number;
  lineSpacing: number;
  paragraphSpacing: number;
  columnWidth: number;
  marginPercent: number;
  usePublisherFonts: boolean;
  imageScale: number;
  justification: "left" | "justify";
  hyphenation: boolean;
  readingMode: ReadingMode;
  reducedMotion: "system" | "reduce" | "full";
  functionWordMode: "suppress" | "grammar";
}

export interface ReaderPosition {
  cfi: string;
  chapterIndex: number;
  displayedPage?: number;
  chapterProgress: number;
  bookProgress: number;
  updatedAt: number;
}

export interface BackendReaderPosition {
  session_key: string;
  last_cfi: string;
  current_chapter: number | null;
  chapter_progress: number;
  book_progress: number;
  updated_at: number;
}

export interface BookReaderSettings {
  override: boolean;
  settings?: Partial<ReaderPresentationSettings>;
  position?: ReaderPosition;
  draftNote?: { annotationId?: string; text: string; color?: string; updatedAt: number; cfi?: string; quote?: string; chapterIndex?: number };
  wholeBookSearchConfirmed?: boolean;
}

export interface LibrarySettings {
  sort: LibrarySort;
  density: LibraryDensity;
  startupDestination: "home" | "library" | "resume";
  sidebarPinned: boolean;
  sidebarCollapsed: boolean;
  pinnedSessionKeys: string[];
  hasCompletedFirstLaunch: boolean;
  pageTransitions: boolean;
  shelfScrollPositions: Record<string, number>;
}

export interface AIExperienceSettings {
  onboardingDismissed: boolean;
}

export interface RecentBook { book: string; session: string; title: string; openedAt: number }

interface ReaderState {
  schemaVersion: 5;
  global: ReaderPresentationSettings;
  books: Record<string, BookReaderSettings>;
  library: LibrarySettings;
  aiExperience: AIExperienceSettings;
  customBackendUrl: string;
  readerProfileId: string | null;
  readerStateMigration: number;
  recentBooks: RecentBook[];
  lastOpened: string | null;
  progress: Record<string, ChapterProgress>;
  setAppearance: (values: Partial<ReaderPresentationSettings>) => void;
  setLibraryPreferences: (values: Partial<LibrarySettings>) => void;
  setAIExperience: (values: Partial<AIExperienceSettings>) => void;
  setBookOverride: (sessionKey: string, override: boolean) => void;
  setBookAppearance: (sessionKey: string, values: Partial<ReaderPresentationSettings>) => void;
  setBookPosition: (sessionKey: string, position: ReaderPosition) => void;
  setDraftNote: (sessionKey: string, draftNote?: BookReaderSettings["draftNote"]) => void;
  confirmWholeBookSearch: (sessionKey: string) => void;
  setReaderProfile: (readerProfileId: string) => void;
  markReaderStateMigrated: () => void;
  setDiagnosticBackendUrl: (url: string) => void;
  touchBook: (book: RecentBook) => void;
  setProgress: (key: string, progress: ChapterProgress) => void;
}

export const defaultPresentation: ReaderPresentationSettings = {
  appTheme: "system", readerTheme: "paper", accent: "gold", font: "literata",
  fontSize: 19, lineSpacing: 1.65, paragraphSpacing: 0.8, columnWidth: 760,
  marginPercent: 4, usePublisherFonts: true, imageScale: 1, justification: "left",
  hyphenation: false, readingMode: "paged", reducedMotion: "system", functionWordMode: "suppress",
};

export const defaultLibrarySettings: LibrarySettings = {
  sort: "recent", density: "grid", startupDestination: "home",
  sidebarPinned: false, sidebarCollapsed: true, pinnedSessionKeys: [], hasCompletedFirstLaunch: false, pageTransitions: true, shelfScrollPositions: {},
};

type LegacyState = Partial<ReaderState> & {
  theme?: AppTheme; readerTheme?: ReaderTheme; accent?: Accent; font?: ReaderFont;
  fontSize?: number; lineSpacing?: number; paragraphSpacing?: number; columnWidth?: number;
  reducedMotion?: ReaderPresentationSettings["reducedMotion"];
  functionWordMode?: ReaderPresentationSettings["functionWordMode"];
  librarySort?: LibrarySort; libraryDensity?: LibraryDensity;
  startupDestination?: LibrarySettings["startupDestination"]; backendMode?: unknown;
};

export function migrateReaderState(persisted: unknown): Partial<ReaderState> {
  const legacy = { ...((persisted ?? {}) as LegacyState) };
  const global = { ...defaultPresentation, ...(legacy.global ?? {}) };
  if (legacy.theme) global.appTheme = legacy.theme;
  if (legacy.readerTheme) global.readerTheme = legacy.readerTheme;
  else if (legacy.theme === "dark") global.readerTheme = "night";
  else if (legacy.theme === "contrast") global.readerTheme = "oled";
  for (const key of ["accent", "font", "fontSize", "lineSpacing", "paragraphSpacing", "columnWidth", "reducedMotion", "functionWordMode"] as const) {
    const value = legacy[key];
    if (value !== undefined) Object.assign(global, { [key]: value });
  }
  const library = {
    ...defaultLibrarySettings,
    ...(legacy.library ?? {}),
    ...(legacy.librarySort ? { sort: legacy.librarySort } : {}),
    ...(legacy.libraryDensity ? { density: legacy.libraryDensity } : {}),
    ...(legacy.startupDestination ? { startupDestination: legacy.startupDestination } : {}),
  };
  if ((library.density as string) === "comfortable") library.density = "grid";
  const books = { ...(legacy.books ?? {}) };
  for (const [key, progress] of Object.entries(legacy.progress ?? {})) {
    if (!progress?.lastCfi) continue;
    const parts = key.split("::");
    const chapterIndex = Number(parts.pop());
    const session = parts.pop();
    const book = parts.join("::");
    if (!book || !session || !Number.isInteger(chapterIndex)) continue;
    const sessionKey = `${book}::${session}`;
    const existing = books[sessionKey] ?? { override: false };
    if (!existing.position) {
      books[sessionKey] = { ...existing, position: { cfi: progress.lastCfi, chapterIndex, chapterProgress: progress.currentProgress, bookProgress: 0, updatedAt: Date.now() } };
    }
  }
  delete legacy.backendMode;
  return { ...legacy, schemaVersion: 5, global, library, books, aiExperience: { onboardingDismissed: false, ...((legacy as Partial<ReaderState>).aiExperience ?? {}) } };
}

const isTauri = (): boolean => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
let settingsStore: Awaited<ReturnType<typeof load>> | null = null;
let legacyStore: Awaited<ReturnType<typeof load>> | null = null;
const portableStorePath = (filename: string): Promise<string> => invoke("portable_config_file", { filename });
const getSettingsStore = async () => settingsStore ??= await load(await portableStorePath("reader_settings.json"), { autoSave: 100 });
const getLegacyStore = async () => legacyStore ??= await load(await portableStorePath("reader-state.json"), { autoSave: false });
const storage: StateStorage = {
  getItem: async (name) => {
    if (!isTauri()) return localStorage.getItem(name) ?? localStorage.getItem("bookbuddy-reader-v1");
    const store = await getSettingsStore();
    const current = await store.get<string>(name);
    if (current) return current;
    const verifiedBackup = await store.get<string>(`${name}:verified-backup`);
    if (verifiedBackup) return verifiedBackup;
    const legacy = await getLegacyStore();
    return (await legacy.get<string>("bookbuddy-reader-v1")) ?? null;
  },
  setItem: async (name, value) => {
    if (!isTauri()) { localStorage.setItem(name, value); return; }
    const store = await getSettingsStore();
    const previous = await store.get<string>(name);
    if (previous) await store.set(`${name}:verified-backup`, previous);
    await store.set(name, value);
    await store.save();
    const verified = await store.get<string>(name);
    if (verified !== value) {
      if (previous) await store.set(name, previous);
      await store.save();
      throw new Error("Reader settings verification failed; the previous verified settings were preserved.");
    }
  },
  removeItem: async (name) => {
    if (!isTauri()) { localStorage.removeItem(name); return; }
    const store = await getSettingsStore();
    await store.delete(name);
    await store.save();
  },
};

export const progressKey = (book: string, session: string, chapter: number): string => `${book}::${session}::${chapter}`;

export const effectiveReaderSettings = (state: Pick<ReaderState, "global" | "books">, sessionKey: string): ReaderPresentationSettings => {
  const book = state.books[sessionKey];
  return book?.override ? { ...state.global, ...(book.settings ?? {}) } : state.global;
};

export const useReaderStore = create<ReaderState>()(persist((set) => ({
  schemaVersion: 5,
  global: defaultPresentation,
  books: {},
  library: defaultLibrarySettings,
  aiExperience: { onboardingDismissed: false },
  customBackendUrl: "http://127.0.0.1:8000",
  readerProfileId: null, readerStateMigration: 0,
  recentBooks: [], lastOpened: null, progress: {},
  setAppearance: (values) => set((state) => ({ global: { ...state.global, ...values } })),
  setLibraryPreferences: (values) => set((state) => ({ library: { ...state.library, ...values } })),
  setAIExperience: (values) => set((state) => ({ aiExperience: { ...state.aiExperience, ...values } })),
  setBookOverride: (sessionKey, override) => set((state) => ({ books: { ...state.books, [sessionKey]: { ...(state.books[sessionKey] ?? {}), override } } })),
  setBookAppearance: (sessionKey, values) => set((state) => ({ books: { ...state.books, [sessionKey]: { ...(state.books[sessionKey] ?? { override: true }), override: true, settings: { ...(state.books[sessionKey]?.settings ?? {}), ...values } } } })),
  setBookPosition: (sessionKey, position) => set((state) => ({ books: { ...state.books, [sessionKey]: { ...(state.books[sessionKey] ?? { override: false }), position } } })),
  setDraftNote: (sessionKey, draftNote) => set((state) => ({ books: { ...state.books, [sessionKey]: { ...(state.books[sessionKey] ?? { override: false }), draftNote } } })),
  confirmWholeBookSearch: (sessionKey) => set((state) => ({ books: { ...state.books, [sessionKey]: { ...(state.books[sessionKey] ?? { override: false }), wholeBookSearchConfirmed: true } } })),
  setReaderProfile: (readerProfileId) => set({ readerProfileId }),
  markReaderStateMigrated: () => set({ readerStateMigration: 1 }),
  setDiagnosticBackendUrl: (customBackendUrl) => set({ customBackendUrl }),
  touchBook: (book) => set((state) => ({
    lastOpened: `${book.book}::${book.session}`,
    recentBooks: [book, ...state.recentBooks.filter((item) => item.book !== book.book || item.session !== book.session)].slice(0, 30),
  })),
  setProgress: (key, progress) => set((state) => ({ progress: { ...state.progress, [key]: progress } })),
}), {
  name: "bookbuddy-reader-v5", version: 5, storage: createJSONStorage(() => storage),
  migrate: migrateReaderState,
  partialize: (state) => ({ schemaVersion: state.schemaVersion, global: state.global, books: state.books, library: state.library, aiExperience: state.aiExperience, customBackendUrl: state.customBackendUrl, readerProfileId: state.readerProfileId, readerStateMigration: state.readerStateMigration, recentBooks: state.recentBooks, lastOpened: state.lastOpened, progress: state.progress }),
}));

export async function waitForReaderStoreHydration(): Promise<void> {
  if (useReaderStore.persist.hasHydrated()) return;
  await new Promise<void>((resolve) => {
    const unsubscribe = useReaderStore.persist.onFinishHydration(() => { unsubscribe(); resolve(); });
    void useReaderStore.persist.rehydrate();
  });
}

export function hydrateBackendReaderPositions(books: readonly BackendReaderPosition[]): void {
  const state = useReaderStore.getState();
  const seeded = seedBackendReaderPositions(state.books, books);
  if (seeded !== state.books) useReaderStore.setState({ books: seeded });
}

export function seedBackendReaderPositions(localBooks: Record<string, BookReaderSettings>, backendBooks: readonly BackendReaderPosition[]): Record<string, BookReaderSettings> {
  let seeded = localBooks;
  for (const book of backendBooks) {
    // reader_settings.json is authoritative. The backend is consulted only to
    // seed books that do not already have an exact local CFI.
    if (seeded[book.session_key]?.position?.cfi) continue;
    const position = positionFromBackend(book);
    if (!position) continue;
    if (seeded === localBooks) seeded = { ...localBooks };
    seeded[book.session_key] = { ...(seeded[book.session_key] ?? { override: false }), position };
  }
  return seeded;
}

export function positionFromBackend(book: BackendReaderPosition): ReaderPosition | null {
  if (!book.last_cfi || book.current_chapter === null) return null;
  return {
    cfi: book.last_cfi,
    chapterIndex: book.current_chapter,
    chapterProgress: book.chapter_progress,
    bookProgress: book.book_progress,
    updatedAt: book.updated_at * 1000,
  };
}

export async function flushReaderSettings(): Promise<void> {
  if (settingsStore) await settingsStore.save();
}

export function applyStoredTheme(): void {
  const { appTheme, accent, reducedMotion } = useReaderStore.getState().global;
  if (appTheme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset.theme = appTheme;
  document.documentElement.dataset.accent = accent;
  document.documentElement.dataset.motion = reducedMotion;
}
