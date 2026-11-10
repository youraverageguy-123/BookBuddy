import { lazy, Suspense, useEffect } from "react";
import { HashRouter, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { AppShell } from "./components/layout/AppShell";
import LibraryPage from "./pages/LibraryPage";

const HomePage = lazy(() => import("./pages/HomePage"));
const CollectionsPage = lazy(() => import("./pages/CollectionsPage"));
const ReaderPage = lazy(() => import("./pages/ReaderPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const BookDetailsPage = lazy(() => import("./pages/BookDetailsPage"));
const KnowledgePage = lazy(() => import("./pages/KnowledgePage"));

function RouteLoadingState() { return <main className="centered-state" role="status">Loading view…</main>; }

export default function App({ onLibraryReady }: { onLibraryReady?: () => void }) {
  useEffect(() => {
    const suppressWebviewMenu = (event: MouseEvent) => event.preventDefault();
    window.addEventListener("contextmenu", suppressWebviewMenu, true);
    return () => window.removeEventListener("contextmenu", suppressWebviewMenu, true);
  }, []);

  return <ErrorBoundary><HashRouter><Suspense fallback={<RouteLoadingState />}><Routes>
    <Route element={<AppShell />}><Route index element={<HomePage onReady={onLibraryReady} />} /><Route path="library" element={<LibraryPage onReady={onLibraryReady} />} /><Route path="collections" element={<CollectionsPage />} /><Route path="settings" element={<SettingsPage />} /></Route>
    <Route element={<AppShell />}><Route path="book/:book/:session" element={<BookDetailsPage />} /><Route path="book/:book/:session/knowledge" element={<KnowledgePage />} /></Route>
    <Route path="reader/:book/:session" element={<ReaderPage />} />
    <Route path="*" element={<main className="centered-state"><h1>Page not found</h1><a href="#/">Return to Library</a></main>} />
  </Routes></Suspense></HashRouter></ErrorBoundary>;
}
