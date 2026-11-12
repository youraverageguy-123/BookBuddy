import type { CSSProperties } from "react";
import { annotationColorPresets } from "../../reader/rendition/annotationRendering";

export function NoteColorSelector({ color, onChange }: { color: string; onChange: (color: string) => void }) {
  return <fieldset className="note-color-selector">
    <legend>Note color</legend>
    <div className="annotation-preset-grid" aria-label="Note colors">
      {annotationColorPresets.map((preset) => <button key={preset.value} type="button" className={color.toLowerCase() === preset.value ? "active" : ""}
        aria-label={preset.name} title={preset.name} style={{ "--annotation-color": preset.value } as CSSProperties} onClick={() => onChange(preset.value)}><span/></button>)}
      <label className="note-custom-color" title="Custom color">
        <input type="color" aria-label="Choose a custom note color" value={color} onChange={(event) => onChange(event.target.value)}/>
      </label>
    </div>
  </fieldset>;
}
