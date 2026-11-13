import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BookOpen, LoaderCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { analysisApi } from "../../api/analysis";
import { healthApi } from "../../api/health";

const errorReasons: Record<string, string> = {
  network_unavailable: "Gemini is not responding right now (service unavailable or a network error). BookBuddy keeps retrying.",
  quota_exceeded: "Your Gemini quota is used up for now. Analysis resumes when the quota resets.",
  invalid_key: "The saved Gemini key was rejected.",
  permission_denied: "The key does not have permission to use the chosen model. Try another model in Settings.",
  region_unsupported: "Gemini is not available in this region.",
  unsupported_response_schema: "The chosen model does not support the analysis format. Try another model in Settings.",
};
const WORKING = ["queued", "analyzing", "staged", "eligible", "committing"];
const RECENT_SECONDS = 15 * 60;

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/**
 * Explains why there is no story knowledge yet, from the real analysis state:
 * running, stuck on provider errors, failed, paused, or not started.
 */
export function AnalysisStateNotice({ book, session, asOfChapter, readerLink }: { book: string; session: string; asOfChapter: number; readerLink: string }) {
  const bookLink = `/book/${encodeURIComponent(book)}/${encodeURIComponent(session)}`;
  const aiSettings = useQuery({ queryKey: ["ai-settings"], queryFn: healthApi.aiSettings, retry: false, refetchInterval: 5000 });
  const status = useQuery({ queryKey: ["reader-analysis", book, session], queryFn: () => analysisApi.status(book, session), retry: false, refetchInterval: 5000 });
  const overview = useQuery({ queryKey: ["analysis-overview", book, session], queryFn: () => analysisApi.overview(book, session), retry: false, refetchInterval: 5000 });

  const jobs = status.data?.jobs ?? [];
  const working = jobs.filter((job) => WORKING.includes(job.state)).length;
  const paused = jobs.filter((job) => job.state === "paused").length;
  const failed = jobs.filter((job) => job.state === "error").length;
  const customRun = overview.data?.task.status === "processing";
  const aiOn = Boolean(aiSettings.data?.capabilities.text);
  const autoOn = Boolean(aiSettings.data?.background_analysis.enabled && !aiSettings.data?.background_analysis.paused);
  const lastError = aiSettings.data?.last_error ?? null;
  const recentError = lastError && Date.now() / 1000 - lastError.at < RECENT_SECONDS ? lastError : null;
  const reason = recentError ? errorReasons[recentError.code] ?? "Gemini returned an error." : "";
  const analysedThrough = overview.data?.analysed_through ?? -1;
  const inFlight = working > 0 || customRun;

  let title: string; let body: string; let busy = false; let warn = false;
  if (asOfChapter < 0) {
    title = "Nothing to show yet"; body = "Finish a chapter, or open the book page and tell BookBuddy how far you have already read.";
  } else if (!aiOn) {
    title = "Story knowledge needs a Gemini key"; body = "Add a key in Settings → AI. Reading, notes, and the dictionary work without one.";
  } else if (inFlight && recentError) {
    title = "Analysis is waiting on Gemini"; warn = true; busy = true;
    body = `${reason} ${working ? plural(working, "chapter") : "The current run"} ${working === 1 || !working ? "is" : "are"} waiting to be analysed.`;
  } else if (inFlight) {
    title = "Analysing your chapters"; busy = true;
    body = `${working ? plural(working, "chapter") : "This book"} ${working === 1 || !working ? "is" : "are"} being analysed now. This page fills in as each chapter finishes.`;
  } else if (failed > 0) {
    title = "Analysis stopped"; warn = true;
    body = `${plural(failed, "chapter")} could not be analysed${reason ? `: ${reason}` : "."} Use Custom analysis on the book page to try again.`;
  } else if (paused > 0) {
    title = "Analysis is paused"; body = "Resume background analysis in Settings → AI to continue.";
  } else if (analysedThrough >= 0) {
    title = "Nothing worth showing yet";
    body = `Chapters through ${analysedThrough + 1} are analysed but contained no named characters or events; front matter often does not. Keep reading, or raise the chapter on the book page.`;
  } else if (autoOn) {
    title = "No story knowledge yet"; body = "Background analysis is on and will pick up the next chapter you finish. To analyse chapters you have already read, use Custom analysis on the book page.";
  } else {
    title = "Analysis is off"; body = "Choose Auto or Custom analysis on the book page to build story knowledge for this book.";
  }

  return <div className={`quiet-empty large ${warn ? "is-warning" : ""}`} role={warn ? "alert" : "status"}><div>
    {busy && !warn && <LoaderCircle className="spin empty-icon" aria-hidden="true"/>}
    {warn && <AlertTriangle className="empty-icon" aria-hidden="true"/>}
    <h2>{title}</h2>
    <p>{body}</p>
    <p><Link className="primary" to={bookLink}>Open book page</Link> <Link className="secondary" to={readerLink}><BookOpen/>Continue reading</Link> <Link className="secondary" to="/settings">AI settings</Link></p>
  </div></div>;
}
