import { useEffect, useMemo, useState } from "react";
import type { AnalysisOverview } from "../../types/contracts";
import { constellation, describeRun, formatElapsed } from "./analysisModel";

const WIDTH = 640;
const HEIGHT = 260;
const MAX_STARS = 80;

/**
 * The loading screen for a custom analysis run: one star per chapter lights up
 * as it is read, and lines join them the way the relationship map will.
 */
export function AnalysisProgress({ overview, cancelling, onCancel }: { overview: AnalysisOverview; cancelling: boolean; onCancel: () => void }) {
  const run = describeRun(overview);
  // Counted from when the run began, so the clock does not restart when the page is reopened.
  const startedAt = overview.task.started_at ? overview.task.started_at * 1000 : null;
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = startedAt ?? Date.now();
    const timer = window.setInterval(() => setElapsed(Math.max(0, (Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  // Very long books share stars between chapters so the sky stays readable.
  const starCount = Math.min(run.total, MAX_STARS);
  const stars = useMemo(() => constellation(starCount, WIDTH, HEIGHT), [starCount]);
  const perStar = run.total > 0 ? run.total / Math.max(starCount, 1) : 1;
  const litStars = Math.min(starCount, Math.floor(run.finished / perStar));
  const currentStar = run.current === null ? -1 : Math.min(starCount - 1, Math.floor(run.current / perStar));
  const chapterTitle = run.current === null ? "" : overview.chapters.find((chapter) => chapter.index === run.current)?.title ?? "";

  return <div className={`analysis-progress phase-${run.phase}`} role="status" aria-live="polite" aria-label="Chapter analysis progress">
    <svg className="analysis-sky" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true">
      {stars.slice(1, litStars).map((star) => {
        const previous = stars[star.index - 1];
        // Besides the chain, every few stars reach back further so it reads as a web, not a line.
        const far = star.index % 3 === 0 ? stars[star.index - 5] : undefined;
        return <g key={star.index}>
          {previous && <line className="sky-link" x1={previous.x} y1={previous.y} x2={star.x} y2={star.y}/>}
          {far && <line className="sky-link faint" x1={far.x} y1={far.y} x2={star.x} y2={star.y}/>}
        </g>;
      })}
      {stars.map((star) => <circle key={star.index} cx={star.x} cy={star.y} r={star.index === currentStar ? 6 : star.index < litStars ? 4.2 : 2.6}
        className={`sky-star ${star.index < litStars ? "lit" : ""} ${star.index === currentStar ? "current" : ""}`}/>)}
    </svg>
    <div className="analysis-status">
      <strong>{run.headline}</strong>
      {chapterTitle && <span className="analysis-chapter">{chapterTitle}</span>}
      <div className="analysis-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={run.percent} aria-label="Analysis progress"><span style={{ width: `${run.percent}%` }}/></div>
      <p>{run.finished} of {run.total} chapters read · {formatElapsed(elapsed)} elapsed</p>
      <p className="analysis-note">{cancelling ? "Finishing the request already sent to Gemini. This can take up to a minute or two." : "You can leave this page. Analysis keeps going, and chapters already read are kept if it is interrupted."}</p>
      <button type="button" className="secondary" disabled={cancelling} onClick={onCancel}>{cancelling ? "Stopping…" : "Stop analysis"}</button>
    </div>
  </div>;
}
