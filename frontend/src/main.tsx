import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import App from "./App";
import { sessionsQuery } from "./api/books";
import { backendConnection } from "./api/client";
import { readerLibraryQuery, readerStateApi } from "./api/readerState";
import { ensureReaderProfile } from "./readerProfileBootstrap";
import { startupDestinationHash } from "./startupDestination";
import { applyStoredTheme, hydrateBackendReaderPositions, useReaderStore, waitForReaderStoreHydration } from "./store/readerStore";
import "./styles/app.css";

export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 2, staleTime: 5_000 }, mutations: { retry: 0 } } });
const root = createRoot(document.getElementById("root")!);
const isTauri = "__TAURI_INTERNALS__" in window;

function render(onLibraryReady?: () => void): void {
  root.render(<StrictMode><QueryClientProvider client={queryClient}><App onLibraryReady={onLibraryReady} /></QueryClientProvider></StrictMode>);
}

async function prepareReaderProfile() {
  let state = useReaderStore.getState();
  const profile = await ensureReaderProfile(
    state.readerProfileId,
    async () => (await readerStateApi.createProfile()).user_id,
    readerStateApi.library,
  );
  const userId = profile.userId;
  if (profile.created) {
    state.setReaderProfile(profile.userId);
    state = useReaderStore.getState();
  }
  if (profile.created || state.readerStateMigration < 1) {
    const books = state.recentBooks.map((item) => ({ session_key: `${item.book}::${item.session}`, last_opened_at: item.openedAt / 1000, added_at: item.openedAt / 1000 }));
    const chapters = Object.entries(state.progress).flatMap(([key, progress]) => {
      const parts = key.split("::"); const chapterIndex = Number(parts.pop()); const session = parts.pop(); const book = parts.join("::");
      if (!book || !session || !Number.isInteger(chapterIndex)) return [];
      return [{ session_key: `${book}::${session}`, chapter_index: chapterIndex, last_cfi: progress.lastCfi, current_progress: progress.currentProgress, contiguous_progress: progress.contiguousProgress, threshold_started: progress.thresholdStarted, naturally_completed: progress.naturallyCompleted, committed: progress.committed, retry_required: progress.retryRequired }];
    });
    await readerStateApi.importLegacy(userId, books, chapters);
    useReaderStore.getState().markReaderStateMigrated();
  }
  const readerState = await queryClient.ensureQueryData(readerLibraryQuery(userId));
  hydrateBackendReaderPositions(readerState.books);
  return readerState;
}

function applyStartupDestination(readerState: Awaited<ReturnType<typeof prepareReaderProfile>>, desktop: boolean): void {
  const preference = useReaderStore.getState().library.startupDestination;
  const destination = startupDestinationHash(desktop, window.location.hash, preference, readerState.books);
  if (destination) window.location.hash = destination;
}

async function desktopBootstrap(): Promise<void> {
  let readySent = false;
  // The host runs the splash handshake once per launch. If the page is reloaded
  // (F5 / Ctrl+R) the host has already finished and rejects stage updates as
  // stale; the page must then show itself instead of waiting for a reveal that
  // will never come again.
  let reloaded = false;
  const reportStage = async (stage: string): Promise<void> => {
    if (reloaded) return;
    try { await invoke("startup_frontend_stage", { stage }); }
    catch (error) {
      if (!String(error).includes("stale_startup_stage")) throw error;
      reloaded = true;
    }
  };
  const reveal = () => document.documentElement.classList.remove("desktop-starting");
  try {
    await listen("bookbuddy://reveal-main", reveal);
    await backendConnection();
    await reportStage("loadingConfiguration");
    await reportStage("initializingReact");
    await reportStage("restoringSession");
    await waitForReaderStoreHydration();
    applyStoredTheme();
    const readerState = await prepareReaderProfile();
    if (!reloaded) applyStartupDestination(readerState, true);
    await reportStage("loadingLibrary");
    await queryClient.ensureQueryData(sessionsQuery);
    if (reloaded) { render(); reveal(); return; }
    render(() => {
      if (readySent) return;
      readySent = true;
      requestAnimationFrame(() => { void invoke("startup_frontend_ready"); });
    });
  } catch (error) {
    if (reloaded) { render(); reveal(); return; }
    const code = error instanceof Error && error.name === "ZodError" ? "frontend_contract_invalid" : "frontend_initialization_failed";
    await invoke("startup_frontend_failed", { code }).catch(() => undefined);
  }
}

if (isTauri) void desktopBootstrap();
else {
  document.documentElement.classList.remove("desktop-starting");
  void waitForReaderStoreHydration().then(() => { applyStoredTheme(); return prepareReaderProfile(); }).then((state) => { applyStartupDestination(state, false); render(); }).catch(() => render());
}
