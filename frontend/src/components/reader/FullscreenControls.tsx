import { Home, Minus, Shrink, X } from "lucide-react";
import { useEffect, useRef } from "react";

export function FullscreenControls({ fullscreen, revealed, onRevealedChange, onHome, onExit, onMinimize, onClose }: { fullscreen: boolean; revealed: boolean; onRevealedChange: (value: boolean) => void; onHome: () => void; onExit: () => void; onMinimize: () => void; onClose: () => void }) {
  const dwell = useRef<number | null>(null); const hide = useRef<number | null>(null);
  const clearDwell = () => { if (dwell.current !== null) window.clearTimeout(dwell.current); dwell.current = null; };
  const clearHide = () => { if (hide.current !== null) window.clearTimeout(hide.current); hide.current = null; };
  useEffect(() => () => { clearDwell(); clearHide(); }, []);
  if (!fullscreen) return null;
  return <>
    <div data-testid="fullscreen-activation-zone" className="fullscreen-activation-zone" aria-hidden="true" onPointerEnter={() => { if (revealed) return; clearDwell(); dwell.current = window.setTimeout(() => onRevealedChange(true), 1000); }} onPointerLeave={clearDwell}/>
    {revealed && <div className="fullscreen-controls" role="toolbar" aria-label="Fullscreen window controls" onPointerEnter={clearHide} onPointerLeave={() => { clearHide(); hide.current = window.setTimeout(() => onRevealedChange(false), 450); }} onFocus={clearHide} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) { clearHide(); hide.current = window.setTimeout(() => onRevealedChange(false), 450); } }}><button title="Home" aria-label="Go to Home" onClick={onHome}><Home/></button><span/><button title="Minimize window" aria-label="Minimize window" onClick={onMinimize}><Minus/></button><button title="Exit fullscreen" aria-label="Exit fullscreen" onClick={onExit}><Shrink/></button><button title="Close BookBuddy" aria-label="Close window" className="close-window" onClick={onClose}><X/></button></div>}
  </>;
}
