import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { analysisApi } from "../../api/analysis";
import { healthApi } from "../../api/health";
import { knowledgeApi } from "../../api/knowledge";
import { readerStateApi } from "../../api/readerState";
import { toast } from "../../components/common/toast";
import { AnalysisProgress } from "./AnalysisProgress";
import { describeRun } from "./analysisModel";

type Mode = "off" | "auto" | "custom";
const modes: { id: Mode; label: string; hint: string }[] = [
  { id: "off", label: "Off", hint: "No AI analysis for this book." },
  { id: "auto", label: "Auto", hint: "Analyse each chapter in the background as you finish it." },
  { id: "custom", label: "Custom", hint: "Already read this book? Pick how far you got and analyse up to there." },
];

/** Lets the reader choose how this book is analysed, and runs and follows a custom analysis. */
export function AnalysisCard({ book, session, userId, mode, declaredThrough, currentChapter }: {
  book: string; session: string; userId: string; mode: Mode | null; declaredThrough: number | null; currentChapter: number | null;
}) {
  const queryClient = useQueryClient();
  const overview = useQuery({
    queryKey: ["analysis-overview", book, session], queryFn: () => analysisApi.overview(book, session),
    refetchInterval: (query) => query.state.data?.task.status === "processing" ? 1000 : false,
  });
  const aiSettings = useQuery({ queryKey: ["ai-settings"], queryFn: healthApi.aiSettings, retry: false });
  const data = overview.data;
  const running = data?.task.status === "processing";
  const globalAuto = Boolean(aiSettings.data?.background_analysis.enabled);
  const selected: Mode = mode ?? (globalAuto ? "auto" : "off");

  const [chapter, setChapter] = useState<number | null>(null);
  const lastChapter = Math.max((data?.total_chapters ?? 1) - 1, 0);
  const chosen = Math.min(chapter ?? declaredThrough ?? Math.max(currentChapter ?? 0, data?.analysed_through ?? 0, 0), lastChapter);
  const preview = useQuery({
    queryKey: ["analysis-preview", book, session, chosen, data?.analysed_through], enabled: selected === "custom" && Boolean(data) && !running,
    queryFn: () => analysisApi.custom(book, session, userId, chosen, true),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["analysis-overview", book, session] });
    void queryClient.invalidateQueries({ queryKey: ["reader-library", userId] });
  };
  const setMode = useMutation({
    mutationFn: async (next: Mode) => {
      await readerStateApi.updateBook(userId, book, session, { analysis_mode: next });
      // Auto for a book only works when background analysis is allowed at all.
      if (next === "auto" && !globalAuto) await healthApi.patchAiSettings({ background_analysis_enabled: true });
    },
    onSuccess: () => { refresh(); void queryClient.invalidateQueries({ queryKey: ["ai-settings"] }); },
    onError: () => toast.error("The analysis mode could not be changed."),
  });
  const start = useMutation({
    mutationFn: () => analysisApi.custom(book, session, userId, chosen),
    onSuccess: refresh,
    onError: () => toast.error("Analysis could not be started."),
  });
  const cancel = useMutation({ mutationFn: () => analysisApi.cancelRun(book, session), onSettled: refresh });

  // Announce the end of a run once, and refresh what the rest of the page shows.
  const previousStatus = useRef<string | null>(null);
  const status = data?.task.status ?? null;
  useEffect(() => {
    if (previousStatus.current === "processing" && status && status !== "processing") {
      if (status === "completed") toast.success("Story knowledge is ready.");
      else if (status === "error") toast.error("Analysis stopped before it finished. Chapters already read are kept.");
      void queryClient.invalidateQueries({ queryKey: ["reader-library", userId] });
      void queryClient.invalidateQueries({ queryKey: ["reader-knowledge", book, session] });
    }
    previousStatus.current = status;
  }, [book, queryClient, session, status, userId]);

  const unlockedThrough = declaredThrough ?? -1;
  const summary = useQuery({
    queryKey: ["reader-knowledge", book, session, unlockedThrough], enabled: unlockedThrough >= 0 && !running,
    queryFn: () => knowledgeApi.overview(book, session, unlockedThrough),
  });
  const run = data ? describeRun(data) : null;
  const pending = preview.data?.chapters_to_analyse ?? null;
  const needsKey = Boolean(data && !data.ai_available);
  // Nothing to do when this chapter is both analysed and already the declared boundary.
  const alreadyUnlocked = pending === 0 && declaredThrough === chosen;
  const knowledgeLink = `/book/${encodeURIComponent(book)}/${encodeURIComponent(session)}/knowledge?tab=relationships`;

  return <section className="analysis-card" aria-labelledby="analysis-heading">
    <header>
      <h2 id="analysis-heading"><Sparkles aria-hidden="true"/>Story analysis</h2>
      {data && <p>{data.analysed_through >= 0 ? `Analysed through chapter ${data.analysed_through + 1} of ${data.total_chapters}.` : "No chapters analysed yet."}</p>}
    </header>
    {running && data ? <AnalysisProgress overview={data} cancelling={cancel.isPending} onCancel={() => cancel.mutate()}/> : <>
      <div className="analysis-modes" role="radiogroup" aria-label="Analysis mode">
        {modes.map((entry) => <button key={entry.id} type="button" role="radio" aria-checked={selected === entry.id} className={selected === entry.id ? "active" : ""}
          disabled={setMode.isPending} onClick={() => { if (selected !== entry.id) setMode.mutate(entry.id); }}>
          <strong>{entry.label}</strong><small>{entry.hint}</small>
        </button>)}
      </div>
      {needsKey && selected !== "off" && <p className="analysis-hint">Analysis needs a Gemini API key. <Link to="/settings">Open AI settings</Link></p>}
      {selected === "custom" && data && <div className="analysis-custom">
        <label>I have read through
          <select value={chosen} onChange={(event) => setChapter(Number(event.target.value))}>
            {data.chapters.map((item) => <option key={item.index} value={item.index}>{`${item.index + 1}. ${item.title}`}</option>)}
          </select>
        </label>
        <p className="analysis-hint" aria-live="polite">
          {pending === null ? "Checking what needs analysis…"
            : alreadyUnlocked ? `Story knowledge is already unlocked through chapter ${chosen + 1}. Pick a later chapter to go further.`
            : pending === 0 ? `Chapters 1–${chosen + 1} are already analysed. Starting only unlocks them.`
            : `${pending} chapter${pending === 1 ? "" : "s"} will be sent to Gemini for analysis. This uses your API quota and can take a few minutes.`}
        </p>
        <p className="analysis-hint">Characters, the relationship map, the timeline and chat unlock up to this chapter. Your reading position and progress do not change.</p>
        {!alreadyUnlocked && <button type="button" className="primary" disabled={start.isPending || pending === null || (needsKey && pending > 0)} onClick={() => start.mutate()}>
          {pending === 0 ? "Unlock story knowledge" : "Start analysis"}
        </button>}
      </div>}
      {run && (run.phase === "failed" || run.phase === "cancelled") && <p className="analysis-hint" role="status">{run.headline} {run.finished} of {run.total} chapters are done; starting again continues from there.</p>}
      {unlockedThrough >= 0 && summary.data?.available && <div className="analysis-summary" role="status">
        <CheckCircle2 aria-hidden="true"/>
        <span>Story knowledge is ready through chapter {unlockedThrough + 1}: {summary.data.entities.length} characters and places, {summary.data.relationships.length} relationships, {summary.data.timeline.length} events.</span>
        <Link className="secondary" to={knowledgeLink}>View relationship map</Link>
      </div>}
    </>}
  </section>;
}
