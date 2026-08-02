import { Highlighter, Underline, X } from "lucide-react";
import { annotationColorPresets, type VisualAnnotationType } from "../../reader/rendition/annotationRendering";

export function AnnotationColorPicker({ type, color, x, y, saving, onColorChange, onSave, onCancel }: {
  type: VisualAnnotationType;
  color: string;
  x: number;
  y: number;
  saving: boolean;
  onColorChange: (color: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const Icon = type === "highlight" ? Highlighter : Underline;
  const label = type === "highlight" ? "Highlight" : "Underline";
  return <aside className="annotation-color-picker" role="dialog" aria-label={`${label} color`} style={{ left:Math.max(12,Math.min(window.innerWidth-292,x-140)), top:Math.max(68,Math.min(window.innerHeight-300,y+10)) }}>
    <header><span><Icon/>{label} color</span><button aria-label="Cancel color selection" onClick={onCancel}><X/></button></header>
    <div className="annotation-preset-grid" aria-label="Basic colors">
      {annotationColorPresets.map((preset) => <button key={preset.value} type="button" className={color.toLowerCase() === preset.value ? "active" : ""} aria-label={preset.name} title={preset.name} style={{ "--annotation-color":preset.value } as React.CSSProperties} onClick={() => onColorChange(preset.value)}><span/></button>)}
    </div>
    <label className="annotation-custom-color"><span>Custom color</span><input type="color" aria-label="Choose any color" value={color} onChange={(event) => onColorChange(event.target.value)}/><output>{color.toUpperCase()}</output></label>
    <button className="primary annotation-apply" disabled={saving} onClick={onSave}>{saving ? "Saving…" : `Apply ${label.toLowerCase()}`}</button>
  </aside>;
}
