import { BookOpen, Copy, Highlighter, Languages, MessageSquareText, Search, Sparkles, Underline, UserRound } from "lucide-react";
import { useCallback, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { readerPluginManager, type SelectionActionId } from "../../plugins";
import { selectionToolbarPlacement } from "./selectionToolbarPlacement";

const icons: Record<SelectionActionId, typeof BookOpen> = { dictionary:BookOpen,story:Sparkles,character:UserRound,copy:Copy,highlight:Highlighter,underline:Underline,note:MessageSquareText,search:Search,translate:Languages };

export function SelectionToolbar({ x, y, capabilities, onAction }: { x:number; y:number; capabilities:Record<string,boolean>; onAction:(action:SelectionActionId)=>void }) {
  const actions = readerPluginManager.selectionActions(capabilities);
  const toolbar = useRef<HTMLDivElement>(null);
  const [placement, setPlacement] = useState({ left: x, top: y, measured: false });
  const updatePlacement = useCallback(() => {
    if (!toolbar.current) return;
    const next = selectionToolbarPlacement(x, y, toolbar.current.offsetWidth, toolbar.current.offsetHeight, window.innerWidth, window.innerHeight);
    setPlacement({ ...next, measured: true });
  }, [x, y]);
  useLayoutEffect(() => {
    updatePlacement();
    window.addEventListener("resize", updatePlacement);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updatePlacement);
    if (toolbar.current) observer?.observe(toolbar.current);
    return () => { window.removeEventListener("resize", updatePlacement); observer?.disconnect(); };
  }, [actions.length, updatePlacement]);
  const style = { "--selection-toolbar-left": `${placement.left}px`, top: placement.top, visibility: placement.measured ? undefined : "hidden" } as CSSProperties;
  return <div ref={toolbar} className="selection-toolbar" role="toolbar" aria-label="Selected text actions" style={style}>
    {actions.map((action) => { const Icon=icons[action.id]; return <button key={action.id} disabled={!action.enabled} title={action.enabled?action.label:`${action.label} is unavailable`} aria-label={action.label} onClick={() => onAction(action.id)}><Icon/><span>{action.label}</span></button>; })}
  </div>;
}
