import { Info } from "lucide-react";
import type { FormEvent } from "react";
import { readerFontOptions } from "../../reader/fonts";
import { effectiveReaderSettings, useReaderStore } from "../../store/readerStore";

function ReaderHelp({ text }: { text: string }) {
  return <span className="setting-help" tabIndex={0} aria-label={text} data-tooltip={text}><Info/></span>;
}

function ReaderRange({ label, value, min, max, step = 1, suffix = "", help, formatValue = (current) => current, onChange }: {
  label: string; value: number; min: number; max: number; step?: number; suffix?: string; help?: string;
  formatValue?: (value: number) => number; onChange: (value: number) => void;
}) {
  const updateValue = (event: FormEvent<HTMLInputElement>) => onChange(Number(event.currentTarget.value));
  return <label>
    <span>{label}{help && <ReaderHelp text={help}/>} <output>{formatValue(value)}{suffix}</output></span>
    <input type="range" min={min} max={max} step={step} value={value} onInput={updateValue} onChange={updateValue}/>
  </label>;
}

/** Font, spacing, width, and layout controls for the book being read. */
export function TypographyPanel({ sessionKey }: { sessionKey: string }) {
  const store = useReaderStore();
  const settings = effectiveReaderSettings(store, sessionKey);
  const overriding = Boolean(store.books[sessionKey]?.override);
  // Changes go to this book alone when it has its own settings, otherwise to the reader defaults.
  const apply = (values: Parameters<typeof store.setAppearance>[0]) => overriding ? store.setBookAppearance(sessionKey, values) : store.setAppearance(values);

  return <aside className="typography-panel" aria-label="Typography controls">
    <label>
      <span>Override this book <ReaderHelp text="Off uses your reader defaults. On stores a separate set of controls for only this EPUB."/></span>
      <input type="checkbox" checked={overriding} onChange={(event) => store.setBookOverride(sessionKey, event.target.checked)}/>
    </label>
    <label>
      <span>Book font <ReaderHelp text="Original EPUB font uses the typefaces embedded or named by the publisher. Other choices replace only the font face; publisher headings, drop caps, indents, emphasis, and layout remain."/></span>
      <select value={settings.usePublisherFonts ? "publisher" : settings.font}
        onChange={(event) => apply(event.target.value === "publisher" ? { usePublisherFonts: true } : { usePublisherFonts: false, font: event.target.value as typeof settings.font })}>
        <option value="publisher">Original EPUB font & styling</option>
        {readerFontOptions.map((font) => <option key={font.id} value={font.id}>{font.label}</option>)}
      </select>
    </label>
    <ReaderRange label="Font size" help="Changes the base reading-text size while keeping the EPUB's relative heading and drop-cap sizes." value={settings.fontSize} min={14} max={38} suffix="px" onChange={(fontSize) => apply({ fontSize })}/>
    <ReaderRange label="Line height" help="Controls vertical space between lines of reading text." value={settings.lineSpacing} min={1.2} max={2.2} step={0.05} onChange={(lineSpacing) => apply({ lineSpacing })}/>
    <ReaderRange label="Paragraph spacing" help="Adds space after paragraphs without removing the publisher's indents, alignment classes, or chapter layout." value={settings.paragraphSpacing} min={0} max={2} step={0.1} suffix="em" onChange={(paragraphSpacing) => apply({ paragraphSpacing })}/>
    <ReaderRange label="Column width" help="Sets the maximum width of one reading page or column." value={settings.columnWidth} min={540} max={1100} step={20} suffix="px" onChange={(columnWidth) => apply({ columnWidth })}/>
    <ReaderRange label="Image scale" help="Limits large EPUB images while preserving their aspect ratio." value={settings.imageScale} min={0.5} max={1} step={0.05} suffix="%" formatValue={(value) => Math.round(value * 100)} onChange={(imageScale) => apply({ imageScale })}/>
    <label>
      <span>Reading mode <ReaderHelp text="Paged lays the EPUB out like pages and supports spreads on wide screens. Continuous makes each chapter vertically scrollable."/></span>
      <select value={settings.readingMode} onChange={(event) => apply({ readingMode: event.target.value as "paged" | "continuous" })}>
        <option value="paged">Paged</option>
        <option value="continuous">Continuous scroll</option>
      </select>
    </label>
  </aside>;
}
